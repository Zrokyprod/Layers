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


# ── budget tracker (Option B) ────────────────────────────────────────────────


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


# ── Option B: live LLM resolver ─────────────────────────────────────────────


def make_live_llm_resolver(
    *,
    replay_mode: str = REPLAY_MODE_REAL_LLM,
    candidate_prompt_override: Optional[str] = None,
    candidate_model_override: Optional[str] = None,
    budget_tracker: Optional[ReplayBudgetTracker] = None,
) -> ActualOutputResolver:
    """Return an ``ActualOutputResolver`` that re-executes the source Call
    against the live LLM provider, applying optional prompt/model overrides.

    Parameters
    ----------
    candidate_prompt_override
        When set, replaces the ``messages`` or ``prompt`` field from the
        original Call payload before issuing the provider request.
    candidate_model_override
        When set, replaces the model slug from the original Call payload.
    budget_tracker
        Optional spend guard. The resolver checks ``can_spend`` before
        each provider call and returns ``reason="budget_exceeded"`` when
        the cap would be breached.
    """
    resolved_replay_mode = _normalize_live_replay_mode(replay_mode)

    def _resolve(trace: GoldenTrace, source_call: Optional[Call]) -> ActualOutput:
        mode_metadata: dict[str, Any] = {
            "requested_replay_mode": resolved_replay_mode,
        }
        if source_call is None:
            return ActualOutput(
                text=None,
                reason="source_call_missing",
                metadata=mode_metadata,
            )

        payload = _safe_json_object(source_call.payload_json)

        if resolved_replay_mode == REPLAY_MODE_LIVE_SANDBOX:
            return _run_live_sandbox_replay(
                trace=trace,
                source_call=source_call,
                payload=payload,
                candidate_prompt_override=candidate_prompt_override,
                candidate_model_override=candidate_model_override,
                budget_tracker=budget_tracker,
                mode_metadata=mode_metadata,
            )

        # Build messages list. Prefer the modern "messages" array; fall
        # back to a single user message from "prompt".
        messages: list[dict[str, Any]]
        raw_messages = payload.get("messages")
        if isinstance(raw_messages, list):
            messages = [dict(m) for m in raw_messages if isinstance(m, dict)]
        else:
            prompt_text = str(payload.get("prompt") or "")
            if not prompt_text:
                return ActualOutput(
                    text=None,
                    reason="source_call_missing_prompt",
                    metadata=mode_metadata,
                )
            messages = [{"role": "user", "content": prompt_text}]

        if resolved_replay_mode == REPLAY_MODE_MOCKED_TOOL:
            tool_snapshot = _extract_tool_snapshot(source_call)
            if tool_snapshot is None:
                mode_metadata["tool_behavior_diff"] = {
                    "available": False,
                    "changed": None,
                    "mode": "mocked_tool",
                    "reason": "tool_snapshot_missing",
                }
                return ActualOutput(
                    text=None,
                    reason="tool_snapshot_missing",
                    metadata=mode_metadata,
                )
            _prepend_replay_context(
                messages,
                title=(
                    "Replay mode: use these frozen tool outputs as the only "
                    "tool evidence. Do not invent new tool results."
                ),
                value=tool_snapshot["data"],
            )
            mode_metadata["tool_behavior_diff"] = {
                "available": True,
                "changed": False,
                "baseline": tool_snapshot["data"],
                "candidate": tool_snapshot["data"],
                "mode": "mocked_tool_frozen_outputs",
                "source": tool_snapshot["source"],
            }
        elif resolved_replay_mode == REPLAY_MODE_SHADOW:
            mode_metadata["shadow_comparison"] = {
                "baseline": "golden_trace_expected_output",
                "candidate": "live_model_output",
            }

        # Apply prompt override — replace the user message content when
        # only one user message exists, otherwise prepend a system message.
        if candidate_prompt_override and candidate_prompt_override.strip():
            user_msgs = [i for i, m in enumerate(messages) if m.get("role") == "user"]
            if len(user_msgs) == 1:
                messages[user_msgs[0]]["content"] = candidate_prompt_override.strip()
            else:
                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": candidate_prompt_override.strip(),
                    },
                )

        # Determine model — override wins, then original payload, then
        # the source Call column.
        model = candidate_model_override or str(payload.get("model") or "") or source_call.model
        if not model:
            return ActualOutput(
                text=None,
                reason="source_call_missing_model",
                metadata=mode_metadata,
            )

        # Budget gate — refuse the call if we'd exceed the run cap.
        if budget_tracker is not None and not budget_tracker.can_spend():
            return ActualOutput(
                text=None,
                reason="budget_exceeded",
                metadata=mode_metadata,
            )

        # Issue the live provider call.
        try:
            from app.services.llm_client import get_llm_client

            start = datetime.now(timezone.utc)
            response = get_llm_client().chat_completions_create(
                messages=messages,
                model=model,
            )
            latency_ms = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "live_llm_resolver.provider_error run=%s trace=%s err=%s",
                trace.golden_set_id,
                trace.id,
                exc,
                exc_info=True,
            )
            return ActualOutput(
                text=None,
                reason=f"provider_error:{type(exc).__name__}",
                metadata=mode_metadata,
            )

        # Extract text from the completion.
        try:
            text = str(response.choices[0].message.content or "")
        except Exception:  # noqa: BLE001
            text = ""

        # Extract usage when available (OpenRouter / OpenAI shape).
        usage = getattr(response, "usage", None) or {}
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

        # Rough cost estimate (OpenRouter-style pricing is ~$ per 1M tokens).
        # We keep the estimate conservative so the budget gate doesn't overshoot.
        # A more precise calculation lives in the cost-ingestion pipeline.
        cost_total = _estimate_llm_cost(model, input_tokens, output_tokens)

        if budget_tracker is not None:
            budget_tracker.record_spend(cost_total)

        return ActualOutput(
            text=text,
            model=model,
            latency_ms=latency_ms,
            cost_total=cost_total,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            metadata=mode_metadata,
        )

    return _resolve


