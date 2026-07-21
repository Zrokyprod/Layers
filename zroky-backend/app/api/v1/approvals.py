"""Final approval API."""

from fastapi import APIRouter

from app.api.routes.approvals import router as final_approvals_router
from app.api.routes.runtime_policy import router as runtime_policy_router

router = APIRouter()
router.include_router(final_approvals_router)
router.include_router(runtime_policy_router)

__all__ = ["router"]
