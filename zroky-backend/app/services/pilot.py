"""
Pilot-tier service — autopilot actions + policy (plan §6.3, §13).

Two surfaces backed by migration 0052:

  • `pilot_actions`  — one row per autopilot decision against an anomaly.
                       tier ∈ {1,2,3}, status ∈
                       {pending, applied, reverted, failed, skipped}.
                       Tier-1 actions are reversible by definition.
  • `pilot_policies` — one row per project (UNIQUE on project_id).
                       `policy_json` carries the per-tier configuration
                       (enable flags, allowed action types, min_confidence
                       thresholds, daily caps, kill_switch).

Module 4.3 ships:
  - `list_pilot_actions`, `get_pilot_action`             read paths
  - `revert_pilot_action`                                state transition
  - `get_or_create_policy`, `upsert_policy`              policy CRUD
  - `DEFAULT_POLICY` + `validate_policy_payload`         policy schema guard
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import PilotAction, PilotPolicy

logger = logging.getLogger(__name__)


# ── vocab (must match DB CHECK constraints from migration 0052) ──────────────

VALID_ACTION_STATUSES = frozenset(
    {"pending", "applied", "reverted", "failed", "skipped"}
)
VALID_TIERS = frozenset({1, 2, 3})
REVERTIBLE_TIER = 1  # plan §6.3: only tier-1 actions are reversible


# ── policy schema (plan §6.3 canonical default) ──────────────────────────────

DEFAULT_POLICY: dict[str, Any] = {
    "tier1_enabled": False,
    "tier1_actions": ["model_rollback", "fallback_swap", "retry_tune"],
    "tier1_min_confidence": 0.95,
    "tier1_max_blast_radius": "single_route",
    "tier1_daily_cap": 5,
    "tier2_enabled": False,
    "tier2_actions": ["prompt_revert_pr", "schema_fix_pr", "replay_prompt_fix", "replay_model_fix"],
    "tier2_require_replay_pass": True,
    # Module 10 — per-project Tier-2 daily PR cap. Defaults to None so
    # the dispatcher falls back to the global PILOT_TIER2_DAILY_PR_CAP
    # setting. Set to an int to override (0 = disable Tier-2 entirely
    # without flipping `tier2_enabled` off).
    "tier2_daily_cap": None,
    "tier3_alert_channels": ["email"],
    "kill_switch": False,
    "runtime_enabled": True,
    "runtime_max_tool_calls": 20,
    "runtime_max_retries": 3,
    "runtime_max_cost_usd": 1.0,
    "runtime_allowed_tools": [],
    "runtime_sensitive_tools": [
        "payment",
        "charge",
        "refund",
        "delete",
        "email",
        "send_email",
        "transfer",
        "payout",
    ],
    "runtime_sensitive_actions_require_approval": True,
    "runtime_block_pii_leak": True,
    "runtime_block_prompt_injected_external_action": True,
    "runtime_approval_ttl_minutes": 60,
    "runtime_amount_approval_threshold_usd": 500.0,
    "runtime_amount_deny_threshold_usd": 5000.0,
    "runtime_production_deploys_require_approval": True,
    "runtime_changed_recipient_deny": True,
}

# Keys + their expected types (validation contract — see validate_policy_payload)
_POLICY_FIELDS: dict[str, tuple[type | tuple[type, ...], str]] = {
    "tier1_enabled": (bool, "boolean"),
    "tier1_actions": (list, "list of strings"),
    "tier1_min_confidence": ((int, float), "number in [0, 1]"),
    "tier1_max_blast_radius": (str, "non-empty string"),
    "tier1_daily_cap": (int, "non-negative integer"),
    "tier2_enabled": (bool, "boolean"),
    "tier2_actions": (list, "list of strings"),
    "tier2_require_replay_pass": (bool, "boolean"),
    # Nullable int; validation handled inline (None OR non-negative int).
    "tier2_daily_cap": ((int, type(None)), "non-negative integer or null"),
    "tier3_alert_channels": (list, "list of strings"),
    "kill_switch": (bool, "boolean"),
    "runtime_enabled": (bool, "boolean"),
    "runtime_max_tool_calls": (int, "non-negative integer"),
    "runtime_max_retries": (int, "non-negative integer"),
    "runtime_max_cost_usd": ((int, float), "non-negative number"),
    "runtime_allowed_tools": (list, "list of strings"),
    "runtime_sensitive_tools": (list, "list of strings"),
    "runtime_sensitive_actions_require_approval": (bool, "boolean"),
    "runtime_block_pii_leak": (bool, "boolean"),
    "runtime_block_prompt_injected_external_action": (bool, "boolean"),
    "runtime_approval_ttl_minutes": (int, "positive integer"),
    "runtime_amount_approval_threshold_usd": ((int, float, type(None)), "non-negative number or null"),
    "runtime_amount_deny_threshold_usd": ((int, float, type(None)), "non-negative number or null"),
    "runtime_production_deploys_require_approval": (bool, "boolean"),
    "runtime_changed_recipient_deny": (bool, "boolean"),
}


class PolicyValidationError(ValueError):
    """Raised when a policy_json payload fails schema validation."""


def validate_policy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Type + range validation for a `pilot_policies.policy_json` payload.

    Returns a sanitised dict containing exactly the keys defined in
    `_POLICY_FIELDS` (extra keys are dropped). Raises
    `PolicyValidationError` with a human-readable message on the first
    violation.

    Note: `bool` is a subclass of `int` in Python — so this function
    checks bool before int explicitly to avoid `True` slipping into a
    numeric field check.
    """
    if not isinstance(payload, dict):
        raise PolicyValidationError("policy must be a JSON object")

    out: dict[str, Any] = {}
    for key, (expected_type, description) in _POLICY_FIELDS.items():
        if key not in payload:
            raise PolicyValidationError(f"missing required key: {key}")
        value = payload[key]

        # Reject bools where number is expected (Python: bool ⊂ int)
        expected_types = expected_type if isinstance(expected_type, tuple) else (expected_type,)
        if isinstance(value, bool) and any(item in expected_types for item in (int, float)):
            raise PolicyValidationError(
                f"{key!r} must be a {description}, got bool"
            )

        if not isinstance(value, expected_type):
            raise PolicyValidationError(
                f"{key!r} must be a {description}, got {type(value).__name__}"
            )

        if key == "tier1_min_confidence":
            if not (0.0 <= float(value) <= 1.0):
                raise PolicyValidationError(
                    "'tier1_min_confidence' must be in [0, 1]"
                )
            out[key] = float(value)
            continue

        if key == "tier1_daily_cap":
            if int(value) < 0:
                raise PolicyValidationError(
                    "'tier1_daily_cap' must be non-negative"
                )
            out[key] = int(value)
            continue

        if key == "tier2_daily_cap":
            # Module 10 — None means "fall back to global setting";
            # otherwise non-negative int. bool is rejected (already
            # filtered above as int) but None passes the type check
            # so we land here for both branches.
            if value is None:
                out[key] = None
                continue
            if int(value) < 0:
                raise PolicyValidationError(
                    "'tier2_daily_cap' must be non-negative or null"
                )
            out[key] = int(value)
            continue

        if key == "tier1_max_blast_radius":
            stripped = str(value).strip()
            if not stripped:
                raise PolicyValidationError(
                    "'tier1_max_blast_radius' must be a non-empty string"
                )
            out[key] = stripped
            continue

        if key in {"tier1_actions", "tier2_actions", "tier3_alert_channels", "runtime_allowed_tools", "runtime_sensitive_tools"}:
            cleaned: list[str] = []
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    raise PolicyValidationError(
                        f"{key!r} entries must be non-empty strings"
                    )
                cleaned.append(item.strip())
            out[key] = cleaned
            continue

        if key in {"runtime_max_tool_calls", "runtime_max_retries"}:
            if int(value) < 0:
                raise PolicyValidationError(f"{key!r} must be non-negative")
            out[key] = int(value)
            continue

        if key in {
            "runtime_max_cost_usd",
            "runtime_amount_approval_threshold_usd",
            "runtime_amount_deny_threshold_usd",
        }:
            if value is None:
                out[key] = None
                continue
            if float(value) < 0:
                raise PolicyValidationError(f"{key!r} must be non-negative")
            out[key] = float(value)
            continue

        if key == "runtime_approval_ttl_minutes":
            if int(value) <= 0:
                raise PolicyValidationError("'runtime_approval_ttl_minutes' must be positive")
            out[key] = int(value)
            continue

        out[key] = value
    return out


