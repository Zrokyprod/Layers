"""Top-level API router.

Legacy-surface routes are gated by ``FEATURE_LEGACY_*`` flags from
``app.core.config.Settings`` per ZROKY-TECHNICAL-PLAN-V2.md §1.3.

A route's import is colocated with its include block so the entire entry is
removable in a single hunk when its replacement module ships.
"""

from fastapi import APIRouter

from app.api.routes.alerts import router as alerts_router
from app.api.v1.actions import router as action_intents_router
from app.api.v1.assurance_packs import router as assurance_packs_router
from app.mcp.routes import router as mcp_ingress_router
from app.api.routes.actions import router as actions_router
from app.api.routes.agents import router as agents_router
from app.api.routes.auth import router as auth_router
from app.api.routes.budget import router as budget_router
from app.api.routes.calls import router as calls_router
from app.api.routes.capture import router as capture_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.events import router as events_router
from app.api.routes.export import router as export_router
from app.api.routes.health import router as health_router
from app.api.routes.home import router as home_router
from app.api.routes.github_webhooks import router as github_webhooks_router
from app.api.routes.ingest import router as ingest_router
from app.api.v1.intents import router as intents_router
from app.api.routes.internal import router as internal_router
from app.api.v1.connectors import router as integrations_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.systems import (
    router as system_of_record_integrations_router,
)
from app.api.routes.notifications import router as notifications_router
from app.api.v1.observations import router as observations_router
from app.api.v1.outcome_graphs import router as outcome_graphs_router
from app.api.v1.policy import router as policy_router
from app.api.routes.projects import router as projects_router
from app.api.v1.relay_protocol import router as relay_protocol_router
from app.api.v1.recovery import router as recovery_router
from app.api.v1.runs import router as runs_router
from app.api.routes.providers import router as providers_router
from app.api.routes.realtime_ws import router as realtime_ws_router
from app.api.routes.security import router as security_router
from app.api.routes.settings import router as settings_router
from app.api.routes.traces import router as traces_router
from app.api.routes.tool_registry import router as tool_registry_router
from app.api.routes.feature_interest import (
    admin_router as feature_interest_admin_router,
    router as feature_interest_router,
)
from app.api.routes.feature_flags import router as feature_flags_router
from app.api.routes.outcomes import router as outcomes_router
from app.api.routes.pilot import router as pilot_router
from app.api.v1.approvals import router as approvals_router
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
api_router.include_router(intents_router, tags=["intents"])
api_router.include_router(policy_router, tags=["policy"])
api_router.include_router(relay_protocol_router, tags=["relay-protocol"])
api_router.include_router(recovery_router, tags=["recovery"])
api_router.include_router(runs_router, tags=["runs"])
api_router.include_router(events_router, tags=["events"])
api_router.include_router(assurance_packs_router, tags=["assurance-packs"])
api_router.include_router(action_intents_router, tags=["verified-actions"])
# MCP-native interception ingress. Always registered but inert (404) unless
# Settings.MCP_INTERCEPTION_ENABLED is true — see app.mcp.routes.
api_router.include_router(mcp_ingress_router, tags=["mcp"])
api_router.include_router(actions_router, tags=["actions"])
api_router.include_router(evidence_router, tags=["evidence"])
api_router.include_router(agents_router, tags=["agents"])  # Agent tool-control profiles
api_router.include_router(tool_registry_router, tags=["tool-registry"])  # Agent runtime and verifier catalog
api_router.include_router(alerts_router, tags=["alerts"])
api_router.include_router(incidents_router, tags=["incidents"])
api_router.include_router(integrations_router, tags=["integrations"])
api_router.include_router(system_of_record_integrations_router, tags=["integrations"])
api_router.include_router(notifications_router, tags=["notifications"])
api_router.include_router(observations_router, tags=["observations"])
api_router.include_router(outcome_graphs_router, tags=["outcome-graphs"])
api_router.include_router(settings_router, tags=["settings"])
api_router.include_router(providers_router, tags=["providers"])
api_router.include_router(export_router, tags=["export"])
api_router.include_router(github_webhooks_router, tags=["github-webhooks"])
api_router.include_router(projects_router, tags=["projects"])
api_router.include_router(approvals_router, tags=["approvals"])  # Final approvals plus runtime-policy compatibility
api_router.include_router(pilot_router, tags=["pilot"])  # Pilot tier (Module 4.3)
api_router.include_router(outcomes_router, tags=["outcomes"])  # Cost-of-Failure Attribution
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
# Launch-hidden legacy groups. Disabled by default in product deployments.
api_router.include_router(budget_router, tags=["budget"])

# Legacy admin compatibility route. Owner stays opt-in per deployment.
if _settings.FEATURE_LEGACY_OWNER:
    from app.api.v1.admin import router as owner_router
    api_router.include_router(owner_router, tags=["owner"])

# §11.3 billing surface — always mounted (POST /checkout, /portal,
# /webhook + GET /me and /usage). Deprecated tenant-subscription
# routes (/plans and GET/PUT /subscription) are removed.
from app.api.routes.billing import router as billing_router
api_router.include_router(billing_router, tags=["billing"])

if _settings.FEATURE_LEGACY_INVITATIONS:
    from app.api.routes.invitations import router as invitations_router
    api_router.include_router(invitations_router, tags=["invitations"])
