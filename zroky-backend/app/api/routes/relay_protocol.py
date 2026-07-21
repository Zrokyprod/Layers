from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.infrastructure.relay_protocol import RelayReadCommand, RelayReadCommandRequest, prepare_read_command


router = APIRouter(prefix="/v1/relay-protocol")


@router.post("/read-commands/prepare", response_model=RelayReadCommand)
@limiter.limit("120/minute")
def prepare_customer_read_command(
    request: Request,
    body: RelayReadCommandRequest,
    context: TenantContext = Depends(require_tenant_context),
) -> RelayReadCommand:
    return prepare_read_command(context.tenant_id, body)
