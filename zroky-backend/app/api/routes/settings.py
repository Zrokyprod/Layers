import re
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from app.api.dependencies.tenant import require_tenant_role
from app.core.config import Settings, get_settings
from app.core.limiter import limiter
from app.db.models import DiagnosisJob, User
from app.db.session import db_healthcheck, get_db_session, get_db_session_read
from app.schemas.dashboard import (
    GithubConnectionStatusResponse,
    GithubConnectCallbackRequest,
    NotificationSettingsResponse,
    NotificationSettingsUpdateRequest,
    PiiDetectorTestRequest,
    PiiDetectorTestResponse,
    PiiPolicyResponse,
    PiiPolicyUpdateRequest,
    PricingInterviewNote,
    PricingValidationResponse,
    PricingValidationUpdateRequest,
    ProviderVerificationItem,
    ProviderVerificationListResponse,
    ProviderVerificationTestResponse,
    RollbackDrillResponse,
    RollbackDrillVerificationCheck,
    RollbackDrillVerificationResponse,
    RollbackDrillVerifyRequest,
    RollbackDrillUpdateRequest,
    RetentionDataErasureResponse,
    RetentionPolicyResponse,
    RetentionPolicyUpdateRequest,
)
from app.schemas.project import ProjectResponse
from app.core.security_logging import sanitize_exception
from app.services.github_tokens import (
    ensure_github_token_encryption_ready,
    encrypt_github_token,
    normalize_github_scopes,
)
from app.services.dashboard_config import (
    ensure_project_exists,
    get_notification_settings,
    get_or_create_dashboard_config,
    get_pii_patterns,
    get_pricing_validation,
    get_provider_verifications,
    get_rollback_drill,
    set_notification_settings,
    set_pii_patterns,
    set_pricing_validation,
    set_provider_verifications,
    set_rollback_drill,
)
from app.services.dashboard_data import safe_load_json
from app.services.privacy import mask_error_message, mask_text
from app.services.provider_status import verify_provider_connection
from app.services.redis_client import redis_healthcheck
from app.services.retention import purge_project_all_data
from app.services.security import generate_oauth_state_with_payload, verify_oauth_state_with_payload
from app.services.user_identity import require_authenticated_user

router = APIRouter(prefix="/v1/settings")

_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
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


