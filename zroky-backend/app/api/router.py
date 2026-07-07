"""Top-level API router.

Legacy-surface routes are gated by ``FEATURE_LEGACY_*`` flags from
``app.core.config.Settings`` per ZROKY-TECHNICAL-PLAN-V2.md §1.3.

A route's import is colocated with its include block so the entire entry is
removable in a single hunk when its replacement module ships.
"""

from fastapi import APIRouter

from app.api.routes.alerts import router as alerts_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.action_intents import router as action_intents_router
from app.api.routes.agents import router as agents_router
from app.api.routes.ask import router as ask_router
from app.api.routes.auth import router as auth_router
from app.api.routes.calls import router as calls_router
from app.api.routes.capture import router as capture_router
from app.api.routes.contracts import router as contracts_router
from app.api.routes.diagnoses import router as diagnoses_router
from app.api.routes.digest import router as digest_router
from app.api.routes.evidence import router as evidence_router
from app.api.routes.export import router as export_router
from app.api.routes.fix_events import router as fix_events_router
from app.api.routes.health import router as health_router
from app.api.routes.home import router as home_router
from app.api.routes.github_webhooks import router as github_webhooks_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.internal import router as internal_router
from app.api.routes.integrations import router as integrations_router
from app.api.routes.system_of_record_integrations import (
    router as system_of_record_integrations_router,
)
from app.api.routes.live import router as live_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.projects import router as projects_router
from app.api.routes.providers import router as providers_router
from app.api.routes.realtime_ws import router as realtime_ws_router
from app.api.routes.security import router as security_router
from app.api.routes.settings import router as settings_router
from app.api.routes.traces import router as traces_router
from app.api.routes.tool_registry import router as tool_registry_router
from app.api.routes.detectors import router as detectors_router
from app.api.routes.feature_interest import (
    admin_router as feature_interest_admin_router,
    router as feature_interest_router,
)
from app.api.routes.feature_flags import router as feature_flags_router
from app.api.routes.goldens import router as goldens_router
from app.api.routes.issues import router as issues_router
from app.api.routes.intel import router as intel_router
from app.api.routes.judge_calibration_routes import (
    router as judge_calibration_router,
)
from app.api.routes.judge_health import router as judge_health_router
from app.api.routes.ablation import router as ablation_router
from app.api.routes.outcomes import router as outcomes_router
from app.api.routes.reliability import router as reliability_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.routes.provider_drift import router as provider_drift_router
from app.api.routes.pilot import router as pilot_router
from app.api.routes.replay import router as replay_router
from app.api.routes.regression_ci import router as regression_ci_router
from app.api.routes.replay_dispatch import router as replay_dispatch_router
from app.api.routes.replay_runs import router as replay_runs_router
from app.api.routes.runtime_policy import router as runtime_policy_router
from app.core.config import get_settings

_settings = get_settings()

api_router = APIRouter()

