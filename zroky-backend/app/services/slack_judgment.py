from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import TenantSlackInstall
from app.db.session import SessionLocal
from app.services.ask import AskAnswer, answer_question

_MAX_TIMESTAMP_SKEW_SECONDS = 60 * 5
_MAX_SECTION_TEXT = 2800
_ISSUE_HINT_RE = re.compile(
    r"\b(?:issue|incident|anomaly)[:#\s]+([A-Za-z0-9][A-Za-z0-9_.:-]{1,63})",
    re.IGNORECASE,
)
_CALL_HINT_RE = re.compile(
    r"\b(?:call|trace|request)[:#\s]+([A-Za-z0-9][A-Za-z0-9_.:-]{1,63})",
    re.IGNORECASE,
)
_COMMAND_HELP = {"help", "--help", "-h", "?"}


@dataclass(frozen=True)
class SlackInstallResolution:
    install: TenantSlackInstall | None
    error: Literal["not_connected", "ambiguous"] | None = None


@dataclass(frozen=True)
class SlackQuestion:
    question: str
    context: dict[str, str]


def verify_slack_signature(
    signing_secret: str | None,
    timestamp: str | None,
    raw_body: bytes,
    signature: str | None,
    *,
    now: int | None = None,
) -> bool:
    """Validate Slack's v0 HMAC signature over the exact raw request body."""
    secret = (signing_secret or "").strip()
    sig = (signature or "").strip()
    ts = (timestamp or "").strip()
    if not secret or not sig or not ts:
        return False
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    current = int(time.time()) if now is None else int(now)
    if abs(current - ts_int) > _MAX_TIMESTAMP_SKEW_SECONDS:
        return False

    base = b"v0:" + ts.encode("utf-8") + b":" + raw_body
    digest = hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, sig)


def resolve_slack_install(
    db: Session,
    *,
    team_id: str | None,
    channel_id: str | None,
) -> SlackInstallResolution:
    """Resolve a Slack workspace/channel request to one Zroky project install."""
    team = (team_id or "").strip()
    channel = (channel_id or "").strip()
    if not team:
        return SlackInstallResolution(install=None, error="not_connected")

    installs = db.execute(
        select(TenantSlackInstall).where(TenantSlackInstall.team_id == team)
    ).scalars().all()
    if not installs:
        return SlackInstallResolution(install=None, error="not_connected")

    exact = [install for install in installs if channel and install.channel_id == channel]
    if len(exact) == 1:
        return SlackInstallResolution(install=exact[0])
    if len(installs) == 1:
        return SlackInstallResolution(install=installs[0])
    return SlackInstallResolution(install=None, error="ambiguous")


def build_slack_question(text: str | None) -> SlackQuestion | None:
    raw = (text or "").strip()
    if not raw or raw.lower() in _COMMAND_HELP:
        return None

    issue_id = _extract_hint(_ISSUE_HINT_RE, raw)
    call_id = _extract_hint(_CALL_HINT_RE, raw)
    lower = raw.lower()

    if lower.startswith("investigate "):
        target = raw.split(None, 1)[1].strip()
        issue_id = issue_id or _identifier_after_verb(raw, "investigate")
        subject = f"issue {issue_id}" if issue_id else target
        question = (
            f"Investigate {subject}. What is the root cause, user impact, "
            "and next action?"
        )
    elif lower.startswith("root cause"):
        issue_id = issue_id or _identifier_after_verb(raw, "root cause")
        subject = f"issue {issue_id}" if issue_id else raw
        question = f"What is the likely root cause for {subject}?"
    elif lower.startswith("similar"):
        subject = raw
        if issue_id:
            subject = f"issue {issue_id}"
        question = f"Show similar cases for {subject} from the last 30 days."
    else:
        question = raw

    context: dict[str, str] = {}
    if issue_id:
        context["issue_id"] = issue_id
    if call_id:
        context["call_id"] = call_id
    return SlackQuestion(question=question, context=context)