def _normalize_live_replay_mode(replay_mode: str | None) -> str:
    mode = (replay_mode or REPLAY_MODE_REAL_LLM).strip() or REPLAY_MODE_REAL_LLM
    if mode in REAL_COMPARISON_REPLAY_MODES:
        return mode
    return REPLAY_MODE_REAL_LLM


def _prepend_replay_context(
    messages: list[dict[str, Any]],
    *,
    title: str,
    value: Any,
) -> None:
    messages.insert(
        0,
        {
            "role": "system",
            "content": f"{title}\n\n{_compact_json(value, limit=6000)}",
        },
    )


def _compact_json(value: Any, *, limit: int = 6000) -> str:
    try:
        text = json.dumps(value, separators=(",", ":"), default=str)
    except Exception:
        text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def _safe_json_value(raw: Optional[str]) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return raw


def _extract_tool_snapshot(source_call: Optional[Call]) -> dict[str, Any] | None:
    if source_call is None:
        return None

    summary_raw = source_call.tool_lifecycle_summary_json
    if summary_raw:
        return {
            "source": "tool_lifecycle_summary_json",
            "data": _safe_json_value(summary_raw),
        }

    payload = _safe_json_object(source_call.payload_json)
    for key in (
        "tool_lifecycle_summary",
        "tool_calls_made",
        "tool_calls",
        "tool_results",
        "tools",
    ):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return {
                "source": f"payload.{key}",
                "data": value,
            }
    return None


