from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Agent, RuntimePolicyRule
from app.services.pilot import DEFAULT_POLICY, get_or_create_policy, parse_policy_json, validate_policy_payload


class RuntimePolicyRuleNotFound(ValueError):
    """Raised when a scoped runtime policy rule does not exist."""


class RuntimePolicyRuleValidationError(ValueError):
    """Raised when a scoped runtime policy rule is invalid."""


RUNTIME_POLICY_RULE_FIELDS = frozenset(
    key for key in DEFAULT_POLICY if key == "kill_switch" or key.startswith("runtime_")
)


@dataclass(frozen=True)
class ResolvedRuntimePolicy:
    policy: dict[str, Any]
    matched_rules: list[dict[str, Any]]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        decoded = json.loads(value)
    except Exception:
        return fallback
    return decoded if isinstance(decoded, type(fallback)) else fallback


def _bounded(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    if not rendered:
        return None
    return rendered[:max_length]


def _normalize(value: Any) -> str | None:
    rendered = _bounded(value, max_length=255)
    if rendered is None:
        return None
    return rendered.strip().lower().replace("-", "_")


def _policy_patch(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimePolicyRuleValidationError("policy_patch must be a JSON object.")
    patch = {key: value for key, value in payload.items() if key in RUNTIME_POLICY_RULE_FIELDS}
    if not patch:
        raise RuntimePolicyRuleValidationError("policy_patch must include at least one supported runtime policy field.")
    candidate = {**DEFAULT_POLICY, **patch}
    sanitised = validate_policy_payload(candidate)
    return {key: sanitised[key] for key in patch}


def _apply_patch(policy: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    candidate = {**policy, **patch}
    return validate_policy_payload(candidate)


def _ensure_agent_scope(db: Session, *, project_id: str, agent_id: str | None) -> None:
    if not agent_id:
        return
    row = db.execute(
        select(Agent).where(
            Agent.project_id == project_id,
            Agent.id == agent_id,
            Agent.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if row is None:
        raise RuntimePolicyRuleValidationError("agent_id must reference an active agent in this project.")


def runtime_policy_rule_to_dict(row: RuntimePolicyRule) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "description": row.description,
        "agent_id": row.agent_id,
        "action_type": row.action_type,
        "environment": row.environment,
        "policy_patch": _json_loads(row.policy_patch_json, {}),
        "priority": row.priority,
        "version": row.version,
        "is_enabled": row.is_enabled,
        "created_by_subject": row.created_by_subject,
        "updated_by_subject": row.updated_by_subject,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_runtime_policy_rules(
    db: Session,
    *,
    project_id: str,
    enabled: bool | None = None,
) -> list[RuntimePolicyRule]:
    query = select(RuntimePolicyRule).where(RuntimePolicyRule.project_id == project_id)
    if enabled is not None:
        query = query.where(RuntimePolicyRule.is_enabled.is_(enabled))
    return list(
        db.execute(
            query.order_by(
                RuntimePolicyRule.agent_id.asc().nullsfirst(),
                RuntimePolicyRule.action_type.asc().nullsfirst(),
                RuntimePolicyRule.environment.asc().nullsfirst(),
                RuntimePolicyRule.priority.asc(),
                RuntimePolicyRule.updated_at.desc(),
            )
        ).scalars()
    )


def create_runtime_policy_rule(
    db: Session,
    *,
    project_id: str,
    name: str,
    policy_patch: dict[str, Any],
    actor: str | None,
    agent_id: str | None = None,
    action_type: str | None = None,
    environment: str | None = None,
    description: str | None = None,
    priority: int = 0,
    is_enabled: bool = True,
) -> RuntimePolicyRule:
    safe_name = _bounded(name, max_length=255)
    if safe_name is None:
        raise RuntimePolicyRuleValidationError("name is required.")
    safe_agent_id = _bounded(agent_id, max_length=36)
    _ensure_agent_scope(db, project_id=project_id, agent_id=safe_agent_id)
    patch = _policy_patch(policy_patch)
    row = RuntimePolicyRule(
        id=str(uuid4()),
        project_id=project_id,
        name=safe_name,
        description=_bounded(description, max_length=2000),
        agent_id=safe_agent_id,
        action_type=_bounded(action_type, max_length=64),
        environment=_bounded(environment, max_length=64),
        policy_patch_json=_json_dumps(patch),
        priority=int(priority),
        version=1,
        is_enabled=bool(is_enabled),
        created_by_subject=_bounded(actor, max_length=255),
        updated_by_subject=_bounded(actor, max_length=255),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_runtime_policy_rule(
    db: Session,
    *,
    project_id: str,
    rule_id: str,
    actor: str | None,
    name: str | None = None,
    policy_patch: dict[str, Any] | None = None,
    agent_id: str | None = None,
    action_type: str | None = None,
    environment: str | None = None,
    description: str | None = None,
    priority: int | None = None,
    is_enabled: bool | None = None,
) -> RuntimePolicyRule:
    row = db.execute(
        select(RuntimePolicyRule).where(
            RuntimePolicyRule.project_id == project_id,
            RuntimePolicyRule.id == rule_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise RuntimePolicyRuleNotFound("Runtime policy rule not found.")

    if name is not None:
        safe_name = _bounded(name, max_length=255)
        if safe_name is None:
            raise RuntimePolicyRuleValidationError("name is required.")
        row.name = safe_name
    if description is not None:
        row.description = _bounded(description, max_length=2000)
    if agent_id is not None:
        safe_agent_id = _bounded(agent_id, max_length=36)
        _ensure_agent_scope(db, project_id=project_id, agent_id=safe_agent_id)
        row.agent_id = safe_agent_id
    if action_type is not None:
        row.action_type = _bounded(action_type, max_length=64)
    if environment is not None:
        row.environment = _bounded(environment, max_length=64)
    if policy_patch is not None:
        row.policy_patch_json = _json_dumps(_policy_patch(policy_patch))
    if priority is not None:
        row.priority = int(priority)
    if is_enabled is not None:
        row.is_enabled = bool(is_enabled)

    row.version = int(row.version or 1) + 1
    row.updated_by_subject = _bounded(actor, max_length=255)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def disable_runtime_policy_rule(
    db: Session,
    *,
    project_id: str,
    rule_id: str,
    actor: str | None,
) -> RuntimePolicyRule:
    return update_runtime_policy_rule(
        db,
        project_id=project_id,
        rule_id=rule_id,
        actor=actor,
        is_enabled=False,
    )


def _rule_matches(row: RuntimePolicyRule, *, agent_id: str | None, action_type: str | None, environment: str | None) -> bool:
    if row.agent_id and row.agent_id != agent_id:
        return False
    if row.action_type and _normalize(row.action_type) != _normalize(action_type):
        return False
    if row.environment and _normalize(row.environment) != _normalize(environment):
        return False
    return True


def _specificity(row: RuntimePolicyRule) -> int:
    score = 0
    if row.action_type:
        score += 10
    if row.environment:
        score += 20
    if row.agent_id:
        score += 40
    return score


def _rule_summary(row: RuntimePolicyRule) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "agent_id": row.agent_id,
        "action_type": row.action_type,
        "environment": row.environment,
        "priority": row.priority,
        "version": row.version,
        "specificity": _specificity(row),
    }


def resolve_runtime_policy(
    db: Session,
    *,
    project_id: str,
    payload: dict[str, Any],
) -> ResolvedRuntimePolicy:
    policy_row = get_or_create_policy(db, project_id=project_id)
    policy = parse_policy_json(policy_row.policy_json)
    agent_id = _bounded(payload.get("agent_id"), max_length=36)
    action_type = _bounded(payload.get("action_type") or payload.get("tool_name"), max_length=64)
    environment = _bounded(payload.get("environment"), max_length=64)

    candidates = list_runtime_policy_rules(db, project_id=project_id, enabled=True)
    matches = [
        row
        for row in candidates
        if _rule_matches(row, agent_id=agent_id, action_type=action_type, environment=environment)
    ]
    matches.sort(
        key=lambda row: (
            _specificity(row),
            int(row.priority or 0),
            row.updated_at or datetime.min,
            row.id,
        )
    )

    matched_rules: list[dict[str, Any]] = []
    action_decision_source_rule_id: str | None = None
    for row in matches:
        patch = _json_loads(row.policy_patch_json, {})
        policy = _apply_patch(policy, patch)
        if "runtime_action_decision" in patch:
            action_decision_source_rule_id = row.id
        matched_rules.append(_rule_summary(row))

    policy["_runtime_policy_resolution"] = {
        "source": "project_policy+scoped_rules" if matched_rules else "project_policy",
        "matched_rules": matched_rules,
        "action_decision_source_rule_id": action_decision_source_rule_id,
    }
    return ResolvedRuntimePolicy(policy=policy, matched_rules=matched_rules)
