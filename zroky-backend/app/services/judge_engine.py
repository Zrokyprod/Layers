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
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

from app.core.config import get_settings
from app.services.billing_plans import DEFAULT_PLAN_CODE

logger = logging.getLogger(__name__)


# ── verdict vocab ───────────────────────────────────────────────────────────

VERDICT_PASS = "pass"
VERDICT_FAIL = "fail"
VERDICT_INCONCLUSIVE = "inconclusive"
VALID_VERDICTS: frozenset[str] = frozenset(
    {VERDICT_PASS, VERDICT_FAIL, VERDICT_INCONCLUSIVE}
)

# Numeric encoding used to compute the median verdict in EnsembleEvaluator.
# pass=1, inconclusive=0, fail=-1 — symmetric around inconclusive so an
# odd-count median always lands on one of the three classes.
_VERDICT_SCORE: dict[str, int] = {
    VERDICT_PASS: 1,
    VERDICT_INCONCLUSIVE: 0,
    VERDICT_FAIL: -1,
}
_SCORE_TO_VERDICT: dict[int, str] = {v: k for k, v in _VERDICT_SCORE.items()}


@dataclass(frozen=True)
class Verdict:
    """Atomic judge result.

    Attributes
    ----------
    verdict
        One of VERDICT_PASS / VERDICT_FAIL / VERDICT_INCONCLUSIVE.
    confidence
        Float in [0.0, 1.0]. For single judges this is the LLM's self-
        reported confidence; for ensembles, the agreement rate (count of
        majority-class judges / total).
    reason
        One-sentence rationale. Truncated to 500 chars by `normalize()`.
    model
        Backing model name (single judge) or "ensemble:<n>" for ensembles.
    latency_ms
        Wall-clock elapsed for the evaluation. Useful for budget tracking
        on replay runs.
    metadata
        Engine-specific extras: for ensembles, per-judge verdicts under
        `judges`. NEVER include PII — caller code may forward this dict
        into evidence_json on anomaly rows.
    """

    verdict: str
    confidence: float
    reason: str = ""
    model: str = ""
    latency_ms: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict, with metadata flattened to a plain dict."""
        d = asdict(self)
        d["metadata"] = dict(self.metadata or {})
        return d

    @staticmethod
    def normalize(
        verdict: str,
        confidence: float,
        reason: str = "",
        *,
        model: str = "",
        latency_ms: int = 0,
        metadata: Mapping[str, Any] | None = None,
    ) -> "Verdict":
        """Construct a Verdict with all values forced into the valid range."""
        v = (verdict or "").strip().lower()
        if v not in VALID_VERDICTS:
            v = VERDICT_INCONCLUSIVE
        try:
            c = float(confidence)
        except (TypeError, ValueError):
            c = 0.0
        if not (0.0 <= c <= 1.0):
            c = max(0.0, min(1.0, c))
        r = (reason or "").strip()
        if len(r) > 500:
            r = r[:497] + "..."
        return Verdict(
            verdict=v,
            confidence=c,
            reason=r,
            model=model or "",
            latency_ms=max(0, int(latency_ms or 0)),
            metadata=dict(metadata or {}),
        )


# ── prompts ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a quality-assurance judge for AI agent outputs. "
    "Compare the actual output against the expected output and any context. "
    'Respond ONLY with valid JSON of shape {"verdict":"pass"|"fail"|"inconclusive",'
    '"confidence":0.0-1.0,"reason":"<one sentence>"}. '
    'Use "pass" when the actual output is semantically equivalent to the expected. '
    'Use "fail" when it is materially wrong, missing, or hallucinated. '
    'Use "inconclusive" only if you cannot determine equivalence.'
)


def _build_user_prompt(
    *,
    actual: str,
    expected: str,
    context: Mapping[str, Any] | None,
) -> str:
    """Compose the user-side prompt for a judge call.

    Caps each field at a generous length so we never blow the context
    window even with very large agent responses. The cap is intentionally
    larger than the shadow judge's 800 chars because replay traces can
    legitimately be longer.
    """
    parts: list[str] = []
    parts.append(f"expected:\n{(expected or '')[:4000]}")
    parts.append(f"actual:\n{(actual or '')[:4000]}")
    if context:
        try:
            ctx_json = json.dumps(context, separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            ctx_json = str(context)
        parts.append(f"context:\n{ctx_json[:2000]}")
    return "\n\n".join(parts)


def _parse_verdict_json(raw: str) -> tuple[str, float, str]:
    """Parse the judge's JSON response into (verdict, confidence, reason).

    Tolerant: strips ```json fences, falls back to inconclusive on any
    parse failure so the caller never sees an exception from the engine
    itself (LLMs lie about JSON).
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        # Strip first fence + optional `json` tag, then last fence.
        text = text.lstrip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
        if "```" in text:
            text = text.split("```", 1)[0]
        text = text.strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return VERDICT_INCONCLUSIVE, 0.0, "judge_output_unparseable"
    if not isinstance(data, dict):
        return VERDICT_INCONCLUSIVE, 0.0, "judge_output_not_object"
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in VALID_VERDICTS:
        verdict = VERDICT_INCONCLUSIVE
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    reason = str(data.get("reason", "") or "").strip()
    return verdict, confidence, reason


