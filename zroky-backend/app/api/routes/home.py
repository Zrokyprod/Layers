from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.api.routes._action_intents_helpers import (
    _execution_attempt_response,
    _intent_response,
    _runner_response,
)
from app.api.routes.billing import get_billing_usage
from app.api.routes.outcome_serializers import (
    _serialize_reconciliation,
    _serialize_source_mutation,
)
from app.api.routes.projects import _api_key_to_response
from app.api.routes.runtime_policy import _decision_to_response
from app.db.models import (
    ActionIntent,
    ActionReceipt,
    ApiKey,
    McpUpstreamBinding,
    OutcomeReconciliationCheck,
    PilotPolicy,
    RuntimePolicyDecision,
    SourceMutationRecord,
    SystemOfRecordConnectorConfig,
)
from app.db.session import get_db_session
from app.core.limiter import limiter
from app.schemas.home import (
    HomeAgentProfileMeta,
    HomeControlHealth,
    HomeSummaryData,
    HomeSummaryMetrics,
    HomeSummaryResponse,
    HomeSummarySources,
)
from app.schemas.outcomes import OutcomeReconciliationSummaryResponse, SourceMutationSummaryResponse
from app.services.agent_profiles import (
    agent_profile_to_dict,
    count_active_agent_profiles,
    list_agent_profiles,
    resolve_agent_profile_limit,
)
from app.services.action_kernel import list_action_intents
from app.services.action_runner import list_action_runners, list_project_execution_attempts
from app.services.outcome_reconciliation import get_reconciliation_summary, list_reconciliations
from app.services.source_mutations import list_source_mutations, source_mutation_summary

router = APIRouter(prefix="/v1/home", tags=["home"])


def _count(db: Session, statement) -> int:
    return int(db.execute(statement).scalar_one() or 0)


def _has_sequence_risk(policy_hit_json: str | None, reasons_json: str | None) -> bool:
    try:
        policy_hit: Any = json.loads(policy_hit_json or "{}")
    except json.JSONDecodeError:
        policy_hit = {}
    if isinstance(policy_hit, dict) and "sequence_risk" in policy_hit:
        return True
    try:
        reasons: Any = json.loads(reasons_json or "[]")
    except json.JSONDecodeError:
        reasons = []
    return any(isinstance(reason, str) and "sequence risk" in reason.lower() for reason in reasons)


def _dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return dict(value)


