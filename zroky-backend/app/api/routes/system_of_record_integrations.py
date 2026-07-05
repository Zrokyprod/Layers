from __future__ import annotations

from fastapi import APIRouter
from app.services.zoho_oauth import exchange_zoho_code

from ._sor_integrations_commerce import router as commerce_router
from ._sor_integrations_crm_core import router as crm_core_router
from ._sor_integrations_crm_enterprise import router as crm_enterprise_router
from ._sor_integrations_postgres import router as postgres_router
from ._sor_integrations_records import router as records_router
from ._sor_integrations_refunds import router as refunds_router

router = APIRouter(prefix="/v1/integrations/system-of-record")
router.include_router(refunds_router)
router.include_router(records_router)
router.include_router(commerce_router)
router.include_router(crm_core_router)
router.include_router(crm_enterprise_router)
router.include_router(postgres_router)
