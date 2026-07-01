from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Agent, Project
from app.services import entitlements_resolver
from app.services.action_runner import ActionRunnerError, register_action_runner
from app.services.pilot import get_or_create_policy, parse_policy_json, upsert_policy


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
    "stripe_refund",
    "razorpay_refund",
    "crm_record",
    "hubspot_crm",
    "salesforce_crm",
    "zoho_crm",
    "zendesk_ticket",
    "jira_issue",
    "netsuite_finance",
    "ticket_status",
    "email_delivery",
    "github_ci",
}

ACTION_TYPE_OPERATION_KINDS = {
    "refund": "TRANSFER",
    "payment_adjustment": "TRANSFER",
    "invoice_spend_approval": "TRANSFER",
    "customer_record_update": "UPDATE",
    "ticket_close": "UPDATE",
    "database_record_update": "UPDATE",
    "internal_api_mutation": "UPDATE",
    "email_send": "SEND",
    "deploy_change": "EXECUTE",
    "custom": "EXECUTE",
}


class AgentProfileConflict(ValueError):
    pass


class AgentProfileNotFound(ValueError):
    pass


class AgentProfileValidationError(ValueError):
    pass


class AgentProfileLimitExceeded(ValueError):
    def __init__(self, *, count: int, limit: int) -> None:
        self.count = count
        self.limit = limit
        super().__init__(
            f"Agent limit reached for this plan ({count}/{limit}). Upgrade to add more agents."
        )


class AgentProfileMandateError(ValueError):
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


def count_active_agent_profiles(db: Session, *, project_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Agent)
            .where(Agent.project_id == project_id, Agent.is_active.is_(True))
        )
        or 0
    )


def resolve_agent_profile_limit(db: Session, *, project_id: str) -> int:
    raw = entitlements_resolver.get(db, project_id, "agents.max", default=1)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


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

    _assert_agent_capacity(db, project_id=project_id)

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


def _assert_agent_capacity(
    db: Session,
    *,
    project_id: str,
    excluding_id: str | None = None,
) -> None:
    limit = resolve_agent_profile_limit(db, project_id=project_id)
    if limit == -1:
        return

    _lock_project_for_agent_capacity(db, project_id=project_id)

    count_query = (
        select(func.count())
        .select_from(Agent)
        .where(Agent.project_id == project_id, Agent.is_active.is_(True))
    )
    if excluding_id is not None:
        count_query = count_query.where(Agent.id != excluding_id)

    active_count = int(db.scalar(count_query) or 0)
    if active_count >= limit:
        raise AgentProfileLimitExceeded(count=active_count, limit=limit)


def _lock_project_for_agent_capacity(db: Session, *, project_id: str) -> None:
    stmt = select(Project.id).where(Project.id == project_id)
    bind = db.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update()
    db.execute(stmt).scalar_one_or_none()


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


def apply_agent_setup_mandate(
    db: Session,
    *,
    project_id: str,
    agent_id: str,
    actor_subject: str | None = None,
) -> Agent:
    row = get_agent_profile(db, project_id=project_id, agent_id=agent_id)
    if row is None:
        raise AgentProfileNotFound("Agent profile not found.")
    if not row.is_active:
        raise AgentProfileMandateError("Inactive agent profiles cannot enforce runtime policy.")

    profile = agent_profile_to_dict(row)
    risk_limits = profile["risk_limits"]
    allowed_action_types = list(profile["allowed_action_types"])
    tool_names = list(profile["tool_names"])
    if not allowed_action_types and not tool_names:
        raise AgentProfileMandateError("Add at least one protected action type or tool before enforcing policy.")
    if not allowed_action_types:
        raise AgentProfileMandateError("Add at least one protected action type before registering a runner.")

    current_policy = parse_policy_json(get_or_create_policy(db, project_id=project_id).policy_json)
    approval_threshold = _numeric_limit(
        risk_limits,
        "approval_required_above_usd",
        fallback=current_policy.get("runtime_amount_approval_threshold_usd"),
        minimum=0,
    )
    deny_threshold = _numeric_limit(
        risk_limits,
        "deny_above_usd",
        fallback=current_policy.get("runtime_amount_deny_threshold_usd"),
        minimum=0,
    )
    ttl_minutes = _integer_limit(
        risk_limits,
        "approval_ttl_minutes",
        fallback=current_policy.get("runtime_approval_ttl_minutes"),
        minimum=1,
    )
    if (
        approval_threshold is not None
        and deny_threshold is not None
        and deny_threshold <= approval_threshold
    ):
        raise AgentProfileMandateError("deny_above_usd must be greater than approval_required_above_usd.")

    agent_runtime_allowlist = _runtime_policy_allowlist(allowed_action_types=allowed_action_types, tool_names=tool_names)
    runtime_allowlist = _merge_string_lists(
        current_policy.get("runtime_allowed_tools"),
        agent_runtime_allowlist,
    )
    sensitive_tools = _merge_string_lists(
        current_policy.get("runtime_sensitive_tools"),
        agent_runtime_allowlist,
    )

    next_policy = {
        **current_policy,
        "runtime_enabled": True,
        "runtime_allowed_tools": runtime_allowlist,
        "runtime_sensitive_tools": sensitive_tools,
        "runtime_sensitive_actions_require_approval": True,
        "runtime_amount_approval_threshold_usd": approval_threshold,
        "runtime_amount_deny_threshold_usd": deny_threshold,
        "runtime_max_cost_usd": deny_threshold if deny_threshold is not None else current_policy.get("runtime_max_cost_usd"),
        "runtime_approval_ttl_minutes": ttl_minutes,
        "runtime_changed_recipient_deny": True,
    }
    policy = upsert_policy(
        db,
        project_id=project_id,
        payload=next_policy,
        updated_by=actor_subject,
    )
    runner_mode = _runner_mode(profile["metadata"])
    runner_type = "managed_sandbox" if runner_mode == "managed" else "customer_hosted"
    supported_operation_kinds = _operation_kinds_for_action_types(allowed_action_types)
    runner_name = f"{profile['slug']}-runner"
    runner_environment = str(profile.get("environment") or "production").strip() or "production"
    credential_ref = _credential_ref(profile["metadata"])
    try:
        registered_runner = register_action_runner(
            db,
            project_id=project_id,
            name=runner_name,
            runner_type=runner_type,
            environment=runner_environment,
            supported_operation_kinds=supported_operation_kinds,
            credential_scope={"credential_ref": credential_ref},
            capability_version="agent-setup.v1",
            registered_by_subject=actor_subject,
        )
    except ActionRunnerError as exc:
        raise AgentProfileMandateError(str(exc)) from exc
    runner = registered_runner.row
    if runner_type == "managed_sandbox":
        runner.status = "online"
        runner.last_heartbeat_at = datetime.now(timezone.utc)
        runner.heartbeat_payload_json = json_dumps(
            {
                "source": "agent_setup_mandate",
                "managed_by": "zroky",
            }
        )
        db.add(runner)

    enforced_at = datetime.now(timezone.utc).isoformat()
    metadata = dict(profile["metadata"])
    metadata["protection_state"] = "enforced"
    metadata["runtime_policy_mandate_enforced"] = True
    metadata["runtime_policy_mandate"] = {
        "scope": "project",
        "policy_id": policy.id,
        "policy_store": "pilot_policies.policy_json",
        "enforced_at": enforced_at,
        "enforced_by": actor_subject,
        "runner_id": runner.id,
        "runner_name": runner.name,
        "runner_type": runner.runner_type,
        "runner_environment": runner.environment,
        "runner_supported_operation_kinds": supported_operation_kinds,
        "runner_credential_ref": credential_ref,
        "agent_runtime_allowed_tools": agent_runtime_allowlist,
        "project_runtime_allowed_tools": runtime_allowlist,
        "runtime_amount_approval_threshold_usd": approval_threshold,
        "runtime_amount_deny_threshold_usd": deny_threshold,
        "runtime_max_cost_usd": next_policy["runtime_max_cost_usd"],
        "runtime_approval_ttl_minutes": ttl_minutes,
    }
    _remove_legacy_readiness_metadata(metadata)
    row.metadata_json = json_dumps(metadata)
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


