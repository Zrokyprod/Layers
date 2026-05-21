"""Judge Tier 3 — narrow-scope shadow judge (Module 7.5 refactor).

Spec (W9-10):
  - Runs on calls tagged LOW_CONFIDENCE or LOOP_DETECTED **only**.
  - 1% sampling rate of eligible calls.
  - Cost cap: 2% of tenant LLM spend; auto-disable at 5%.
  - Feature flag `judge_shadow_enabled` — default off; 3 internal tenants on.
  - Model: nano/haiku class (claude-haiku-3-5 or gpt-4o-mini).
  - Never blocks production; runs in background task only.
  - No verdict ever reaches production guardrail logic (Q2).

Module 7.5: the LLM call + JSON parsing now delegates to
`judge_engine.SingleJudgeEvaluator` so this module is purely
shadow-judge-specific concerns (eligibility, sampling, cost caps,
prompt assembly, calibration recording).

What changed vs. the original:
  - Inline `chat_completions_create` + bespoke fenced-JSON parser were
    removed; SingleJudgeEvaluator handles both with the same robustness
    that grades replay traces.
  - Every shadow verdict now records a calibration sample where the
    deterministic-detector verdict (LOW_CONFIDENCE/LOOP_DETECTED → fail)
    is the ground truth. This funnels live drift data into the
    `judge_drift_alert` channel from Module 7.
  - The wire-format return shape is **unchanged** (dict with verdict,
    confidence, reason) so `worker.tasks.run_shadow_judge_task` and any
    downstream log-search tooling are untouched.
"""
from __future__ import annotations

import json
import logging
import random
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, func as sa_func
from sqlalchemy.orm import Session

from app.db.models import Call, DiagnosisJob, FeatureFlag, PlatformLlmUsage
from app.services import judge_calibration
from app.services.judge_engine import (
    SingleJudgeEvaluator,
    VERDICT_FAIL,
    Verdict,
)

logger = logging.getLogger(__name__)

_FLAG_KEY = "judge_shadow_enabled"
_ELIGIBLE_CODES = frozenset({"LOW_CONFIDENCE", "LOOP_DETECTED"})
_SAMPLE_RATE = 0.01
_COST_CAP_PCT = 0.02
_AUTO_DISABLE_PCT = 0.05
# Shadow judge model is intentionally fixed (nano/haiku class) per plan
# §17.2; the per-org JUDGE_SINGLE_MODEL setting drives replay grading,
# not shadow grading. Keeping these decoupled lets us swap one without
# disturbing the other's cost profile.
_JUDGE_MODEL = "openai/gpt-4o-mini"
_SYSTEM_PROMPT = (
    "You are a quality-assurance judge for AI agent calls. "
    "Given the call context below, output a JSON object with keys: "
    '{"verdict": "pass"|"fail"|"inconclusive", "confidence": 0.0-1.0, "reason": "<one sentence>"}. '
    "Output ONLY valid JSON. No prose."
)


# ── public API ────────────────────────────────────────────────────────────────

def should_run_shadow_judge(
    *,
    db: Session,
    tenant_id: str,
    failure_code: str,
    rng: random.Random | None = None,
) -> bool:
    """Fast eligibility check — called inline in the ingest/diagnosis path.

    Returns True only when:
    1. Feature flag `judge_shadow_enabled` is on for this tenant.
    2. failure_code is in ELIGIBLE_CODES.
    3. Random sample passes (1%).
    4. Tenant judge spend is below auto-disable threshold (5%).
    """
    if failure_code not in _ELIGIBLE_CODES:
        return False
    if not _flag_enabled(db, tenant_id):
        return False
    r = rng or random
    if r.random() > _SAMPLE_RATE:
        return False
    if _judge_spend_fraction(db, tenant_id) >= _AUTO_DISABLE_PCT:
        logger.warning(
            "judge_shadow: auto-disabled for tenant=%s (spend >= %.0f%%)",
            tenant_id,
            _AUTO_DISABLE_PCT * 100,
        )
        return False
    return True