@router.get("/summary", response_model=HomeSummaryResponse)
@limiter.limit("60/minute")
def get_home_summary(
    request: Request,
    days: int = Query(default=30, ge=1, le=90),
    db: Session = Depends(get_db_session),
    context: TenantContext = Depends(require_tenant_context),
) -> HomeSummaryResponse:
    tenant_id = context.tenant_id
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    sources = HomeSummarySources()

    controlled_actions = _count(
        db,
        select(func.count(ActionIntent.id)).where(
            ActionIntent.project_id == tenant_id,
            ActionIntent.created_at >= since,
        ),
    )
    pending_approvals = _count(
        db,
        select(func.count(RuntimePolicyDecision.id)).where(
            RuntimePolicyDecision.project_id == tenant_id,
            RuntimePolicyDecision.status == "pending_approval",
        ),
    )
    outcome_rows = db.execute(
        select(OutcomeReconciliationCheck.verdict, func.count(OutcomeReconciliationCheck.id))
        .where(
            OutcomeReconciliationCheck.project_id == tenant_id,
            OutcomeReconciliationCheck.checked_at >= since,
        )
        .group_by(OutcomeReconciliationCheck.verdict)
    ).all()
    outcome_counts = {str(verdict): int(count or 0) for verdict, count in outcome_rows}
    outcome_checks = sum(outcome_counts.values())
    verified_outcomes = outcome_counts.get("matched", 0)

    receipts_generated = _count(
        db,
        select(func.count(ActionReceipt.id)).where(
            ActionReceipt.project_id == tenant_id,
            ActionReceipt.generated_at >= since,
        ),
    )
    mutation_rows = db.execute(
        select(SourceMutationRecord.classification, func.count(SourceMutationRecord.id))
        .where(
            SourceMutationRecord.project_id == tenant_id,
            SourceMutationRecord.occurred_at >= since,
        )
        .group_by(SourceMutationRecord.classification)
    ).all()
    mutation_counts = {str(classification): int(count or 0) for classification, count in mutation_rows}
    bypass_mutations = mutation_counts.get("policy_bypass", 0)
    unreceipted_mutations = sum(
        mutation_counts.get(classification, 0)
        for classification in ("legacy_path", "unmanaged_agent_action", "policy_bypass", "unknown_actor")
    )

    sequence_rows = db.execute(
        select(RuntimePolicyDecision.policy_hit_json, RuntimePolicyDecision.reasons_json).where(
            RuntimePolicyDecision.project_id == tenant_id,
            RuntimePolicyDecision.created_at >= since,
        )
    ).all()
    sequence_risks = sum(1 for policy_hit_json, reasons_json in sequence_rows if _has_sequence_risk(policy_hit_json, reasons_json))

    outcome_summary = get_reconciliation_summary(db, project_id=tenant_id, days=days)
    source_summary = source_mutation_summary(db, project_id=tenant_id)
    agent_rows, _agent_total = list_agent_profiles(
        db,
        project_id=tenant_id,
        include_inactive=False,
        limit=200,
        offset=0,
    )
    active_agent_count = count_active_agent_profiles(db, project_id=tenant_id)
    agent_payloads = [agent_profile_to_dict(row) for row in agent_rows]
    policy_enforced_agents = sum(
        1 for agent in agent_payloads
        if bool((agent.get("metadata") or {}).get("runtime_policy_mandate_enforced"))
    )
    configured_action_packs = len({
        str((agent.get("metadata") or {}).get("setup_action_pack_id")).strip()
        for agent in agent_payloads
        if str((agent.get("metadata") or {}).get("setup_action_pack_id") or "").strip()
    })
    runner_rows = list_action_runners(db, project_id=tenant_id)
    online_runners = sum(1 for row in runner_rows if row.status == "online")
    active_sor_connectors = _count(
        db,
        select(func.count(SystemOfRecordConnectorConfig.id)).where(
            SystemOfRecordConnectorConfig.project_id == tenant_id,
            SystemOfRecordConnectorConfig.is_active.is_(True),
        ),
    )
    tested_sor_connectors = _count(
        db,
        select(func.count(SystemOfRecordConnectorConfig.id)).where(
            SystemOfRecordConnectorConfig.project_id == tenant_id,
            SystemOfRecordConnectorConfig.is_active.is_(True),
            SystemOfRecordConnectorConfig.last_tested_at.is_not(None),
        ),
    )
    mcp_binding = db.execute(
        select(McpUpstreamBinding).where(McpUpstreamBinding.project_id == tenant_id)
    ).scalar_one_or_none()
    pilot_policy = db.execute(
        select(PilotPolicy).where(PilotPolicy.project_id == tenant_id)
    ).scalar_one_or_none()
    try:
        policy_payload = json.loads(pilot_policy.policy_json) if pilot_policy else {}
    except (json.JSONDecodeError, TypeError):
        policy_payload = {}
    max_active_agents = resolve_agent_profile_limit(db, project_id=tenant_id)
    key_rows: Sequence[ApiKey] = []
    if ROLE_RANK.get(context.role, 0) >= ROLE_RANK["admin"]:
        key_rows = db.execute(
            select(ApiKey).where(ApiKey.project_id == tenant_id).order_by(ApiKey.created_at.desc())
        ).scalars().all()
    else:
        sources.api_keys = False

    try:
        billing_usage = get_billing_usage(request=request, tenant_id=tenant_id, db=db)
    except Exception:
        billing_usage = None
        sources.billing_usage = False

    data = HomeSummaryData(
        intents=[
            _dump(_intent_response(db, row))
            for row in list_action_intents(db, project_id=tenant_id, limit=75, offset=0)
        ],
        approvals=[
            _dump(_decision_to_response(row))
            for row in db.execute(
                select(RuntimePolicyDecision)
                .where(
                    RuntimePolicyDecision.project_id == tenant_id,
                    RuntimePolicyDecision.status == "pending_approval",
                )
                .order_by(RuntimePolicyDecision.created_at.desc())
                .limit(100)
            ).scalars().all()
        ],
        outcomes=[
            _dump(_serialize_reconciliation(row))
            for row in list_reconciliations(db, project_id=tenant_id, verdict=None, limit=75)
        ],
        outcome_summary=_dump(
            OutcomeReconciliationSummaryResponse(
                window_days=outcome_summary.window_days,
                total=outcome_summary.total,
                matched=outcome_summary.matched,
                mismatched=outcome_summary.mismatched,
                not_verified=outcome_summary.not_verified,
                verified=outcome_summary.verified,
                pending=outcome_summary.pending,
                unverifiable=outcome_summary.unverifiable,
                partial=outcome_summary.partial,
                cancelled=outcome_summary.cancelled,
            )
        ),
        source_summary=_dump(SourceMutationSummaryResponse(**source_summary)),
        mutations=[
            _dump(_serialize_source_mutation(row))
            for row in list_source_mutations(
                db,
                project_id=tenant_id,
                unreceipted_only=True,
                limit=75,
            )
        ],
        stale_attempts=[
            _dump(_execution_attempt_response(row))
            for row in list_project_execution_attempts(
                db,
                project_id=tenant_id,
                statuses=["planned", "running"],
                stale=True,
                stale_after_seconds=600,
                limit=75,
                offset=0,
            )
        ],
        agent_profiles=agent_payloads,
        agent_profile_meta=HomeAgentProfileMeta(
            active_count=active_agent_count,
            max_active_agents=max_active_agents,
            limit_reached=max_active_agents >= 0 and active_agent_count >= max_active_agents,
        ),
        action_runners=[_dump(_runner_response(row)) for row in runner_rows],
        api_keys=[_dump(_api_key_to_response(row)) for row in key_rows],
        billing_usage=_dump(billing_usage) if billing_usage is not None else None,
        control_health=HomeControlHealth(
            active_agents=active_agent_count,
            policy_enforced_agents=policy_enforced_agents,
            configured_action_packs=configured_action_packs,
            online_runners=online_runners,
            active_sor_connectors=active_sor_connectors,
            tested_sor_connectors=tested_sor_connectors,
            mcp_gateway_status=mcp_binding.status if mcp_binding else "not_configured",
            mcp_gateway_test_status=mcp_binding.test_status if mcp_binding else "not_tested",
            runtime_enabled=bool(policy_payload.get("runtime_enabled", True)),
            kill_switch_enabled=bool(policy_payload.get("kill_switch", False)),
        ),
    )

    return HomeSummaryResponse(
        project_id=tenant_id,
        window_days=days,
        window_start=since,
        generated_at=now,
        metrics=HomeSummaryMetrics(
            controlled_actions=controlled_actions,
            pending_approvals=pending_approvals,
            verified_outcomes=verified_outcomes,
            outcome_checks=outcome_checks,
            receipts_generated=receipts_generated,
            bypass_mutations=bypass_mutations,
            unreceipted_mutations=unreceipted_mutations,
            sequence_risks=sequence_risks,
        ),
        sources=sources,
        data=data,
    )