def _numeric_limit(
    source: Mapping[str, Any],
    key: str,
    *,
    fallback: Any,
    minimum: float,
) -> float | None:
    value = source.get(key, fallback)
    if value is None:
        return None
    if isinstance(value, bool):
        raise AgentProfileMandateError(f"{key} must be a number.")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise AgentProfileMandateError(f"{key} must be a number.") from exc
    if parsed < minimum:
        raise AgentProfileMandateError(f"{key} must be at least {minimum}.")
    return parsed


def _integer_limit(
    source: Mapping[str, Any],
    key: str,
    *,
    fallback: Any,
    minimum: int,
) -> int:
    value = source.get(key, fallback)
    if isinstance(value, bool):
        raise AgentProfileMandateError(f"{key} must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AgentProfileMandateError(f"{key} must be an integer.") from exc
    if parsed < minimum:
        raise AgentProfileMandateError(f"{key} must be at least {minimum}.")
    return parsed


def _runtime_policy_allowlist(*, allowed_action_types: list[str], tool_names: list[str]) -> list[str]:
    return _merge_string_lists(allowed_action_types, tool_names)


def _operation_kinds_for_action_types(action_types: list[str]) -> list[str]:
    kinds: list[str] = []
    seen: set[str] = set()
    for action_type in action_types:
        kind = ACTION_TYPE_OPERATION_KINDS.get(str(action_type).strip().lower())
        if kind and kind not in seen:
            seen.add(kind)
            kinds.append(kind)
    if not kinds:
        raise AgentProfileMandateError("No runner operation kinds could be derived from allowed action types.")
    return kinds


def _runner_mode(metadata: Mapping[str, Any]) -> str:
    runner = metadata.get("runner_verification")
    if isinstance(runner, Mapping):
        value = str(runner.get("runner_mode") or "").strip()
        if value == "managed":
            return "managed"
    return "customer_hosted"


def _credential_ref(metadata: Mapping[str, Any]) -> str:
    runner = metadata.get("runner_verification")
    if isinstance(runner, Mapping):
        value = str(runner.get("credential_ref") or "").strip()
        if value:
            return value
    raise AgentProfileMandateError("Add a non-secret credential reference before registering a runner.")


def _merge_string_lists(*values: Any) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in values:
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, list):
            candidates = value
        else:
            candidates = []
        for item in candidates:
            text = str(item).strip()
            normalized = text.lower().replace("-", "_")
            if text and normalized not in seen:
                seen.add(normalized)
                merged.append(text)
    return merged


def _remove_legacy_readiness_metadata(metadata: dict[str, Any]) -> None:
    metadata.pop("readiness", None)
    metadata.pop("readiness_preview_completed", None)
    metadata.pop("local_readiness_test_ran", None)
    metadata.pop("receipt_preview_generated", None)
    control_binding = metadata.get("control_binding")
    if isinstance(control_binding, dict):
        control_binding.pop("readiness", None)


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
