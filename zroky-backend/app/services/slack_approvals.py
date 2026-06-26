from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import RuntimePolicyDecision
from app.services.runtime_policy import (
    RuntimePolicyApprovalConflict,
    expire_runtime_policy_decision,
    resolve_runtime_policy_decision,
)

_SCHEMA_VERSION = "zroky.slack_approval.v1"
_APPROVE_ACTION_ID = "runtime_policy_approve"
_REJECT_ACTION_ID = "runtime_policy_reject"
SLACK_APPROVAL_ACTION_IDS = {_APPROVE_ACTION_ID, _REJECT_ACTION_ID}


class SlackApprovalError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _approval_secret() -> str:
    settings = get_settings()
    secret = (
        settings.OAUTH_STATE_SECRET
        or settings.AUTH_JWT_SECRET
        or settings.SLACK_SIGNING_SECRET
        or ""
    ).strip()
    if not secret:
        raise SlackApprovalError("Slack approval signing secret is not configured.")
    return secret


def _signature(payload: dict[str, Any]) -> str:
    return hmac.new(_approval_secret().encode("utf-8"), _json_dumps(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def _parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _escape(value: Any) -> str:
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _button(label: str, action_id: str, value: str, *, style: Literal["primary", "danger"] | None = None) -> dict[str, Any]:
    button: dict[str, Any] = {
        "type": "button",
        "text": {"type": "plain_text", "text": label},
        "action_id": action_id,
        "value": value,
    }
    if style:
        button["style"] = style
    return button


def _link_button(label: str, url: str) -> dict[str, Any]:
    return {
        "type": "button",
        "text": {"type": "plain_text", "text": label},
        "url": url,
    }


def slack_approval_value(row: RuntimePolicyDecision, *, issued_at: datetime | None = None) -> str:
    if not row.approval_scope_hash:
        raise SlackApprovalError("Runtime policy decision is missing an approval scope hash.")
    request = _loads(row.request_json, {})
    tool_args = request.get("tool_args") if isinstance(request, dict) else {}
    intent_digest = tool_args.get("intent_digest") if isinstance(tool_args, dict) else None
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "project_id": row.project_id,
        "decision_id": row.id,
        "approval_scope_hash": row.approval_scope_hash,
        "intent_digest": intent_digest,
        "required_approval_count": row.required_approval_count or 1,
        "issued_at": _iso(issued_at or _now()),
        "expires_at": _iso(row.expires_at),
    }
    payload["signature"] = _signature(payload)
    return _json_dumps(payload)


def verify_slack_approval_value(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SlackApprovalError("Invalid Slack approval token.") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA_VERSION:
        raise SlackApprovalError("Invalid Slack approval token.")
    signature = str(payload.get("signature") or "")
    unsigned = {key: payload[key] for key in payload if key != "signature"}
    if not signature or not hmac.compare_digest(signature, _signature(unsigned)):
        raise SlackApprovalError("Invalid Slack approval token signature.")
    for required in ("project_id", "decision_id", "approval_scope_hash"):
        if not str(payload.get(required) or "").strip():
            raise SlackApprovalError("Slack approval token is missing required context.")
    return payload


def build_runtime_policy_approval_slack_payload(row: RuntimePolicyDecision) -> dict[str, Any]:
    dashboard_url = get_settings().FRONTEND_URL.rstrip("/")
    value = slack_approval_value(row)
    required = max(1, row.required_approval_count or 1)
    recorded = max(0, row.approval_count or 0)
    fields = [
        {"type": "mrkdwn", "text": f"*Approval ID*\n`{_escape(row.id)}`"},
        {"type": "mrkdwn", "text": f"*Action*\n{_escape(row.action_type or row.tool_name or 'runtime action')}"},
        {"type": "mrkdwn", "text": f"*Agent*\n{_escape(row.agent_name or 'unknown')}"},
        {"type": "mrkdwn", "text": f"*Progress*\n{recorded}/{required} approvals"},
    ]
    if row.expires_at is not None:
        fields.append({"type": "mrkdwn", "text": f"*Expires*\n{_escape(_iso(row.expires_at))}"})
    return {
        "text": f"Zroky approval required: {row.action_type or row.tool_name or row.id}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*Zroky approval required*\n"
                        "Approve or reject only after verifying the exact action effect in Zroky."
                    ),
                },
            },
            {"type": "section", "fields": fields},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Scope hash `{_escape(row.approval_scope_hash)}`",
                    }
                ],
            },
            {
                "type": "actions",
                "elements": [
                    _button("Approve", _APPROVE_ACTION_ID, value, style="primary"),
                    _button("Reject", _REJECT_ACTION_ID, value, style="danger"),
                    _link_button("Open in Zroky", f"{dashboard_url}/approvals?decision_id={row.id}"),
                ],
            },
        ],
    }


