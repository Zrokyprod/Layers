from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_context, require_tenant_role, TenantContext
from app.core.config import Settings, get_settings
from app.core.limiter import limiter
from app.db.models import TenantSlackInstall, TenantTeamsInstall
from app.db.session import get_db_session, get_db_session_read
from app.services.dashboard_config import ensure_project_exists, get_or_create_dashboard_config, set_notification_settings, get_notification_settings
from app.services.security import generate_oauth_state_with_payload, verify_oauth_state_with_payload
from app.services.slack_integration import build_slack_status, encrypt_slack_token, encrypt_slack_webhook_url, ensure_slack_token_encryption_ready, get_slack_install, send_slack_message
from app.services.slack_judgment import (
    answer_and_post_slack_question,
    answer_slack_action,
    answer_slack_question,
    build_slack_error_payload,
    build_slack_working_payload,
    resolve_slack_install,
    verify_slack_signature,
)
from app.services.teams_integration import build_teams_status, encrypt_teams_webhook_url, ensure_teams_webhook_encryption_ready, get_teams_install, send_teams_message

router = APIRouter(prefix="/v1/integrations")
logger = logging.getLogger(__name__)

_SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
_SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"


class SlackInstallStartResponse(BaseModel):
    authorization_url: str


class SlackInstallStatusResponse(BaseModel):
    connected: bool
    team_id: str | None = None
    team_name: str | None = None
    channel_id: str | None = None
    channel_name: str | None = None
    bot_user_id: str | None = None
    scopes: list[str] = []
    installed_by_user: str | None = None
    installed_at: datetime | None = None
    updated_at: datetime | None = None


class SlackTestMessageRequest(BaseModel):
    text: str | None = None


class SlackTestMessageResponse(BaseModel):
    ok: bool
    message: str


class TeamsInstallStatusResponse(BaseModel):
    connected: bool
    channel_name: str | None = None
    connector_type: str | None = None
    installed_by_user: str | None = None
    installed_at: datetime | None = None
    updated_at: datetime | None = None


class TeamsInstallRequest(BaseModel):
    webhook_url: str
    channel_name: str | None = None


class TeamsTestMessageRequest(BaseModel):
    text: str | None = None


class TeamsTestMessageResponse(BaseModel):
    ok: bool
    message: str


def _oauth_state_secret(settings: Settings) -> str:
    secret = (settings.OAUTH_STATE_SECRET or settings.AUTH_JWT_SECRET or "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth state secret is not configured.",
        )
    return secret


def _require_slack_oauth_config(settings: Settings) -> None:
    if not settings.SLACK_CLIENT_ID or not settings.SLACK_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack OAuth is not configured on this server.",
        )
    ensure_slack_token_encryption_ready()


def _extract_slack_team(payload: dict[str, Any]) -> tuple[str, str | None]:
    team = payload.get("team")
    if not isinstance(team, dict):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Slack OAuth response missing team.")
    team_id = str(team.get("id") or "").strip()
    if not team_id:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Slack OAuth response missing team id.")
    team_name_raw = team.get("name")
    team_name = str(team_name_raw).strip() if isinstance(team_name_raw, str) and team_name_raw.strip() else None
    return team_id, team_name


def _extract_incoming_webhook(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    webhook = payload.get("incoming_webhook")
    if not isinstance(webhook, dict):
        return None, None, None
    webhook_url_raw = webhook.get("url")
    channel_id_raw = webhook.get("channel_id")
    channel_name_raw = webhook.get("channel")
    webhook_url = str(webhook_url_raw).strip() if isinstance(webhook_url_raw, str) and webhook_url_raw.strip() else None
    channel_id = str(channel_id_raw).strip() if isinstance(channel_id_raw, str) and channel_id_raw.strip() else None
    channel_name = str(channel_name_raw).strip() if isinstance(channel_name_raw, str) and channel_name_raw.strip() else None
    return webhook_url, channel_id, channel_name


async def _exchange_slack_code(code: str, settings: Settings) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            _SLACK_TOKEN_URL,
            data={
                "client_id": settings.SLACK_CLIENT_ID,
                "client_secret": settings.SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.SLACK_OAUTH_REDIRECT_URL,
            },
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Slack OAuth token exchange failed.")
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        error = str(payload.get("error") or "unknown_error") if isinstance(payload, dict) else "unknown_error"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Slack OAuth failed: {error}")
    return payload


def _form_value(form: dict[str, list[str]], key: str) -> str | None:
    values = form.get(key)
    if not values:
        return None
    value = values[0]
    return value.strip() if isinstance(value, str) else None


async def _read_verified_slack_form(request: Request) -> dict[str, list[str]]:
    raw_body = await request.body()
    settings = get_settings()
    if not settings.SLACK_SIGNING_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SLACK_SIGNING_SECRET is not configured.",
        )
    ok = verify_slack_signature(
        settings.SLACK_SIGNING_SECRET,
        request.headers.get("x-slack-request-timestamp"),
        raw_body,
        request.headers.get("x-slack-signature"),
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack signature.",
        )
    return parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)