# ── evaluators ─────────────────────────────────────────────────────────────


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


_MULTIDIM_DIMENSIONS: tuple[str, ...] = (
    "accuracy",
    "faithfulness",
    "relevance",
    "coherence",
)

_REFREE_DIMENSIONS: tuple[str, ...] = (
    "relevance",
    "coherence",
    "groundedness",
    "completeness",
)

_MULTIDIM_SYSTEM_PROMPT = (
    "You are a multi-dimensional quality-assurance judge for AI agent outputs. "
    "Compare the actual output against the expected output and any context provided. "
    "Score four dimensions on a 0.0-1.0 scale: "
    "accuracy (semantic match with expected), "
    "faithfulness (no facts added beyond expected/context), "
    "relevance (addresses the question in context), "
    "coherence (internally consistent and logically sound). "
    'Respond ONLY with valid JSON: '
    '{"verdict":"pass"|"fail"|"inconclusive","confidence":0.0-1.0,"reason":"<one sentence>",'
    '"dimensions":{"accuracy":{"score":0.0-1.0,"reason":"<one sentence>"},'
    '"faithfulness":{"score":0.0-1.0,"reason":"<one sentence>"},'
    '"relevance":{"score":0.0-1.0,"reason":"<one sentence>"},'
    '"coherence":{"score":0.0-1.0,"reason":"<one sentence>"}}}. '
    'Use "pass" when mean dimension score >= 0.7 and no dimension is below 0.4. '
    'Use "fail" when mean dimension score < 0.5 or any dimension is below 0.25. '
    'Use "inconclusive" otherwise.'
)

_REFREE_SYSTEM_PROMPT = (
    "You are a reference-free quality judge for AI agent outputs. "
    "You have NO golden/expected output. Judge the output given only the input "
    "question/task (in context) and the output itself. "
    "Score four dimensions on a 0.0-1.0 scale: "
    "relevance (addresses the input question), "
    "coherence (internally consistent and logically sound), "
    "groundedness (avoids unverifiable confident claims; 1.0=grounded/hedged, "
    "0.0=hallucination risk), "
    "completeness (sufficiently answers the question). "
    'Respond ONLY with valid JSON: '
    '{"verdict":"pass"|"fail"|"inconclusive","confidence":0.0-1.0,"reason":"<one sentence>",'
    '"dimensions":{"relevance":{"score":0.0-1.0,"reason":"<one sentence>"},'
    '"coherence":{"score":0.0-1.0,"reason":"<one sentence>"},'
    '"groundedness":{"score":0.0-1.0,"reason":"<one sentence>"},'
    '"completeness":{"score":0.0-1.0,"reason":"<one sentence>"}}}. '
    'Use "pass" when mean dimension score >= 0.7 and groundedness >= 0.6. '
    'Use "fail" when mean dimension score < 0.5 or groundedness < 0.35. '
    'Use "inconclusive" otherwise.'
)


