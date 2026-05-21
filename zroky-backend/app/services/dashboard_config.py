from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Project, ProjectDashboardConfig


DEFAULT_NOTIFICATIONS = {
    "email_enabled": True,
    "slack_enabled": False,
    "teams_enabled": False,
    "browser_enabled": True,
    "terminal_enabled": True,
}

DEFAULT_PRICING_VALIDATION = {
    "selected_launch_model": "undecided",
    "rationale": None,
    "migration_path": None,
    "interviews": [],
    "pricing_locked": False,
    "locked_at": None,
}

DEFAULT_ROLLBACK_DRILL = {
    "deploy_revision": None,
    "rollback_revision": None,
    "deploy_test_passed": False,
    "rollback_test_passed": False,
    "failure_simulation_performed": False,
    "failure_simulation_category": None,
    "failure_simulation_notes": None,
    "drill_notes": None,
    "status": "not_started",
    "completed_at": None,
}


def ensure_project_exists(db: Session, tenant_id: str) -> Project:
    project = db.get(Project, tenant_id)
    if project is None:
        raise ValueError("Project not found")
    return project


def _load_json_object(raw: str | None, default: dict[str, Any]) -> dict[str, Any]:
    if not raw:
        return dict(default)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return dict(default)
    if not isinstance(parsed, dict):
        return dict(default)
    merged = dict(default)
    merged.update(parsed)
    return merged


def _load_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    cleaned: list[str] = []
    for item in parsed:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip())
    return cleaned


def get_or_create_dashboard_config(db: Session, tenant_id: str) -> ProjectDashboardConfig:
    config = db.execute(
        select(ProjectDashboardConfig).where(ProjectDashboardConfig.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if config is not None:
        return config

    config = ProjectDashboardConfig(
        tenant_id=tenant_id,
        budget_threshold_percentage=80.0,
        retention_days=30,
        pii_custom_patterns_json="[]",
        notifications_json=json.dumps(DEFAULT_NOTIFICATIONS),
        provider_verifications_json="{}",
        pricing_validation_json=json.dumps(DEFAULT_PRICING_VALIDATION),
        rollback_drill_json=json.dumps(DEFAULT_ROLLBACK_DRILL),
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def get_notification_settings(config: ProjectDashboardConfig) -> dict[str, Any]:
    return _load_json_object(config.notifications_json, DEFAULT_NOTIFICATIONS)


def set_notification_settings(config: ProjectDashboardConfig, settings: dict[str, Any]) -> None:
    payload = {
        "email_enabled": bool(settings.get("email_enabled", True)),
        "slack_enabled": bool(settings.get("slack_enabled", False)),
        "teams_enabled": bool(settings.get("teams_enabled", False)),
        "browser_enabled": bool(settings.get("browser_enabled", True)),
        "terminal_enabled": bool(settings.get("terminal_enabled", True)),
    }
    config.notifications_json = json.dumps(payload, separators=(",", ":"))


def get_pii_patterns(config: ProjectDashboardConfig) -> list[str]:
    return _load_json_list(config.pii_custom_patterns_json)


def set_pii_patterns(config: ProjectDashboardConfig, patterns: list[str]) -> None:
    config.pii_custom_patterns_json = json.dumps(patterns, separators=(",", ":"))


def get_provider_verifications(config: ProjectDashboardConfig) -> dict[str, Any]:
    return _load_json_object(config.provider_verifications_json, {})


def set_provider_verifications(config: ProjectDashboardConfig, payload: dict[str, Any]) -> None:
    config.provider_verifications_json = json.dumps(payload, separators=(",", ":"))


def get_pricing_validation(config: ProjectDashboardConfig) -> dict[str, Any]:
    return _load_json_object(config.pricing_validation_json, DEFAULT_PRICING_VALIDATION)


def set_pricing_validation(config: ProjectDashboardConfig, payload: dict[str, Any]) -> None:
    config.pricing_validation_json = json.dumps(payload, separators=(",", ":"))


def get_rollback_drill(config: ProjectDashboardConfig) -> dict[str, Any]:
    return _load_json_object(config.rollback_drill_json, DEFAULT_ROLLBACK_DRILL)


def set_rollback_drill(config: ProjectDashboardConfig, payload: dict[str, Any]) -> None:
    config.rollback_drill_json = json.dumps(payload, separators=(",", ":"))
