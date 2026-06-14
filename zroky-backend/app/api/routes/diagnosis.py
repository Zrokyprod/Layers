import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id, require_tenant_role
from app.core.config import get_settings
from app.db.models import (
    DiagnosisFeedback,
    DiagnosisFixWatch,
    DiagnosisJob,
    DiagnosisPullRequest,
    ProjectDashboardConfig,
    DiagnosisShareToken,
    DiagnosisUiState,
    User,
)
from app.db.session import get_db_session
from app.observability.metrics import record_diagnosis_job
from app.schemas.diagnosis import (
    DiagnosisFeedbackResponse,
    DiagnosisFeedbackSubmitRequest,
    DiagnosisFixWatchResponse,
    DiagnosisFixCopiedResponse,
    DiagnosisGeneratePrRequest,
    DiagnosisGeneratePrResponse,
    DiagnosisPrLinkResponse,
    DiagnosisResolveResponse,
    DiagnosisShareCreateResponse,
    DiagnosisShareReadResponse,
    DiagnosisStatusResponse,
    DiagnosisSubmitRequest,
    DiagnosisSubmitResponse,
    DiagnosisUiStateResponse,
    DiagnosisAssignmentRequest,
    DiagnosisSnoozeRequest,
    DiagnosisDismissRequest,
)
from app.services.audit_logs import (
    AUDIT_ACTION_FIX_COPIED,
    AUDIT_ACTION_PR_GENERATED,
    AUDIT_ACTION_RESOLVED,
    create_audit_log,
    create_audit_log_best_effort,
    safe_actor_subject_from_request,
)
from app.services.github_tokens import decrypt_github_token
from app.services.github_pr import build_generated_patch, create_pull_request_with_patch
from app.services.github_webhooks import append_zroky_tracking_marker
from app.services.fix_adoption import ensure_fix_event_prerequisites, record_fix_event
from app.services.fix_identity import extract_fix_id_from_result, normalize_fix_id, safe_json_object
from app.services.privacy import mask_error_message, mask_json_string, mask_payload
from app.services.security import generate_share_token_material, hash_share_token
from app.services.user_identity import resolve_request_identity
from app.worker.tasks import process_diagnosis

router = APIRouter(prefix="/v1/diagnosis")
logger = logging.getLogger(__name__)
from app.api.routes._internal.diagnosis_helpers import (
    FIX_WATCH_WINDOW,
    _as_utc,
    _build_fix_watch_response,
    _extract_job_categories,
    _get_job_or_404,
    _payload_text_field,
    _project_pii_patterns,
    _resolve_github_pr_token,
    _safe_actor_subject,
)

@router.post("/submit", response_model=DiagnosisSubmitResponse)
def submit_diagnosis(
    body: DiagnosisSubmitRequest,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> DiagnosisSubmitResponse:
    if body.tenant_id and body.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch between authenticated context and request body.",
        )

    custom_pii_patterns = _project_pii_patterns(db, tenant_id)
    safe_payload = mask_payload(body.payload, custom_patterns=custom_pii_patterns)
    agent_name = _payload_text_field(safe_payload, "agent_name")
    prompt_fingerprint = _payload_text_field(safe_payload, "prompt_fingerprint")

    job = DiagnosisJob(
        tenant_id=tenant_id,
        diagnosis_id=body.diagnosis_id,
        status="queued",
        agent_name=agent_name,
        prompt_fingerprint=prompt_fingerprint,
        payload_json=json.dumps(safe_payload, separators=(",", ":")),
    )
    db.add(job)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        record_diagnosis_job("already_exists")
        return DiagnosisSubmitResponse(
            status="already_exists",
            diagnosis_id=body.diagnosis_id,
            task_id=None,
        )

    try:
        task = process_diagnosis.delay(tenant_id, body.diagnosis_id, safe_payload)
    except Exception as exc:
        logger.exception("Failed to enqueue diagnosis task")
        job.status = "enqueue_failed"
        job.error_message = mask_error_message(exc)
        db.add(job)
        db.commit()
        record_diagnosis_job("enqueue_failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Queue is unavailable. Please retry shortly.",
        ) from exc

    record_diagnosis_job("queued")

    return DiagnosisSubmitResponse(
        status="queued",
        diagnosis_id=body.diagnosis_id,
        task_id=task.id,
    )