def answer_slack_question(
    db: Session,
    *,
    project_id: str,
    slack_text: str | None,
) -> dict[str, Any]:
    parsed = build_slack_question(slack_text)
    if parsed is None:
        return build_slack_help_payload()
    answer = answer_question(
        db,
        project_id=project_id,
        question=parsed.question,
        context=parsed.context,
    )
    return build_slack_answer_payload(
        answer,
        question=parsed.question,
        project_id=project_id,
    )


def answer_slack_action(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    value: str | None,
) -> dict[str, Any]:
    data = _safe_json_dict(value)
    parsed = _question_from_action(action_id, data)
    answer = answer_question(
        db,
        project_id=project_id,
        question=parsed.question,
        context=parsed.context,
    )
    return build_slack_answer_payload(
        answer,
        question=parsed.question,
        project_id=project_id,
    )


def answer_and_post_slack_question(
    *,
    project_id: str,
    slack_text: str | None,
    response_url: str,
) -> bool:
    try:
        with SessionLocal() as db:
            payload = answer_slack_question(db, project_id=project_id, slack_text=slack_text)
    except Exception:
        payload = build_slack_error_payload(
            "Ask Judgment failed. Retry from Slack or open Zroky dashboard."
        )
    return post_slack_response_url(response_url, payload)


def post_slack_response_url(response_url: str, payload: dict[str, Any]) -> bool:
    url = response_url.strip()
    if not url.startswith("https://hooks.slack.com/commands/"):
        return False
    try:
        response = httpx.post(url, json=payload, timeout=10.0)
    except Exception:
        return False
    return 200 <= response.status_code < 300


def build_slack_answer_payload(
    answer: AskAnswer,
    *,
    question: str,
    project_id: str,
) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": _truncate(
                    f"*Ask Judgment*\n{_escape_mrkdwn(answer.answer)}",
                    _MAX_SECTION_TEXT,
                ),
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Project `{_escape_mrkdwn(project_id)}` | "
                        f"intent `{_escape_mrkdwn(answer.intent)}` | "
                        f"confidence `{answer.confidence:.2f}`"
                    ),
                }
            ],
        },
    ]

    if answer.suggested_actions:
        action_lines = "\n".join(
            f"- {_escape_mrkdwn(action)}" for action in answer.suggested_actions[:5]
        )
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _truncate(f"*Next actions*\n{action_lines}", _MAX_SECTION_TEXT),
                },
            }
        )

    evidence_lines = _evidence_lines(answer.evidence)
    if evidence_lines:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _truncate(f"*Evidence*\n{evidence_lines}", _MAX_SECTION_TEXT),
                },
            }
        )

    dashboard_url = get_settings().FRONTEND_URL.rstrip("/")
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open dashboard"},
                    "url": dashboard_url,
                }
            ],
        }
    )

    return {
        "response_type": "ephemeral",
        "replace_original": False,
        "text": answer.answer,
        "blocks": blocks,
    }


def build_slack_help_payload() -> dict[str, Any]:
    text = (
        "*Ask Judgment in Slack*\n"
        "`/judgment investigate issue-123`\n"
        "`/judgment root cause issue-123`\n"
        "`/judgment similar cases for agent checkout-agent`\n"
        "`/judgment why did agent checkout-agent fail today?`"
    )
    return {
        "response_type": "ephemeral",
        "text": "Ask Judgment usage",
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        ],
    }


def build_slack_working_payload() -> dict[str, Any]:
    return {
        "response_type": "ephemeral",
        "text": "Ask Judgment is investigating. I will post the answer in this thread.",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Ask Judgment is investigating. I will post the answer in this thread.",
                },
            }
        ],
    }


def build_slack_error_payload(message: str) -> dict[str, Any]:
    return {
        "response_type": "ephemeral",
        "text": message,
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": _escape_mrkdwn(message)},
            }
        ],
    }


