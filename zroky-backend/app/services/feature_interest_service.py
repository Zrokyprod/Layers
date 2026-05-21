"""Service layer for feature-interest voting.

Pure DB helpers — no FastAPI deps. Routes import these functions
directly. Mirrors the convention used by `app/services/pilot.py`.

Public API:
  • upsert_vote(...)         — create or update a vote (idempotent)
  • get_user_vote(...)       — current vote for a (subject, feature)
  • summarize_feature(...)   — counts + share + threshold status
  • summarize_all(...)       — summaries across all registered features
  • list_recent_votes(...)   — paginated rows for admin detail view
  • mask_email(email)        — 'dev@acme.com' -> 'd***@acme.com'
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.models import FeatureInterestVote, Project, User
from app.services.feature_interest_registry import (
    COMING_SOON_FEATURES,
    get_feature_metadata,
    is_known_feature,
)


class UnknownFeatureError(ValueError):
    """Raised when feature_key is not in the registry."""


class InvalidVoteError(ValueError):
    """Raised when vote value is not 'interested' or 'not_interested'."""


VALID_VOTES = frozenset({"interested", "not_interested"})


# ── customer-facing helpers ─────────────────────────────────────────────────


def upsert_vote(
    db: Session,
    *,
    subject: str,
    project_id: str,
    feature_key: str,
    vote: str,
    use_case: str | None = None,
) -> FeatureInterestVote:
    """Create or update a vote for (subject, feature_key).

    Raises:
        UnknownFeatureError: if `feature_key` isn't registered.
        InvalidVoteError: if `vote` isn't one of the valid values.
    """
    if not is_known_feature(feature_key):
        raise UnknownFeatureError(
            f"feature_key {feature_key!r} is not a registered coming-soon poll"
        )
    if vote not in VALID_VOTES:
        raise InvalidVoteError(
            f"vote must be one of {sorted(VALID_VOTES)}, got {vote!r}"
        )

    normalized_use_case = (use_case or "").strip() or None

    existing = db.execute(
        select(FeatureInterestVote).where(
            FeatureInterestVote.subject == subject,
            FeatureInterestVote.feature_key == feature_key,
        )
    ).scalar_one_or_none()

    if existing is None:
        row = FeatureInterestVote(
            id=str(uuid4()),
            subject=subject,
            project_id=project_id,
            feature_key=feature_key,
            vote=vote,
            use_case=normalized_use_case,
        )
        db.add(row)
        db.flush()
        db.commit()
        db.refresh(row)
        return row

    existing.vote = vote
    existing.use_case = normalized_use_case
    existing.project_id = project_id
    existing.updated_at = datetime.now(timezone.utc)
    db.add(existing)
    db.flush()
    db.commit()
    db.refresh(existing)
    return existing


def get_user_vote(
    db: Session, *, subject: str, feature_key: str
) -> FeatureInterestVote | None:
    """Return the current vote for (subject, feature_key) or None."""
    return db.execute(
        select(FeatureInterestVote).where(
            FeatureInterestVote.subject == subject,
            FeatureInterestVote.feature_key == feature_key,
        )
    ).scalar_one_or_none()


# ── admin-facing helpers ────────────────────────────────────────────────────


def _compute_summary(
    *,
    feature_key: str,
    total: int,
    interested: int,
    last_voted_at: datetime | None,
) -> dict[str, object]:
    """Shared shape used by `summarize_feature` / `summarize_all`.

    Returned dict matches the `AdminVoteSummary` Pydantic model.
    """
    meta = get_feature_metadata(feature_key) or {}
    threshold = float(meta.get("ships_after_threshold", 0.30) or 0.30)
    not_interested = total - interested
    interested_pct = (interested / total) if total > 0 else 0.0

    if total == 0:
        status = "no_votes"
    elif interested_pct >= threshold:
        status = "above_threshold"
    else:
        status = "below_threshold"

    return {
        "feature_key": feature_key,
        "name": str(meta.get("name", feature_key)),
        "description": str(meta.get("description", "")),
        "total": total,
        "interested": interested,
        "not_interested": not_interested,
        "interested_pct": round(interested_pct, 4),
        "ships_after_threshold": threshold,
        "status": status,
        "last_voted_at": last_voted_at,
    }


def summarize_feature(
    db: Session, *, feature_key: str
) -> dict[str, object]:
    """Counts + share + threshold status for one feature_key.

    Returns the dict shape of `AdminVoteSummary`. Unknown feature_key
    still returns a valid summary with total=0 — admin UI may want
    to show "no votes yet" rather than 404.
    """
    rows = db.execute(
        select(
            FeatureInterestVote.vote,
            func.count(FeatureInterestVote.id),
            func.max(FeatureInterestVote.updated_at),
        )
        .where(FeatureInterestVote.feature_key == feature_key)
        .group_by(FeatureInterestVote.vote)
    ).all()

    interested = 0
    not_interested = 0
    last_voted_at: datetime | None = None
    for vote_value, count, latest in rows:
        if vote_value == "interested":
            interested = int(count)
        elif vote_value == "not_interested":
            not_interested = int(count)
        if latest is not None and (last_voted_at is None or latest > last_voted_at):
            last_voted_at = latest

    total = interested + not_interested
    return _compute_summary(
        feature_key=feature_key,
        total=total,
        interested=interested,
        last_voted_at=last_voted_at,
    )


def summarize_all(db: Session) -> list[dict[str, object]]:
    """Summaries for every registered feature_key.

    Returns one summary per entry in COMING_SOON_FEATURES, even those
    with zero votes. Order matches dict iteration (insertion order).
    """
    return [
        summarize_feature(db, feature_key=key)
        for key in COMING_SOON_FEATURES.keys()
    ]


def list_recent_votes(
    db: Session,
    *,
    feature_key: str,
    limit: int = 100,
    vote_filter: str | None = None,
    since: datetime | None = None,
) -> list[dict[str, object]]:
    """Return recent votes for a feature_key, newest first.

    Joins to Project + User so the admin view can show project name
    and a masked email. Filters:
      • vote_filter: restrict to 'interested' / 'not_interested'.
      • since:       only votes created on or after this timestamp.

    Returns a list of dicts shaped like `AdminVoteRow`. Email is
    masked here so callers cannot accidentally expose it.
    """
    stmt = (
        select(
            FeatureInterestVote,
            Project.name.label("project_name"),
            User.email.label("user_email"),
        )
        .outerjoin(Project, Project.id == FeatureInterestVote.project_id)
        .outerjoin(User, User.subject == FeatureInterestVote.subject)
        .where(FeatureInterestVote.feature_key == feature_key)
        .order_by(desc(FeatureInterestVote.created_at))
        .limit(max(1, min(int(limit), 500)))
    )
    if vote_filter is not None:
        if vote_filter not in VALID_VOTES:
            raise InvalidVoteError(
                f"vote_filter must be one of {sorted(VALID_VOTES)}"
            )
        stmt = stmt.where(FeatureInterestVote.vote == vote_filter)
    if since is not None:
        stmt = stmt.where(FeatureInterestVote.created_at >= since)

    rows = db.execute(stmt).all()
    return [
        {
            "vote_id": vote.id,
            "feature_key": vote.feature_key,
            "vote": vote.vote,
            "use_case": vote.use_case,
            "user_email_masked": mask_email(user_email),
            "user_subject": vote.subject,
            "project_id": vote.project_id,
            "project_name": project_name,
            "created_at": vote.created_at,
            "updated_at": vote.updated_at,
        }
        for vote, project_name, user_email in rows
    ]


def count_votes(
    db: Session, *, feature_key: str | None = None
) -> int:
    """Total vote count. If feature_key is None, counts across all."""
    stmt = select(func.count(FeatureInterestVote.id))
    if feature_key is not None:
        stmt = stmt.where(FeatureInterestVote.feature_key == feature_key)
    return int(db.execute(stmt).scalar_one() or 0)


# ── utilities ───────────────────────────────────────────────────────────────


def mask_email(email: str | None) -> str | None:
    """Mask an email for the admin row view.

    'dev@acme.com'    -> 'd***@acme.com'
    'a@b.io'          -> '*@b.io'   (very short locals fully masked)
    None              -> None
    Anything weird    -> a safe '***' fallback so we never leak the raw.
    """
    if email is None:
        return None
    cleaned = email.strip()
    if not cleaned or "@" not in cleaned:
        return "***"
    local, _, domain = cleaned.partition("@")
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}***@{domain}"


def iter_all_known_keys() -> Iterable[str]:
    """Convenience iterator over all registered feature keys."""
    return iter(COMING_SOON_FEATURES.keys())
