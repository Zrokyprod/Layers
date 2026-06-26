from __future__ import annotations

import json
import re
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Agent


SCHEMA_VERSION = "zroky.agent_tool_control.v1"

VALID_RUNTIME_PATHS = {"sdk", "http_gateway", "mcp_gateway", "webhook"}
VALID_RISKY_ACTION_TYPES = {
    "refund",
    "payment_adjustment",
    "invoice_spend_approval",
    "customer_record_update",
    "ticket_close",
    "email_send",
    "deploy_change",
    "internal_api_mutation",
    "database_record_update",
    "custom",
}
VALID_VERIFICATION_CONNECTORS = {
    "generic_rest",
    "webhook_callback",
    "database_read",
    "ledger_refund",
    "crm_record",
    "ticket_status",
    "email_delivery",
    "github_ci",
}


class AgentProfileConflict(ValueError):
    pass


class AgentProfileNotFound(ValueError):
    pass


class AgentProfileValidationError(ValueError):
    pass


def json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def slug_for_agent_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:255] or "unknown-agent"


def normalize_string_list(values: list[str] | None, *, lower: bool = False) -> list[str]:
    if not values:
        return []
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in values:
        text = str(item).strip()
        if lower:
            text = text.lower()
        if text and text not in seen:
            seen.add(text)
            cleaned.append(text)
    return cleaned


def validate_profile_payload(payload: Mapping[str, Any]) -> None:
    runtime_path = str(payload.get("runtime_path") or "sdk").strip().lower()
    if runtime_path not in VALID_RUNTIME_PATHS:
        raise AgentProfileValidationError("runtime_path is not supported.")

    allowed = set(normalize_string_list(payload.get("allowed_action_types"), lower=True))
    blocked = set(normalize_string_list(payload.get("blocked_action_types"), lower=True))
    invalid_actions = sorted((allowed | blocked) - VALID_RISKY_ACTION_TYPES)
    if invalid_actions:
        raise AgentProfileValidationError(
            f"Unsupported action type: {', '.join(invalid_actions)}"
        )

    overlap = sorted(allowed & blocked)
    if overlap:
        raise AgentProfileValidationError(
            f"Action type cannot be both allowed and blocked: {', '.join(overlap)}"
        )

    connectors = set(normalize_string_list(payload.get("verification_connectors"), lower=True))
    invalid_connectors = sorted(connectors - VALID_VERIFICATION_CONNECTORS)
    if invalid_connectors:
        raise AgentProfileValidationError(
            f"Unsupported verification connector: {', '.join(invalid_connectors)}"
        )


