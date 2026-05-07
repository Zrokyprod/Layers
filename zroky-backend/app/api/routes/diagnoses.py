from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_role
from app.core.limiter import limiter
from app.api.routes.diagnosis import (
    create_diagnosis_share_link,
    get_diagnosis_fix_watch,
    get_diagnosis_shared_view,
    get_diagnosis_status,
    list_diagnoses,
    resolve_diagnosis,
    submit_diagnosis_feedback,
)
from app.db.session import get_db_session
from app.schemas.diagnosis import (
    DiagnosisFeedbackResponse,
    DiagnosisFeedbackSubmitRequest,
    DiagnosisFixWatchResponse,
    DiagnosisResolveResponse,
    DiagnosisShareCreateResponse,
    DiagnosisShareReadResponse,
    DiagnosisStatusResponse,
)

router = APIRouter(prefix="/v1/diagnoses")


@router.get("", response_model=list[DiagnosisStatusResponse])
def list_diagnoses_alias(
    status_filter: str | None = None,
    limit: int = 100,
    offset: int = 0,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> list[DiagnosisStatusResponse]:
    return list_diagnoses(
        status_filter=status_filter,
        limit=limit,
        offset=offset,
        tenant_id=tenant_id,
        db=db,
    )


@router.post(
    "/{diagnosis_id}/feedback",
    response_model=DiagnosisFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def submit_diagnosis_feedback_alias(
    diagnosis_id: str,
    body: DiagnosisFeedbackSubmitRequest,
    request: Request,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> DiagnosisFeedbackResponse:
    return submit_diagnosis_feedback(
        diagnosis_id=diagnosis_id,
        body=body,
        request=request,
        tenant_id=tenant_id,
        db=db,
    )


@router.post(
    "/{diagnosis_id}/share",
    response_model=DiagnosisShareCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
def create_diagnosis_share_link_alias(
    diagnosis_id: str,
    request: Request,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> DiagnosisShareCreateResponse:
    return create_diagnosis_share_link(
        diagnosis_id=diagnosis_id,
        request=request,
        tenant_id=tenant_id,
        db=db,
    )


@router.get("/share/{share_token}", response_model=DiagnosisShareReadResponse)
def get_diagnosis_shared_view_alias(
    share_token: str,
    db: Session = Depends(get_db_session),
) -> DiagnosisShareReadResponse:
    return get_diagnosis_shared_view(share_token=share_token, db=db)


@router.post("/{diagnosis_id}/resolve", response_model=DiagnosisResolveResponse)
@limiter.limit("10/minute")
def resolve_diagnosis_alias(
    diagnosis_id: str,
    request: Request,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> DiagnosisResolveResponse:
    return resolve_diagnosis(
        diagnosis_id=diagnosis_id,
        request=request,
        tenant_id=tenant_id,
        db=db,
    )


@router.get("/{diagnosis_id}/fix-watch", response_model=DiagnosisFixWatchResponse)
def get_diagnosis_fix_watch_alias(
    diagnosis_id: str,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> DiagnosisFixWatchResponse:
    return get_diagnosis_fix_watch(
        diagnosis_id=diagnosis_id,
        tenant_id=tenant_id,
        db=db,
    )


@router.get("/{diagnosis_id}", response_model=DiagnosisStatusResponse)
def get_diagnosis_status_alias(
    diagnosis_id: str,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> DiagnosisStatusResponse:
    return get_diagnosis_status(
        diagnosis_id=diagnosis_id,
        tenant_id=tenant_id,
        db=db,
    )