@router.get("", response_model=list[DiagnosisStatusResponse])
def list_diagnoses(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> list[DiagnosisStatusResponse]:
    query = (
        select(DiagnosisJob)
        .where(DiagnosisJob.tenant_id == tenant_id)
        .order_by(DiagnosisJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if status_filter:
        query = query.where(DiagnosisJob.status == status_filter.strip().lower())

    jobs = db.execute(query).scalars().all()
    return [
        DiagnosisStatusResponse(
            tenant_id=job.tenant_id,
            diagnosis_id=job.diagnosis_id,
            status=job.status,
            result_json=mask_json_string(job.result_json),
            error_message=mask_error_message(job.error_message) if job.error_message else None,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        for job in jobs
    ]


@router.post(
    "/{diagnosis_id}/feedback",
    response_model=DiagnosisFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_diagnosis_feedback(
    diagnosis_id: str,
    body: DiagnosisFeedbackSubmitRequest,
    request: Request,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> DiagnosisFeedbackResponse:
    _get_job_or_404(db=db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)

    feedback = DiagnosisFeedback(
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        was_helpful=body.was_helpful,
        developer_note=body.developer_note,
        created_by_subject=_safe_actor_subject(request),
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return DiagnosisFeedbackResponse(
        feedback_id=feedback.id,
        tenant_id=feedback.tenant_id,
        diagnosis_id=feedback.diagnosis_id,
        was_helpful=feedback.was_helpful,
        developer_note=feedback.developer_note,
        created_by_subject=feedback.created_by_subject,
        created_at=feedback.created_at,
    )


@router.post(
    "/{diagnosis_id}/share",
    response_model=DiagnosisShareCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_diagnosis_share_link(
    diagnosis_id: str,
    request: Request,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> DiagnosisShareCreateResponse:
    _get_job_or_404(db=db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)

    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.READ_ONLY_SHARE_TOKEN_TTL_SECONDS)
    created_by_subject = _safe_actor_subject(request)

    share_token_record: DiagnosisShareToken | None = None
    raw_share_token: str | None = None
    for _ in range(3):
        token_value, token_prefix, token_hash = generate_share_token_material()
        candidate = DiagnosisShareToken(
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
            token_prefix=token_prefix,
            token_hash=token_hash,
            created_by_subject=created_by_subject,
            expires_at=expires_at,
        )
        db.add(candidate)
        try:
            db.commit()
            db.refresh(candidate)
            share_token_record = candidate
            raw_share_token = token_value
            break
        except IntegrityError:
            db.rollback()

    if share_token_record is None or raw_share_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not issue share link. Please retry.",
        )

    return DiagnosisShareCreateResponse(
        share_id=share_token_record.id,
        diagnosis_id=share_token_record.diagnosis_id,
        token=raw_share_token,
        token_prefix=share_token_record.token_prefix,
        expires_at=share_token_record.expires_at,
        created_at=share_token_record.created_at,
    )


@router.get("/share/{share_token}", response_model=DiagnosisShareReadResponse)
def get_diagnosis_shared_view(
    share_token: str,
    db: Session = Depends(get_db_session),
) -> DiagnosisShareReadResponse:
    query = select(DiagnosisShareToken).where(DiagnosisShareToken.token_hash == hash_share_token(share_token))
    share = db.execute(query).scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")

    now = datetime.now(timezone.utc)
    expires_at = _as_utc(share.expires_at)
    if share.revoked_at is not None or expires_at <= now:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share link is no longer active")

    job = _get_job_or_404(db=db, tenant_id=share.tenant_id, diagnosis_id=share.diagnosis_id)
    return DiagnosisShareReadResponse(
        share_id=share.id,
        diagnosis_id=job.diagnosis_id,
        tenant_id=job.tenant_id,
        status=job.status,
        result_json=mask_json_string(job.result_json),
        error_message=mask_error_message(job.error_message) if job.error_message else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
        expires_at=expires_at,
    )


@router.post("/{diagnosis_id}/resolve", response_model=DiagnosisResolveResponse)
def resolve_diagnosis(
    diagnosis_id: str,
    request: Request,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> DiagnosisResolveResponse:
    job = _get_job_or_404(db=db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    watch_expires_at = now + FIX_WATCH_WINDOW
    target_categories = sorted(_extract_job_categories(job))
    actor_subject = _safe_actor_subject(request)

    watch_query = select(DiagnosisFixWatch).where(
        DiagnosisFixWatch.tenant_id == tenant_id,
        DiagnosisFixWatch.diagnosis_id == diagnosis_id,
    )
    watch = db.execute(watch_query).scalar_one_or_none()
    if watch is None:
        watch = DiagnosisFixWatch(
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
            target_categories_json=json.dumps(target_categories, separators=(",", ":")),
            resolved_at=now,
            watch_expires_at=watch_expires_at,
            created_by_subject=actor_subject,
        )
    else:
        watch.target_categories_json = json.dumps(target_categories, separators=(",", ":"))
        watch.resolved_at = now
        watch.watch_expires_at = watch_expires_at
        watch.created_by_subject = actor_subject

    db.add(watch)
    db.commit()

    create_audit_log_best_effort(
        db,
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        action=AUDIT_ACTION_RESOLVED,
        actor_subject=actor_subject,
        metadata={
            "target_categories": target_categories,
            "watch_expires_at": watch_expires_at.isoformat(),
        },
    )

    return DiagnosisResolveResponse(
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        status="active",
        resolved_at=now,
        watch_expires_at=watch_expires_at,
        target_categories=target_categories,
        message="Diagnosis marked resolved. Fix-watch started for 7 days.",
    )


@router.get("/{diagnosis_id}/fix-watch", response_model=DiagnosisFixWatchResponse)
def get_diagnosis_fix_watch(
    diagnosis_id: str,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> DiagnosisFixWatchResponse:
    _get_job_or_404(db=db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)

    watch_query = select(DiagnosisFixWatch).where(
        DiagnosisFixWatch.tenant_id == tenant_id,
        DiagnosisFixWatch.diagnosis_id == diagnosis_id,
    )
    watch = db.execute(watch_query).scalar_one_or_none()
    if watch is None:
        return DiagnosisFixWatchResponse(
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
            status="not_started",
            resolved_at=None,
            watch_expires_at=None,
            target_categories=[],
            recurrence_count=0,
            last_recurrence_at=None,
            message="Resolve this diagnosis to start fix-watch monitoring.",
        )

    return _build_fix_watch_response(db=db, watch=watch)


@router.post(
    "/{diagnosis_id}/fix-copied",
    response_model=DiagnosisFixCopiedResponse,
    status_code=status.HTTP_201_CREATED,
)
def log_diagnosis_fix_copied(
    diagnosis_id: str,
    request: Request,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> DiagnosisFixCopiedResponse:
    job = _get_job_or_404(db=db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)

    entry = create_audit_log(
        db,
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        action=AUDIT_ACTION_FIX_COPIED,
        actor_subject=_safe_actor_subject(request),
        metadata=None,
    )

    result_payload = safe_json_object(job.result_json)
    fix_id = extract_fix_id_from_result(result_payload, diagnosis_id=diagnosis_id)
    ensure_fix_event_prerequisites(
        db,
        project_id=tenant_id,
        diagnosis_id=diagnosis_id,
        fix_id=fix_id,
        event_type="copied",
        anchor_time=entry.created_at,
        source="dashboard",
        inferred_from="fix_copied",
        metadata={"feed": "fix_copied"},
    )
    record_fix_event(
        db,
        project_id=tenant_id,
        diagnosis_id=diagnosis_id,
        fix_id=fix_id,
        event_type="copied",
        metadata={"source_endpoint": "diagnosis_fix_copied"},
        idempotency_key=f"dashboard:fix-copied:{tenant_id}:{diagnosis_id}",
        source="dashboard",
        timestamp=entry.created_at,
    )

    return DiagnosisFixCopiedResponse(
        tenant_id=entry.tenant_id,
        diagnosis_id=entry.diagnosis_id,
        action=entry.action,
        created_at=entry.created_at,
    )


@router.post(
    "/{diagnosis_id}/generate-pr",
    response_model=DiagnosisGeneratePrResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_diagnosis_pr(
    diagnosis_id: str,
    body: DiagnosisGeneratePrRequest,
    request: Request,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> DiagnosisGeneratePrResponse:
    job = _get_job_or_404(db=db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)
    settings = get_settings()

    repository_owner = body.repository_owner or settings.GITHUB_PR_DEFAULT_OWNER
    repository_name = body.repository_name or settings.GITHUB_PR_DEFAULT_REPO
    base_branch = body.base_branch or settings.GITHUB_PR_DEFAULT_BASE_BRANCH

    if not repository_owner or not repository_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "repository_owner and repository_name are required. "
                "Provide them in request body or configure GITHUB_PR_DEFAULT_OWNER/GITHUB_PR_DEFAULT_REPO."
            ),
        )

    generated_patch = build_generated_patch(
        diagnosis_id=diagnosis_id,
        diagnosis_payload_json=job.payload_json,
        diagnosis_result_json=job.result_json,
        override_patch=body.generated_patch,
        override_file_path=body.file_path,
        override_title=body.title,
        override_body=body.body,
        override_commit_message=body.commit_message,
        override_branch_name=body.branch_name,
    )
    result_payload = safe_json_object(job.result_json)
    fix_id = normalize_fix_id(body.fix_id) or extract_fix_id_from_result(
        result_payload,
        diagnosis_id=diagnosis_id,
    )
    generated_patch.body = append_zroky_tracking_marker(
        generated_patch.body,
        project_id=tenant_id,
        diagnosis_id=diagnosis_id,
        fix_id=fix_id,
    )

    github_token, auth_source = _resolve_github_pr_token(request, db)

    github_result = create_pull_request_with_patch(
        token=github_token,
        repository_owner=repository_owner,
        repository_name=repository_name,
        base_branch=base_branch,
        generated_patch=generated_patch,
    )

    link = DiagnosisPullRequest(
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        fix_id=fix_id,
        repository_owner=repository_owner,
        repository_name=repository_name,
        base_branch=base_branch,
        branch_name=github_result.branch_name,
        pull_request_number=github_result.pull_request_number,
        pull_request_url=github_result.pull_request_url,
        pull_request_title=github_result.pull_request_title,
        file_path=github_result.file_path,
        commit_sha=github_result.commit_sha,
        generated_patch=generated_patch.generated_patch,
        created_by_subject=_safe_actor_subject(request),
    )
    db.add(link)

    try:
        db.commit()
        db.refresh(link)
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            select(DiagnosisPullRequest).where(
                DiagnosisPullRequest.tenant_id == tenant_id,
                DiagnosisPullRequest.diagnosis_id == diagnosis_id,
                DiagnosisPullRequest.branch_name == github_result.branch_name,
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        link = existing
        if not link.fix_id:
            link.fix_id = fix_id
            db.add(link)
            db.commit()
            db.refresh(link)

    fix_event_metadata = {
        "repository_owner": link.repository_owner,
        "repository_name": link.repository_name,
        "pull_request_number": link.pull_request_number,
        "pull_request_url": link.pull_request_url,
        "branch_name": link.branch_name,
        "commit_sha": link.commit_sha,
        "auth_source": auth_source,
        "source_endpoint": "diagnosis_generate_pr",
    }
    ensure_fix_event_prerequisites(
        db,
        project_id=tenant_id,
        diagnosis_id=diagnosis_id,
        fix_id=fix_id,
        event_type="pr_generated",
        anchor_time=link.created_at,
        source="dashboard",
        inferred_from="pr_generated",
        metadata={"feed": "generate_pr"},
    )
    record_fix_event(
        db,
        project_id=tenant_id,
        diagnosis_id=diagnosis_id,
        fix_id=fix_id,
        event_type="pr_generated",
        metadata=fix_event_metadata,
        idempotency_key=f"github:pr-generated:{tenant_id}:{diagnosis_id}:{link.pull_request_number}",
        source="dashboard",
        timestamp=link.created_at,
    )

    create_audit_log_best_effort(
        db,
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        action=AUDIT_ACTION_PR_GENERATED,
        actor_subject=_safe_actor_subject(request),
        metadata={
            "repository_owner": link.repository_owner,
            "repository_name": link.repository_name,
            "pull_request_number": link.pull_request_number,
            "pull_request_url": link.pull_request_url,
            "branch_name": link.branch_name,
            "fix_id": fix_id,
            "auth_source": auth_source,
        },
    )

    return DiagnosisGeneratePrResponse(
        tenant_id=link.tenant_id,
        diagnosis_id=link.diagnosis_id,
        fix_id=fix_id,
        auth_source=auth_source,
        repository_owner=link.repository_owner,
        repository_name=link.repository_name,
        base_branch=link.base_branch,
        branch_name=link.branch_name,
        pull_request_number=link.pull_request_number,
        pull_request_url=link.pull_request_url,
        pull_request_title=link.pull_request_title,
        file_path=link.file_path,
        commit_sha=link.commit_sha,
        merge_commit_sha=link.merge_commit_sha,
        merged_at=link.merged_at,
        last_ci_state=link.last_ci_state,
        last_ci_conclusion=link.last_ci_conclusion,
        last_ci_completed_at=link.last_ci_completed_at,
        generated_patch=link.generated_patch,
        created_at=link.created_at,
    )


@router.get("/{diagnosis_id}/prs", response_model=list[DiagnosisPrLinkResponse])
def list_diagnosis_pr_links(
    diagnosis_id: str,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> list[DiagnosisPrLinkResponse]:
    _get_job_or_404(db=db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)

    rows = db.execute(
        select(DiagnosisPullRequest)
        .where(
            DiagnosisPullRequest.tenant_id == tenant_id,
            DiagnosisPullRequest.diagnosis_id == diagnosis_id,
        )
        .order_by(DiagnosisPullRequest.created_at.desc())
    ).scalars().all()

    return [
        DiagnosisPrLinkResponse(
            pr_link_id=row.id,
            tenant_id=row.tenant_id,
            diagnosis_id=row.diagnosis_id,
            fix_id=row.fix_id,
            repository_owner=row.repository_owner,
            repository_name=row.repository_name,
            base_branch=row.base_branch,
            branch_name=row.branch_name,
            pull_request_number=row.pull_request_number,
            pull_request_url=row.pull_request_url,
            pull_request_title=row.pull_request_title,
            file_path=row.file_path,
            commit_sha=row.commit_sha,
            merge_commit_sha=row.merge_commit_sha,
            merged_at=row.merged_at,
            last_ci_state=row.last_ci_state,
            last_ci_conclusion=row.last_ci_conclusion,
            last_ci_completed_at=row.last_ci_completed_at,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/{diagnosis_id}", response_model=DiagnosisStatusResponse)
def get_diagnosis_status(
    diagnosis_id: str,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> DiagnosisStatusResponse:
    job = _get_job_or_404(db=db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)

    return DiagnosisStatusResponse(
        tenant_id=job.tenant_id,
        diagnosis_id=job.diagnosis_id,
        status=job.status,
        result_json=mask_json_string(job.result_json),
        error_message=mask_error_message(job.error_message) if job.error_message else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/{diagnosis_id}/state", response_model=DiagnosisUiStateResponse)
def get_diagnosis_ui_state(
    diagnosis_id: str,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> DiagnosisUiStateResponse:
    _get_job_or_404(db=db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)

    query = select(DiagnosisUiState).where(
        DiagnosisUiState.tenant_id == tenant_id,
        DiagnosisUiState.diagnosis_id == diagnosis_id,
    )
    state = db.execute(query).scalar_one_or_none()
    if state is None:
        # return defaults
        return DiagnosisUiStateResponse(
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
            assigned_subject=None,
            snoozed_until=None,
            dismissed=False,
            updated_at=datetime.now(timezone.utc),
        )

    return DiagnosisUiStateResponse(
        tenant_id=state.tenant_id,
        diagnosis_id=state.diagnosis_id,
        assigned_subject=state.assigned_subject,
        snoozed_until=state.snoozed_until,
        dismissed=bool(state.dismissed),
        updated_at=state.updated_at,
    )


@router.post("/{diagnosis_id}/assignment", response_model=DiagnosisUiStateResponse)
def set_diagnosis_assignment(
    diagnosis_id: str,
    body: DiagnosisAssignmentRequest,
    request: Request,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> DiagnosisUiStateResponse:
    _get_job_or_404(db=db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)

    query = select(DiagnosisUiState).where(
        DiagnosisUiState.tenant_id == tenant_id,
        DiagnosisUiState.diagnosis_id == diagnosis_id,
    )
    state = db.execute(query).scalar_one_or_none()
    if state is None:
        state = DiagnosisUiState(
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
            assigned_subject=body.assigned_subject,
        )
    else:
        state.assigned_subject = body.assigned_subject

    db.add(state)
    db.commit()
    db.refresh(state)

    return DiagnosisUiStateResponse(
        tenant_id=state.tenant_id,
        diagnosis_id=state.diagnosis_id,
        assigned_subject=state.assigned_subject,
        snoozed_until=state.snoozed_until,
        dismissed=bool(state.dismissed),
        updated_at=state.updated_at,
    )


@router.post("/{diagnosis_id}/snooze", response_model=DiagnosisUiStateResponse)
def set_diagnosis_snooze(
    diagnosis_id: str,
    body: DiagnosisSnoozeRequest,
    request: Request,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> DiagnosisUiStateResponse:
    _get_job_or_404(db=db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)

    query = select(DiagnosisUiState).where(
        DiagnosisUiState.tenant_id == tenant_id,
        DiagnosisUiState.diagnosis_id == diagnosis_id,
    )
    state = db.execute(query).scalar_one_or_none()
    if state is None:
        state = DiagnosisUiState(
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
            snoozed_until=body.snoozed_until,
        )
    else:
        state.snoozed_until = body.snoozed_until

    db.add(state)
    db.commit()
    db.refresh(state)

    return DiagnosisUiStateResponse(
        tenant_id=state.tenant_id,
        diagnosis_id=state.diagnosis_id,
        assigned_subject=state.assigned_subject,
        snoozed_until=state.snoozed_until,
        dismissed=bool(state.dismissed),
        updated_at=state.updated_at,
    )


@router.post("/{diagnosis_id}/dismiss", response_model=DiagnosisUiStateResponse)
def set_diagnosis_dismiss(
    diagnosis_id: str,
    body: DiagnosisDismissRequest,
    request: Request,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> DiagnosisUiStateResponse:
    _get_job_or_404(db=db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)

    query = select(DiagnosisUiState).where(
        DiagnosisUiState.tenant_id == tenant_id,
        DiagnosisUiState.diagnosis_id == diagnosis_id,
    )
    state = db.execute(query).scalar_one_or_none()
    if state is None:
        state = DiagnosisUiState(
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
            dismissed=bool(body.dismissed),
        )
    else:
        state.dismissed = bool(body.dismissed)

    db.add(state)
    db.commit()
    db.refresh(state)

    return DiagnosisUiStateResponse(
        tenant_id=state.tenant_id,
        diagnosis_id=state.diagnosis_id,
        assigned_subject=state.assigned_subject,
        snoozed_until=state.snoozed_until,
        dismissed=bool(state.dismissed),
        updated_at=state.updated_at,
    )


@router.get("/{tenant_id}/{diagnosis_id}", response_model=DiagnosisStatusResponse)
def get_diagnosis_status_legacy(
    tenant_id: str,
    diagnosis_id: str,
    context_tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> DiagnosisStatusResponse:
    if context_tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch between path and authenticated context.",
        )
    return get_diagnosis_status(diagnosis_id=diagnosis_id, tenant_id=context_tenant_id, db=db)