# ── Always-on routes (Watch + Pilot core surface) ─────────────────────
api_router.include_router(health_router, tags=["health"])
api_router.include_router(home_router, tags=["home"])
api_router.include_router(internal_router, tags=["internal"])
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(security_router, tags=["security"])
api_router.include_router(realtime_ws_router, tags=["realtime"])
api_router.include_router(ingest_router, tags=["ingest"])
api_router.include_router(capture_router, tags=["capture"])
api_router.include_router(calls_router, tags=["calls"])
api_router.include_router(traces_router, tags=["traces"])
api_router.include_router(live_router, tags=["live"])
api_router.include_router(analytics_router, tags=["analytics"])
api_router.include_router(action_intents_router, tags=["verified-actions"])
api_router.include_router(evidence_router, tags=["evidence"])
api_router.include_router(agents_router, tags=["agents"])  # Agent tool-control profiles
api_router.include_router(tool_registry_router, tags=["tool-registry"])  # Agent runtime and verifier catalog
api_router.include_router(ask_router, tags=["ask"])  # Ask Zroky — natural-language Q&A
api_router.include_router(alerts_router, tags=["alerts"])
api_router.include_router(integrations_router, tags=["integrations"])
api_router.include_router(system_of_record_integrations_router, tags=["integrations"])
api_router.include_router(notifications_router, tags=["notifications"])
api_router.include_router(settings_router, tags=["settings"])
api_router.include_router(providers_router, tags=["providers"])
api_router.include_router(export_router, tags=["export"])
api_router.include_router(fix_events_router, tags=["fix-events"])
api_router.include_router(github_webhooks_router, tags=["github-webhooks"])
api_router.include_router(diagnoses_router, tags=["diagnoses"])
api_router.include_router(digest_router, tags=["digest"])
api_router.include_router(projects_router, tags=["projects"])
api_router.include_router(issues_router, tags=["issues"])  # public problem API backed by Anomaly
api_router.include_router(goldens_router, tags=["goldens"])  # Pilot tier (Module 4.1)
api_router.include_router(contracts_router, tags=["contracts"])  # Paid P0 canonical regression contracts
api_router.include_router(replay_router, tags=["replay"])  # legacy single-fix replay jobs
api_router.include_router(replay_runs_router, tags=["replay-runs"])  # Pilot tier (Module 4.2)
api_router.include_router(replay_dispatch_router, tags=["replay-dispatch"])  # Pilot tier (Module 9 — GitHub Action)
api_router.include_router(regression_ci_router, tags=["regression-ci"])  # Wedge 1 — Pre-deploy Replay CI Gate
api_router.include_router(runtime_policy_router, tags=["runtime-policy"])  # Phase 9 pre-action policy gate
api_router.include_router(pilot_router, tags=["pilot"])  # Pilot tier (Module 4.3)
api_router.include_router(intel_router, tags=["intel"])  # Pilot tier (Module 4.6)
api_router.include_router(detectors_router, tags=["detectors"])
api_router.include_router(judge_health_router, tags=["judge-health"])  # Layer 3 surface
api_router.include_router(
    judge_calibration_router, tags=["judge-calibration"]
)  # Calibrated Judge wedge
api_router.include_router(provider_drift_router, tags=["provider-drift"])  # Wedge 2
api_router.include_router(outcomes_router, tags=["outcomes"])  # Cost-of-Failure Attribution
api_router.include_router(ablation_router, tags=["ablation"])  # Ablation Root-Cause Attribution
api_router.include_router(reliability_router, tags=["reliability"])  # Agent Reliability Scorecard
api_router.include_router(recommendations_router, tags=["recommendations"])  # Reliability Intelligence Queue
# Module 9 smoke-test: coming-soon feature interest polling.
# Customer write surface (/v1/feature-interest) + always-on admin
# read surface (/v1/admin/feature-interest) gated by provisioning token.
api_router.include_router(feature_interest_router, tags=["feature-interest"])
api_router.include_router(
    feature_interest_admin_router, tags=["feature-interest-admin"],
)
api_router.include_router(feature_flags_router, tags=["feature-flags"])

# ── Legacy-gated routes (default OFF, removed when UI is also removed) ───────
# (FEATURE_LEGACY_ASSISTANT, FEATURE_LEGACY_AI_INTEGRATION removed:
#  source files deleted in Module 1.)
# (FEATURE_LEGACY_NOTIFICATIONS, FEATURE_LEGACY_SUPPORT, FEATURE_LEGACY_ONBOARDING:
#  source files deleted in Module 1; flags removed.)

# ── Legacy-gated routes (default ON until later module ships replacement) ────
if _settings.FEATURE_LEGACY_OWNER:
    from app.api.routes.owner import router as owner_router
    api_router.include_router(owner_router, tags=["owner"])

# §11.3 billing surface — always mounted (POST /checkout, /portal,
# /webhook + GET /me and /usage). Deprecated tenant-subscription
# routes (/plans and GET/PUT /subscription) are removed.
from app.api.routes.billing import router as billing_router
api_router.include_router(billing_router, tags=["billing"])

if _settings.FEATURE_LEGACY_INVITATIONS:
    from app.api.routes.invitations import router as invitations_router
    api_router.include_router(invitations_router, tags=["invitations"])

if _settings.FEATURE_LEGACY_DIAGNOSIS_ALIAS:
    from app.api.routes.diagnosis import router as diagnosis_router
    api_router.include_router(diagnosis_router, tags=["diagnosis"])