def _slack_resolution_error(error: str | None) -> dict[str, Any]:
    if error == "ambiguous":
        return build_slack_error_payload(
            "This Slack workspace is connected to multiple Zroky projects. "
            "Run Ask Judgment from the project-specific channel configured in Zroky."
        )
    return build_slack_error_payload(
        "Slack is not connected to a Zroky project for this workspace/channel. "
        "Connect Slack from Zroky Settings -> Integrations."
    )


@router.get("/slack/status", response_model=SlackInstallStatusResponse)
def get_slack_status(
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> SlackInstallStatusResponse:
    ensure_project_exists(db, tenant_id)
    return SlackInstallStatusResponse(**build_slack_status(get_slack_install(db, tenant_id)))


@router.post("/slack/install", response_model=SlackInstallStartResponse)
@limiter.limit("10/minute")
def start_slack_install(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> SlackInstallStartResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admin role is required.")
    ensure_project_exists(db, context.tenant_id)
    settings = get_settings()
    _require_slack_oauth_config(settings)
    state = generate_oauth_state_with_payload(
        _oauth_state_secret(settings),
        {
            "purpose": "slack_install",
            "tenant_id": context.tenant_id,
            "subject": context.subject,
        },
    )
    params = {
        "client_id": settings.SLACK_CLIENT_ID,
        "scope": settings.SLACK_OAUTH_SCOPES,
        "redirect_uri": settings.SLACK_OAUTH_REDIRECT_URL,
        "state": state,
    }
    return SlackInstallStartResponse(authorization_url=f"{_SLACK_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/slack/callback")
@limiter.limit("10/minute")
async def complete_slack_install(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    settings = get_settings()
    _require_slack_oauth_config(settings)
    state_payload = verify_oauth_state_with_payload(state, _oauth_state_secret(settings))
    if state_payload is None or state_payload.get("purpose") != "slack_install":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired Slack OAuth state.")
    tenant_id = str(state_payload.get("tenant_id") or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slack OAuth state missing tenant.")
    ensure_project_exists(db, tenant_id)
    payload = await _exchange_slack_code(code, settings)
    team_id, team_name = _extract_slack_team(payload)
    webhook_url, channel_id, channel_name = _extract_incoming_webhook(payload)
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Slack OAuth response missing access token.")
    bot_user_id_raw = payload.get("bot_user_id")
    bot_user_id = str(bot_user_id_raw).strip() if isinstance(bot_user_id_raw, str) and bot_user_id_raw.strip() else None
    scope_raw = payload.get("scope")
    scope = str(scope_raw).strip() if isinstance(scope_raw, str) and scope_raw.strip() else settings.SLACK_OAUTH_SCOPES
    now = datetime.now(timezone.utc)
    install = get_slack_install(db, tenant_id)
    if install is None:
        install = TenantSlackInstall(tenant_id=tenant_id, installed_at=now)
    install.team_id = team_id
    install.team_name = team_name
    install.access_token_encrypted = encrypt_slack_token(access_token)
    install.webhook_url = encrypt_slack_webhook_url(webhook_url)
    install.channel_id = channel_id
    install.channel_name = channel_name
    install.bot_user_id = bot_user_id
    install.scope = scope
    install.installed_by_user = str(state_payload.get("subject") or "").strip() or None
    install.updated_at = now
    db.add(install)
    config = get_or_create_dashboard_config(db, tenant_id)
    notification_settings = get_notification_settings(config)
    notification_settings["slack_enabled"] = True
    set_notification_settings(config, notification_settings)
    db.add(config)
    db.commit()
    return RedirectResponse(url=f"{settings.FRONTEND_URL.rstrip('/')}/settings/integrations/slack?connected=1")


@router.delete("/slack/install", response_model=SlackInstallStatusResponse)
@limiter.limit("10/minute")
def disconnect_slack(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> SlackInstallStatusResponse:
    ensure_project_exists(db, tenant_id)
    install = get_slack_install(db, tenant_id)
    if install is not None:
        db.delete(install)
    config = get_or_create_dashboard_config(db, tenant_id)
    notification_settings = get_notification_settings(config)
    notification_settings["slack_enabled"] = False
    set_notification_settings(config, notification_settings)
    db.add(config)
    db.commit()
    return SlackInstallStatusResponse(**build_slack_status(None))


@router.post("/slack/test", response_model=SlackTestMessageResponse)
@limiter.limit("10/minute")
async def send_slack_test_message(
    request: Request,
    body: SlackTestMessageRequest,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> SlackTestMessageResponse:
    ensure_project_exists(db, tenant_id)
    install = get_slack_install(db, tenant_id)
    if install is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slack is not connected for this project.")
    text = body.text or "Zroky Slack integration is connected. You will receive alerts and reliability events here."
    ok = await send_slack_message(db, tenant_id, text)
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Slack test message failed.")
    return SlackTestMessageResponse(ok=True, message="Slack test message sent.")


@router.post("/slack/command")
@limiter.limit("60/minute")
async def handle_slack_command(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    form = await _read_verified_slack_form(request)
    resolution = resolve_slack_install(
        db,
        team_id=_form_value(form, "team_id"),
        channel_id=_form_value(form, "channel_id"),
    )
    if resolution.install is None:
        return _slack_resolution_error(resolution.error)

    response_url = _form_value(form, "response_url")
    if response_url:
        background_tasks.add_task(
            answer_and_post_slack_question,
            project_id=resolution.install.tenant_id,
            slack_text=_form_value(form, "text"),
            response_url=response_url,
        )
        return build_slack_working_payload()

    try:
        return answer_slack_question(
            db,
            project_id=resolution.install.tenant_id,
            slack_text=_form_value(form, "text"),
        )
    except Exception:
        logger.exception("slack command failed team=%s", _form_value(form, "team_id"))
        return build_slack_error_payload("Ask Judgment failed. Retry from Slack or open Zroky dashboard.")


@router.post("/slack/actions")
@limiter.limit("60/minute")
async def handle_slack_actions(
    request: Request,
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    form = await _read_verified_slack_form(request)
    raw_payload = _form_value(form, "payload") or "{}"
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Slack action payload.",
        ) from None
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Slack action payload.",
        )

    team = payload.get("team") if isinstance(payload.get("team"), dict) else {}
    channel = payload.get("channel") if isinstance(payload.get("channel"), dict) else {}
    resolution = resolve_slack_install(
        db,
        team_id=str(team.get("id") or payload.get("team_id") or "").strip(),
        channel_id=str(channel.get("id") or "").strip(),
    )
    if resolution.install is None:
        return _slack_resolution_error(resolution.error)

    actions = payload.get("actions")
    if not isinstance(actions, list) or not actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack action payload missing action.",
        )
    action = actions[0] if isinstance(actions[0], dict) else {}
    action_id = str(action.get("action_id") or "").strip()
    if action_id not in {"judgment_investigate", "judgment_root_cause", "judgment_similar"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown Slack action.",
        )

    try:
        return answer_slack_action(
            db,
            project_id=resolution.install.tenant_id,
            action_id=action_id,
            value=str(action.get("value") or ""),
        )
    except Exception:
        logger.exception("slack action failed action=%s", action_id)
        return build_slack_error_payload("Ask Judgment failed. Retry from Slack or open Zroky dashboard.")


@router.get("/teams/status", response_model=TeamsInstallStatusResponse)
def get_teams_status(
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> TeamsInstallStatusResponse:
    ensure_project_exists(db, tenant_id)
    return TeamsInstallStatusResponse(**build_teams_status(get_teams_install(db, tenant_id)))


@router.put("/teams/install", response_model=TeamsInstallStatusResponse)
@limiter.limit("10/minute")
def upsert_teams_install(
    request: Request,
    body: TeamsInstallRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> TeamsInstallStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admin role is required.")
    ensure_project_exists(db, context.tenant_id)
    ensure_teams_webhook_encryption_ready()
    now = datetime.now(timezone.utc)
    channel_name = body.channel_name.strip() if body.channel_name and body.channel_name.strip() else None
    install = get_teams_install(db, context.tenant_id)
    if install is None:
        install = TenantTeamsInstall(tenant_id=context.tenant_id, installed_at=now)
    install.webhook_url_encrypted = encrypt_teams_webhook_url(body.webhook_url)
    install.channel_name = channel_name
    install.connector_type = "webhook"
    install.installed_by_user = context.subject
    install.updated_at = now
    db.add(install)
    db.commit()
    db.refresh(install)
    return TeamsInstallStatusResponse(**build_teams_status(install))


@router.delete("/teams/install", response_model=TeamsInstallStatusResponse)
@limiter.limit("10/minute")
def disconnect_teams(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> TeamsInstallStatusResponse:
    ensure_project_exists(db, tenant_id)
    install = get_teams_install(db, tenant_id)
    if install is not None:
        db.delete(install)
        db.commit()
    return TeamsInstallStatusResponse(**build_teams_status(None))


@router.post("/teams/test", response_model=TeamsTestMessageResponse)
@limiter.limit("10/minute")
async def send_teams_test_message(
    request: Request,
    body: TeamsTestMessageRequest,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> TeamsTestMessageResponse:
    ensure_project_exists(db, tenant_id)
    install = get_teams_install(db, tenant_id)
    if install is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Microsoft Teams is not connected for this project.")
    text = body.text or "Zroky Microsoft Teams integration is connected. You will receive alerts and reliability events here."
    ok = await send_teams_message(db, tenant_id, text)
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Microsoft Teams test message failed.")
    return TeamsTestMessageResponse(ok=True, message="Microsoft Teams test message sent.")
