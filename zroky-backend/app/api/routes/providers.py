from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_role
from app.core.limiter import limiter
from app.api.routes.settings import list_provider_verifications, test_provider_connection
from app.db.session import get_db_session
from app.schemas.dashboard import ProviderVerificationListResponse, ProviderVerificationTestResponse

router = APIRouter(prefix="/v1/providers")


@router.get("/status", response_model=ProviderVerificationListResponse)
def get_provider_status(
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> ProviderVerificationListResponse:
    return list_provider_verifications(tenant_id=tenant_id, db=db)


@router.post("/{provider}/test", response_model=ProviderVerificationTestResponse)
@limiter.limit("10/minute")
def test_provider_status(
    request: Request,
    provider: str,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> ProviderVerificationTestResponse:
    return test_provider_connection(provider=provider, tenant_id=tenant_id, db=db)
