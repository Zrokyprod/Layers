from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes._internal.owner_money_path import (
    FINAL_READINESS_COMMANDS,
    PRODUCT_STANDARD,
)
from app.api.routes._internal.owner_money_path_schemas import (
    OwnerLaunchGateEvidence,
    OwnerLaunchReadinessGate,
    OwnerLaunchReadinessResponse,
    OwnerMoneyPathHealthResponse,
)
from app.core.config import get_settings
from app.core.config_validation import _looks_like_ed25519_private_key
from app.db.models import (
    FinalAssurancePack,
    FinalOutcomeGraph,
    FinalOutcomeIncident,
    FinalPolicyDecision,
    FinalRecoveryPlan,
    FinalSourceConnector,
    FinalWorkflowIntent,
    RuntimePolicyDecision,
)


def _evidence(
    label: str,
    value: str | int | float | bool | None,
    *,
    status: str | None = None,
    detail: str | None = None,
) -> OwnerLaunchGateEvidence:
    return OwnerLaunchGateEvidence(
        label=label,
        value=value,
        status=status,
        detail=detail,
    )


def _gate(
    *,
    code: str,
    title: str,
    summary: str,
    blockers: list[str],
    missing: list[str] | None = None,
    evidence: list[OwnerLaunchGateEvidence],
    verification_commands: list[str],
) -> OwnerLaunchReadinessGate:
    missing = missing or []
    status = "fail" if blockers else ("not_verified" if missing else "pass")
    return OwnerLaunchReadinessGate(
        code=code,
        title=title,
        status=status,
        summary=summary,
        blockers=blockers + missing,
        evidence=evidence,
        verification_commands=verification_commands,
    )


def _count(db: Session, model: type, *conditions: object) -> int:
    return int(db.scalar(select(func.count(model.id)).where(*conditions)) or 0)


