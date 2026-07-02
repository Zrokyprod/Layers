"""Cross-action ("sequence") risk detection for protected action intents.

Single-action policy (``runtime_policy``) answers "is *this* action allowed?".
This module answers the question no single-action guard can: "do the recent
actions of this agent, taken *together*, form a dangerous pattern?" - e.g. a
bulk/sensitive read followed by an external send is an exfiltration shape even
when every step is individually allowed.

Design constraints (v1):
  - Pure detector. The only DB access is *reading* recent action intents; this
    module never mutates a decision. Escalation of the persisted decision row is
    owned by ``runtime_policy.escalate_runtime_policy_result_for_sequence_risk``
    where the audit/trace helpers live.
  - Deterministic rules only. No model calls, no probabilities. False positives
    are worse than misses here, so the default recommendation is
    ``hold_for_approval`` (a human looks); ``block`` is reserved for a single
    high-confidence pattern.
  - No new migration. ``ActionIntent.trace_id`` lives inside
    ``trace_context_json`` (not an indexed column), so we load a bounded recent
    window using the existing ``(project_id, agent_id, created_at)`` index and
    filter to the same ``trace_id`` in Python.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import ActionIntent

logger = logging.getLogger(__name__)


# Recommendation vocabulary consumed by the escalation helper.
SEQUENCE_HOLD = "hold_for_approval"
SEQUENCE_BLOCK = "block"

# Lookback bounds - keep the scan cheap and deterministic.
_LOOKBACK_LIMIT = 50
_LOOKBACK_WINDOW = timedelta(minutes=30)
_MONEY_WINDOW = timedelta(minutes=15)
_MONEY_COUNT_THRESHOLD = 3  # 3+ money actions in a short window

# Deterministic classification markers (matched against action_type + flattened
# resource/parameters/purpose text, all lowercased).
_MUTATING_KINDS = {"transfer", "update", "send", "execute", "delete"}
_URL_MARKERS = ("http://", "https://", "://", "webhook")
_EXPORT_MARKERS = ("export", "download", "dump", "backup", "extract", "scrape")
_READ_MARKERS = ("read", "list", "search", "query", "fetch", "select", "report", "get_all", "all_", "bulk")
_MONEY_MARKERS = ("refund", "transfer", "payout", "payment", "charge", "wire", "disburse", "remit")
_CREDENTIAL_MARKERS = (
    "password",
    "credential",
    "secret",
    "api_key",
    "apikey",
    "token",
    "mfa",
    "sso",
    "unlock",
    "key_rotation",
    "rotate_key",
    "security_group",
    "permission",
    "privilege",
    "grant_role",
)
_SEND_MARKERS = ("email", "send", "mail", "message", "notify", "sms", "forward", "webhook", "post")


@dataclass(frozen=True)
class SequenceRiskSignal:
    """A detected cross-action pattern that should escalate the current action."""

    pattern: str
    recommended: str  # SEQUENCE_HOLD | SEQUENCE_BLOCK
    confidence: str  # "high" | "medium"
    reason: str
    trace_id: str | None
    contributing_action_ids: list[str]


@dataclass(frozen=True)
class _Step:
    action_id: str
    operation_kind: str
    action_type: str
    created_at: datetime
    trace_id: str | None
    is_external: bool
    is_read_or_export: bool
    is_money: bool
    is_credential_update: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _has_any(haystack: str, markers: tuple[str, ...]) -> bool:
    return any(marker in haystack for marker in markers)


def _classify(intent: ActionIntent) -> _Step:
    action_type = (intent.action_type or "").strip().lower()
    operation_kind = (intent.operation_kind or "").strip().lower()
    trace_context = _json_loads(intent.trace_context_json, {})
    trace_id = None
    if isinstance(trace_context, dict):
        raw_trace = trace_context.get("trace_id")
        trace_id = str(raw_trace) if raw_trace else None

    # Flatten the free-form payload for keyword scanning. resource/parameters
    # carry the destination + shape of the action (recipient, url, scope).
    blob_parts = [action_type]
    for column in (intent.resource_json, intent.parameters_json, intent.purpose_json):
        loaded = _json_loads(column, {})
        if loaded:
            blob_parts.append(json.dumps(loaded, default=str).lower())
    blob = " ".join(blob_parts)

    is_url = _has_any(blob, _URL_MARKERS)
    is_export = _has_any(action_type, _EXPORT_MARKERS) or _has_any(blob, _EXPORT_MARKERS)
    has_email_recipient = "@" in blob
    is_send = operation_kind == "send" or _has_any(action_type, _SEND_MARKERS)

    # External = leaves the trust boundary. A URL/webhook or an export is
    # unambiguous; a SEND with an email recipient is treated as external too
    # (conservative: it only ever triggers a HOLD, never a BLOCK on its own).
    is_external = is_url or is_export or (is_send and has_email_recipient)

    # Read/collect = a data-gathering step. There is no dedicated READ operation
    # kind in the taxonomy, so detect via non-mutating kind + read markers, or an
    # explicit export.
    is_read_or_export = is_export or (
        operation_kind not in _MUTATING_KINDS and _has_any(action_type, _READ_MARKERS)
    )

    is_money = operation_kind == "transfer" or _has_any(action_type, _MONEY_MARKERS)

    is_credential_update = _has_any(blob, _CREDENTIAL_MARKERS) and (
        operation_kind in {"update", "execute"} or "reset" in action_type or _has_any(action_type, _CREDENTIAL_MARKERS)
    )

    return _Step(
        action_id=intent.id,
        operation_kind=operation_kind,
        action_type=action_type,
        created_at=_as_aware(intent.created_at),
        trace_id=trace_id,
        is_external=is_external,
        is_read_or_export=is_read_or_export,
        is_money=is_money,
        is_credential_update=is_credential_update,
    )


def detect_sequence_pattern(current: _Step, prior: list[_Step]) -> SequenceRiskSignal | None:
    """Pure rule engine. ``current`` is the action being decided; ``prior`` are
    the earlier steps in the same run/window, newest-first order not required.

    Rules are evaluated most-severe first and the first match wins. All rules
    treat ``current`` as the step that *completes* the pattern, which keeps the
    escalation precise: we hold/block exactly the action that would do harm.
    """

    def contributing(extra: list[_Step]) -> list[str]:
        return [current.action_id, *[s.action_id for s in extra]]

    # Rule 3 (most severe): credential/security change followed by an external
    # send/export = account-takeover exfiltration. High confidence only when the
    # outward channel is unambiguous (URL/webhook or an export), else HOLD.
    if current.is_external:
        cred_steps = [s for s in prior if s.is_credential_update]
        if cred_steps:
            high_confidence = current.is_read_or_export or _has_any(current.action_type, _URL_MARKERS + _EXPORT_MARKERS)
            return SequenceRiskSignal(
                pattern="credential_change_then_external_transfer",
                recommended=SEQUENCE_BLOCK if high_confidence else SEQUENCE_HOLD,
                confidence="high" if high_confidence else "medium",
                reason=(
                    "a credential/security change was followed by an external "
                    "send/export in the same run - account-takeover exfiltration shape"
                ),
                trace_id=current.trace_id,
                contributing_action_ids=contributing(cred_steps[:3]),
            )

    # Rule 1: bulk/sensitive read followed by an external send/export = data
    # exfiltration. HOLD.
    if current.is_external:
        read_steps = [s for s in prior if s.is_read_or_export]
        if read_steps:
            return SequenceRiskSignal(
                pattern="sensitive_read_then_external_send",
                recommended=SEQUENCE_HOLD,
                confidence="medium",
                reason=(
                    "a sensitive/bulk read was followed by an external send/export "
                    "in the same run - data-exfiltration shape"
                ),
                trace_id=current.trace_id,
                contributing_action_ids=contributing(read_steps[:3]),
            )

    # Rule 2: 3+ money-moving actions in a short window = fund-drain. HOLD.
    if current.is_money:
        window_start = current.created_at - _MONEY_WINDOW
        money_steps = [s for s in prior if s.is_money and s.created_at >= window_start]
        if len(money_steps) + 1 >= _MONEY_COUNT_THRESHOLD:
            return SequenceRiskSignal(
                pattern="rapid_repeated_money_movement",
                recommended=SEQUENCE_HOLD,
                confidence="medium",
                reason=(
                    f"{len(money_steps) + 1} money-moving actions within "
                    f"{int(_MONEY_WINDOW.total_seconds() // 60)} minutes - fund-drain shape"
                ),
                trace_id=current.trace_id,
                contributing_action_ids=contributing(money_steps[:3]),
            )

    return None


def evaluate_sequence_risk(
    db: Session,
    *,
    project_id: str,
    intent: ActionIntent,
) -> SequenceRiskSignal | None:
    """Load the recent action window for ``intent``'s agent, group it to the same
    run, and return a sequence-risk signal if a dangerous pattern completes at
    ``intent``. Returns ``None`` on no match. Never raises into the caller - a
    detector failure must not block an otherwise-allowed action.
    """

    try:
        current = _classify(intent)
        # A "run" is identified by trace_id. Without one we cannot establish that
        # recent actions belong together, so we do not fire - this keeps the
        # signal precise and avoids grouping unrelated actions across the project.
        if not current.trace_id:
            return None

        window_start = _now() - _LOOKBACK_WINDOW
        query = select(ActionIntent).where(
            ActionIntent.project_id == project_id,
            ActionIntent.created_at >= window_start,
        )
        if intent.agent_id:
            query = query.where(ActionIntent.agent_id == intent.agent_id)
        query = query.order_by(desc(ActionIntent.created_at)).limit(_LOOKBACK_LIMIT)

        rows = db.execute(query).scalars().all()

        # Group to the same run (same trace_id), excluding the current action.
        prior: list[_Step] = []
        seen: set[str] = set()
        for row in rows:
            if row.id in seen or row.id == current.action_id:
                continue
            seen.add(row.id)
            step = _classify(row)
            if step.trace_id == current.trace_id:
                prior.append(step)

        return detect_sequence_pattern(current, prior)
    except Exception:  # pragma: no cover - defensive: never break the gate path
        logger.warning("sequence risk evaluation failed for intent %s", getattr(intent, "id", "?"), exc_info=True)
        return None
