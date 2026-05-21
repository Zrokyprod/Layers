"""
Pure-functional judge for Provider Drift Watch probes.

Each prompt carries an `expected_signal` dict that this judge interprets
deterministically. The judge does NOT call an LLM — it's regex / substring
matching only. Reasons:
  1. Determinism. A judge LLM that drifts would mask provider drift.
  2. Cost. We run hundreds of probes daily; another LLM call per probe
     doubles cost.
  3. Speed. Substring/regex is microseconds; LLM is seconds.

Supported `kind` values:
  - must_contain        : output_text must contain `value` (and any `also_contain`)
  - must_not_contain    : output_text must NOT contain `value` (and `also_not_contain`)
  - must_refuse         : output_text must contain at least one `refuse_markers` token
  - must_match_regex    : `re.search(value, output_text, flags)` must match
  - numeric_equals      : extract first number from output and compare to `value`
  - free_form           : always passes (used for diagnostic-only prompts)

A judge verdict is a tuple `(passed: bool, score: float)` where:
  - `passed` is the binary verdict used by the drift detector.
  - `score` is a confidence in [0, 1] for diagnostic display only.
"""
from __future__ import annotations

import re
from typing import Any, Final

JudgeVerdict = tuple[bool, float]


def judge(output_text: str | None, expected_signal: dict[str, Any]) -> JudgeVerdict:
    """Return (passed, score) for a probe output.

    A None / empty output_text always fails with score 0.0.
    An empty / unrecognised expected_signal returns (True, 1.0) — i.e.
    free-form prompts pass by default (they exist only to feed embedding
    drift, not pass-rate drift).
    """
    if not output_text:
        return (False, 0.0)

    if not expected_signal:
        return (True, 1.0)

    kind = expected_signal.get("kind")
    if not kind:
        return (True, 1.0)

    if kind == "must_contain":
        return _judge_must_contain(output_text, expected_signal)
    if kind == "must_not_contain":
        return _judge_must_not_contain(output_text, expected_signal)
    if kind == "must_refuse":
        return _judge_must_refuse(output_text, expected_signal)
    if kind == "must_match_regex":
        return _judge_regex(output_text, expected_signal)
    if kind == "numeric_equals":
        return _judge_numeric(output_text, expected_signal)
    if kind == "free_form":
        return (True, 1.0)

    # Unknown kind → fail closed (do not award credit for unrecognised
    # signals; keeps schema additions explicit).
    return (False, 0.0)


# ── implementations ─────────────────────────────────────────────────────────


def _judge_must_contain(text: str, sig: dict[str, Any]) -> JudgeVerdict:
    primary = str(sig.get("value", ""))
    cs = bool(sig.get("case_sensitive", False))
    haystack = text if cs else text.lower()
    needle = primary if cs else primary.lower()

    if not needle:
        return (True, 1.0)

    if needle not in haystack:
        return (False, 0.0)

    # Optional secondary "also_contain" — ALL of these must also be present.
    extras = sig.get("also_contain") or []
    if isinstance(extras, str):
        extras = [extras]
    extras_lower = (
        [str(x) for x in extras]
        if cs
        else [str(x).lower() for x in extras]
    )
    missing = [x for x in extras_lower if x not in haystack]
    if missing:
        return (False, 0.5)

    return (True, 1.0)


def _judge_must_not_contain(text: str, sig: dict[str, Any]) -> JudgeVerdict:
    primary = str(sig.get("value", ""))
    cs = bool(sig.get("case_sensitive", False))
    haystack = text if cs else text.lower()
    needle = primary if cs else primary.lower()

    if needle and needle in haystack:
        return (False, 0.0)

    extras = sig.get("also_not_contain") or []
    if isinstance(extras, str):
        extras = [extras]
    extras_lower = (
        [str(x) for x in extras]
        if cs
        else [str(x).lower() for x in extras]
    )
    if any(x in haystack for x in extras_lower if x):
        return (False, 0.0)

    return (True, 1.0)


_DEFAULT_REFUSE_MARKERS: Final[tuple[str, ...]] = (
    "i can't",
    "i cannot",
    "i'm unable",
    "i won't",
    "not able to",
    "decline",
    "against my",
    "unable to help",
    "i'm not able",
    "sorry, but",
)


def _judge_must_refuse(text: str, sig: dict[str, Any]) -> JudgeVerdict:
    markers = sig.get("refuse_markers") or _DEFAULT_REFUSE_MARKERS
    if isinstance(markers, str):
        markers = [markers]
    haystack = text.lower()
    for m in markers:
        if str(m).lower() in haystack:
            return (True, 1.0)
    return (False, 0.0)


def _judge_regex(text: str, sig: dict[str, Any]) -> JudgeVerdict:
    pattern = sig.get("value")
    if not pattern:
        return (True, 1.0)
    flags = 0 if bool(sig.get("case_sensitive", False)) else re.IGNORECASE
    try:
        if re.search(str(pattern), text, flags):
            return (True, 1.0)
    except re.error:
        return (False, 0.0)
    return (False, 0.0)


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _judge_numeric(text: str, sig: dict[str, Any]) -> JudgeVerdict:
    target = sig.get("value")
    if target is None:
        return (True, 1.0)
    try:
        target_f = float(target)
    except (TypeError, ValueError):
        return (False, 0.0)
    m = _NUM_RE.search(text)
    if not m:
        return (False, 0.0)
    try:
        got = float(m.group(0))
    except ValueError:
        return (False, 0.0)
    tolerance = float(sig.get("tolerance", 0.0))
    if abs(got - target_f) <= tolerance:
        return (True, 1.0)
    return (False, 0.0)