def _build_refree_user_prompt(
    *,
    actual: str,
    context: Mapping[str, Any] | None,
) -> str:
    """Compose the user-side prompt for a reference-free judge call.

    Pulls ``original_prompt`` from context (populated by replay_executor's
    ``_build_judge_context``) as the "input" the agent was answering.
    Remaining context keys are forwarded as supplementary data.
    """
    parts: list[str] = []
    ctx = dict(context or {})
    input_text = str(ctx.pop("original_prompt", "") or "").strip()
    if input_text:
        parts.append(f"input:\n{input_text[:4000]}")
    parts.append(f"actual:\n{(actual or '')[:4000]}")
    if ctx:
        try:
            ctx_json = json.dumps(ctx, separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            ctx_json = str(ctx)
        parts.append(f"context:\n{ctx_json[:2000]}")
    return "\n\n".join(parts)


def _parse_multidim_json(
    raw: str,
    expected_dims: tuple[str, ...],
) -> tuple[str, float, str, dict[str, dict[str, Any]], "float | None"]:
    """Parse a multi-dimensional judge JSON response.

    Returns ``(verdict, confidence, reason, dimensions, overall_score)``.
    - ``dimensions`` maps dim-name → ``{"score": float, "reason": str}``.
      Missing dimension keys are filled with ``{"score": 0.0, "reason": "missing"}``.
    - ``overall_score`` is the unweighted mean of all dimension scores, or
      ``None`` when no valid dimension scores are present.
    - On any parse failure returns an inconclusive verdict with empty
      dimensions so callers never see an exception.
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.lstrip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
        if "```" in text:
            text = text.split("```", 1)[0]
        text = text.strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return VERDICT_INCONCLUSIVE, 0.0, "judge_output_unparseable", {}, None

    if not isinstance(data, dict):
        return VERDICT_INCONCLUSIVE, 0.0, "judge_output_not_object", {}, None

    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in VALID_VERDICTS:
        verdict = VERDICT_INCONCLUSIVE
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    reason = str(data.get("reason", "") or "").strip()

    raw_dims = data.get("dimensions")
    dimensions: dict[str, dict[str, Any]] = {}
    if isinstance(raw_dims, dict):
        for dim in expected_dims:
            raw_dim = raw_dims.get(dim)
            if isinstance(raw_dim, dict):
                try:
                    score = float(raw_dim.get("score", 0.0))
                    score = max(0.0, min(1.0, score))
                except (TypeError, ValueError):
                    score = 0.0
                dim_reason = str(raw_dim.get("reason", "") or "").strip()
                dimensions[dim] = {"score": score, "reason": dim_reason}
            else:
                dimensions[dim] = {"score": 0.0, "reason": "missing"}
    else:
        for dim in expected_dims:
            dimensions[dim] = {"score": 0.0, "reason": "missing"}

    scores = [d["score"] for d in dimensions.values()]
    overall_score: Any = (sum(scores) / len(scores)) if scores else None

    return verdict, confidence, reason, dimensions, overall_score


# ── helper accessors for Verdict.metadata["dimensions"] ──────────────────


def get_dimensions(verdict: Verdict) -> dict[str, dict[str, Any]]:
    """Extract the dimensions dict from a multi-dim Verdict's metadata.

    Returns ``{}`` when the verdict carries no dimension data (e.g. it came
    from a single/ensemble/stub evaluator).
    """
    meta = verdict.metadata
    if not isinstance(meta, dict):
        return {}
    dims = meta.get("dimensions")
    return dims if isinstance(dims, dict) else {}


def get_overall_score(verdict: Verdict) -> Optional[float]:
    """Return the pre-computed overall dimension score, or None."""
    meta = verdict.metadata
    if not isinstance(meta, dict):
        return None
    val = meta.get("overall_score")
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def has_dimensions(verdict: Verdict) -> bool:
    """True when the verdict carries multi-dimensional score data."""
    return bool(get_dimensions(verdict))


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
        # Keep aligned with PLAN_ENTITLEMENTS in billing_plans.py.
        plan = (plan_code or DEFAULT_PLAN_CODE).strip().lower()
        ensemble_allowed = plan in {"plus", "enterprise"}

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
