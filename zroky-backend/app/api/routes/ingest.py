from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_role
from app.api.routes._internal import ingest_processor as _ingest_processor
from app.api.routes._internal.ingest_payload import _resolve_idempotency_key
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.schemas.ingest import IngestBatchRequest, IngestBatchResponse
from app.services.cost_buckets import enrich_payload_with_cost_buckets
from app.services.redis_client import get_redis_client
from app.worker.tasks import process_diagnosis

router = APIRouter(prefix="/v1")

_check_redis_idempotency = _ingest_processor._check_redis_idempotency
_extract_redis_idempotency_key = _ingest_processor._extract_redis_idempotency_key
_set_redis_idempotency = _ingest_processor._set_redis_idempotency


def _sync_ingest_processor_compat_hooks() -> None:
    """Keep historical monkeypatch paths on this route module effective."""
    _ingest_processor.process_diagnosis = process_diagnosis
    _ingest_processor.enrich_payload_with_cost_buckets = enrich_payload_with_cost_buckets
    _ingest_processor.get_redis_client = get_redis_client
    _ingest_processor._check_redis_idempotency = _check_redis_idempotency
    _ingest_processor._set_redis_idempotency = _set_redis_idempotency


def process_ingest_batch_for_tenant(*args, **kwargs) -> IngestBatchResponse:
    _sync_ingest_processor_compat_hooks()
    return _ingest_processor.process_ingest_batch_for_tenant(*args, **kwargs)


@router.post("/ingest", response_model=IngestBatchResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("100/minute")
def ingest_events(
    request: Request,
    body: IngestBatchRequest,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> IngestBatchResponse:
    return process_ingest_batch_for_tenant(
        body=body,
        tenant_id=tenant_id,
        db=db,
        idempotency_header=request.headers.get("X-Idempotency-Key"),
    )
