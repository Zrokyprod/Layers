"""Lightweight intent classifier for Ask Zroky.

We start with deterministic keyword matching to keep the system explainable
and avoid an LLM round-trip just to figure out what data to pull. The
synthesis step is the only LLM call. If keyword classification proves too
brittle later we can swap in a Haiku call here without changing the public
contract.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

IntentName = Literal[
    "cost",
    "latency",
    "failure",
    "specific_call",
    "specific_anomaly",
    "behavior",
    "general",
]


@dataclass(frozen=True)
class Intent:
    name: IntentName
    window_days: int = 7
    agent_name: str | None = None
    user_id: str | None = None
    call_id: str | None = None
    anomaly_id: str | None = None


_COST_KEYWORDS = (
    "cost", "spend", "spent", "expensive", "money", "dollars", "$",
    "budget", "bill", "billing", "charge", "tokens", "waste",
)
_LATENCY_KEYWORDS = (
    "slow", "latency", "p50", "p95", "p99", "timeout", "speed",
    "delay", "lag", "fast",
)
_FAILURE_KEYWORDS = (
    "fail", "broke", "broken", "error", "crash", "anomaly", "issue",
    "wrong", "hallucinat", "incorrect", "bug", "exception", "stuck",
    "loop", "retry",
)
_BEHAVIOR_KEYWORDS = (
    "why", "what did", "show me", "list", "which", "how many",
    "explain", "describe", "summarize",
)
_TIME_PATTERNS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\btoday\b", re.IGNORECASE), 1),
    (re.compile(r"\byesterday\b", re.IGNORECASE), 2),
    (re.compile(r"\bthis week\b|\b7 days?\b|\bweek\b", re.IGNORECASE), 7),
    (re.compile(r"\bthis month\b|\b30 days?\b|\bmonth\b", re.IGNORECASE), 30),
    (re.compile(r"\b24 hours?\b|\b1 day\b", re.IGNORECASE), 1),
)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_AGENT_PATTERNS = (
    # More specific patterns first; first match wins.
    re.compile(r"my\s+([a-zA-Z0-9_-]+)\s+agent", re.IGNORECASE),
    re.compile(r"\bagent\s+([a-zA-Z0-9_-]+)", re.IGNORECASE),
)
_AGENT_STOPWORDS = frozenset({
    "my", "the", "an", "a", "is", "was", "so", "to", "for",
    "in", "on", "of", "at", "by", "and", "or", "but", "this",
    "that", "today", "yesterday",
})


def classify_intent(question: str) -> Intent:
    if not question or not question.strip():
        return Intent(name="general")

    q = question.lower()
    window_days = _detect_window(question)
    agent_name = _detect_agent(question)
    call_id = _detect_uuid(question)

    # Specific call — ID present + a "this/that call" cue
    if call_id and any(token in q for token in ("call", "trace", "request")):
        return Intent(
            name="specific_call",
            window_days=window_days,
            agent_name=agent_name,
            call_id=call_id,
        )

    if call_id and any(token in q for token in ("anomaly", "issue", "incident")):
        return Intent(
            name="specific_anomaly",
            window_days=window_days,
            agent_name=agent_name,
            anomaly_id=call_id,
        )

    if _matches_any(q, _COST_KEYWORDS):
        return Intent(name="cost", window_days=window_days, agent_name=agent_name)

    if _matches_any(q, _LATENCY_KEYWORDS):
        return Intent(name="latency", window_days=window_days, agent_name=agent_name)

    if _matches_any(q, _FAILURE_KEYWORDS):
        return Intent(name="failure", window_days=window_days, agent_name=agent_name)

    if _matches_any(q, _BEHAVIOR_KEYWORDS):
        return Intent(name="behavior", window_days=window_days, agent_name=agent_name)

    return Intent(name="general", window_days=window_days, agent_name=agent_name)


def _matches_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(kw in text for kw in keywords)


def _detect_window(question: str) -> int:
    for pattern, days in _TIME_PATTERNS:
        if pattern.search(question):
            return days
    return 7


def _detect_agent(question: str) -> str | None:
    for pattern in _AGENT_PATTERNS:
        match = pattern.search(question)
        if match:
            candidate = match.group(1).strip()
            if candidate and candidate.lower() not in _AGENT_STOPWORDS:
                return candidate
    return None


def _detect_uuid(question: str) -> str | None:
    match = _UUID_RE.search(question)
    return match.group(0) if match else None