def build_judgment_alert_payload(
    *,
    text: str,
    categories: list[str],
    agent_name: str | None,
    diagnosis_id: str | None,
) -> dict[str, Any]:
    """Build a Slack webhook payload with one-click Judgment investigations."""
    cats = [str(category).strip() for category in categories if str(category).strip()]
    agent = (agent_name or "").strip() or "unknown agent"
    value = _action_value(
        {
            "categories": cats,
            "agent_name": agent_name,
            "diagnosis_id": diagnosis_id,
        }
    )
    fields = [
        {"type": "mrkdwn", "text": f"*Agent*\n`{_escape_mrkdwn(agent)}`"},
        {"type": "mrkdwn", "text": f"*Failure*\n`{_escape_mrkdwn(', '.join(cats) or 'Unknown')}`"},
    ]
    if diagnosis_id:
        fields.append(
            {"type": "mrkdwn", "text": f"*Diagnosis*\n`{_escape_mrkdwn(diagnosis_id)}`"}
        )
    return {
        "text": text,
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": _escape_mrkdwn(text)},
            },
            {"type": "section", "fields": fields},
            {
                "type": "actions",
                "elements": [
                    _button("Investigate", "judgment_investigate", value, style="primary"),
                    _button("Root cause", "judgment_root_cause", value),
                    _button("Similar cases", "judgment_similar", value),
                ],
            },
        ],
    }


def build_new_issue_alert_payload(
    *,
    issue_id: str,
    failure_code: str,
    severity: str | None,
    agent_name: str | None,
    diagnosis_id: str | None,
    call_id: str | None,
) -> dict[str, Any]:
    """Build a Slack payload for a newly-created customer issue."""
    code = _clean_optional(failure_code) or "UNKNOWN"
    issue = _clean_optional(issue_id) or "unknown"
    severity_text = _clean_optional(severity) or "unknown"
    agent = _clean_optional(agent_name) or "unknown agent"
    value = _action_value(
        {
            "issue_id": issue,
            "call_id": call_id,
            "categories": [code],
            "agent_name": agent_name,
            "diagnosis_id": diagnosis_id,
        }
    )
    text = f"New Zroky issue: {code}"
    fields = [
        _field("Issue", issue),
        _field("Failure", code),
        _field("Severity", severity_text),
        _field("Agent", agent),
    ]
    if diagnosis_id:
        fields.append(_field("Diagnosis", diagnosis_id))
    if call_id:
        fields.append(_field("Call", call_id))
    return {
        "text": text,
        "blocks": [
            _section(f"*{text}*"),
            {"type": "section", "fields": fields},
            {
                "type": "actions",
                "elements": [
                    _button("Investigate", "judgment_investigate", value, style="primary"),
                    _button("Root cause", "judgment_root_cause", value),
                    _button("Similar cases", "judgment_similar", value),
                    _link_button("Open issue", _dashboard_url(f"/issues/{issue}")),
                ],
            },
        ],
    }


def build_replay_verified_alert_payload(
    *,
    run_id: str,
    source_issue_id: str | None = None,
    source_call_id: str | None = None,
    failure_code: str | None = None,
    verification_status: str | None = None,
    git_sha: str | None = None,
) -> dict[str, Any]:
    """Build a Slack payload for a replay run that verified a fix."""
    run = _clean_optional(run_id) or "unknown"
    status_text = _clean_optional(verification_status) or "verified_fix"
    value = _action_value(
        {
            "issue_id": source_issue_id,
            "call_id": source_call_id,
            "categories": [failure_code] if failure_code else [],
        }
    )
    fields = [
        _field("Replay run", run),
        _field("Verification", status_text),
    ]
    if source_issue_id:
        fields.append(_field("Issue", source_issue_id))
    if source_call_id:
        fields.append(_field("Call", source_call_id))
    if git_sha:
        fields.append(_field("Git SHA", str(git_sha)[:12]))
    return {
        "text": f"Replay verified fix: {run}",
        "blocks": [
            _section(f"*Replay verified fix*\nRun `{_escape_mrkdwn(run)}` passed trusted verification."),
            {"type": "section", "fields": fields},
            {
                "type": "actions",
                "elements": [
                    _button("Investigate", "judgment_investigate", value, style="primary"),
                    _link_button("Open replay", _dashboard_url(f"/replay/{run}")),
                ],
            },
        ],
    }


