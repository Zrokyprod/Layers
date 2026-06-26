from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.services.action_kernel import RegisteredActionContract, register_action_contract


class ActionPackNotFound(ValueError):
    pass


@dataclass(frozen=True)
class ActionContractTemplate:
    contract_key: str
    version: str
    action_type: str
    operation_kind: str
    domain_family: str
    risk_class: str
    connector_family: str
    schema: Mapping[str, Any]
    verification_profile: Mapping[str, Any]


@dataclass(frozen=True)
class ActionPackDefinition:
    id: str
    display_name: str
    summary: str
    primary_runtime_path: str
    recommended_connectors: tuple[str, ...]
    native_tool_families: tuple[str, ...]
    contract_templates: tuple[ActionContractTemplate, ...]
    dashboard_href: str = "/agents"


SUPPORT_OPS_PACK = ActionPackDefinition(
    id="support-ops-v1",
    display_name="Support operations",
    summary=(
        "Guard customer refunds and customer-record updates with approval, "
        "source-of-record verification, and evidence packs."
    ),
    primary_runtime_path="sdk",
    recommended_connectors=("ledger_refund", "crm_record", "generic_rest", "slack_approval_alert"),
    native_tool_families=("stripe_refund", "razorpay_refund", "hubspot_customer", "salesforce_customer"),
    contract_templates=(
        ActionContractTemplate(
            contract_key="customer.refund.transfer",
            version="1.0",
            action_type="refund",
            operation_kind="TRANSFER",
            domain_family="customer_operations",
            risk_class="R3",
            connector_family="ledger_refund",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["refund_id"],
                        "properties": {
                            "refund_id": {"type": "string", "minLength": 1},
                            "order_id": {"type": "string"},
                            "customer_id": {"type": "string"},
                            "account_id": {"type": "string"},
                            "provider": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["amount_minor", "currency"],
                        "properties": {
                            "amount_minor": {"type": "integer", "minimum": 1},
                            "currency": {"type": "string", "minLength": 3, "maxLength": 3},
                            "reason": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V4",
                "source_of_record": "ledger_refund",
                "positive_assertions": [
                    "equals(refund_id)",
                    "equals(amount_minor)",
                    "equals(currency)",
                    "one_of(status, posted, succeeded, captured)",
                ],
                "approval_policy": "dashboard_or_slack_required_for_r3",
            },
        ),
        ActionContractTemplate(
            contract_key="customer.record.update",
            version="1.0",
            action_type="customer_record_update",
            operation_kind="UPDATE",
            domain_family="customer_operations",
            risk_class="R2",
            connector_family="crm_record",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["customer_id"],
                        "properties": {
                            "customer_id": {"type": "string", "minLength": 1},
                            "account_id": {"type": "string"},
                            "crm_object": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["fields"],
                        "properties": {
                            "fields": {
                                "type": "object",
                                "minProperties": 1,
                                "additionalProperties": True,
                            },
                            "reason": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V3",
                "source_of_record": "crm_record",
                "positive_assertions": [
                    "equals(customer_id)",
                    "equals(updated_fields)",
                    "record_updated_after(action_created_at)",
                ],
                "approval_policy": "dashboard_required_when_sensitive_fields_change",
            },
        ),
    ),
)


DEVOPS_PACK = ActionPackDefinition(
    id="devops-release-v1",
    display_name="DevOps release control",
    summary=(
        "Guard deploy or infrastructure changes with CI verification, "
        "human approval, and auditable evidence."
    ),
    primary_runtime_path="sdk",
    recommended_connectors=("github_ci", "generic_rest", "slack_approval_alert"),
    native_tool_families=("github_pr_ci_deploy",),
    contract_templates=(
        ActionContractTemplate(
            contract_key="devops.deploy.change",
            version="1.0",
            action_type="deploy_change",
            operation_kind="DEPLOY",
            domain_family="devops",
            risk_class="R4",
            connector_family="github_ci",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["repository", "environment"],
                        "properties": {
                            "repository": {"type": "string", "minLength": 1},
                            "environment": {"type": "string", "minLength": 1},
                            "pull_request": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["head_sha"],
                        "properties": {
                            "head_sha": {"type": "string", "minLength": 7},
                            "base_sha": {"type": "string"},
                            "change_summary": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V4",
                "source_of_record": "github_ci",
                "positive_assertions": [
                    "ci_checks_passed(head_sha)",
                    "deployment_environment_matches(environment)",
                    "approval_linked_before_deploy",
                ],
                "approval_policy": "dashboard_or_slack_required_for_r4",
            },
        ),
    ),
)


ACTION_PACKS: tuple[ActionPackDefinition, ...] = (SUPPORT_OPS_PACK, DEVOPS_PACK)


def _template_to_dict(template: ActionContractTemplate) -> dict[str, Any]:
    return {
        "contract_key": template.contract_key,
        "version": template.version,
        "contract_version": f"{template.contract_key}/{template.version}",
        "action_type": template.action_type,
        "operation_kind": template.operation_kind,
        "domain_family": template.domain_family,
        "risk_class": template.risk_class,
        "connector_family": template.connector_family,
        "schema": dict(template.schema),
        "verification_profile": dict(template.verification_profile),
    }


def action_pack_to_dict(pack: ActionPackDefinition) -> dict[str, Any]:
    return {
        "id": pack.id,
        "display_name": pack.display_name,
        "summary": pack.summary,
        "primary_runtime_path": pack.primary_runtime_path,
        "recommended_connectors": list(pack.recommended_connectors),
        "native_tool_families": list(pack.native_tool_families),
        "dashboard_href": pack.dashboard_href,
        "contract_templates": [
            _template_to_dict(template) for template in pack.contract_templates
        ],
    }


def list_action_packs() -> list[ActionPackDefinition]:
    return list(ACTION_PACKS)


def get_action_pack(pack_id: str) -> ActionPackDefinition:
    normalized = pack_id.strip().lower()
    for pack in ACTION_PACKS:
        if pack.id == normalized:
            return pack
    raise ActionPackNotFound("Action pack not found.")


def install_action_pack(
    db: Session,
    *,
    project_id: str,
    pack_id: str,
    created_by_subject: str | None,
) -> tuple[ActionPackDefinition, list[RegisteredActionContract]]:
    pack = get_action_pack(pack_id)
    results: list[RegisteredActionContract] = []
    for template in pack.contract_templates:
        results.append(
            register_action_contract(
                db,
                project_id=project_id,
                contract_key=template.contract_key,
                version=template.version,
                action_type=template.action_type,
                operation_kind=template.operation_kind,
                domain_family=template.domain_family,
                schema=template.schema,
                risk_class=template.risk_class,
                verification_profile=template.verification_profile,
                connector_family=template.connector_family,
                created_by_subject=created_by_subject,
            )
        )
    return pack, results
