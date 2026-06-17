"""
Judge engine (Module 7; plan §4.2 Phoenix-aligned, §6.2/§6.4 advisory + replay
verdicts, §11.2 entitlement keys).

This module is the canonical "LLM-as-judge" surface. It replaces the narrow
shadow-judge path (`app/services/judge_shadow.py`) with a general-purpose
Evaluator abstraction used by:

  - Replay-run trace verdicts (each ReplayRunTrace gets a pass/fail via
    `Evaluator.evaluate(actual, expected, context)`).
  - Diagnose advisory ranking (Module 8 will rank fix candidates by judge
    confidence).
  - Shadow judge on diagnosed calls (the existing `judge_shadow.py` path
    is rewritten in Module 7.5 as a thin wrapper around SingleJudgeEvaluator).

Locked design choices (plan §17.2 decision #4):
  - Pro tier: SingleJudgeEvaluator on `claude-haiku-4`.
  - Plus/Enterprise: EnsembleEvaluator with Haiku-4 + GPT-4.5-mini, median
    vote. Calibration drift alarm fires at 5% (see judge_calibration.py).

Surface (intentionally small):
  - `Evaluator` ABC with `evaluate(actual, expected, *, context=None) -> Verdict`.
  - `Verdict` dataclass: deterministic, JSON-serializable, no DB coupling.
  - `SingleJudgeEvaluator` — LLM call via `app.services.llm_client`.
  - `EnsembleEvaluator` — N evaluators + median verdict + per-judge details.
  - `DeterministicStubEvaluator` — exact-match (case-insensitive trim);
    zero-cost; used by tests, CI replay, self-host without API keys.
  - `get_evaluator(plan_code, *, entitlements_dict=None)` — factory picking
    the right impl based on plan code + ensemble entitlement.

Non-goals:
  - This module does NOT write to DB. Callers persist results (replay trace
    row, anomaly row, etc.). Keeps the engine pure-functional and testable.
  - No streaming/partial verdicts. Verdicts are atomic.
  - No per-request cost accounting. The LLM client already records cost in
    `platform_llm_usage`.
"""
from __future__ import annotations

import abc
import json
import logging
import statistics
import time
from typing import Any, Mapping, Optional, Sequence

from app.core.config import get_settings
from app.services.billing_plans import DEFAULT_PLAN_CODE, get_plan_entitlements

logger = logging.getLogger(__name__)


# ── verdict vocab ───────────────────────────────────────────────────────────

from app.services._internal.judge_engine_types import (
    VALID_VERDICTS,
    VERDICT_FAIL,
    VERDICT_INCONCLUSIVE,
    VERDICT_PASS,
    Verdict,
    _SCORE_TO_VERDICT,
    _VERDICT_SCORE,
)

from app.services._internal.judge_engine_helpers import (
    _MULTIDIM_DIMENSIONS,
    _MULTIDIM_SYSTEM_PROMPT,
    _REFREE_DIMENSIONS,
    _REFREE_SYSTEM_PROMPT,
    _SYSTEM_PROMPT,
    _build_refree_user_prompt,
    _build_user_prompt,
    _parse_multidim_json,
    _parse_verdict_json,
    get_dimensions,
    get_overall_score,
    has_dimensions,
)