@router.get("/project", response_model=ProjectResponse)
def get_project_settings(
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> ProjectResponse:
    project = _require_project(db, tenant_id)
    return ProjectResponse(
        project_id=project.id,
        name=project.name,
        owner_ref=project.owner_ref,
        is_active=project.is_active,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("/pii-policy", response_model=PiiPolicyResponse)
def get_pii_policy(
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> PiiPolicyResponse:
    _require_project(db, tenant_id)
    config = get_or_create_dashboard_config(db, tenant_id)
    return PiiPolicyResponse(custom_patterns=get_pii_patterns(config), updated_at=config.updated_at)


@router.put("/pii-policy", response_model=PiiPolicyResponse)
def update_pii_policy(
    body: PiiPolicyUpdateRequest,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> PiiPolicyResponse:
    _require_project(db, tenant_id)
    config = get_or_create_dashboard_config(db, tenant_id)
    set_pii_patterns(config, body.custom_patterns)
    db.add(config)
    db.commit()
    db.refresh(config)
    return PiiPolicyResponse(custom_patterns=get_pii_patterns(config), updated_at=config.updated_at)


@router.post("/pii-policy/test-detector", response_model=PiiDetectorTestResponse)
def test_pii_detector(
    body: PiiDetectorTestRequest,
    _: str = Depends(require_tenant_role("admin")),
) -> PiiDetectorTestResponse:
    try:
        compiled = re.compile(body.pattern)
    except re.error as exc:
        return PiiDetectorTestResponse(
            valid=False,
            match_count=0,
            matches=[],
            error=mask_error_message(exc),
        )

    matches = [mask_text(match.group(0)) for match in compiled.finditer(body.sample_text)]
    return PiiDetectorTestResponse(
        valid=True,
        match_count=len(matches),
        matches=matches[:25],
        error=None,
    )


@router.post("/pii/test", response_model=PiiDetectorTestResponse)
def test_pii_detector_alias(
    body: PiiDetectorTestRequest,
    tenant_id: str = Depends(require_tenant_role("admin")),
) -> PiiDetectorTestResponse:
    return test_pii_detector(body=body, _=tenant_id)


@router.get("/retention", response_model=RetentionPolicyResponse)
def get_retention_policy(
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> RetentionPolicyResponse:
    _require_project(db, tenant_id)
    config = get_or_create_dashboard_config(db, tenant_id)
    return RetentionPolicyResponse(retention_days=config.retention_days, updated_at=config.updated_at)


@router.put("/retention", response_model=RetentionPolicyResponse)
def update_retention_policy(
    body: RetentionPolicyUpdateRequest,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> RetentionPolicyResponse:
    _require_project(db, tenant_id)
    config = get_or_create_dashboard_config(db, tenant_id)
    config.retention_days = body.retention_days
    db.add(config)
    db.commit()
    db.refresh(config)
    return RetentionPolicyResponse(retention_days=config.retention_days, updated_at=config.updated_at)


@router.delete("/retention/data", response_model=RetentionDataErasureResponse)
@limiter.limit("5/minute")
def erase_project_data(
    request: Request,
    dry_run: bool = Query(default=False),
    batch_size: int = Query(default=500, ge=1, le=5000),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> RetentionDataErasureResponse:
    _require_project(db, tenant_id)
    summary = purge_project_all_data(
        session=db,
        tenant_id=tenant_id,
        batch_size=batch_size,
        dry_run=dry_run,
    )
    return RetentionDataErasureResponse(
        tenant_id=summary["tenant_id"],
        dry_run=summary["dry_run"],
        batch_size=summary["batch_size"],
        deleted_by_table=summary["deleted_by_table"],
        total_deleted=summary["total_deleted"],
        erased_at=datetime.now(timezone.utc),
    )


@router.get("/notifications", response_model=NotificationSettingsResponse)
def get_notification_settings_route(
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> NotificationSettingsResponse:
    _require_project(db, tenant_id)
    config = get_or_create_dashboard_config(db, tenant_id)
    settings = get_notification_settings(config)
    return NotificationSettingsResponse(
        email_enabled=bool(settings.get("email_enabled", True)),
        slack_enabled=bool(settings.get("slack_enabled", False)),
        teams_enabled=bool(settings.get("teams_enabled", False)),
        browser_enabled=bool(settings.get("browser_enabled", True)),
        terminal_enabled=bool(settings.get("terminal_enabled", True)),
        updated_at=config.updated_at,
    )


@router.put("/notifications", response_model=NotificationSettingsResponse)
def update_notification_settings_route(
    body: NotificationSettingsUpdateRequest,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> NotificationSettingsResponse:
    _require_project(db, tenant_id)
    config = get_or_create_dashboard_config(db, tenant_id)
    set_notification_settings(
        config,
        {
            "email_enabled": body.email_enabled,
            "slack_enabled": body.slack_enabled,
            "teams_enabled": body.teams_enabled,
            "browser_enabled": body.browser_enabled,
            "terminal_enabled": body.terminal_enabled,
        },
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    settings = get_notification_settings(config)
    return NotificationSettingsResponse(
        email_enabled=bool(settings.get("email_enabled", True)),
        slack_enabled=bool(settings.get("slack_enabled", False)),
        teams_enabled=bool(settings.get("teams_enabled", False)),
        browser_enabled=bool(settings.get("browser_enabled", True)),
        terminal_enabled=bool(settings.get("terminal_enabled", True)),
        updated_at=config.updated_at,
    )


@router.get("/github/connection", response_model=GithubConnectionStatusResponse)
def get_github_connection_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> GithubConnectionStatusResponse:
    _require_project(db, tenant_id)
    user = require_authenticated_user(request, db, auto_create=True)
    return _github_connection_status(user)


@router.get("/github/connect/start")
def start_github_repo_connect(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    _require_project(db, tenant_id)
    settings = get_settings()

    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth is not configured on this server.",
        )

    ensure_github_token_encryption_ready()
    user = require_authenticated_user(request, db, auto_create=True)

    scopes = settings.GITHUB_REPO_OAUTH_SCOPES.strip() or "repo read:user user:email"
    state = generate_oauth_state_with_payload(
        _oauth_state_secret(settings),
        {
            "purpose": "github_repo_connect",
            "tenant_id": tenant_id,
            "subject": user.subject,
        },
    )

    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_CONNECT_OAUTH_REDIRECT_URL,
        "scope": scopes,
        "state": state,
    }
    return RedirectResponse(url=f"{_GITHUB_AUTH_URL}?{urlencode(params)}")


@router.post("/github/connect/callback", response_model=GithubConnectionStatusResponse)
@limiter.limit("5/minute")
def complete_github_repo_connect(
    body: GithubConnectCallbackRequest,
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> GithubConnectionStatusResponse:
    _require_project(db, tenant_id)
    settings = get_settings()

    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth is not configured on this server.",
        )

    ensure_github_token_encryption_ready()
    user = require_authenticated_user(request, db, auto_create=True)

    state_payload = verify_oauth_state_with_payload(body.state, _oauth_state_secret(settings))
    if state_payload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state. Start GitHub connect again.",
        )

    if state_payload.get("purpose") != "github_repo_connect":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state purpose mismatch.",
        )

    if str(state_payload.get("tenant_id") or "") != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state tenant mismatch.",
        )

    if str(state_payload.get("subject") or "") != user.subject:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state user mismatch.",
        )

    github_token, scope_text = _exchange_github_code(code=body.code, settings=settings)
    github_user = _fetch_github_user(github_token)

    github_id = str(github_user.get("id") or "").strip()
    if not github_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub profile response missing user id.",
        )

    github_login_raw = github_user.get("login")
    github_login = str(github_login_raw).strip() if isinstance(github_login_raw, str) else None
    if github_login == "":
        github_login = None

    existing_owner = db.execute(
        select(User).where(User.github_id == github_id, User.id != user.id)
    ).scalar_one_or_none()
    if existing_owner is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This GitHub account is already linked to another user.",
        )

    normalized_scopes = normalize_github_scopes(scope_text)
    now = datetime.now(timezone.utc)

    user.github_id = github_id
    user.github_login = github_login
    if github_login and not user.display_name:
        user.display_name = github_login
    user.github_token_encrypted = encrypt_github_token(github_token)
    user.github_token_scopes = " ".join(normalized_scopes) if normalized_scopes else None
    user.github_token_updated_at = now
    if user.github_token_connected_at is None:
        user.github_token_connected_at = now

    db.add(user)
    db.commit()
    db.refresh(user)

    return _github_connection_status(user)


@router.post("/github/disconnect", response_model=GithubConnectionStatusResponse)
@limiter.limit("5/minute")
def disconnect_github_connection(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> GithubConnectionStatusResponse:
    _require_project(db, tenant_id)
    user = require_authenticated_user(request, db, auto_create=True)

    user.github_id = None
    user.github_login = None
    user.github_token_encrypted = None
    user.github_token_scopes = None
    user.github_token_connected_at = None
    user.github_token_updated_at = datetime.now(timezone.utc)

    db.add(user)
    db.commit()
    db.refresh(user)
    return _github_connection_status(user)


@router.get("/pricing-validation", response_model=PricingValidationResponse)
def get_pricing_validation_settings(
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> PricingValidationResponse:
    _require_project(db, tenant_id)
    config = get_or_create_dashboard_config(db, tenant_id)
    return _build_pricing_validation_response(config)


@router.put("/pricing-validation", response_model=PricingValidationResponse)
def update_pricing_validation_settings(
    body: PricingValidationUpdateRequest,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> PricingValidationResponse:
    _require_project(db, tenant_id)
    config = get_or_create_dashboard_config(db, tenant_id)
    current = _build_pricing_validation_response(config)
    if current.pricing_locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pricing decision is locked and cannot be modified.",
        )

    normalized_refs: list[str] = [_normalize_developer_ref(note.developer_ref) for note in body.interviews]
    unique_developer_count = len(set(normalized_refs))

    if len(normalized_refs) != unique_developer_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate developer_ref entries are not allowed. Each interview must map to a unique beta developer.",
        )

    if body.lock_pricing_decision and unique_developer_count < _MIN_REQUIRED_PRICING_INTERVIEWS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 5 unique beta developer interviews are required before pricing can be locked.",
        )
    if body.lock_pricing_decision and body.selected_launch_model == "undecided":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select a launch pricing model before locking pricing decision.",
        )

    now = datetime.now(timezone.utc)
    payload = {
        "selected_launch_model": body.selected_launch_model,
        "rationale": body.rationale,
        "migration_path": body.migration_path,
        "interviews": [note.model_dump(mode="json") for note in body.interviews],
        "pricing_locked": bool(body.lock_pricing_decision),
        "locked_at": now.isoformat() if body.lock_pricing_decision else None,
    }

    set_pricing_validation(config, payload)
    db.add(config)
    db.commit()
    db.refresh(config)
    return _build_pricing_validation_response(config)


@router.get("/rollback-drill", response_model=RollbackDrillResponse)
def get_rollback_drill_settings(
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> RollbackDrillResponse:
    _require_project(db, tenant_id)
    config = get_or_create_dashboard_config(db, tenant_id)
    return _build_rollback_drill_response(config)


@router.post("/rollback-drill/verify", response_model=RollbackDrillVerificationResponse)
def verify_rollback_drill_settings(
    body: RollbackDrillVerifyRequest,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> RollbackDrillVerificationResponse:
    _require_project(db, tenant_id)
    config = get_or_create_dashboard_config(db, tenant_id)
    existing = get_rollback_drill(config)

    deploy_revision_current = (
        str(existing.get("deploy_revision")).strip()
        if isinstance(existing.get("deploy_revision"), str)
        else ""
    )
    rollback_revision_current = (
        str(existing.get("rollback_revision")).strip()
        if isinstance(existing.get("rollback_revision"), str)
        else ""
    )

    if body.phase == "deploy":
        deploy_revision = (body.deploy_revision or deploy_revision_current or "").strip()
        if not deploy_revision:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="deploy_revision is required for deploy verification.",
            )
    else:
        rollback_revision = (body.rollback_revision or rollback_revision_current or "").strip()
        if not rollback_revision:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="rollback_revision is required for rollback verification.",
            )

    checks, passed = _run_rollback_verification_checks(get_settings())

    payload = dict(existing)
    if body.phase == "deploy":
        payload["deploy_revision"] = deploy_revision
        payload["deploy_test_passed"] = passed
    else:
        payload["rollback_revision"] = rollback_revision
        payload["rollback_test_passed"] = passed

    existing_status_raw = payload.get("status")
    existing_status = str(existing_status_raw).strip().lower() if existing_status_raw is not None else ""
    if existing_status in {"", "not_started"}:
        payload["status"] = "in_progress"

    set_rollback_drill(config, payload)
    db.add(config)
    db.commit()
    db.refresh(config)

    return RollbackDrillVerificationResponse(
        phase=body.phase,
        passed=passed,
        checks=checks,
        verified_at=datetime.now(timezone.utc),
        rollback_drill=_build_rollback_drill_response(config),
    )


@router.put("/rollback-drill", response_model=RollbackDrillResponse)
def update_rollback_drill_settings(
    body: RollbackDrillUpdateRequest,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> RollbackDrillResponse:
    _require_project(db, tenant_id)
    config = get_or_create_dashboard_config(db, tenant_id)
    existing = get_rollback_drill(config)

    if body.failure_simulation_performed and body.failure_simulation_category is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failure simulation category is required when failure simulation is marked as performed.",
        )

    if body.status == "passed":
        pricing_validation = _build_pricing_validation_response(config)
        if not pricing_validation.launch_gate_passed:
            reasons = "; ".join(pricing_validation.blockers)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Pricing validation launch gate is not complete. "
                    f"{reasons}"
                ),
            )

        if not body.deploy_test_passed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Deploy test must pass before rollback drill can be marked passed.",
            )
        if not body.rollback_test_passed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rollback test must pass before rollback drill can be marked passed.",
            )
        if not body.failure_simulation_performed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failure simulation is required before rollback drill can be marked passed.",
            )
        if not body.deploy_revision or not body.rollback_revision:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Deploy and rollback revisions are required before rollback drill can be marked passed.",
            )

    existing_completed_at = _parse_iso_utc(existing.get("completed_at"))
    completed_at: datetime | None
    if body.status in {"passed", "failed"}:
        completed_at = existing_completed_at or datetime.now(timezone.utc)
    else:
        completed_at = None

    payload = {
        "deploy_revision": body.deploy_revision,
        "rollback_revision": body.rollback_revision,
        "deploy_test_passed": body.deploy_test_passed,
        "rollback_test_passed": body.rollback_test_passed,
        "failure_simulation_performed": body.failure_simulation_performed,
        "failure_simulation_category": body.failure_simulation_category,
        "failure_simulation_notes": body.failure_simulation_notes,
        "drill_notes": body.drill_notes,
        "status": body.status,
        "completed_at": completed_at.isoformat() if completed_at is not None else None,
    }

    set_rollback_drill(config, payload)
    db.add(config)
    db.commit()
    db.refresh(config)
    return _build_rollback_drill_response(config)