# ── actions: read paths ──────────────────────────────────────────────────────


def get_pilot_action(
    db: Session, *, project_id: str, action_id: str
) -> PilotAction | None:
    return db.execute(
        select(PilotAction).where(
            PilotAction.project_id == project_id,
            PilotAction.id == action_id,
        )
    ).scalar_one_or_none()


def list_pilot_actions(
    db: Session,
    *,
    project_id: str,
    status: str | None = None,
    tier: int | None = None,
    action_type: str | None = None,
    anomaly_id: str | None = None,
    limit: int = 20,
    before_created_at: datetime | None = None,
    before_id: str | None = None,
) -> list[PilotAction]:
    """List pilot actions for a project, newest-first by created_at.

    Optional filters: status, tier, action_type, anomaly_id.
    Cursor uses (created_at, id) strict-less-than tuple compare for
    deterministic pagination across microsecond ties.
    """
    conditions = [PilotAction.project_id == project_id]
    if status is not None:
        if status not in VALID_ACTION_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(VALID_ACTION_STATUSES)}, "
                f"got {status!r}"
            )
        conditions.append(PilotAction.status == status)
    if tier is not None:
        if tier not in VALID_TIERS:
            raise ValueError(
                f"tier must be one of {sorted(VALID_TIERS)}, got {tier!r}"
            )
        conditions.append(PilotAction.tier == tier)
    if action_type is not None:
        conditions.append(PilotAction.action_type == action_type)
    if anomaly_id is not None:
        conditions.append(PilotAction.anomaly_id == anomaly_id)
    if before_created_at is not None and before_id is not None:
        conditions.append(
            or_(
                PilotAction.created_at < before_created_at,
                and_(
                    PilotAction.created_at == before_created_at,
                    PilotAction.id < before_id,
                ),
            )
        )

    rows = db.execute(
        select(PilotAction)
        .where(*conditions)
        .order_by(PilotAction.created_at.desc(), PilotAction.id.desc())
        .limit(limit)
    ).scalars().all()
    return list(rows)


