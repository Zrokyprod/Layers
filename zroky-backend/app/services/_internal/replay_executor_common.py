"""
Replay run executor (Module 8; plan §6.4 + §4.2 Phoenix Evaluator).

Consumes a `pending` ReplayRun row (created by `replay_runs.dispatch_replay_run`)
and grades every `GoldenTrace` in the parent set against an actual output,
writing one ReplayRunTrace per golden + an aggregate summary onto the run.

This is the consumer side of `app/services/replay_runs.py` (which only creates
pending rows). The route layer enqueues a Celery task; the task calls
`execute_replay_run()` here.

Design choices:
  - Single function, single transaction per trace. Each ReplayRunTrace
    commits independently so a long run doesn't hold one giant lock.
  - "Actual output" is resolved via an injectable `ActualOutputResolver`
    so a future customer-hosted worker can swap the default (which reads
    the source Call's recorded response) for real LLM re-execution against
    the customer's current model+prompt config.
  - Judge selection is plan-aware via `judge_engine.get_evaluator(...)`.
    Tests pass `evaluator=DeterministicStubEvaluator()` for cost-free runs.
  - Calibration sampling is opt-in (`record_calibration=True`) and only
    captures exact-match passes from the deterministic stub as ground
    truth — fail/inconclusive from the stub are too noisy to anchor on.
  - Idempotent on the `pending → running` transition. If a run is already
    `running`, `pass`, `fail`, or `error`, the function returns it unchanged.
    The Celery task layer adds its own per-(project, run) idempotency guard.

What this module deliberately does NOT do:
  - Real LLM re-execution against the customer's model. That requires
    provider keys + a customer-hosted worker (deferred to a later module).
    Module 8 ships the orchestration + judge integration; the resolver is
    a hook for the future worker to plug in.
  - SCHEMA_VIOLATION enforcement against `criteria_json["expected_schema_json"]`.
    The criteria dict is passed into the judge context so the LLM can see
    it, but no structured validation lands here. Schema enforcement is a
    future detector module.
  - Real-time push of trace verdicts to the dashboard SSE. Polling-based
    UX is sufficient per plan §13. SSE for replay is a future enhancement.
"""
from __future__ import annotations

import difflib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Call,
    GoldenSet,
    GoldenTrace,
    ReplayRun,
    ReplayRunTrace,
)
from app.services import judge_calibration
from app.services.judge_mode_resolver import resolve_mode
from app.services.judge_engine import (
    DeterministicStubEvaluator,
    Evaluator,
    VERDICT_FAIL,
    VERDICT_INCONCLUSIVE,
    VERDICT_PASS,
    Verdict,
)
from app.services.replay_runs import (
    REAL_COMPARISON_REPLAY_MODES,
    REPLAY_MODE_LIVE_SANDBOX,
    REPLAY_MODE_MOCKED_TOOL,
    REPLAY_MODE_REAL_LLM,
    REPLAY_MODE_SHADOW,
    REPLAY_MODE_STUB,
)

logger = logging.getLogger(__name__)

# Hard cap to prevent a runaway golden set from monopolizing the worker.
# Plan §11.1 caps `goldens.max_sets` per plan but doesn't cap traces per set.
# 500 is a generous ceiling — the dashboard would already be unusable at
# that scale and the customer should split the set.
MAX_TRACES_PER_RUN: int = 500

# Vocab — keep aligned with the DB CHECK constraint on
# replay_runs.status (migration 0050).
_RUN_PENDING = "pending"
_RUN_RUNNING = "running"
_RUN_PASS = "pass"
_RUN_FAIL = "fail"
_RUN_ERROR = "error"

_TRACE_PASS = "pass"
_TRACE_FAIL = "fail"
_TRACE_ERROR = "error"


# ── injectable hooks ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ActualOutput:
    """Container for the resolver's return value.

    Separates the "we got a result" path from the "we couldn't resolve at
    all" path (e.g. source call was deleted). When `text` is None the
    executor records the trace as `error` with `reason` populating
    judge_scores_json so the dashboard can show the operator what went wrong.
    """

    text: Optional[str]
    reason: Optional[str] = None
    model: Optional[str] = None
    latency_ms: int = 0
    # Option B — real-LLM replay cost / token snapshot per trace.
    cost_total: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    metadata: Optional[dict[str, Any]] = None


ActualOutputResolver = Callable[[GoldenTrace, Optional[Call]], ActualOutput]


class ReplayBudgetTracker:
    """Cumulative spend guard for a single replay run.

    The dispatcher caps each run at ``Settings.REPLAY_REAL_LLM_BUDGET_USD``.
    The live resolver checks ``can_spend`` before every provider call and
    aborts the trace (returning ``ActualOutput`` with reason
    ``budget_exceeded``) when the cap would be breached.
    """

    def __init__(self, budget_usd: float) -> None:
        self.budget_usd = max(budget_usd, 0.0)
        self.spent_usd = 0.0

    def can_spend(self, estimated_usd: float = 0.0) -> bool:
        if self.budget_usd <= 0:
            return False
        return (self.spent_usd + estimated_usd) <= self.budget_usd

    def record_spend(self, cost_usd: float) -> None:
        self.spent_usd += cost_usd


def default_resolver(
    trace: GoldenTrace, source_call: Optional[Call]
) -> ActualOutput:
    """Default actual-output resolver: read the source Call's recorded response.

    This is "stub-mode replay" — it grades the source call's recorded
    behaviour against the golden's expected_output. Useful as an internal-
    consistency check of the golden set itself, and as a stand-in until a
    customer-hosted real-LLM worker lands.
    """
    if source_call is None:
        return ActualOutput(
            text=None,
            reason="source_call_missing",
        )
    payload = _safe_json_object(source_call.payload_json)
    response = payload.get("response")
    if response is None:
        return ActualOutput(
            text=None,
            reason="source_call_missing_response",
        )
    return ActualOutput(
        text=str(response),
        model=str(payload.get("model") or "") or None,
    )


EvaluatorFactory = Callable[[GoldenTrace], Evaluator]


def _safe_json_object(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


__all__ = [name for name in globals() if not name.startswith("__")]