@router.get("/provider-verifications", response_model=ProviderVerificationListResponse)
def list_provider_verifications(
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> ProviderVerificationListResponse:
    _require_project(db, tenant_id)
    config = get_or_create_dashboard_config(db, tenant_id)
    stored = get_provider_verifications(config)

    jobs = db.execute(
        select(DiagnosisJob)
        .where(DiagnosisJob.tenant_id == tenant_id)
        .options(load_only(DiagnosisJob.payload_json))
        .order_by(DiagnosisJob.created_at.desc())
        .limit(2000)
    ).scalars().all()

    tracked_counts: dict[str, int] = {}
    for job in jobs:
        payload = safe_load_json(job.payload_json)
        provider_raw = payload.get("provider")
        provider = str(provider_raw).strip().lower() if provider_raw else "unknown"
        tracked_counts[provider] = tracked_counts.get(provider, 0) + 1

    providers = sorted(set(tracked_counts.keys()) | set(stored.keys()))
    items: list[ProviderVerificationItem] = []
    for provider in providers:
        raw_meta = stored.get(provider)
        meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
        tracked = tracked_counts.get(provider, 0)
        status_raw = meta.get("status")
        status_value: Literal["verified", "unverified", "failed"]
        if status_raw == "verified":
            status_value = "verified"
        elif status_raw == "failed":
            status_value = "failed"
        elif status_raw == "unverified":
            status_value = "unverified"
        else:
            status_value = "verified" if tracked > 0 else "unverified"

        last_checked_at = meta.get("last_checked_at")
        last_error = meta.get("last_error")

        items.append(
            ProviderVerificationItem(
                provider=provider,
                status=status_value,
                tracked_call_count=tracked,
                last_checked_at=_parse_iso_utc(last_checked_at),
                last_error=str(last_error) if last_error else None,
            )
        )

    return ProviderVerificationListResponse(items=items)


@router.post("/provider-verifications/{provider}/test", response_model=ProviderVerificationTestResponse)
def test_provider_connection(
    provider: str,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> ProviderVerificationTestResponse:
    normalized_provider = provider.strip().lower()
    if not normalized_provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider is required")

    _require_project(db, tenant_id)
    config = get_or_create_dashboard_config(db, tenant_id)
    verifications = get_provider_verifications(config)

    check_result = verify_provider_connection(normalized_provider)
    checked_at = check_result["checked_at"]
    verification_status = "verified" if check_result["verified"] else "failed"
    last_error = check_result.get("last_error")

    verifications[normalized_provider] = {
        "status": verification_status,
        "last_checked_at": checked_at.isoformat(),
        "last_error": last_error,
    }
    set_provider_verifications(config, verifications)
    db.add(config)
    db.commit()
    db.refresh(config)

    return ProviderVerificationTestResponse(
        provider=normalized_provider,
        status=verification_status,
        message=str(check_result["message"]),
        checked_at=checked_at,
    )