# ── actions: revert ──────────────────────────────────────────────────────────


class PilotActionRevertError(ValueError):
    """Revert was rejected by business rules (state or tier guard)."""


def revert_pilot_action(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    audit_user: str | None,
) -> PilotAction | None:
    """Mark an applied tier-1 action as reverted.

    Returns:
      - the updated row on success
      - None if the action does not exist for this project
      - Raises PilotActionRevertError if the action is not in `applied`
        status OR is not tier-1 (only tier-1 actions are reversible per
        plan §6.3).

    NOTE: This endpoint only records the revert decision in the database.
    The actual rollback of the underlying config (model pinning, fallback
    flag, retry-tuning knob) is handled by a worker that watches for the
    `reverted_at` field flipping non-NULL. Worker plumbing is deferred to
    a later module.
    """
    action = get_pilot_action(
        db, project_id=project_id, action_id=action_id
    )
    if action is None:
        return None
    if action.status != "applied":
        raise PilotActionRevertError(
            f"action status is {action.status!r}; only 'applied' actions can be reverted"
        )
    if action.tier != REVERTIBLE_TIER:
        raise PilotActionRevertError(
            f"action tier is {action.tier}; only tier-{REVERTIBLE_TIER} actions are reversible"
        )

    action.status = "reverted"
    action.reverted_at = datetime.now(timezone.utc)
    if audit_user is not None:
        action.audit_user = audit_user
    db.add(action)
    db.commit()
    db.refresh(action)
    logger.info(
        "pilot_action_reverted project=%s action=%s tier=%s by=%s",
        project_id, action_id, action.tier, audit_user,
    )
    return action


# ── policy: read + write ─────────────────────────────────────────────────────


def get_or_create_policy(
    db: Session, *, project_id: str
) -> PilotPolicy:
    """Return the policy row for this project, seeding the §6.3 default
    if no row exists yet. Idempotent — safe to call from a GET handler."""
    existing = db.execute(
        select(PilotPolicy).where(PilotPolicy.project_id == project_id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    policy = PilotPolicy(
        id=str(uuid4()),
        project_id=project_id,
        policy_json=json.dumps(deepcopy(DEFAULT_POLICY), separators=(",", ":")),
        updated_by=None,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    logger.info("pilot_policy_seeded_default project=%s", project_id)
    return policy


def upsert_policy(
    db: Session,
    *,
    project_id: str,
    payload: dict[str, Any],
    updated_by: str | None,
) -> PilotPolicy:
    """Validate + persist a policy_json payload.

    Raises PolicyValidationError if the payload fails schema validation.
    Creates the row if it doesn't exist, else updates it in place.
    """
    sanitised = validate_policy_payload(payload)
    policy_json = json.dumps(sanitised, separators=(",", ":"))

    existing = db.execute(
        select(PilotPolicy).where(PilotPolicy.project_id == project_id)
    ).scalar_one_or_none()

    if existing is None:
        policy = PilotPolicy(
            id=str(uuid4()),
            project_id=project_id,
            policy_json=policy_json,
            updated_by=updated_by,
        )
        db.add(policy)
    else:
        existing.policy_json = policy_json
        existing.updated_by = updated_by
        # `updated_at` is bumped by SQLAlchemy `onupdate=func.now()`
        db.add(existing)
        policy = existing

    db.commit()
    db.refresh(policy)
    logger.info(
        "pilot_policy_upserted project=%s by=%s kill_switch=%s",
        project_id, updated_by, sanitised.get("kill_switch"),
    )
    return policy


def parse_policy_json(policy_json: str | None) -> dict[str, Any]:
    """Defensive parser. Returns DEFAULT_POLICY (a fresh copy) if the
    stored JSON is missing or corrupt, so callers can rely on every
    canonical key being present."""
    if not policy_json:
        return deepcopy(DEFAULT_POLICY)
    try:
        decoded = json.loads(policy_json)
    except Exception:
        return deepcopy(DEFAULT_POLICY)
    if not isinstance(decoded, dict):
        return deepcopy(DEFAULT_POLICY)
    # Fill in missing keys from DEFAULT_POLICY so downstream code doesn't
    # have to guard against historical rows that pre-date a new field.
    merged = deepcopy(DEFAULT_POLICY)
    merged.update({k: v for k, v in decoded.items() if k in _POLICY_FIELDS})
    return merged