def _run_live_sandbox_replay(
    *,
    trace: GoldenTrace,
    source_call: Call,
    payload: dict[str, Any],
    candidate_prompt_override: Optional[str],
    candidate_model_override: Optional[str],
    budget_tracker: Optional[ReplayBudgetTracker],
    mode_metadata: dict[str, Any],
) -> ActualOutput:
    from app.core.config import get_settings

    settings = get_settings()
    sandbox_url = (settings.REPLAY_SANDBOX_WORKER_URL or "").strip()
    if not sandbox_url:
        mode_metadata["tool_behavior_diff"] = {
            "available": False,
            "changed": None,
            "mode": "live_sandbox",
            "reason": "sandbox_tool_runtime_unavailable",
        }
        return ActualOutput(
            text=None,
            reason="sandbox_tool_runtime_unavailable",
            metadata=mode_metadata,
        )

    if budget_tracker is not None and not budget_tracker.can_spend():
        return ActualOutput(
            text=None,
            reason="budget_exceeded",
            metadata=mode_metadata,
        )

    tool_snapshot = _extract_tool_snapshot(source_call)
    body = {
        "project_id": source_call.project_id,
        "call_id": source_call.id,
        "golden_trace_id": trace.id,
        "payload": payload,
        "candidate_prompt_override": candidate_prompt_override,
        "candidate_model_override": candidate_model_override,
        "tool_snapshot": tool_snapshot["data"] if tool_snapshot else None,
    }
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.REPLAY_SANDBOX_WORKER_TOKEN:
        headers["Authorization"] = f"Bearer {settings.REPLAY_SANDBOX_WORKER_TOKEN}"

    try:
        import httpx

        start = datetime.now(timezone.utc)
        response = httpx.post(
            sandbox_url,
            json=body,
            headers=headers,
            timeout=float(settings.REPLAY_SANDBOX_TIMEOUT_SECONDS),
        )
        latency_ms = int(
            (datetime.now(timezone.utc) - start).total_seconds() * 1000
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "live_sandbox_resolver.worker_error call=%s trace=%s err=%s",
            source_call.id,
            trace.id,
            exc,
            exc_info=True,
        )
        mode_metadata["tool_behavior_diff"] = {
            "available": False,
            "changed": None,
            "mode": "live_sandbox",
            "reason": f"sandbox_worker_error:{type(exc).__name__}",
        }
        return ActualOutput(
            text=None,
            reason=f"sandbox_worker_error:{type(exc).__name__}",
            metadata=mode_metadata,
        )

    if not isinstance(data, dict):
        return ActualOutput(
            text=None,
            reason="sandbox_worker_invalid_response",
            metadata=mode_metadata,
        )

    text_value = (
        data.get("output_text")
        or data.get("text")
        or data.get("response")
        or data.get("completion")
    )
    if text_value is None:
        return ActualOutput(
            text=None,
            reason="sandbox_worker_missing_output",
            metadata=mode_metadata,
        )

    tool_diff = data.get("tool_behavior_diff")
    if isinstance(tool_diff, dict):
        mode_metadata["tool_behavior_diff"] = tool_diff
    else:
        mode_metadata["tool_behavior_diff"] = {
            "available": tool_snapshot is not None,
            "changed": bool(data.get("tool_behavior_changed")),
            "baseline": tool_snapshot["data"] if tool_snapshot else None,
            "candidate": data.get("tool_results"),
            "mode": "live_sandbox",
            "source": "sandbox_worker",
        }

    cost_total = _as_float(data.get("cost_total") or data.get("cost_usd"), 0.0)
    if budget_tracker is not None:
        budget_tracker.record_spend(cost_total)

    return ActualOutput(
        text=str(text_value),
        model=str(data.get("model") or candidate_model_override or source_call.model or "") or None,
        latency_ms=_as_int(data.get("latency_ms"), latency_ms),
        cost_total=cost_total,
        input_tokens=_as_int(data.get("input_tokens"), 0),
        output_tokens=_as_int(data.get("output_tokens") or data.get("completion_tokens"), 0),
        metadata=mode_metadata,
    )


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _estimate_llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return a conservative USD cost estimate for a provider call.

    Uses cached per-model pricing heuristics. Real billing is computed
    by the ingestion pipeline from the provider invoice; this is only
    for the replay budget tracker.
    """
    # Normalise model slug (strip provider prefix).
    slug = model.lower().split("/")[-1]

    # Conservative defaults — over-estimate so the budget gate is safe.
    # Values are per-1M-tokens in USD.
    PRICING: dict[str, tuple[float, float]] = {
        # Anthropic
        "claude-3-haiku": (0.25, 1.25),
        "claude-3-sonnet": (3.0, 15.0),
        "claude-3-opus": (15.0, 75.0),
        "claude-3.5-sonnet": (3.0, 15.0),
        "claude-3.5-haiku": (0.25, 1.25),
        # OpenAI
        "gpt-4o": (5.0, 15.0),
        "gpt-4o-mini": (0.15, 0.6),
        "gpt-4-turbo": (10.0, 30.0),
        "gpt-4": (30.0, 60.0),
        "gpt-3.5-turbo": (0.5, 1.5),
        # DeepSeek
        "deepseek-chat": (0.14, 0.28),
        "deepseek-chat-v3": (0.14, 0.28),
        # Default fallback — high enough to be safe, low enough not to
        # starve runs on unknown models.
    }

    in_rate, out_rate = PRICING.get(slug, (5.0, 15.0))
    return round(
        (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000, 8
    )


# ── execute ─────────────────────────────────────────────────────────────────


def execute_replay_run(
    db: Session,
    *,
    project_id: str,
    run_id: str,
    evaluator: Optional[Evaluator] = None,
    evaluator_factory: Optional[EvaluatorFactory] = None,
    actual_output_resolver: ActualOutputResolver = default_resolver,
    record_calibration: bool = False,
    max_traces: int = MAX_TRACES_PER_RUN,
    # Option B — real-LLM replay overrides + budget guard.
    candidate_prompt_override: Optional[str] = None,
    candidate_model_override: Optional[str] = None,
    budget_tracker: Optional[ReplayBudgetTracker] = None,
) -> Optional[ReplayRun]:
    """Execute a pending ReplayRun. Returns the updated run, or None if not found.

    Parameters
    ----------
    evaluator
        Pre-built Evaluator. Cheaper than constructing one per trace; pass
        this when calling from a context where you've already resolved the
        plan/entitlements (e.g. Celery worker).
    evaluator_factory
        Per-trace evaluator builder. Useful when criteria_json on different
        traces should pick different judges (e.g. a schema-shaped golden
        wants DeterministicStubEvaluator). Wins over `evaluator` when both
        are given.
    actual_output_resolver
        Hook for the customer-hosted worker. Default reads from source Call.
    record_calibration
        When True, runs a DeterministicStubEvaluator alongside the real judge
        and records the comparison as a calibration sample. Adds zero LLM
        cost but doubles in-process work; default False.

    Returns
    -------
    ReplayRun
        The updated run row (status = pass | fail | error). Returns None
        if no run with that (project_id, run_id) exists.

    Idempotency
    -----------
    Only pending runs are executed. Already-terminal runs are returned as-is.
    """
    run = db.execute(
        select(ReplayRun).where(
            ReplayRun.project_id == project_id,
            ReplayRun.id == run_id,
        )
    ).scalar_one_or_none()
    if run is None:
        return None

    if run.status != _RUN_PENDING:
        # Already running or terminal — do nothing. The dispatcher/route
        # treats this as success since the caller's intent (run got
        # scheduled) is satisfied by the row's existence.
        logger.info(
            "replay_executor.skip run=%s status=%s (non-pending)",
            run.id, run.status,
        )
        return run

    parent = db.execute(
        select(GoldenSet).where(
            GoldenSet.project_id == project_id,
            GoldenSet.id == run.golden_set_id,
        )
    ).scalar_one_or_none()
    if parent is None:
        # Parent set was deleted between dispatch and execute. Mark error.
        return _finalize_error(
            db, run, reason="golden_set_deleted"
        )

    traces = list(
        db.execute(
            select(GoldenTrace)
            .where(
                GoldenTrace.project_id == project_id,
                GoldenTrace.golden_set_id == run.golden_set_id,
            )
            .order_by(GoldenTrace.created_at.asc(), GoldenTrace.id.asc())
            .limit(max_traces + 1)
        ).scalars().all()
    )
    if len(traces) > max_traces:
        return _finalize_error(
            db, run,
            reason=f"too_many_traces (>{max_traces})",
        )
    if not traces:
        # Empty golden set — mark as pass with zero traces. The dashboard
        # already handles zero-trace runs gracefully.
        _mark_running(db, run)
        return _finalize(
            db, run,
            counts={"pass": 0, "fail": 0, "error": 0},
            total=0,
        )

    _mark_running(db, run)

    # Resolve calibration context once per run — cheap read, injected into
    # every trace's judge_scores_json as `judge_accuracy_on_your_data` + `judge_mode`.
    calibration_meta: dict | None = None
    _judge_model: str | None = None
    if evaluator is not None and hasattr(evaluator, "model"):
        _judge_model = getattr(evaluator, "model", None)
    if _judge_model:
        try:
            _mode_view = resolve_mode(db, project_id=project_id, judge_model=_judge_model)
            calibration_meta = {
                "judge_accuracy_on_your_data": _mode_view.accuracy,
                "judge_mode": _mode_view.mode,
                "judge_sample_count": _mode_view.sample_count,
                "judge_last_calibrated": _mode_view.last_run_date,
            }
        except Exception:  # noqa: BLE001
            logger.debug(
                "replay_executor.calibration_meta_failed run=%s", run.id, exc_info=True
            )

    counts = {"pass": 0, "fail": 0, "error": 0}
    for trace in traces:
        verdict_kind = _grade_trace(
            db,
            run=run,
            trace=trace,
            evaluator=evaluator,
            evaluator_factory=evaluator_factory,
            actual_output_resolver=actual_output_resolver,
            record_calibration=record_calibration,
            calibration_meta=calibration_meta,
        )
        counts[verdict_kind] = counts.get(verdict_kind, 0) + 1

    return _finalize(
        db, run,
        counts=counts,
        total=len(traces),
        budget_tracker=budget_tracker,
        calibration_meta=calibration_meta,
    )


# ── per-trace grading ───────────────────────────────────────────────────────


def _grade_trace(
    db: Session,
    *,
    run: ReplayRun,
    trace: GoldenTrace,
    evaluator: Optional[Evaluator],
    evaluator_factory: Optional[EvaluatorFactory],
    actual_output_resolver: ActualOutputResolver,
    record_calibration: bool,
    calibration_meta: Optional[dict] = None,
) -> str:
    """Resolve actual, grade, persist a ReplayRunTrace. Returns the trace's status."""
    source_call: Optional[Call] = None
    if trace.call_id:
        source_call = db.execute(
            select(Call).where(
                Call.id == trace.call_id,
                Call.project_id == trace.project_id,
            )
        ).scalar_one_or_none()

    actual: ActualOutput
    try:
        actual = actual_output_resolver(trace, source_call)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "replay_executor.resolver_failed run=%s trace=%s err=%s",
            run.id, trace.id, exc,
        )
        actual = ActualOutput(text=None, reason=f"resolver_error:{type(exc).__name__}")

    if actual.text is None:
        return _write_trace_row(
            db,
            run=run,
            trace=trace,
            source_call=source_call,
            actual=actual,
            verdict=Verdict.normalize(
                VERDICT_INCONCLUSIVE,
                0.0,
                actual.reason or "no_actual_output",
                model="resolver",
            ),
            status=_TRACE_ERROR,
            call_id_replayed=source_call.id if source_call else None,
            calibration_meta=calibration_meta,
        )

    # Pick evaluator.
    chosen: Evaluator
    if evaluator_factory is not None:
        chosen = evaluator_factory(trace)
    elif evaluator is not None:
        chosen = evaluator
    else:
        # No evaluator supplied — pick a deterministic stub so the function
        # is callable without any LLM key. Callers that want real grading
        # should supply `evaluator=judge_engine.get_evaluator(...)`.
        chosen = DeterministicStubEvaluator()

    expected = trace.expected_output_text or ""
    context = _build_judge_context(trace=trace, source_call=source_call)

    try:
        verdict = chosen.evaluate(actual.text, expected, context=context)
    except Exception as exc:  # noqa: BLE001
        # Evaluator implementations promise not to raise; guard anyway.
        logger.warning(
            "replay_executor.evaluator_raised run=%s trace=%s err=%s",
            run.id, trace.id, exc,
        )
        verdict = Verdict.normalize(
            VERDICT_INCONCLUSIVE, 0.0, f"evaluator_error:{type(exc).__name__}"
        )

    # Optional calibration sample (deterministic-stub ground truth, only
    # when the stub is decisive on exact_match — i.e. a "pass" we can trust).
    if record_calibration:
        try:
            stub_verdict = DeterministicStubEvaluator().evaluate(
                actual.text, expected, context=context
            )
            # Only anchor calibration to confident stub passes; stub fail/
            # inconclusive verdicts are too noisy (paraphrased correct
            # answers would mass-trigger drift alerts).
            if (
                stub_verdict.verdict == VERDICT_PASS
                and stub_verdict.reason == "exact_match"
            ):
                judge_calibration.record_sample(
                    project_id=trace.project_id,
                    judge_model=verdict.model or "unknown",
                    judge_verdict=verdict.verdict,
                    truth_verdict=stub_verdict.verdict,
                )
        except Exception:  # noqa: BLE001
            logger.debug(
                "replay_executor.calibration_sample_failed run=%s trace=%s",
                run.id, trace.id, exc_info=True,
            )

    # Determine the persisted trace status. The judge's verdict is the
    # ground truth here: pass→pass, fail→fail, inconclusive→error.
    trace_status = _verdict_to_trace_status(verdict.verdict)
    return _write_trace_row(
        db,
        run=run,
        trace=trace,
        source_call=source_call,
        actual=actual,
        verdict=verdict,
        status=trace_status,
        call_id_replayed=source_call.id if source_call else None,
        calibration_meta=calibration_meta,
    )