def build_replay_failed_alert_payload(
    *,
    run_id: str,
    status: str,
    source_issue_id: str | None = None,
    source_call_id: str | None = None,
    failure_code: str | None = None,
    verification_status: str | None = None,
    fail_count: int | None = None,
    error_count: int | None = None,
    git_sha: str | None = None,
) -> dict[str, Any]:
    """Build a Slack payload for a non-CI replay run that failed or errored."""
    run = _clean_optional(run_id) or "unknown"
    run_status = _clean_optional(status) or "failed"
    value = _action_value(
        {
            "issue_id": source_issue_id,
            "call_id": source_call_id,
            "categories": [failure_code] if failure_code else [],
        }
    )
    fields = [
        _field("Replay run", run),
        _field("Status", run_status),
    ]
    if verification_status:
        fields.append(_field("Verification", verification_status))
    if fail_count is not None:
        fields.append(_field("Failures", str(fail_count)))
    if error_count is not None:
        fields.append(_field("Errors", str(error_count)))
    if source_issue_id:
        fields.append(_field("Issue", source_issue_id))
    if source_call_id:
        fields.append(_field("Call", source_call_id))
    if git_sha:
        fields.append(_field("Git SHA", str(git_sha)[:12]))
    return {
        "text": f"Replay failed: {run}",
        "blocks": [
            _section(f"*Replay failed*\nRun `{_escape_mrkdwn(run)}` finished with status `{_escape_mrkdwn(run_status)}`."),
            {"type": "section", "fields": fields},
            {
                "type": "actions",
                "elements": [
                    _button("Investigate", "judgment_investigate", value, style="primary"),
                    _button("Root cause", "judgment_root_cause", value),
                    _link_button("Open replay", _dashboard_url(f"/replay/{run}")),
                ],
            },
        ],
    }


def build_ci_gate_failed_alert_payload(
    *,
    run_id: str,
    status: str,
    git_sha: str | None = None,
    source_issue_id: str | None = None,
    failure_code: str | None = None,
    regressed_count: int | None = None,
    error_count: int | None = None,
    trace_count: int | None = None,
    regression_rate: float | None = None,
    threshold: float | None = None,
) -> dict[str, Any]:
    """Build a Slack payload for a failed CI gate."""
    run = _clean_optional(run_id) or "unknown"
    run_status = _clean_optional(status) or "failed"
    value = _action_value(
        {
            "issue_id": source_issue_id,
            "categories": [failure_code] if failure_code else [],
        }
    )
    fields = [
        _field("CI run", run),
        _field("Status", run_status),
    ]
    if git_sha:
        fields.append(_field("Git SHA", str(git_sha)[:12]))
    if regressed_count is not None:
        fields.append(_field("Regressions", str(regressed_count)))
    if error_count is not None:
        fields.append(_field("Errors", str(error_count)))
    if trace_count is not None:
        fields.append(_field("Traces", str(trace_count)))
    if regression_rate is not None:
        fields.append(_field("Regression rate", f"{regression_rate:.2%}"))
    if threshold is not None:
        fields.append(_field("Threshold", f"{threshold:.2%}"))
    if source_issue_id:
        fields.append(_field("Issue", source_issue_id))
    return {
        "text": f"CI gate failed: {run}",
        "blocks": [
            _section(f"*CI gate failed*\nRun `{_escape_mrkdwn(run)}` finished with status `{_escape_mrkdwn(run_status)}`."),
            {"type": "section", "fields": fields},
            {
                "type": "actions",
                "elements": [
                    _button("Investigate", "judgment_investigate", value, style="primary"),
                    _link_button("Open CI gate", _dashboard_url(f"/ci-gates/{run}")),
                ],
            },
        ],
    }