def run_shadow_judge(
    *,
    tenant_id: str,
    call_id: str,
    failure_code: str,
    call_prompt: str | None,
    call_response: str | None,
    diagnosis_summary: str | None,
    policy_text: str | None = None,
    evaluator: SingleJudgeEvaluator | None = None,
) -> dict[str, Any]:
    """Execute the shadow judge LLM call and return the raw verdict dict.

    Never raises — SingleJudgeEvaluator.evaluate() returns an inconclusive
    Verdict on any internal failure (LLM exception, parse error, empty
    choices) so the caller never needs to handle exceptions.

    The `evaluator` parameter is for tests; production callers leave it
    as None and a fresh SingleJudgeEvaluator is built on the fly so each
    call uses the (possibly hot-reloaded) module constant for the model.

    Calibration anchoring: the deterministic detector that emitted
    `failure_code` is treated as the ground truth (verdict=fail). When
    the LLM judge disagrees (says pass), that's a calibration
    disagreement and feeds into Module 7's drift detector.
    """
    user_content = _build_user_prompt(
        call_id=call_id,
        failure_code=failure_code,
        call_prompt=call_prompt,
        call_response=call_response,
        diagnosis_summary=diagnosis_summary,
        policy_text=policy_text,
    )

    judge = evaluator or SingleJudgeEvaluator(
        model=_JUDGE_MODEL,
        system_prompt=_SYSTEM_PROMPT,
    )
    # SingleJudgeEvaluator's prompt template asks the model to compare
    # `actual` vs `expected`; for shadow judging we don't have an
    # expected output — the LLM is grading the call against a policy.
    # We therefore pass the assembled user_content as `actual` and an
    # empty string as `expected`; the system prompt above overrides the
    # default judge instructions and tells the model to ignore the
    # actual/expected framing.
    verdict: Verdict = judge.evaluate(
        actual=user_content,
        expected="",
        context={"failure_code": failure_code, "shadow": True},
    )

    logger.info(
        "judge_shadow verdict tenant=%s call=%s code=%s verdict=%s conf=%.2f latency=%dms",
        tenant_id,
        call_id,
        failure_code,
        verdict.verdict,
        verdict.confidence,
        verdict.latency_ms,
    )

    # Calibration: deterministic detector said "fail" (it flagged the
    # call); record the LLM judge's verdict against that anchor. Best-
    # effort — calibration storage failures must never crash the worker.
    try:
        judge_calibration.record_sample(
            project_id=tenant_id,
            judge_model=verdict.model or _JUDGE_MODEL,
            judge_verdict=verdict.verdict,
            truth_verdict=VERDICT_FAIL,
        )
    except Exception:  # noqa: BLE001
        logger.debug(
            "judge_shadow.calibration_record_failed tenant=%s call=%s",
            tenant_id, call_id, exc_info=True,
        )

    return {
        "verdict": verdict.verdict,
        "confidence": verdict.confidence,
        "reason": verdict.reason,
        # Newly exposed (additive — worker logs already JSON-encode the
        # whole dict so adding fields is safe).
        "model": verdict.model,
        "latency_ms": verdict.latency_ms,
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _flag_enabled(db: Session, tenant_id: str) -> bool:
    row = db.execute(
        select(FeatureFlag).where(FeatureFlag.key == _FLAG_KEY)
    ).scalar_one_or_none()
    if row is None:
        return False
    if row.enabled_globally:
        try:
            disabled = json.loads(row.disabled_tenants_json or "[]")
            return tenant_id not in disabled
        except Exception:
            return True
    try:
        enabled = json.loads(row.enabled_tenants_json or "[]")
        return tenant_id in enabled
    except Exception:
        return False


def _judge_spend_fraction(db: Session, tenant_id: str) -> float:
    """Return judge spend / total LLM spend for the last 24 h."""
    since = datetime.now(UTC) - timedelta(hours=24)
    total_row = db.execute(
        select(sa_func.sum(PlatformLlmUsage.cost_usd)).where(
            PlatformLlmUsage.tenant_id == tenant_id,
            PlatformLlmUsage.created_at >= since,
        )
    ).scalar()
    total = float(total_row or 0.0)
    if total <= 0:
        return 0.0
    judge_row = db.execute(
        select(sa_func.sum(PlatformLlmUsage.cost_usd)).where(
            PlatformLlmUsage.tenant_id == tenant_id,
            PlatformLlmUsage.created_at >= since,
            PlatformLlmUsage.model == _JUDGE_MODEL,
        )
    ).scalar()
    judge = float(judge_row or 0.0)
    return judge / total


def _build_user_prompt(
    *,
    call_id: str,
    failure_code: str,
    call_prompt: str | None,
    call_response: str | None,
    diagnosis_summary: str | None,
    policy_text: str | None,
) -> str:
    parts = [
        f"call_id: {call_id}",
        f"failure_code: {failure_code}",
    ]
    if policy_text:
        parts.append(f"policy:\n{policy_text[:1800]}")
    if call_prompt:
        parts.append(f"prompt:\n{call_prompt[:800]}")
    if call_response:
        parts.append(f"response:\n{call_response[:800]}")
    if diagnosis_summary:
        parts.append(f"diagnosis_summary:\n{diagnosis_summary[:400]}")
    return "\n\n".join(parts)


# Module 7.5: `_parse_verdict` was removed. JSON parsing now lives in
# `judge_engine._parse_verdict_json` which handles the same fenced /
# malformed / non-object cases plus a few we missed (e.g. valid JSON
# that's not an object). The bespoke parser is gone.