def _verdict_to_trace_status(verdict: str) -> str:
    """Map judge verdict → replay_run_traces.status (CHECK = pass/fail/error)."""
    if verdict == VERDICT_PASS:
        return _TRACE_PASS
    if verdict == VERDICT_FAIL:
        return _TRACE_FAIL
    return _TRACE_ERROR  # inconclusive collapses to error so the row gets attention


def _build_judge_context(
    *, trace: GoldenTrace, source_call: Optional[Call]
) -> dict[str, Any]:
    """Compose the `context` dict passed to evaluators."""
    ctx: dict[str, Any] = {
        "trace_id": trace.id,
        "golden_set_id": trace.golden_set_id,
    }
    if trace.criteria_json:
        criteria = _safe_json_object(trace.criteria_json)
        if criteria:
            ctx["criteria"] = criteria
    if source_call is not None:
        payload = _safe_json_object(source_call.payload_json)
        prompt = payload.get("prompt")
        if prompt:
            # Cap at 1500 chars; the judge prompt has its own caps too.
            ctx["original_prompt"] = str(prompt)[:1500]
        model = payload.get("model")
        if model:
            ctx["original_model"] = str(model)
    return ctx


def _write_trace_row(
    db: Session,
    *,
    run: ReplayRun,
    trace: GoldenTrace,
    source_call: Optional[Call],
    actual: ActualOutput,
    verdict: Verdict,
    status: str,
    call_id_replayed: Optional[str],
    calibration_meta: Optional[dict] = None,
) -> str:
    """Insert one ReplayRunTrace row and commit."""
    tool_behavior_diff = _build_tool_behavior_diff(
        source_call=source_call,
        actual=actual,
    )
    scores = {
        "verdict": verdict.verdict,
        "confidence": verdict.confidence,
        "reason": verdict.reason,
        "model": verdict.model,
        "latency_ms": verdict.latency_ms,
        "output_diff": _build_output_diff(
            expected=trace.expected_output_text or "",
            actual=actual.text or "",
        ),
        "tool_behavior_diff": tool_behavior_diff,
        "cost_delta_usd": round(actual.cost_total - float(trace.expected_cost_usd or 0.0), 8),
        "latency_delta_ms": actual.latency_ms - int(trace.expected_latency_ms or 0),
        # Option B — real-LLM replay telemetry per trace.
        "replay_cost_usd": round(actual.cost_total, 8),
        "replay_input_tokens": actual.input_tokens,
        "replay_output_tokens": actual.output_tokens,
    }
    if actual.reason:
        scores["resolver_reason"] = actual.reason
    if actual.metadata:
        resolver_metadata = {
            key: value
            for key, value in actual.metadata.items()
            if key != "tool_behavior_diff"
        }
        if resolver_metadata:
            scores["resolver_metadata"] = resolver_metadata
    # Surface ensemble per-judge details and multi-dim scores if present.
    if verdict.metadata and isinstance(verdict.metadata, dict):
        # Keep judge_scores_json bounded — `judges` can grow with ensemble
        # size but is already capped at a few entries.
        meta_judges = verdict.metadata.get("judges")
        if meta_judges:
            scores["judges"] = meta_judges
        meta_dims = verdict.metadata.get("dimensions")
        if meta_dims:
            scores["dimensions"] = meta_dims
        overall = verdict.metadata.get("overall_score")
        if overall is not None:
            scores["overall_score"] = overall

    # Calibration context — attached when available so the dashboard and
    # regression-CI gate can show accuracy-on-your-data alongside every verdict.
    if calibration_meta:
        if calibration_meta.get("judge_accuracy_on_your_data") is not None:
            scores["judge_accuracy_on_your_data"] = calibration_meta["judge_accuracy_on_your_data"]
        if calibration_meta.get("judge_mode") is not None:
            scores["judge_mode"] = calibration_meta["judge_mode"]

    row = ReplayRunTrace(
        id=str(uuid4()),
        replay_run_id=run.id,
        golden_trace_id=trace.id,
        project_id=trace.project_id,
        call_id_replayed=call_id_replayed,
        judge_scores_json=json.dumps(scores, separators=(",", ":"), default=str),
        status=status,
        diff_metric=_simple_diff_metric(trace.expected_output_text or "", actual.text or ""),
        # Bound stored output text so big agent responses don't blow up the row.
        output_text=(actual.text[:8000] if actual.text else None),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    logger.debug(
        "replay_executor.trace_written run=%s trace=%s status=%s verdict=%s",
        run.id, trace.id, status, verdict.verdict,
    )
    return status


def _simple_diff_metric(expected: str, actual: str) -> float:
    if not expected and not actual:
        return 0.0
    if not expected or not actual:
        return 1.0
    return round(1.0 - difflib.SequenceMatcher(None, expected, actual).ratio(), 4)


def _build_output_diff(*, expected: str, actual: str) -> dict[str, Any]:
    return {
        "changed": expected != actual,
        "expected_preview": expected[:1000],
        "actual_preview": actual[:1000],
        "diff_metric": _simple_diff_metric(expected, actual),
    }


def _build_tool_behavior_diff(
    *,
    source_call: Optional[Call],
    actual: ActualOutput | None = None,
) -> dict[str, Any]:
    if actual is not None and actual.metadata:
        metadata_diff = actual.metadata.get("tool_behavior_diff")
        if isinstance(metadata_diff, dict):
            return metadata_diff
    if source_call is None:
        return {
            "available": False,
            "changed": None,
            "reason": "source_call_missing",
        }
    snapshot = _extract_tool_snapshot(source_call)
    if snapshot is None:
        return {
            "available": False,
            "changed": None,
            "reason": "tool_snapshot_missing",
        }
    mode = (
        "frozen_recorded_summary"
        if snapshot["source"] == "tool_lifecycle_summary_json"
        else "frozen_recorded_payload"
    )
    return {
        "available": True,
        "changed": False,
        "baseline": snapshot["data"],
        "candidate": snapshot["data"],
        "mode": mode,
        "source": snapshot["source"],
    }


def _aggregate_trace_proof(
    db: Session,
    *,
    run_id: str,
    project_id: str,
) -> dict[str, Any]:
    rows = list(
        db.execute(
            select(ReplayRunTrace).where(
                ReplayRunTrace.project_id == project_id,
                ReplayRunTrace.replay_run_id == run_id,
            )
        ).scalars().all()
    )
    output_diffs: list[dict[str, Any]] = []
    tool_diffs: list[dict[str, Any]] = []
    cost_delta = 0.0
    latency_delta = 0
    for row in rows:
        scores = _safe_json_object(row.judge_scores_json)
        output = scores.get("output_diff")
        if isinstance(output, dict):
            output_diffs.append(output)
        tool = scores.get("tool_behavior_diff")
        if isinstance(tool, dict):
            tool_diffs.append(tool)
        cost_delta += float(scores.get("cost_delta_usd") or 0.0)
        latency_delta += int(scores.get("latency_delta_ms") or 0)
    return {
        "output_diff": {
            "changed_count": sum(1 for item in output_diffs if item.get("changed") is True),
            "items": output_diffs[:10],
        },
        "tool_behavior_diff": {
            "changed_count": sum(1 for item in tool_diffs if item.get("changed") is True),
            "missing_count": sum(1 for item in tool_diffs if item.get("available") is False),
            "items": tool_diffs[:10],
        },
        "cost_delta_usd": round(cost_delta, 8),
        "latency_delta_ms": latency_delta,
    }


# ── run-level state transitions ─────────────────────────────────────────────


def _source_failure_signal(
    db: Session,
    *,
    run: ReplayRun,
    existing: dict[str, Any],
) -> bool:
    if existing.get("source_issue_id") or existing.get("source_issue_failure_code"):
        return True

    call_ids = [
        row.call_id
        for row in db.execute(
            select(GoldenTrace.call_id).where(
                GoldenTrace.project_id == run.project_id,
                GoldenTrace.golden_set_id == run.golden_set_id,
                GoldenTrace.call_id.is_not(None),
            )
        ).all()
        if row.call_id
    ]
    if not call_ids:
        return False

    calls = db.execute(
        select(Call).where(
            Call.project_id == run.project_id,
            Call.id.in_(call_ids),
        )
    ).scalars().all()
    return any(_call_has_failure_signal(call) for call in calls)


def _call_has_failure_signal(call: Call) -> bool:
    status_text = (call.status or "").strip().lower()
    success_statuses = {
        "ok",
        "success",
        "succeeded",
        "complete",
        "completed",
        "pass",
    }
    if call.error_code:
        return True
    if status_text and status_text not in success_statuses:
        return True

    payload = _safe_json_object(call.payload_json)
    for key in (
        "error",
        "error_code",
        "error_message",
        "failure_code",
        "failure_reason",
    ):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return True
    payload_status = str(payload.get("status") or "").strip().lower()
    return payload_status in {"failed", "error", "errored", "timeout"}


def _mark_running(db: Session, run: ReplayRun) -> None:
    run.status = _RUN_RUNNING
    run.started_at = datetime.now(timezone.utc)
    db.add(run)
    db.commit()
    db.refresh(run)


def _finalize(
    db: Session,
    run: ReplayRun,
    *,
    counts: dict[str, int],
    total: int,
    budget_tracker: Optional[ReplayBudgetTracker] = None,
    calibration_meta: Optional[dict] = None,
) -> ReplayRun:
    """Apply pass/fail/error decision rule + write summary."""
    pass_n = int(counts.get("pass", 0))
    fail_n = int(counts.get("fail", 0))
    error_n = int(counts.get("error", 0))

    # Decision rule (locked):
    #   any fail              → run = fail
    #   no fail, any error    → run = error
    #   all pass (or empty)   → run = pass
    if fail_n > 0:
        final = _RUN_FAIL
    elif error_n > 0:
        final = _RUN_ERROR
    else:
        final = _RUN_PASS

    # Preserve any existing trace_count_at_dispatch snapshot from
    # dispatch_replay_run for dashboard progress rendering.
    existing = _safe_json_object(run.summary_json)
    replay_mode = str(
        existing.get("requested_replay_mode")
        or existing.get("replay_mode")
        or REPLAY_MODE_STUB
    )
    proof = _aggregate_trace_proof(db, run_id=run.id, project_id=run.project_id)
    tool_missing = int(
        proof.get("tool_behavior_diff", {}).get("missing_count") or 0
    ) > 0
    tool_proof_required = replay_mode in {
        REPLAY_MODE_MOCKED_TOOL,
        REPLAY_MODE_LIVE_SANDBOX,
    }
    verified_fix = (
        replay_mode in REAL_COMPARISON_REPLAY_MODES
        and final == _RUN_PASS
        and not (tool_proof_required and tool_missing)
    )
    if replay_mode == REPLAY_MODE_STUB:
        verification_status = "sanity_check_only"
    elif verified_fix:
        verification_status = "verified_fix"
    elif final == _RUN_PASS and tool_proof_required and tool_missing:
        verification_status = "real_comparison_missing_tool_proof"
    elif final == _RUN_ERROR:
        verification_status = "real_comparison_error"
    else:
        verification_status = "real_comparison_failed"
    reproduced_original_failure = (
        None
        if replay_mode == REPLAY_MODE_STUB
        else _source_failure_signal(db, run=run, existing=existing)
    )
    summary = {
        **existing,
        "trace_count_at_dispatch": existing.get(
            "trace_count_at_dispatch", total
        ),
        "trace_count_executed": total,
        "pass_count": pass_n,
        "fail_count": fail_n,
        "error_count": error_n,
        "reproduced_original_failure": reproduced_original_failure,
        "fix_passed": final == _RUN_PASS,
        "verified_fix": verified_fix,
        "verification_status": verification_status,
    }
    summary.update(proof)
    # Option B — surface cumulative replay spend so the dashboard can
    # show "This run cost $0.34 in live LLM calls".
    if budget_tracker is not None:
        summary["replay_cost_usd"] = round(budget_tracker.spent_usd, 8)
    # Calibration snapshot — attach accuracy + mode so the run summary also
    # carries the calibration context without a second API call.
    if calibration_meta:
        if calibration_meta.get("judge_accuracy_on_your_data") is not None:
            summary["judge_accuracy_on_your_data"] = calibration_meta["judge_accuracy_on_your_data"]
        if calibration_meta.get("judge_mode") is not None:
            summary["judge_mode"] = calibration_meta["judge_mode"]
    run.status = final
    run.completed_at = datetime.now(timezone.utc)
    run.summary_json = json.dumps(summary, separators=(",", ":"))
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        "replay_executor.finalized run=%s status=%s pass=%d fail=%d error=%d",
        run.id, final, pass_n, fail_n, error_n,
    )
    return run