class Evaluator(abc.ABC):
    """Abstract evaluator. One method, one return type.

    Aligned with Arize Phoenix's `Evaluator` shape (plan §4.2) so customers
    porting from Phoenix have a familiar surface.
    """

    name: str = "abstract"

    @abc.abstractmethod
    def evaluate(
        self,
        actual: str,
        expected: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Verdict:
        """Return a Verdict comparing `actual` against `expected`.

        Implementations MUST NOT raise on LLM/transport errors; wrap them
        as `verdict=inconclusive`. The only legal exceptions are
        programmer errors (type errors, bad arguments).
        """
        raise NotImplementedError


class DeterministicStubEvaluator(Evaluator):
    """Zero-LLM evaluator. Used by tests, self-host without API keys, and
    as the safe-default fallback when no judge model is configured.

    Comparison rule:
      - Trimmed + lowercased exact match → pass with confidence=1.0.
      - Empty `expected` → inconclusive (we have no ground truth).
      - Otherwise → fail with confidence=1.0 (deterministic).

    Use this in CI where the goldens have exact expected outputs (JSON
    schemas, tool-call shapes, etc.) — it's free and fast.
    """

    name = "deterministic_stub"

    def evaluate(
        self,
        actual: str,
        expected: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Verdict:
        start = time.perf_counter()
        a = (actual or "").strip().lower()
        e = (expected or "").strip().lower()
        if not e:
            return Verdict.normalize(
                VERDICT_INCONCLUSIVE,
                0.0,
                "no_expected_provided",
                model=self.name,
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        if a == e:
            return Verdict.normalize(
                VERDICT_PASS,
                1.0,
                "exact_match",
                model=self.name,
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        return Verdict.normalize(
            VERDICT_FAIL,
            1.0,
            "exact_mismatch",
            model=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )


class SingleJudgeEvaluator(Evaluator):
    """LLM-backed evaluator using a single model (Pro tier).

    Default model is `Settings.JUDGE_SINGLE_MODEL` (claude-haiku-4). Callers
    may override per-instance for ad-hoc evals (e.g. the founder console
    experimenting with a new judge model).
    """

    name = "single"

    def __init__(
        self,
        model: Optional[str] = None,
        *,
        system_prompt: Optional[str] = None,
    ) -> None:
        s = get_settings()
        self.model = (model or s.JUDGE_SINGLE_MODEL or "").strip()
        if not self.model:
            raise ValueError(
                "SingleJudgeEvaluator: model is required "
                "(set JUDGE_SINGLE_MODEL or pass model=...)"
            )
        self.max_tokens = int(s.JUDGE_MAX_TOKENS)
        self.temperature = float(s.JUDGE_TEMPERATURE)
        # Optional override of the canonical replay-style system prompt.
        # Used by `judge_shadow.py` (Module 7.5) which has its own QA-judge
        # framing because it grades against a policy, not an expected
        # output. Empty/whitespace strings fall back to the default so
        # the override is always purposeful.
        self.system_prompt = (system_prompt or _SYSTEM_PROMPT).strip() or _SYSTEM_PROMPT

    def evaluate(
        self,
        actual: str,
        expected: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Verdict:
        start = time.perf_counter()
        from app.services.llm_client import get_llm_client  # local import; LLM client may raise on missing key

        user_prompt = _build_user_prompt(
            actual=actual, expected=expected, context=context
        )
        try:
            client = get_llm_client()
            resp = client.chat_completions_create(
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            raw = ""
            choices = getattr(resp, "choices", None) or []
            if choices:
                msg = getattr(choices[0], "message", None)
                if msg is not None:
                    raw = getattr(msg, "content", "") or ""
            verdict, confidence, reason = _parse_verdict_json(raw)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.info(
                "judge_engine.single model=%s verdict=%s conf=%.2f ms=%d",
                self.model, verdict, confidence, elapsed_ms,
            )
            return Verdict.normalize(
                verdict,
                confidence,
                reason,
                model=self.model,
                latency_ms=elapsed_ms,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "judge_engine.single failed model=%s err=%s",
                self.model, exc,
            )
            return Verdict.normalize(
                VERDICT_INCONCLUSIVE,
                0.0,
                f"judge_error:{type(exc).__name__}",
                model=self.model,
                latency_ms=elapsed_ms,
            )


class EnsembleEvaluator(Evaluator):
    """N-judge ensemble with median verdict (Plus/Enterprise).

    Vote rule:
      - Each child evaluator returns a Verdict; verdict mapped to integer
        score (pass=1, inconclusive=0, fail=-1).
      - Median of scores → final verdict class.
      - Confidence = (count of majority-class judges) / total judges.
      - Reason = top-confidence majority judge's reason.

    Inconclusive children count toward the median (preserving their dampening
    effect) but do NOT count as "majority agreement" when computing
    confidence — confidence reflects PASS/FAIL agreement strength only.

    Per-judge details are exposed in `metadata["judges"]` for audit.
    """

    name = "ensemble"

    def __init__(self, evaluators: Sequence[Evaluator]) -> None:
        children = list(evaluators or [])
        if len(children) < 2:
            raise ValueError(
                "EnsembleEvaluator requires at least 2 child evaluators; "
                f"got {len(children)}"
            )
        self.evaluators = tuple(children)

    def evaluate(
        self,
        actual: str,
        expected: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Verdict:
        start = time.perf_counter()
        per_judge: list[dict[str, Any]] = []
        scores: list[int] = []
        for ev in self.evaluators:
            v = ev.evaluate(actual, expected, context=context)
            per_judge.append(v.to_dict())
            scores.append(_VERDICT_SCORE[v.verdict])

        # Use `statistics.median_low` so an even-count tie deterministically
        # falls toward the lower (more conservative — fail/inconclusive) side.
        median_score = int(statistics.median_low(scores))
        final_verdict = _SCORE_TO_VERDICT[median_score]

        # Confidence: fraction agreeing with the final verdict.
        agreeing = sum(1 for s in scores if _SCORE_TO_VERDICT[s] == final_verdict)
        confidence = agreeing / len(scores)

        # Reason: borrow from the highest-confidence agreeing judge.
        agreeing_judges = [
            j for j in per_judge if j["verdict"] == final_verdict
        ]
        reason = ""
        if agreeing_judges:
            top = max(agreeing_judges, key=lambda j: float(j.get("confidence") or 0.0))
            reason = str(top.get("reason") or "").strip()

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "judge_engine.ensemble n=%d verdict=%s conf=%.2f ms=%d",
            len(self.evaluators), final_verdict, confidence, elapsed_ms,
        )
        return Verdict.normalize(
            final_verdict,
            confidence,
            reason or f"ensemble({len(self.evaluators)}) median",
            model=f"ensemble:{len(self.evaluators)}",
            latency_ms=elapsed_ms,
            metadata={"judges": per_judge},
        )


# ── multi-dimensional evaluators ───────────────────────────────────────────


class MultiDimEvaluator(Evaluator):
    """Reference-based multi-dimensional evaluator (requires golden output).

    Extends the standard verdict with four per-dimension scores:
    ``accuracy``, ``faithfulness``, ``relevance``, ``coherence``.

    The dimension scores are stored in ``Verdict.metadata["dimensions"]``
    and the unweighted mean in ``Verdict.metadata["overall_score"]``.
    Backward-compatible — callers that only read ``verdict.verdict`` and
    ``verdict.confidence`` continue to work without changes.

    Entitlement note: available on Pilot/Pro and above. The factory
    ``get_multidim_evaluator()`` gates on ``JUDGE_MULTIDIM_ENABLED``.
    """

    name = "multidim"
    dimensions = _MULTIDIM_DIMENSIONS

    def __init__(self, model: Optional[str] = None) -> None:
        s = get_settings()
        resolved = (model or s.JUDGE_MULTIDIM_MODEL or s.JUDGE_SINGLE_MODEL or "").strip()
        if not resolved:
            raise ValueError(
                "MultiDimEvaluator: model is required "
                "(set JUDGE_MULTIDIM_MODEL, JUDGE_SINGLE_MODEL, or pass model=...)"
            )
        self.model = resolved
        self.max_tokens = int(s.JUDGE_MAX_TOKENS) * 4
        self.temperature = float(s.JUDGE_TEMPERATURE)

    def evaluate(
        self,
        actual: str,
        expected: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Verdict:
        start = time.perf_counter()
        from app.services.llm_client import get_llm_client  # noqa: PLC0415

        user_prompt = _build_user_prompt(
            actual=actual, expected=expected, context=context
        )
        try:
            client = get_llm_client()
            resp = client.chat_completions_create(
                messages=[
                    {"role": "system", "content": _MULTIDIM_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            raw = ""
            choices = getattr(resp, "choices", None) or []
            if choices:
                msg = getattr(choices[0], "message", None)
                if msg is not None:
                    raw = getattr(msg, "content", "") or ""
            verdict, confidence, reason, dims, overall = _parse_multidim_json(
                raw, self.dimensions
            )
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.info(
                "judge_engine.multidim model=%s verdict=%s conf=%.2f overall=%.2f ms=%d",
                self.model, verdict, confidence,
                overall if overall is not None else 0.0, elapsed_ms,
            )
            meta: dict[str, Any] = {}
            if dims:
                meta["dimensions"] = dims
            if overall is not None:
                meta["overall_score"] = round(overall, 4)
            return Verdict.normalize(
                verdict,
                confidence,
                reason,
                model=self.model,
                latency_ms=elapsed_ms,
                metadata=meta or None,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "judge_engine.multidim failed model=%s err=%s",
                self.model, exc,
            )
            return Verdict.normalize(
                VERDICT_INCONCLUSIVE,
                0.0,
                f"judge_error:{type(exc).__name__}",
                model=self.model,
                latency_ms=elapsed_ms,
            )


class ReferenceFreeEvaluator(Evaluator):
    """Reference-free multi-dimensional evaluator (no golden output needed).

    Judges quality using only the agent's actual output and the original
    input question (pulled from ``context["original_prompt"]`` when
    available). Does NOT require ``expected`` — useful for cold-start
    projects that have no golden sets yet.

    Dimensions scored: ``relevance``, ``coherence``, ``groundedness``,
    ``completeness``.

    ``groundedness`` is the primary hallucination-risk proxy: a low score
    (< 0.35) triggers a ``fail`` verdict even if other dimensions pass,
    matching the ``HALLUCINATION_RISK`` anomaly detector threshold in
    ``anomalies.py``.

    Dimension scores are stored in ``Verdict.metadata["dimensions"]``;
    overall mean in ``Verdict.metadata["overall_score"]``.
    """

    name = "reference_free"
    dimensions = _REFREE_DIMENSIONS

    def __init__(self, model: Optional[str] = None) -> None:
        s = get_settings()
        resolved = (
            model or s.JUDGE_REFERENCE_FREE_MODEL or s.JUDGE_SINGLE_MODEL or ""
        ).strip()
        if not resolved:
            raise ValueError(
                "ReferenceFreeEvaluator: model is required "
                "(set JUDGE_REFERENCE_FREE_MODEL, JUDGE_SINGLE_MODEL, or pass model=...)"
            )
        self.model = resolved
        self.max_tokens = int(s.JUDGE_MAX_TOKENS) * 4
        self.temperature = float(s.JUDGE_TEMPERATURE)

    def evaluate(
        self,
        actual: str,
        expected: str,  # intentionally unused; kept for interface conformance
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Verdict:
        start = time.perf_counter()
        from app.services.llm_client import get_llm_client  # noqa: PLC0415

        user_prompt = _build_refree_user_prompt(actual=actual, context=context)
        try:
            client = get_llm_client()
            resp = client.chat_completions_create(
                messages=[
                    {"role": "system", "content": _REFREE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            raw = ""
            choices = getattr(resp, "choices", None) or []
            if choices:
                msg = getattr(choices[0], "message", None)
                if msg is not None:
                    raw = getattr(msg, "content", "") or ""
            verdict, confidence, reason, dims, overall = _parse_multidim_json(
                raw, self.dimensions
            )
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.info(
                "judge_engine.reference_free model=%s verdict=%s conf=%.2f overall=%.2f ms=%d",
                self.model, verdict, confidence,
                overall if overall is not None else 0.0, elapsed_ms,
            )
            meta: dict[str, Any] = {}
            if dims:
                meta["dimensions"] = dims
            if overall is not None:
                meta["overall_score"] = round(overall, 4)
            return Verdict.normalize(
                verdict,
                confidence,
                reason,
                model=self.model,
                latency_ms=elapsed_ms,
                metadata=meta or None,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "judge_engine.reference_free failed model=%s err=%s",
                self.model, exc,
            )
            return Verdict.normalize(
                VERDICT_INCONCLUSIVE,
                0.0,
                f"judge_error:{type(exc).__name__}",
                model=self.model,
                latency_ms=elapsed_ms,
            )


# ── factory ────────────────────────────────────────────────────────────────


def _parse_ensemble_models() -> list[str]:
    """Parse JUDGE_ENSEMBLE_MODELS_JSON into a model-name list.

    Returns [] on any parse failure; the factory then falls back to single.
    """
    raw = (get_settings().JUDGE_ENSEMBLE_MODELS_JSON or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "JUDGE_ENSEMBLE_MODELS_JSON is not valid JSON; falling back to single"
        )
        return []
    if not isinstance(parsed, list):
        logger.warning(
            "JUDGE_ENSEMBLE_MODELS_JSON must be a JSON array; falling back to single"
        )
        return []
    out: list[str] = []
    for item in parsed:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def get_evaluator(
    plan_code: Optional[str] = None,
    *,
    entitlements_dict: Optional[Mapping[str, Any]] = None,
    deterministic: bool = False,
) -> Evaluator:
    """Pick an evaluator based on plan + entitlement.

    Parameters
    ----------
    plan_code
        The org's plan code. Used for default-case selection; the
        authoritative gate is `entitlements_dict["judge.ensemble_enabled"]`.
    entitlements_dict
        The resolved entitlement dict for the org (from
        `entitlements_resolver.resolve_all()`). When present, takes
        precedence over `plan_code` for the ensemble decision so override
        rows from the founder console actually take effect.
    deterministic
        Forces the stub evaluator regardless of plan/entitlement. Used by
        tests and any CI flow that wants zero-cost exact-match grading.

    Decision tree:
      1. `deterministic=True`                   → DeterministicStubEvaluator
      2. JUDGE_ENABLED=False (kill-switch)      → DeterministicStubEvaluator
      3. Settings.OPENROUTER_API_KEY is empty   → DeterministicStubEvaluator
      4. ensemble entitlement true + >=2 models → EnsembleEvaluator
      5. Otherwise                              → SingleJudgeEvaluator
    """
    s = get_settings()

    if deterministic:
        return DeterministicStubEvaluator()

    if not s.JUDGE_ENABLED:
        return DeterministicStubEvaluator()

    if not (s.OPENROUTER_API_KEY or s.OPENAI_API_KEY):
        # No way to make an LLM call — fall back to deterministic so
        # callers don't 500. Calibration logs will flag the degradation.
        logger.info(
            "judge_engine.factory: no LLM key configured; "
            "returning deterministic stub"
        )
        return DeterministicStubEvaluator()

    ensemble_allowed = False
    if entitlements_dict is not None:
        ensemble_allowed = bool(entitlements_dict.get("judge.ensemble_enabled"))
    else:
        # Plan-code defaulting when caller didn't resolve entitlements.
        try:
            template = get_plan_entitlements(plan_code or DEFAULT_PLAN_CODE)
        except Exception:  # noqa: BLE001 - unknown/corrupt plan falls back closed.
            template = get_plan_entitlements(DEFAULT_PLAN_CODE)
        ensemble_allowed = bool(template.get("judge.ensemble_enabled"))

    if ensemble_allowed:
        models = _parse_ensemble_models()
        if len(models) >= 2:
            children: list[Evaluator] = [
                SingleJudgeEvaluator(model=m) for m in models
            ]
            return EnsembleEvaluator(children)
        # Configured for ensemble but no models declared → log + degrade.
        logger.warning(
            "judge_engine.factory: ensemble entitled but "
            "JUDGE_ENSEMBLE_MODELS_JSON declares < 2 models; using single"
        )

    return SingleJudgeEvaluator()


# ── convenience top-level helpers ──────────────────────────────────────────


def judge(
    actual: str,
    expected: str,
    *,
    plan_code: Optional[str] = None,
    entitlements_dict: Optional[Mapping[str, Any]] = None,
    context: Mapping[str, Any] | None = None,
    deterministic: bool = False,
) -> Verdict:
    """One-shot helper: resolve the right evaluator and run it.

    Use this when the caller doesn't want to manage an Evaluator instance
    (most replay/diagnose call-sites). For high-throughput paths that
    re-evaluate many items, construct the Evaluator once via
    `get_evaluator()` and call `.evaluate()` repeatedly.
    """
    ev = get_evaluator(
        plan_code=plan_code,
        entitlements_dict=entitlements_dict,
        deterministic=deterministic,
    )
    return ev.evaluate(actual, expected, context=context)


def get_multidim_evaluator(
    model: Optional[str] = None,
    *,
    deterministic: bool = False,
) -> Evaluator:
    """Return a MultiDimEvaluator, falling back to DeterministicStubEvaluator.

    Decision tree:
      1. ``deterministic=True``             → DeterministicStubEvaluator
      2. ``JUDGE_MULTIDIM_ENABLED=False``   → DeterministicStubEvaluator
      3. No LLM key configured              → DeterministicStubEvaluator
      4. Otherwise                          → MultiDimEvaluator
    """
    s = get_settings()
    if deterministic:
        return DeterministicStubEvaluator()
    if not s.JUDGE_MULTIDIM_ENABLED:
        return DeterministicStubEvaluator()
    if not (s.OPENROUTER_API_KEY or s.OPENAI_API_KEY):
        logger.info("judge_engine.multidim_factory: no LLM key; returning stub")
        return DeterministicStubEvaluator()
    return MultiDimEvaluator(model=model)


def get_reference_free_evaluator(
    model: Optional[str] = None,
    *,
    deterministic: bool = False,
) -> Evaluator:
    """Return a ReferenceFreeEvaluator, falling back to DeterministicStubEvaluator.

    Decision tree:
      1. ``deterministic=True``                   → DeterministicStubEvaluator
      2. ``JUDGE_REFERENCE_FREE_ENABLED=False``   → DeterministicStubEvaluator
      3. No LLM key configured                    → DeterministicStubEvaluator
      4. Otherwise                                → ReferenceFreeEvaluator
    """
    s = get_settings()
    if deterministic:
        return DeterministicStubEvaluator()
    if not s.JUDGE_REFERENCE_FREE_ENABLED:
        return DeterministicStubEvaluator()
    if not (s.OPENROUTER_API_KEY or s.OPENAI_API_KEY):
        logger.info("judge_engine.refree_factory: no LLM key; returning stub")
        return DeterministicStubEvaluator()
    return ReferenceFreeEvaluator(model=model)


def judge_multidim(
    actual: str,
    expected: str,
    *,
    model: Optional[str] = None,
    context: Mapping[str, Any] | None = None,
    deterministic: bool = False,
) -> Verdict:
    """One-shot multi-dimensional evaluation helper.

    Returns a Verdict with dimension scores in ``metadata["dimensions"]``
    and mean score in ``metadata["overall_score"]``.
    """
    ev = get_multidim_evaluator(model=model, deterministic=deterministic)
    return ev.evaluate(actual, expected, context=context)


def judge_reference_free(
    actual: str,
    *,
    model: Optional[str] = None,
    context: Mapping[str, Any] | None = None,
    deterministic: bool = False,
) -> Verdict:
    """One-shot reference-free evaluation helper.

    No golden output required. Scores relevance, coherence, groundedness,
    and completeness from the output alone (+ optional context).
    """
    ev = get_reference_free_evaluator(model=model, deterministic=deterministic)
    return ev.evaluate(actual, "", context=context)


__all__ = [
    "VERDICT_PASS",
    "VERDICT_FAIL",
    "VERDICT_INCONCLUSIVE",
    "VALID_VERDICTS",
    "Verdict",
    "Evaluator",
    "DeterministicStubEvaluator",
    "SingleJudgeEvaluator",
    "EnsembleEvaluator",
    "MultiDimEvaluator",
    "ReferenceFreeEvaluator",
    "get_evaluator",
    "get_multidim_evaluator",
    "get_reference_free_evaluator",
    "judge",
    "judge_multidim",
    "judge_reference_free",
    "get_dimensions",
    "get_overall_score",
    "has_dimensions",
    "_MULTIDIM_DIMENSIONS",
    "_REFREE_DIMENSIONS",
]
