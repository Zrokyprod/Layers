from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

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