def resolve_slack_approval_action(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    value: str,
    slack_user_id: str | None,
    slack_user_name: str | None = None,
    allowed_slack_user_ids: list[str] | None = None,
) -> dict[str, Any]:
    if action_id not in SLACK_APPROVAL_ACTION_IDS:
        raise SlackApprovalError("Unknown Slack approval action.")
    try:
        token = verify_slack_approval_value(value)
    except SlackApprovalError as exc:
        return _approval_error_payload(str(exc))
    if token["project_id"] != project_id:
        return _approval_error_payload("Slack approval token is not scoped to this Zroky project.")

    row = db.execute(
        select(RuntimePolicyDecision).where(
            RuntimePolicyDecision.project_id == project_id,
            RuntimePolicyDecision.id == token["decision_id"],
        )
    ).scalar_one_or_none()
    if row is None:
        return _approval_error_payload("This approval no longer exists in Zroky.")
    if row.approval_scope_hash != token["approval_scope_hash"]:
        return _approval_error_payload("Slack approval context is stale. Reopen the current approval in Zroky.")
    if row.status != "pending_approval":
        return _approval_error_payload(f"This approval is already {row.status}.")

    actor = _slack_actor(slack_user_id, slack_user_name)
    allowed_ids = {str(item).strip() for item in (allowed_slack_user_ids or []) if str(item).strip()}
    if not allowed_ids:
        return _approval_error_payload("Slack approvals are not enabled for any authorized Slack user.")
    if not slack_user_id or slack_user_id not in allowed_ids:
        return _approval_error_payload("This Slack user is not authorized to approve Zroky actions.")
    if row.expires_at is not None:
        expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= _now():
            expire_runtime_policy_decision(
                db,
                project_id=project_id,
                decision_id=row.id,
                actor=actor,
                reason="Slack approval rejected stale expired context.",
            )
            return _approval_error_payload("This approval expired. Create a fresh action intent before approving.")

    approved = action_id == _APPROVE_ACTION_ID
    try:
        resolved = resolve_runtime_policy_decision(
            db,
            project_id=project_id,
            decision_id=row.id,
            approved=approved,
            actor=actor,
            reason=_slack_reason(approved=approved, slack_user_id=slack_user_id, slack_user_name=slack_user_name),
        )
    except RuntimePolicyApprovalConflict as exc:
        return _approval_error_payload(str(exc))
    if resolved is None:
        return _approval_error_payload("This approval is no longer pending.")
    return _approval_success_payload(resolved, approved=approved)


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _slack_actor(slack_user_id: str | None, slack_user_name: str | None) -> str:
    user_id = str(slack_user_id or "").strip()
    if user_id:
        return f"slack:{user_id}"[:128]
    user_name = str(slack_user_name or "").strip()
    return f"slack:{user_name or 'unknown'}"[:128]


def _slack_reason(*, approved: bool, slack_user_id: str | None, slack_user_name: str | None) -> str:
    verb = "approved" if approved else "rejected"
    user = str(slack_user_name or slack_user_id or "unknown Slack user").strip()
    return f"Slack {verb} by {user}."


def _approval_success_payload(row: RuntimePolicyDecision, *, approved: bool) -> dict[str, Any]:
    if row.status == "pending_approval":
        text = f"Approval recorded. {row.approval_count}/{row.required_approval_count or 1} approvals complete."
    elif approved:
        text = "Approval accepted. Zroky can now continue the protected action."
    else:
        text = "Action rejected. Zroky will keep this protected action blocked."
    return {
        "response_type": "ephemeral",
        "replace_original": False,
        "text": text,
        "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": _escape(text)}}],
    }


def _approval_error_payload(message: str) -> dict[str, Any]:
    return {
        "response_type": "ephemeral",
        "replace_original": False,
        "text": message,
        "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": _escape(message)}}],
    }
