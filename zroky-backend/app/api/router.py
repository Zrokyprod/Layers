from fastapi import APIRouter

from app.api.routes.ai_integration import router as ai_integration_router
from app.api.routes.assistant import router as assistant_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.auth import router as auth_router
from app.api.routes.billing import router as billing_router
from app.api.routes.calls import router as calls_router
from app.api.routes.diagnosis import router as diagnosis_router
from app.api.routes.diagnoses import router as diagnoses_router
from app.api.routes.export import router as export_router
from app.api.routes.fix_events import router as fix_events_router
from app.api.routes.health import router as health_router
from app.api.routes.github_webhooks import router as github_webhooks_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.internal import router as internal_router
from app.api.routes.invitations import router as invitations_router
from app.api.routes.live import router as live_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.onboarding import router as onboarding_router
from app.api.routes.owner import router as owner_router
from app.api.routes.projects import router as projects_router
from app.api.routes.providers import router as providers_router
from app.api.routes.realtime_ws import router as realtime_ws_router
from app.api.routes.security import router as security_router
from app.api.routes.settings import router as settings_router
from app.api.routes.support import router as support_router
from app.api.routes.feature_flags import router as feature_flags_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(internal_router, tags=["internal"])
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(security_router, tags=["security"])
api_router.include_router(realtime_ws_router, tags=["realtime"])
api_router.include_router(ingest_router, tags=["ingest"])
api_router.include_router(calls_router, tags=["calls"])
api_router.include_router(live_router, tags=["live"])
api_router.include_router(analytics_router, tags=["analytics"])
api_router.include_router(alerts_router, tags=["alerts"])
api_router.include_router(settings_router, tags=["settings"])
api_router.include_router(providers_router, tags=["providers"])
api_router.include_router(export_router, tags=["export"])
api_router.include_router(fix_events_router, tags=["fix-events"])
api_router.include_router(github_webhooks_router, tags=["github-webhooks"])
api_router.include_router(onboarding_router, tags=["onboarding"])
api_router.include_router(owner_router, tags=["owner"])
api_router.include_router(diagnosis_router, tags=["diagnosis"])
api_router.include_router(diagnoses_router, tags=["diagnoses"])
api_router.include_router(projects_router, tags=["projects"])
api_router.include_router(invitations_router, tags=["invitations"])
api_router.include_router(notifications_router, tags=["notifications"])
api_router.include_router(billing_router, tags=["billing"])
api_router.include_router(support_router, tags=["support"])
api_router.include_router(feature_flags_router, tags=["feature-flags"])
api_router.include_router(ai_integration_router, tags=["ai"])
api_router.include_router(assistant_router, tags=["assistant"])