def agent_profile_to_dict(row: Agent) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "id": row.id,
        "project_id": row.project_id,
        "display_name": row.name,
        "slug": row.slug,
        "description": row.description,
        "runtime_path": getattr(row, "runtime_path", None) or "sdk",
        "framework": getattr(row, "framework", None),
        "environment": getattr(row, "environment", None),
        "model_provider": getattr(row, "model_provider", None),
        "model_name": getattr(row, "model_name", None),
        "tool_names": json_list(getattr(row, "tool_names_json", None)),
        "allowed_action_types": json_list(getattr(row, "allowed_action_types_json", None)),
        "blocked_action_types": json_list(getattr(row, "blocked_action_types_json", None)),
        "default_policy_id": getattr(row, "default_policy_id", None),
        "risk_limits": json_object(getattr(row, "risk_limits_json", None)),
        "verification_connectors": json_list(getattr(row, "verification_connectors_json", None)),
        "metadata": json_object(getattr(row, "metadata_json", None)),
        "is_active": bool(getattr(row, "is_active", True)),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_agent_profiles(
    db: Session,
    *,
    project_id: str,
    include_inactive: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Agent], int]:
    query = select(Agent).where(Agent.project_id == project_id)
    count_query = select(func.count()).select_from(Agent).where(Agent.project_id == project_id)
    if not include_inactive:
        query = query.where(Agent.is_active.is_(True))
        count_query = count_query.where(Agent.is_active.is_(True))
    rows = (
        db.execute(
            query.order_by(Agent.updated_at.desc(), Agent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    total = int(db.scalar(count_query) or 0)
    return rows, total


def get_agent_profile(db: Session, *, project_id: str, agent_id: str) -> Agent | None:
    return db.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.id == agent_id)
    ).scalar_one_or_none()


def create_agent_profile(
    db: Session,
    *,
    project_id: str,
    payload: Mapping[str, Any],
    actor_subject: str | None = None,
) -> Agent:
    merged = _clean_payload(payload)
    validate_profile_payload(merged)
    display_name = str(merged["display_name"]).strip()
    slug = slug_for_agent_name(display_name)
    existing = db.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.slug == slug)
    ).scalar_one_or_none()
    if existing is not None:
        raise AgentProfileConflict("Agent profile already exists for this name.")

    row = Agent(
        id=str(uuid4()),
        project_id=project_id,
        name=display_name,
        slug=slug,
        description=merged.get("description"),
        created_by_subject=actor_subject,
        updated_by_subject=actor_subject,
    )
    _assign_profile_fields(row, merged)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_agent_profile(
    db: Session,
    *,
    project_id: str,
    agent_id: str,
    payload: Mapping[str, Any],
    actor_subject: str | None = None,
) -> Agent:
    row = get_agent_profile(db, project_id=project_id, agent_id=agent_id)
    if row is None:
        raise AgentProfileNotFound("Agent profile not found.")

    current = agent_profile_to_dict(row)
    merged = {**current, **_clean_payload(payload, partial=True)}
    validate_profile_payload(merged)

    if "display_name" in payload:
        display_name = str(merged["display_name"]).strip()
        slug = slug_for_agent_name(display_name)
        duplicate = db.execute(
            select(Agent).where(
                Agent.project_id == project_id,
                Agent.slug == slug,
                Agent.id != agent_id,
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise AgentProfileConflict("Agent profile already exists for this name.")
        row.name = display_name
        row.slug = slug

    if "description" in payload:
        row.description = merged.get("description")
    row.updated_by_subject = actor_subject
    _assign_profile_fields(row, merged, only=set(payload.keys()))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def deactivate_agent_profile(
    db: Session,
    *,
    project_id: str,
    agent_id: str,
    actor_subject: str | None = None,
) -> Agent:
    row = get_agent_profile(db, project_id=project_id, agent_id=agent_id)
    if row is None:
        raise AgentProfileNotFound("Agent profile not found.")
    row.is_active = False
    row.updated_by_subject = actor_subject
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _clean_payload(payload: Mapping[str, Any], *, partial: bool = False) -> dict[str, Any]:
    cleaned = {key: value for key, value in payload.items() if value is not None}
    if not partial:
        cleaned.setdefault("runtime_path", "sdk")
        cleaned.setdefault("tool_names", [])
        cleaned.setdefault("allowed_action_types", [])
        cleaned.setdefault("blocked_action_types", [])
        cleaned.setdefault("risk_limits", {})
        cleaned.setdefault("verification_connectors", [])
        cleaned.setdefault("metadata", {})
    for key in ("runtime_path", "framework", "environment", "model_provider", "model_name", "default_policy_id"):
        if key in cleaned and isinstance(cleaned[key], str):
            cleaned[key] = cleaned[key].strip() or None
    if "runtime_path" in cleaned and cleaned["runtime_path"]:
        cleaned["runtime_path"] = str(cleaned["runtime_path"]).lower()
    for key in ("allowed_action_types", "blocked_action_types", "verification_connectors"):
        if key in cleaned:
            cleaned[key] = normalize_string_list(cleaned[key], lower=True)
    if "tool_names" in cleaned:
        cleaned["tool_names"] = normalize_string_list(cleaned["tool_names"], lower=False)
    return cleaned


def _assign_profile_fields(
    row: Agent,
    payload: Mapping[str, Any],
    *,
    only: set[str] | None = None,
) -> None:
    def should_assign(key: str) -> bool:
        return only is None or key in only

    if should_assign("runtime_path"):
        row.runtime_path = str(payload.get("runtime_path") or "sdk")
    for attr in ("framework", "environment", "model_provider", "model_name", "default_policy_id"):
        if should_assign(attr):
            setattr(row, attr, payload.get(attr))
    if should_assign("tool_names"):
        row.tool_names_json = json_dumps(payload.get("tool_names") or [])
    if should_assign("allowed_action_types"):
        row.allowed_action_types_json = json_dumps(payload.get("allowed_action_types") or [])
    if should_assign("blocked_action_types"):
        row.blocked_action_types_json = json_dumps(payload.get("blocked_action_types") or [])
    if should_assign("risk_limits"):
        row.risk_limits_json = json_dumps(payload.get("risk_limits") or {})
    if should_assign("verification_connectors"):
        row.verification_connectors_json = json_dumps(payload.get("verification_connectors") or [])
    if should_assign("metadata"):
        row.metadata_json = json_dumps(payload.get("metadata") or {})
