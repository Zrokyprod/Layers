from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security_logging import sanitize_exception
from app.db.models import User
from app.db.session import db_healthcheck
from app.schemas.dashboard import (
    EvaluationSettingsResponse,
    GithubConnectionStatusResponse,
    PricingInterviewNote,
    PricingValidationResponse,
    RollbackDrillResponse,
    RollbackDrillVerificationCheck,
)
from app.services.dashboard_config import (
    ensure_project_exists,
    get_evaluation_settings,
    get_pricing_validation,
    get_rollback_drill,
)
from app.services.github_tokens import normalize_github_scopes
from app.services.privacy import mask_error_message
from app.services.redis_client import redis_healthcheck

_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"
_MIN_REQUIRED_PRICING_INTERVIEWS = 5

def _parse_iso_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _oauth_state_secret(settings: Settings) -> str:
    secret = (settings.OAUTH_STATE_SECRET or settings.AUTH_JWT_SECRET or "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth state secret is not configured.",
        )
    return secret


def _github_connection_status(user: User) -> GithubConnectionStatusResponse:
    scopes = normalize_github_scopes(user.github_token_scopes)
    connected = bool((user.github_token_encrypted or "").strip())
    return GithubConnectionStatusResponse(
        connected=connected,
        github_id=user.github_id,
        github_login=user.github_login,
        scopes=scopes,
        connected_at=user.github_token_connected_at if connected else None,
        updated_at=user.github_token_updated_at,
    )


def _evaluation_settings_response(config) -> EvaluationSettingsResponse:
    payload = get_evaluation_settings(config)
    return EvaluationSettingsResponse(
        judge_mode=payload.get("judge_mode") or "standard",
        default_judge_model=str(payload.get("default_judge_model") or "auto"),
        minimum_confidence=float(payload.get("minimum_confidence", 0.75)),
        auto_calibration_enabled=bool(payload.get("auto_calibration_enabled", True)),
        record_replay_calibration=bool(payload.get("record_replay_calibration", True)),
        updated_at=config.updated_at,
    )


def _exchange_github_code(
    *,
    code: str,
    settings: Settings,
) -> tuple[str, str | None]:
    try:
        response = httpx.post(
            _GITHUB_TOKEN_URL,
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GITHUB_CONNECT_OAUTH_REDIRECT_URL,
            },
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # Sanitize exception to prevent token exposure in error messages
        safe_exc = sanitize_exception(exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to contact GitHub API.",
        ) from safe_exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub token response was invalid.",
        )

    token_raw = payload.get("access_token")
    token = str(token_raw).strip() if token_raw is not None else ""
    if not token:
        error_detail = payload.get("error_description") or payload.get("error") or "unknown error"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub token exchange failed: {error_detail}",
        )

    scope_raw = payload.get("scope")
    scope = str(scope_raw).strip() if isinstance(scope_raw, str) else None
    return token, scope


def _fetch_github_user(token: str) -> dict[str, Any]:
    try:
        response = httpx.get(
            _GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        safe_exc = sanitize_exception(exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch GitHub user profile.",
        ) from safe_exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub profile response was invalid.",
        )
    return payload


def _require_project(db: Session, tenant_id: str):
    try:
        return ensure_project_exists(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=mask_error_message(exc),
        ) from exc


def _parse_pricing_interviews(value: Any) -> list[PricingInterviewNote]:
    if not isinstance(value, list):
        return []

    interviews: list[PricingInterviewNote] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            interviews.append(PricingInterviewNote.model_validate(item))
        except Exception:
            continue
    return interviews


def _normalize_developer_ref(value: str) -> str:
    return value.strip().lower()


