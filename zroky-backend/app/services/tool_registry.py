from __future__ import annotations

from app.db.models import Agent
from app.services.agent_profiles import SCHEMA_VERSION, json_list
from app.services._tool_registry_native import NATIVE_TOOL_FAMILIES
from app.services._tool_registry_runtime import RUNTIME_PATHS
from app.services._tool_registry_types import (
    ALL_LAUNCH_ACTION_TYPES,
    ImplementationStatus,
    LaunchTier,
    RegistryKind,
    ToolRegistryItem,
)
from app.services._tool_registry_verification import VERIFICATION_CONNECTORS


def serialize_registry_item(item: ToolRegistryItem) -> dict[str, object]:
    return {
        "id": item.id,
        "kind": item.kind,
        "label": item.label,
        "description": item.description,
        "category": item.category,
        "phase": "phase1",
        "implementation_status": item.implementation_status,
        "launch_tier": item.launch_tier,
        "supported_action_types": list(item.supported_action_types),
        "recommended_for_action_types": list(item.recommended_for_action_types),
        "requires_customer_credentials": item.requires_customer_credentials,
        "dashboard_href": item.dashboard_href,
        "backend_capability": item.backend_capability,
        "availability_notes": item.availability_notes,
    }


def action_types_for_agent(agent: Agent | None, requested_action_type: str | None) -> list[str]:
    if requested_action_type:
        return [requested_action_type.strip().lower()]
    if agent is None:
        return []
    allowed = json_list(getattr(agent, "allowed_action_types_json", None))
    if allowed:
        return [item.lower() for item in allowed]
    return []


def recommendations_for_action_types(action_types: list[str]) -> dict[str, object]:
    action_set = {item.strip().lower() for item in action_types if item.strip()}
    if not action_set:
        return {
            "action_types": [],
            "runtime_path_ids": ["sdk"],
            "verification_connector_ids": ["generic_rest", "webhook_callback"],
            "native_tool_family_ids": [],
            "next_steps": [
                "Define the agent's risky action types.",
                "Start with the SDK wrapper unless the agent cannot use code changes.",
                "Use a generic REST verifier or webhook callback until a native verifier exists.",
            ],
        }

    runtime_ids = ["sdk", "customer_hosted_runner"]
    connector_ids = [
        item.id
        for item in VERIFICATION_CONNECTORS
        if item.launch_tier == "p0"
        and action_set.intersection(item.recommended_for_action_types or item.supported_action_types)
    ]
    native_ids = [
        item.id
        for item in NATIVE_TOOL_FAMILIES
        if item.implementation_status != "planned"
        and action_set.intersection(item.recommended_for_action_types)
    ]
    if not connector_ids:
        connector_ids = ["generic_rest", "webhook_callback"]

    next_steps = [
        "Wrap this agent's tool call with the SDK or route it through a gateway.",
        "Choose one verifier that can prove the real system outcome.",
        "Run one real action and confirm Evidence Pack status becomes matched, mismatched, or not_verified.",
    ]
    return {
        "action_types": sorted(action_set),
        "runtime_path_ids": runtime_ids,
        "verification_connector_ids": _dedupe(connector_ids),
        "native_tool_family_ids": _dedupe(native_ids),
        "next_steps": next_steps,
    }


def build_tool_registry(agent: Agent | None = None, requested_action_type: str | None = None) -> dict[str, object]:
    action_types = action_types_for_agent(agent, requested_action_type)
    return {
        "schema_version": SCHEMA_VERSION,
        "agent_id": agent.id if agent is not None else None,
        "action_type": requested_action_type,
        "runtime_paths": [serialize_registry_item(item) for item in RUNTIME_PATHS],
        "verification_connectors": [serialize_registry_item(item) for item in VERIFICATION_CONNECTORS],
        "native_tool_families": [serialize_registry_item(item) for item in NATIVE_TOOL_FAMILIES],
        "recommended": recommendations_for_action_types(action_types),
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out
