from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services._action_pack_definitions_expansion import (
    DATA_OPS_PACK,
    FINANCE_OPS_PACK,
    OUTREACH_OPS_PACK,
)
from app.services._action_pack_definitions_primary import (
    DEVOPS_PACK,
    ECOMMERCE_OPS_PACK,
    SUPPORT_OPS_PACK,
)
from app.services._action_pack_types import (
    ActionContractTemplate,
    ActionPackDefinition,
    ActionPackNotFound,
)
from app.services.action_kernel import RegisteredActionContract, register_action_contract


ACTION_PACKS: tuple[ActionPackDefinition, ...] = (
    SUPPORT_OPS_PACK,
    DEVOPS_PACK,
    ECOMMERCE_OPS_PACK,
    FINANCE_OPS_PACK,
    OUTREACH_OPS_PACK,
    DATA_OPS_PACK,
)


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
        "quickstart_steps": list(pack.quickstart_steps),
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