def _finalize_error(
    db: Session, run: ReplayRun, *, reason: str
) -> ReplayRun:
    """Short-circuit fatal-error finalize (no traces graded)."""
    existing = _safe_json_object(run.summary_json)
    replay_mode = str(
        existing.get("requested_replay_mode")
        or existing.get("replay_mode")
        or REPLAY_MODE_STUB
    )
    reproduced_original_failure = (
        None
        if replay_mode == REPLAY_MODE_STUB
        else _source_failure_signal(db, run=run, existing=existing)
    )
    summary = {
        **existing,
        "trace_count_at_dispatch": existing.get("trace_count_at_dispatch", 0),
        "trace_count_executed": 0,
        "pass_count": 0,
        "fail_count": 0,
        "error_count": 0,
        "error_reason": reason,
        "reproduced_original_failure": reproduced_original_failure,
        "fix_passed": False,
        "verified_fix": False,
        "verification_status": "sanity_check_only"
        if replay_mode == REPLAY_MODE_STUB
        else "real_comparison_error",
    }
    run.status = _RUN_ERROR
    run.completed_at = datetime.now(timezone.utc)
    run.summary_json = json.dumps(summary, separators=(",", ":"))
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.warning(
        "replay_executor.finalized_error run=%s reason=%s", run.id, reason
    )
    return run


# ── small helpers ───────────────────────────────────────────────────────────


def _safe_json_object(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


__all__ = [
    "ActualOutput",
    "ActualOutputResolver",
    "EvaluatorFactory",
    "MAX_TRACES_PER_RUN",
    "ReplayBudgetTracker",
    "default_resolver",
    "execute_replay_run",
    "make_live_llm_resolver",
    "_estimate_llm_cost",
]