def _question_from_action(action_id: str, data: dict[str, Any]) -> SlackQuestion:
    issue_id = _clean_id(data.get("issue_id"))
    call_id = _clean_id(data.get("call_id"))
    agent_name = _clean_optional(data.get("agent_name"))
    diagnosis_id = _clean_optional(data.get("diagnosis_id"))
    categories = [
        str(category).strip()
        for category in data.get("categories", [])
        if str(category).strip()
    ]
    category_text = ", ".join(categories) if categories else "recent failures"
    agent_text = f" for agent {agent_name}" if agent_name else ""
    diagnosis_text = f" Diagnosis id: {diagnosis_id}." if diagnosis_id else ""

    context: dict[str, str] = {}
    if issue_id:
        context["issue_id"] = issue_id
    if call_id:
        context["call_id"] = call_id

    if action_id == "judgment_similar":
        question = f"Show similar {category_text} cases{agent_text} from the last 30 days.{diagnosis_text}"
    elif action_id == "judgment_root_cause":
        question = f"What is the likely root cause for {category_text}{agent_text}?{diagnosis_text}"
    else:
        question = (
            f"Investigate {category_text}{agent_text}. What is the root cause, "
            f"user impact, and next action?{diagnosis_text}"
        )
    return SlackQuestion(question=question, context=context)


def _extract_hint(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return _clean_id(match.group(1))


def _identifier_after_verb(text: str, verb: str) -> str | None:
    rest = text[len(verb):].strip()
    if not rest:
        return None
    token = rest.split()[0].strip("`'\".,;")
    if _looks_like_identifier(token):
        return _clean_id(token)
    return None


def _looks_like_identifier(value: str) -> bool:
    candidate = value.strip()
    if not 2 <= len(candidate) <= 64:
        return False
    if candidate.lower() in {"why", "what", "how", "agent", "root", "cause"}:
        return False
    return bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$", candidate)) and (
        candidate.lower().startswith(("issue", "inc", "anom"))
        or any(char.isdigit() for char in candidate)
        or any(char in candidate for char in "-_:")
    )


def _clean_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip("`'\"")
    if not text or len(text) > 64:
        return None
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$", text):
        return None
    return text


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:120] if text else None


def _safe_json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _action_value(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), default=str)[:1900]


def _button(
    label: str,
    action_id: str,
    value: str,
    *,
    style: str | None = None,
) -> dict[str, Any]:
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


def _field(label: str, value: str) -> dict[str, Any]:
    return {
        "type": "mrkdwn",
        "text": f"*{_escape_mrkdwn(label)}*\n`{_escape_mrkdwn(value)}`",
    }


def _section(text: str) -> dict[str, Any]:
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": _truncate(text, _MAX_SECTION_TEXT)},
    }


def _dashboard_url(path: str) -> str:
    base = get_settings().FRONTEND_URL.rstrip("/")
    suffix = path if path.startswith("/") else f"/{path}"
    return f"{base}{suffix}"


def _evidence_lines(evidence: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    base_url = get_settings().FRONTEND_URL.rstrip("/")
    for item in evidence[:5]:
        label = _escape_mrkdwn(str(item.get("label") or item.get("id") or "Evidence"))
        href = str(item.get("href") or "").strip()
        if href.startswith("/"):
            lines.append(f"- <{base_url}{href}|{label}>")
        else:
            lines.append(f"- {label}")
    return "\n".join(lines)


def _escape_mrkdwn(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(limit - 3, 0)] + "..."
