"""
Category vocabulary + severity ladder for Provider Drift Watch.

`CATEGORIES` is the canonical ordered tuple. Order matters for stable
display in the public dashboard and RSS feed. Adding a new category
requires:
  1. Appending it here (do NOT reorder existing entries).
  2. Updating the migration CHECK constraint (or running a follow-up
     migration that widens it).
  3. Adding at least one prompt with that category to the suite.
"""
from __future__ import annotations

from typing import Final

# Ordered for display stability.
CATEGORIES: Final[tuple[str, ...]] = (
    "math",
    "refusal",
    "code",
    "summarization",
    "multi_turn",
    "tool_use",
    "factuality",
    "instruction_following",
)

VALID_CATEGORIES: Final[frozenset[str]] = frozenset(CATEGORIES)


class Severity:
    """Severity ladder.

    Thresholds (absolute z-score on the *combined* metric):
        INFO     >= 2.0
        WARN     >= 3.0
        CRITICAL >= 4.0  OR  pass-rate drop >= 15 pp

    The aggregator decides; downstream code (UI, RSS) only reads.
    """

    INFO: Final[str] = "info"
    WARN: Final[str] = "warn"
    CRITICAL: Final[str] = "critical"

    ALL: Final[tuple[str, ...]] = (INFO, WARN, CRITICAL)
