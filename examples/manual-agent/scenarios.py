"""Manual QA scenarios for Zroky protected-action testing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mock_tools import (
    change_feature_flag,
    grant_access,
    refund_payment,
    revoke_access,
    send_external_message,
    update_crm_record,
)


@dataclass(frozen=True)
class ActionIntent:
    contract_version: str
    action: str
    operation_kind: str
    domain_family: str
    risk_class: str
    connector_family: str
    params: dict[str, Any]
    resource: dict[str, Any]
    purpose: dict[str, Any]
    verification_profile: str
    mock_result: dict[str, Any]


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    expected_dashboard_modules: tuple[str, ...]
    actions: tuple[ActionIntent, ...]


SCENARIOS: dict[str, Scenario] = {
    "access-grant": Scenario(
        name="access-grant",
        description="Safe customer access grant.",
        expected_dashboard_modules=("Actions", "Outcomes", "Evidence"),
        actions=(
            ActionIntent(
                contract_version="manual.customer.access.grant/1.0",
                action="customer.access.grant",
                operation_kind="UPDATE",
                domain_family="manual_qa",
                risk_class="R2",
                connector_family="mock_access",
                params={"customer_id": "cus_123", "role": "viewer"},
                resource={"type": "customer_access", "id": "cus_123:viewer"},
                purpose={"reason": "Grant limited viewer access for a support workflow."},
                verification_profile="mock-access-role-match",
                mock_result=grant_access("cus_123", "viewer"),
            ),
        ),
    ),
    "access-revoke": Scenario(
        name="access-revoke",
        description="Customer access revocation.",
        expected_dashboard_modules=("Actions", "Outcomes", "Evidence"),
        actions=(
            ActionIntent(
                contract_version="manual.customer.access.revoke/1.0",
                action="customer.access.revoke",
                operation_kind="UPDATE",
                domain_family="manual_qa",
                risk_class="R2",
                connector_family="mock_access",
                params={"customer_id": "cus_123", "role": "viewer"},
                resource={"type": "customer_access", "id": "cus_123:viewer"},
                purpose={"reason": "Remove temporary support access."},
                verification_profile="mock-access-role-match",
                mock_result=revoke_access("cus_123", "viewer"),
            ),
        ),
    ),
    "refund-high": Scenario(
        name="refund-high",
        description="High-value refund that should exercise approval policy.",
        expected_dashboard_modules=("Actions", "Approvals", "Outcomes", "Evidence"),
        actions=(
            ActionIntent(
                contract_version="manual.payment.refund/1.0",
                action="payment.refund",
                operation_kind="EXECUTE",
                domain_family="manual_qa",
                risk_class="R3",
                connector_family="mock_ledger",
                params={"account_id": "acct_881", "amount_minor": 420000, "currency": "USD"},
                resource={"type": "ledger_refund", "id": "acct_881:refund"},
                purpose={"reason": "Manual QA high-value refund hold path."},
                verification_profile="mock-ledger-refund-match",
                mock_result=refund_payment("acct_881", 420000),
            ),
        ),
    ),
    "crm-update": Scenario(
        name="crm-update",
        description="Customer record mutation.",
        expected_dashboard_modules=("Actions", "Outcomes", "Evidence"),
        actions=(
            ActionIntent(
                contract_version="manual.crm.record.update/1.0",
                action="crm.record.update",
                operation_kind="UPDATE",
                domain_family="manual_qa",
                risk_class="R2",
                connector_family="mock_crm",
                params={"customer_id": "cus_123", "field": "tier", "value": "enterprise"},
                resource={"type": "crm_record", "id": "cus_123"},
                purpose={"reason": "Update account tier after contract review."},
                verification_profile="mock-crm-field-match",
                mock_result=update_crm_record("cus_123", "tier", "enterprise"),
            ),
        ),
    ),
    "deploy-change": Scenario(
        name="deploy-change",
        description="Production feature flag change.",
        expected_dashboard_modules=("Actions", "Approvals", "Outcomes", "Evidence"),
        actions=(
            ActionIntent(
                contract_version="manual.production.feature_flag.change/1.0",
                action="production.feature_flag.change",
                operation_kind="UPDATE",
                domain_family="manual_qa",
                risk_class="R4",
                connector_family="mock_deploy",
                params={"flag": "ai_agent_refunds", "enabled": True, "environment": "production"},
                resource={"type": "feature_flag", "id": "ai_agent_refunds"},
                purpose={"reason": "Manual QA production-change path."},
                verification_profile="mock-feature-flag-match",
                mock_result=change_feature_flag("ai_agent_refunds", True),
            ),
        ),
    ),
    "sequence-risk": Scenario(
        name="sequence-risk",
        description="Individually normal actions that form a risky sequence.",
        expected_dashboard_modules=("Actions", "Approvals", "Policies"),
        actions=(
            ActionIntent(
                contract_version="manual.customer.bulk_read/1.0",
                action="customer.bulk_read",
                operation_kind="READ",
                domain_family="manual_qa",
                risk_class="R1",
                connector_family="mock_crm",
                params={"segment": "refund_candidates", "count": 250},
                resource={"type": "customer_segment", "id": "refund_candidates"},
                purpose={"reason": "Read candidates before support action."},
                verification_profile="mock-read-audit",
                mock_result={"mock_system": "mock_crm", "status": "read", "count": 250},
            ),
            ActionIntent(
                contract_version="manual.message.external.send/1.0",
                action="message.external.send",
                operation_kind="EXECUTE",
                domain_family="manual_qa",
                risk_class="R2",
                connector_family="mock_messaging",
                params={"channel": "email", "recipient": "customer@example.com", "template": "refund_followup"},
                resource={"type": "external_message", "id": "customer@example.com"},
                purpose={"reason": "Send customer follow-up."},
                verification_profile="mock-message-audit",
                mock_result=send_external_message("email", "customer@example.com"),
            ),
            ActionIntent(
                contract_version="manual.payment.refund/1.0",
                action="payment.refund",
                operation_kind="EXECUTE",
                domain_family="manual_qa",
                risk_class="R3",
                connector_family="mock_ledger",
                params={"account_id": "acct_881", "amount_minor": 420000, "currency": "USD"},
                resource={"type": "ledger_refund", "id": "acct_881:sequence-refund"},
                purpose={"reason": "Sequence-risk QA: read + message + money movement."},
                verification_profile="mock-ledger-refund-match",
                mock_result=refund_payment("acct_881", 420000),
            ),
        ),
    ),
    "verifier-fail": Scenario(
        name="verifier-fail",
        description="Tool reports success but source-of-record should not match.",
        expected_dashboard_modules=("Actions", "Outcomes"),
        actions=(
            ActionIntent(
                contract_version="manual.customer.access.grant/1.0",
                action="customer.access.grant",
                operation_kind="UPDATE",
                domain_family="manual_qa",
                risk_class="R2",
                connector_family="mock_access",
                params={
                    "customer_id": "cus_mismatch",
                    "role": "admin",
                    "qa_expected_verifier_result": "mismatch",
                },
                resource={"type": "customer_access", "id": "cus_mismatch:admin"},
                purpose={"reason": "Manual QA proof failure path."},
                verification_profile="mock-access-role-mismatch",
                mock_result={"mock_system": "mock_access", "status": "reported_success_but_not_present"},
            ),
        ),
    ),
    "connector-missing": Scenario(
        name="connector-missing",
        description="Action requiring a verifier connector that is not configured.",
        expected_dashboard_modules=("Actions", "Connectors"),
        actions=(
            ActionIntent(
                contract_version="manual.billing.invoice.approve/1.0",
                action="billing.invoice.approve",
                operation_kind="EXECUTE",
                domain_family="manual_qa",
                risk_class="R3",
                connector_family="mock_billing",
                params={"invoice_id": "inv_missing_connector", "amount_minor": 125000, "currency": "USD"},
                resource={"type": "billing_invoice", "id": "inv_missing_connector"},
                purpose={"reason": "Manual QA connector gap path."},
                verification_profile="mock-billing-connector-required",
                mock_result={"mock_system": "mock_billing", "status": "approval_requested"},
            ),
        ),
    ),
}


def scenario_names() -> list[str]:
    return sorted(SCENARIOS)


def get_scenario(name: str) -> Scenario:
    try:
        return SCENARIOS[name]
    except KeyError as exc:
        valid = ", ".join(scenario_names())
        raise ValueError(f"Unknown scenario '{name}'. Use one of: {valid}, all") from exc
