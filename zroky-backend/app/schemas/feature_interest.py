"""Pydantic schemas for feature-interest voting (Module 9 smoke-test).

Customer-facing payloads:
  • FeatureVoteRequest    — POST body
  • FeatureVoteResponse   — GET/POST result

Owner-facing payloads:
  • AdminVoteSummary      — counts + percentages per feature
  • AdminVoteRow          — single row in the recent_votes list
  • AdminFeatureDetail    — summary + recent_votes (paginated)
  • AdminAllFeatures      — summaries across all registered features
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


VoteValue = Literal["interested", "not_interested"]


# ── customer side ───────────────────────────────────────────────────────────


class FeatureVoteRequest(BaseModel):
    """Body for POST /v1/feature-interest.

    `use_case` is the free-text follow-up. Recommended (but not
    required) when vote == 'interested' so we learn what fix
    customers actually want auto-applied.
    """

    feature_key: str = Field(..., min_length=1, max_length=64)
    vote: VoteValue
    use_case: str | None = Field(default=None, max_length=2000)


class FeatureVoteResponse(BaseModel):
    """Returned by POST and GET /v1/feature-interest/me.

    No vote counts are exposed — by design (decision: don't bias
    customer votes via herd / social proof signal).
    """

    feature_key: str
    vote: VoteValue
    use_case: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── admin / owner side ──────────────────────────────────────────────────────


class AdminVoteSummary(BaseModel):
    """Aggregate counts + share for one feature_key.

    `status` is one of:
      • 'below_threshold'  — interested_pct < ships_after_threshold
      • 'above_threshold'  — interested_pct ≥ ships_after_threshold
      • 'no_votes'         — total == 0
    """

    feature_key: str
    name: str
    description: str
    total: int
    interested: int
    not_interested: int
    interested_pct: float
    ships_after_threshold: float
    status: Literal["below_threshold", "above_threshold", "no_votes"]
    last_voted_at: datetime | None


class AdminVoteRow(BaseModel):
    """Single vote with masked email + project name for owner table view.

    `user_email_masked` is the masked form (e.g. 'd***@acme.com').
    The full email is intentionally NOT included to reduce screenshot
    leak risk — the founder console can wire a separate "Reveal"
    endpoint later if needed.
    """

    vote_id: str
    feature_key: str
    vote: VoteValue
    use_case: str | None
    user_email_masked: str | None
    user_subject: str
    project_id: str
    project_name: str | None
    created_at: datetime
    updated_at: datetime


class AdminFeatureDetail(BaseModel):
    """Summary + recent_votes for a single feature_key (paginated)."""

    summary: AdminVoteSummary
    recent_votes: list[AdminVoteRow]
    next_cursor: str | None = None


class AdminAllFeatures(BaseModel):
    """All registered features at a glance for the owner dashboard."""

    features: list[AdminVoteSummary]
    generated_at: datetime