def build_launch_readiness(
    db: Session,
    *,
    money_path: OwnerMoneyPathHealthResponse,
) -> OwnerLaunchReadinessResponse:
    now = datetime.now(UTC)
    since = now - timedelta(days=7)
    settings = get_settings()
    gates: list[OwnerLaunchReadinessGate] = []

    active_packs = _count(db, FinalAssurancePack, FinalAssurancePack.status == "active")
    active_connectors = _count(db, FinalSourceConnector, FinalSourceConnector.status == "active")
    bound_contract_projects = int(
        db.scalar(
            select(func.count(func.distinct(FinalAssurancePack.project_id)))
            .select_from(FinalAssurancePack)
            .join(
                FinalSourceConnector,
                (FinalSourceConnector.project_id == FinalAssurancePack.project_id)
                & (FinalSourceConnector.environment == FinalAssurancePack.environment),
            )
            .where(
                FinalAssurancePack.status == "active",
                FinalSourceConnector.status == "active",
            )
        )
        or 0
    )
    recent_intents = _count(db, FinalWorkflowIntent, FinalWorkflowIntent.created_at >= since)
    contract_missing = []
    if active_packs == 0:
        contract_missing.append("active_assurance_pack_missing")
    if active_connectors == 0:
        contract_missing.append("active_source_connector_missing")
    if bound_contract_projects == 0:
        contract_missing.append("bound_proof_contract_missing")
    if recent_intents == 0:
        contract_missing.append("recent_intent_missing")
    gates.append(
        _gate(
            code="workflow_proof_contracts",
            title="Workflow Proof Contracts",
            summary="Active assurance packs and read-only source connectors must turn agent intents into verifiable workflows.",
            blockers=[],
            missing=contract_missing,
            evidence=[
                _evidence("active_assurance_packs", active_packs),
                _evidence("active_source_connectors", active_connectors),
                _evidence("projects_with_bound_proof_contracts", bound_contract_projects),
                _evidence("intents_7d", recent_intents),
            ],
            verification_commands=[
                "python -m pytest tests/test_final_intents_api.py tests/test_final_outcome_graph.py -q",
            ],
        )
    )

    workflow_decisions = _count(db, FinalPolicyDecision, FinalPolicyDecision.decided_at >= since)
    protected_action_decisions = _count(
        db,
        RuntimePolicyDecision,
        RuntimePolicyDecision.created_at >= since,
    )
    workflow_stops = _count(
        db,
        FinalPolicyDecision,
        FinalPolicyDecision.decided_at >= since,
        FinalPolicyDecision.decision.in_(("deny", "approval_required")),
    )
    protected_action_stops = _count(
        db,
        RuntimePolicyDecision,
        RuntimePolicyDecision.created_at >= since,
        RuntimePolicyDecision.decision.in_(("block", "requires_approval")),
    )
    recent_decisions = workflow_decisions + protected_action_decisions
    stopped_decisions = workflow_stops + protected_action_stops
    policy_missing = []
    if recent_decisions == 0:
        policy_missing.append("runtime_policy_decision_missing")
    if stopped_decisions == 0:
        policy_missing.append("runtime_hold_or_block_proof_missing")
    gates.append(
        _gate(
            code="runtime_policy_control",
            title="Runtime Policy Control",
            summary="The live action path must prove that risky actions can be held for approval or denied before execution.",
            blockers=[],
            missing=policy_missing,
            evidence=[
                _evidence("policy_decisions_7d", recent_decisions),
                _evidence("held_or_denied_7d", stopped_decisions),
                _evidence("protected_action_decisions_7d", protected_action_decisions),
                _evidence("workflow_policy_decisions_7d", workflow_decisions),
            ],
            verification_commands=[
                "python -m pytest tests/test_runtime_policy_gate.py tests/test_final_intents_api.py -q",
            ],
        )
    )

    recent_graphs = _count(db, FinalOutcomeGraph, FinalOutcomeGraph.created_at >= since)
    verified_graphs = _count(
        db,
        FinalOutcomeGraph,
        FinalOutcomeGraph.created_at >= since,
        FinalOutcomeGraph.classification == "verified",
    )
    caught_graphs = _count(
        db,
        FinalOutcomeGraph,
        FinalOutcomeGraph.created_at >= since,
        FinalOutcomeGraph.classification.in_(("wrong", "missing", "forbidden", "duplicate")),
    )
    pending_graphs = _count(
        db,
        FinalOutcomeGraph,
        FinalOutcomeGraph.created_at >= since,
        FinalOutcomeGraph.classification.in_(("pending", "unknown")),
    )
    outcome_missing = []
    if recent_graphs == 0:
        outcome_missing.append("outcome_graph_missing")
    if verified_graphs == 0:
        outcome_missing.append("verified_outcome_proof_missing")
    gates.append(
        _gate(
            code="outcome_verification",
            title="Outcome Verification",
            summary="System-of-record proof, not agent output, must decide whether an action succeeded.",
            blockers=[],
            missing=outcome_missing,
            evidence=[
                _evidence("outcome_graphs_7d", recent_graphs),
                _evidence("verified_7d", verified_graphs),
                _evidence("caught_7d", caught_graphs),
                _evidence("pending_or_unknown_7d", pending_graphs),
            ],
            verification_commands=[
                "python -m pytest tests/test_final_outcome_graph_ledger.py tests/test_final_outcome_graph.py -q",
            ],
        )
    )

    incidents = _count(db, FinalOutcomeIncident, FinalOutcomeIncident.created_at >= since)
    unresolved_incidents = _count(
        db,
        FinalOutcomeIncident,
        FinalOutcomeIncident.created_at >= since,
        FinalOutcomeIncident.status.in_(("open", "recovering", "unresolved")),
    )
    successful_plans = _count(
        db,
        FinalRecoveryPlan,
        FinalRecoveryPlan.created_at >= since,
        FinalRecoveryPlan.execution_status == "succeeded",
    )
    proven_recoveries = int(
        db.scalar(
            select(func.count(func.distinct(FinalOutcomeIncident.id)))
            .select_from(FinalOutcomeIncident)
            .join(FinalRecoveryPlan, FinalRecoveryPlan.incident_id == FinalOutcomeIncident.id)
            .join(FinalOutcomeGraph, FinalOutcomeGraph.id == FinalOutcomeIncident.outcome_graph_id)
            .where(
                FinalOutcomeIncident.created_at >= since,
                FinalOutcomeIncident.status == "resolved",
                FinalOutcomeIncident.resolved_at.is_not(None),
                FinalRecoveryPlan.execution_status == "succeeded",
                FinalOutcomeGraph.classification == "verified",
            )
        )
        or 0
    )
    recovery_missing = []
    if incidents == 0:
        recovery_missing.append("actionable_incident_missing")
    if successful_plans == 0:
        recovery_missing.append("successful_recovery_missing")
    if proven_recoveries == 0:
        recovery_missing.append("proof_resolved_incident_missing")
    gates.append(
        _gate(
            code="proof_driven_recovery",
            title="Proof-driven Recovery",
            summary="Recovery succeeds only when fresh system-of-record proof resolves the incident.",
            blockers=[],
            missing=recovery_missing,
            evidence=[
                _evidence("incidents_7d", incidents),
                _evidence("successful_recovery_plans_7d", successful_plans),
                _evidence("proof_resolved_incidents_7d", proven_recoveries),
                _evidence("currently_unresolved_incidents", unresolved_incidents),
            ],
            verification_commands=[
                "python -m pytest tests/test_final_intents_api.py -k recovery -q",
            ],
        )
    )

    signing_ready = _looks_like_ed25519_private_key(settings.ACTION_RECEIPT_ED25519_PRIVATE_KEY)
    evidence_missing = []
    if not signing_ready:
        evidence_missing.append("attestation_signing_key_missing")
    if verified_graphs == 0:
        evidence_missing.append("attestable_verified_graph_missing")
    gates.append(
        _gate(
            code="signed_evidence",
            title="Signed Evidence",
            summary="Verified outcomes must be exportable as independently verifiable Ed25519 DSSE attestations.",
            blockers=[],
            missing=evidence_missing,
            evidence=[
                _evidence("attestation_signing_configured", signing_ready),
                _evidence("attestable_verified_graphs_7d", verified_graphs),
            ],
            verification_commands=[
                "python -m pytest tests/test_final_outcome_graph_ledger.py -k 'attestation or evidence_export' -q",
            ],
        )
    )

    provider_verification = money_path.platform.billing_provider_verification
    billing_blockers = []
    if not settings.BILLING_ENABLED:
        billing_blockers.append("billing_disabled")
    if provider_verification.state != "verified":
        billing_blockers.append("billing_provider_unverified")
    gates.append(
        _gate(
            code="billing",
            title="Billing",
            summary="Paid launch requires enabled billing and one successfully applied provider event.",
            blockers=billing_blockers,
            evidence=[
                _evidence("billing_enabled", settings.BILLING_ENABLED),
                _evidence(
                    "billing_provider_verification",
                    provider_verification.state,
                    detail=provider_verification.detail,
                ),
            ],
            verification_commands=[
                "python -m pytest tests/test_billing_v2.py tests/test_owner_money_path_health.py -q",
            ],
        )
    )

    paid_launch_allowed = all(gate.status == "pass" for gate in gates)
    hard_blockers = [
        f"{gate.code}:{blocker}"
        for gate in gates
        for blocker in gate.blockers
    ]
    return OwnerLaunchReadinessResponse(
        generated_at=now,
        product_standard=PRODUCT_STANDARD,
        overall_status="pass" if paid_launch_allowed else "blocked",
        paid_launch_allowed=paid_launch_allowed,
        gates=gates,
        hard_blockers=hard_blockers,
        verification_commands=FINAL_READINESS_COMMANDS,
    )