def _build_pricing_validation_response(config) -> PricingValidationResponse:
    payload = get_pricing_validation(config)
    interviews = _parse_pricing_interviews(payload.get("interviews"))

    selected_model_raw = payload.get("selected_launch_model")
    selected_model: Literal["tiered", "usage_based", "undecided"]
    if selected_model_raw in {"tiered", "usage_based", "undecided"}:
        selected_model = selected_model_raw
    else:
        selected_model = "undecided"

    interview_count = len(interviews)
    unique_developer_count = len(
        {
            _normalize_developer_ref(note.developer_ref)
            for note in interviews
            if note.developer_ref and note.developer_ref.strip()
        }
    )
    minimum_interviews_met = unique_developer_count >= _MIN_REQUIRED_PRICING_INTERVIEWS
    missing_interviews = max(0, _MIN_REQUIRED_PRICING_INTERVIEWS - unique_developer_count)
    pricing_locked = bool(payload.get("pricing_locked", False))
    launch_gate_passed = minimum_interviews_met and pricing_locked and selected_model != "undecided"

    blockers: list[str] = []
    if not minimum_interviews_met:
        blockers.append(
            "At least 5 unique beta developer interviews are required before launch pricing can be finalized."
        )
    if selected_model == "undecided":
        blockers.append("Select a launch pricing model (tiered or usage_based).")
    if not pricing_locked:
        blockers.append("Lock the launch pricing decision after interview evidence is complete.")

    return PricingValidationResponse(
        selected_launch_model=selected_model,
        rationale=str(payload.get("rationale")) if payload.get("rationale") is not None else None,
        migration_path=str(payload.get("migration_path")) if payload.get("migration_path") is not None else None,
        interviews=interviews,
        interview_count=interview_count,
        unique_developer_count=unique_developer_count,
        required_interviews=_MIN_REQUIRED_PRICING_INTERVIEWS,
        missing_interviews=missing_interviews,
        minimum_interviews_met=minimum_interviews_met,
        pricing_locked=pricing_locked,
        launch_gate_passed=launch_gate_passed,
        blockers=blockers,
        locked_at=_parse_iso_utc(payload.get("locked_at")),
        updated_at=config.updated_at,
    )


def _build_rollback_drill_response(config) -> RollbackDrillResponse:
    payload = get_rollback_drill(config)

    status_raw = payload.get("status")
    resolved_status: Literal["not_started", "in_progress", "passed", "failed"]
    if status_raw in {"not_started", "in_progress", "passed", "failed"}:
        resolved_status = status_raw
    else:
        resolved_status = "not_started"

    category_raw = payload.get("failure_simulation_category")
    category_value = str(category_raw).strip().upper() if isinstance(category_raw, str) and category_raw.strip() else None

    return RollbackDrillResponse(
        deploy_revision=str(payload.get("deploy_revision")) if payload.get("deploy_revision") is not None else None,
        rollback_revision=str(payload.get("rollback_revision")) if payload.get("rollback_revision") is not None else None,
        deploy_test_passed=bool(payload.get("deploy_test_passed", False)),
        rollback_test_passed=bool(payload.get("rollback_test_passed", False)),
        failure_simulation_performed=bool(payload.get("failure_simulation_performed", False)),
        failure_simulation_category=category_value,
        failure_simulation_notes=(
            str(payload.get("failure_simulation_notes"))
            if payload.get("failure_simulation_notes") is not None
            else None
        ),
        drill_notes=str(payload.get("drill_notes")) if payload.get("drill_notes") is not None else None,
        status=resolved_status,
        completed_at=_parse_iso_utc(payload.get("completed_at")),
        updated_at=config.updated_at,
    )


def _run_rollback_verification_checks(settings: Settings) -> tuple[list[RollbackDrillVerificationCheck], bool]:
    checks: list[RollbackDrillVerificationCheck] = []

    if settings.ENABLE_READY_DB_CHECK:
        database_ok = bool(db_healthcheck())
        checks.append(
            RollbackDrillVerificationCheck(
                name="database",
                status="ok" if database_ok else "failed",
                detail="Database readiness check passed." if database_ok else "Database readiness check failed.",
            )
        )
    else:
        checks.append(
            RollbackDrillVerificationCheck(
                name="database",
                status="skipped",
                detail="Database readiness check skipped because ENABLE_READY_DB_CHECK is disabled.",
            )
        )

    if settings.ENABLE_READY_REDIS_CHECK:
        redis_ok = bool(redis_healthcheck())
        checks.append(
            RollbackDrillVerificationCheck(
                name="redis",
                status="ok" if redis_ok else "failed",
                detail="Redis readiness check passed." if redis_ok else "Redis readiness check failed.",
            )
        )
    else:
        checks.append(
            RollbackDrillVerificationCheck(
                name="redis",
                status="skipped",
                detail="Redis readiness check skipped because ENABLE_READY_REDIS_CHECK is disabled.",
            )
        )

    passed = all(check.status != "failed" for check in checks)
    return checks, passed


