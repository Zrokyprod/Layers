"""Feature-interest voting routes (Module 9 smoke-test).

Two routers exported from this file:

  • `router`        — customer surface at `/v1/feature-interest/*`.
                      Requires a logged-in user (TenantContext.subject).
                      Always mounted.

  • `admin_router`  — owner surface at `/v1/admin/feature-interest/*`.
                      Requires `X-Provisioning-Token` (or admin JWT)
                      via `require_provisioning_access`. Always mounted.
                      Founder Console (Module 11) will consume these
                      endpoints from the zroky-admin app.

No new entitlement — anyone with a project membership can vote. The
write surface is intentionally cheap (single upsert) so we never
gate-keep the data we *want* to collect.
"""
import csv
import io
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies.provisioning import require_provisioning_access
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.schemas.feature_interest import (
    AdminAllFeatures,
    AdminFeatureDetail,
    AdminVoteRow,
    AdminVoteSummary,
    FeatureVoteRequest,
    FeatureVoteResponse,
)
from app.services.feature_interest_registry import is_known_feature
from app.services.feature_interest_service import (
    InvalidVoteError,
    UnknownFeatureError,
    get_user_vote,
    list_recent_votes,
    summarize_all,
    summarize_feature,
    upsert_vote,
)


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Customer surface — /v1/feature-interest/*
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/v1/feature-interest")


def _require_user_subject(ctx: TenantContext) -> str:
    """Voting requires a user identity (subject), not a machine API key.

    TenantContext.subject is populated for JWT/session auth but is
    `None` when the request authenticated via API key or project
    header. Reject those — votes are personal opinions, not project
    facts.
    """
    if not ctx.subject or not ctx.subject.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Feature voting requires a logged-in user. API key "
                "authentication is not supported for this endpoint."
            ),
        )
    return ctx.subject.strip()


@router.post(
    "",
    response_model=FeatureVoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Upsert the current user's vote on a coming-soon feature.",
)
@limiter.limit("30/minute")
def submit_vote(
    request: Request,
    body: FeatureVoteRequest = Body(...),
    ctx: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> FeatureVoteResponse:
    """Create or update the current user's vote.

    One vote per (subject, feature_key). Voting again overwrites
    the previous answer. `use_case` is optional free-text (max 2000
    chars) — encouraged when `vote == 'interested'`.
    """
    subject = _require_user_subject(ctx)
    try:
        row = upsert_vote(
            db,
            subject=subject,
            project_id=ctx.tenant_id,
            feature_key=body.feature_key.strip(),
            vote=body.vote,
            use_case=body.use_case,
        )
    except UnknownFeatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except InvalidVoteError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    logger.info(
        "feature_vote_recorded subject=%s feature=%s vote=%s",
        subject, row.feature_key, row.vote,
    )
    return FeatureVoteResponse.model_validate(row)


@router.get(
    "/me",
    response_model=FeatureVoteResponse,
    summary="Get the current user's vote on a coming-soon feature.",
)
@limiter.limit("60/minute")
def get_my_vote(
    request: Request,
    feature_key: str = Query(..., min_length=1, max_length=64),
    ctx: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> FeatureVoteResponse:
    """Return the vote, or 404 if the user has not voted yet.

    Also returns 400 if the feature_key is not in the registry — same
    behavior as POST, so the dashboard can render the same error.
    """
    subject = _require_user_subject(ctx)
    feature_key = feature_key.strip()
    if not is_known_feature(feature_key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"feature_key {feature_key!r} is not a registered coming-soon poll",
        )
    row = get_user_vote(db, subject=subject, feature_key=feature_key)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No vote recorded for this feature.",
        )
    return FeatureVoteResponse.model_validate(row)


# ─────────────────────────────────────────────────────────────────────────────
# Admin / owner surface — /v1/admin/feature-interest/*
# ─────────────────────────────────────────────────────────────────────────────

admin_router = APIRouter(
    prefix="/v1/admin/feature-interest",
    dependencies=[Depends(require_provisioning_access)],
)


@admin_router.get(
    "",
    response_model=AdminAllFeatures,
    summary="Summary of all coming-soon features at a glance.",
)
def admin_list_features(
    db: Session = Depends(get_db_session),
) -> AdminAllFeatures:
    """Returns one summary per registered feature_key.

    Includes features with zero votes so the dashboard can render a
    consistent table.
    """
    summaries = [AdminVoteSummary(**s) for s in summarize_all(db)]
    return AdminAllFeatures(
        features=summaries,
        generated_at=datetime.now(UTC),
    )


@admin_router.get(
    "/{feature_key}",
    response_model=AdminFeatureDetail,
    summary="Summary + recent votes for a single feature_key.",
)
def admin_feature_detail(
    feature_key: str,
    limit: int = Query(default=100, ge=1, le=500),
    vote: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> AdminFeatureDetail:
    """Returns the aggregate summary + recent_votes list.

    Filters:
      • vote   = 'interested' | 'not_interested' (optional)
      • since  = ISO-8601 timestamp (optional, only votes after)
      • limit  = 1..500 (default 100)
    """
    summary = AdminVoteSummary(**summarize_feature(db, feature_key=feature_key))
    try:
        rows = list_recent_votes(
            db,
            feature_key=feature_key,
            limit=limit,
            vote_filter=vote,
            since=since,
        )
    except InvalidVoteError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    recent = [AdminVoteRow(**r) for r in rows]
    return AdminFeatureDetail(summary=summary, recent_votes=recent)


@admin_router.get(
    "/{feature_key}/export.csv",
    response_class=StreamingResponse,
    summary="Export all votes for a feature_key as CSV.",
)
def admin_export_csv(
    feature_key: str,
    db: Session = Depends(get_db_session),
) -> StreamingResponse:
    """Stream a CSV of every vote on this feature_key.

    Columns:
      created_at, updated_at, vote, user_email_masked, user_subject,
      project_id, project_name, use_case
    """
    rows = list_recent_votes(
        db, feature_key=feature_key, limit=500
    )

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "created_at", "updated_at", "vote", "user_email_masked",
        "user_subject", "project_id", "project_name", "use_case",
    ])
    for row in rows:
        writer.writerow([
            row["created_at"].isoformat() if row["created_at"] else "",
            row["updated_at"].isoformat() if row["updated_at"] else "",
            row["vote"],
            row["user_email_masked"] or "",
            row["user_subject"],
            row["project_id"],
            row["project_name"] or "",
            (row["use_case"] or "").replace("\n", " ").replace("\r", " "),
        ])

    buf.seek(0)
    filename = f"feature_votes_{feature_key.replace('.', '_')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
