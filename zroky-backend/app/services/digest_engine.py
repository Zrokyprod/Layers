from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from html import escape as html_escape
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Anomaly, Call, Digest, PilotAction, ProjectMembership, ReplayRun, User
from app.services import billing_plans, entitlements_resolver

AUDIENCES: tuple[str, ...] = ("engineer", "manager", "executive")
DEFAULT_AUDIENCE = "engineer"
_SUCCESS_STATUSES = {"success", "ok", "completed", "pass", "done"}
_SEVERITIES = ("low", "medium", "high", "critical")


class WeekFormatError(ValueError):
    pass


class UnknownAudienceError(ValueError):
    pass


def monday_of(value: date) -> date:
    return value - timedelta(days=value.weekday())


def parse_week_param(value: str) -> date:
    if value is None or not str(value).strip():
        raise WeekFormatError("Week is required.")

    raw = str(value).strip()
    upper = raw.upper()
    if "-W" in upper:
        try:
            year_text, week_text = upper.split("-W", 1)
            year = int(year_text)
            week = int(week_text)
        except ValueError as exc:
            raise WeekFormatError("Expected ISO week format YYYY-WNN.") from exc
        if week < 1 or week > 53:
            raise WeekFormatError("ISO week is out of range.")
        try:
            return date.fromisocalendar(year, week, 1)
        except ValueError as exc:
            raise WeekFormatError(str(exc)) from exc

    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise WeekFormatError("Expected YYYY-MM-DD or YYYY-WNN.") from exc
    if parsed.weekday() != 0:
        raise WeekFormatError("Digest week_start must be a Monday.")
    return parsed


def parse_summary_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_recipients(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]


def get_digest(db: Session, *, project_id: str, week_start: date) -> Digest | None:
    return db.execute(
        select(Digest).where(
            Digest.project_id == project_id,
            Digest.week_start == week_start,
        )
    ).scalar_one_or_none()


def list_digests(
    db: Session,
    *,
    project_id: str,
    limit: int = 20,
    before_week_start: date | None = None,
) -> list[Digest]:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    query = select(Digest).where(Digest.project_id == project_id)
    if before_week_start is not None:
        query = query.where(Digest.week_start < before_week_start)
    query = query.order_by(Digest.week_start.desc()).limit(limit)
    return list(db.execute(query).scalars().all())


def serialize_digest(digest: Digest) -> dict[str, Any]:
    return {
        "id": digest.id,
        "project_id": digest.project_id,
        "week_start": digest.week_start.isoformat(),
        "summary": parse_summary_json(digest.summary_json),
        "html_blob": digest.html_blob,
        "sent_to_emails": parse_recipients(digest.sent_to_emails),
        "sent_at": digest.sent_at.isoformat() if digest.sent_at else None,
        "created_at": digest.created_at.isoformat() if digest.created_at else None,
        "updated_at": digest.updated_at.isoformat() if digest.updated_at else None,
    }


def serialize_digest_summary(digest: Digest) -> dict[str, Any]:
    return {
        "id": digest.id,
        "project_id": digest.project_id,
        "week_start": digest.week_start.isoformat(),
        "sent_to_emails": parse_recipients(digest.sent_to_emails),
        "sent_at": digest.sent_at.isoformat() if digest.sent_at else None,
        "created_at": digest.created_at.isoformat() if digest.created_at else None,
        "updated_at": digest.updated_at.isoformat() if digest.updated_at else None,
    }


def _validate_audience(audience: str) -> str:
    normalized = (audience or "").strip().lower()
    if normalized not in AUDIENCES:
        raise UnknownAudienceError(f"Unknown digest audience: {audience}")
    return normalized


def _window(week_start: date) -> tuple[datetime, datetime]:
    start = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=7)


def _in_window(column: Any, start: datetime, end: datetime) -> Any:
    return column >= start, column < end


def _is_failed(call: Call) -> bool:
    status = (call.status or "").strip().lower()
    return bool(call.error_code) or status not in _SUCCESS_STATUSES


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _percent_change(current: float, prior: float) -> float | None:
    if prior == 0:
        return None
    return round((current - prior) / prior, 4)


def _recommendation(calls: dict[str, Any], anomalies: dict[str, Any]) -> str:
    if calls["total"] == 0:
        return "No calls were ingested this week. Verify SDK capture before relying on the digest."
    top = anomalies["by_detector"][0] if anomalies["by_detector"] else None
    if top:
        return f"Most common anomaly this week: {top['detector']} ({top['count']} occurrences)."
    if calls["failed"] > 0:
        return f"{round(calls['failure_rate'] * 100, 1)}% of calls failed this week. Review the top failed traces first."
    return "No major anomalies detected this week. Keep replay coverage current."


def compute_summary(
    db: Session,
    *,
    project_id: str,
    week_start: date,
    audience: str,
) -> dict[str, Any]:
    audience = _validate_audience(audience)
    start, end = _window(week_start)

    calls = list(
        db.execute(
            select(Call).where(
                Call.project_id == project_id,
                *_in_window(Call.created_at, start, end),
            )
        ).scalars().all()
    )
    failed_calls = [call for call in calls if _is_failed(call)]
    calls_block = {
        "total": len(calls),
        "failed": len(failed_calls),
        "failure_rate": round(len(failed_calls) / len(calls), 4) if calls else 0.0,
    }

    anomalies_rows = list(
        db.execute(
            select(Anomaly).where(
                Anomaly.project_id == project_id,
                *_in_window(Anomaly.first_seen_at, start, end),
            )
        ).scalars().all()
    )
    by_detector = Counter(a.detector for a in anomalies_rows if a.detector)
    by_severity = {severity: 0 for severity in _SEVERITIES}
    for anomaly in anomalies_rows:
        if anomaly.severity in by_severity:
            by_severity[anomaly.severity] += 1
    anomalies_block = {
        "total": len(anomalies_rows),
        "by_detector": [
            {"detector": detector, "count": count}
            for detector, count in by_detector.most_common()
        ],
        "by_severity": by_severity,
        "open_at_week_end": sum(1 for a in anomalies_rows if a.status in {"open", "acknowledged"}),
    }

    pilot_actions = list(
        db.execute(
            select(PilotAction).where(
                PilotAction.project_id == project_id,
                *_in_window(PilotAction.created_at, start, end),
            )
        ).scalars().all()
    )
    anomaly_by_id = {a.id: a for a in anomalies_rows}
    fixed_fingerprints = {
        anomaly_by_id[action.anomaly_id].fingerprint
        for action in pilot_actions
        if action.status in {"applied", "reverted"} and action.anomaly_id in anomaly_by_id
    }
    prevented_waste = sum(
        _safe_float(call.cost_total)
        for call in failed_calls
        if call.error_code and call.error_code in fixed_fingerprints
    )
    cost_block = {
        "total_usd": round(sum(_safe_float(call.cost_total) for call in calls), 4),
        "failed_usd": round(sum(_safe_float(call.cost_total) for call in failed_calls), 4),
        "prevented_waste_usd": round(prevented_waste, 4),
    }

    summary: dict[str, Any] = {
        "audience": audience,
        "week_start": week_start.isoformat(),
        "week_end": (week_start + timedelta(days=7)).isoformat(),
        "calls": calls_block,
        "cost": cost_block,
        "anomalies": anomalies_block,
        "recommendation": _recommendation(calls_block, anomalies_block),
    }

    if audience in {"manager", "executive"}:
        pilot_block = {
            "tier1_applied": sum(1 for p in pilot_actions if p.tier == 1 and p.status == "applied"),
            "tier1_reverted": sum(1 for p in pilot_actions if p.tier == 1 and p.status == "reverted"),
            "tier2_applied": sum(1 for p in pilot_actions if p.tier == 2 and p.status == "applied"),
            "tier2_skipped": sum(1 for p in pilot_actions if p.tier == 2 and p.status == "skipped"),
            "tier2_failed": sum(1 for p in pilot_actions if p.tier == 2 and p.status == "failed"),
            "tier2_pr_urls": [
                p.pr_url
                for p in pilot_actions
                if p.tier == 2
                and p.pr_url
                and not p.pr_url.startswith(("dry-run://", "recording://"))
            ],
        }
        replay_runs = list(
            db.execute(
                select(ReplayRun).where(
                    ReplayRun.project_id == project_id,
                    *_in_window(ReplayRun.created_at, start, end),
                )
            ).scalars().all()
        )
        pass_count = 0
        trace_count = 0
        for run in replay_runs:
            run_summary = parse_summary_json(run.summary_json)
            traces = int(run_summary.get("trace_count_at_dispatch") or 0)
            if traces > 0:
                pass_count += int(run_summary.get("pass_count") or 0)
                trace_count += traces
        summary["pilot"] = pilot_block
        summary["replay"] = {
            "runs": len(replay_runs),
            "passed_runs": sum(1 for run in replay_runs if run.status == "pass"),
            "trace_pass_rate": round(pass_count / trace_count, 4) if trace_count else None,
        }

    if audience == "executive":
        prior = get_digest(db, project_id=project_id, week_start=week_start - timedelta(days=7))
        prior_summary = parse_summary_json(prior.summary_json) if prior else {}
        if prior_summary:
            prior_calls = _safe_float(prior_summary.get("calls", {}).get("total"))
            prior_cost = _safe_float(prior_summary.get("cost", {}).get("total_usd"))
            prior_anomalies = _safe_float(prior_summary.get("anomalies", {}).get("total"))
            summary["trend"] = {
                "calls": {
                    "wow_pct": _percent_change(float(calls_block["total"]), prior_calls),
                    "prior_value": prior_calls,
                },
                "cost": {
                    "wow_pct": _percent_change(float(cost_block["total_usd"]), prior_cost),
                    "prior_value": prior_cost,
                },
                "anomalies": {
                    "wow_pct": _percent_change(float(anomalies_block["total"]), prior_anomalies),
                    "prior_value": prior_anomalies,
                },
            }

    return summary


def render_html(summary: dict[str, Any]) -> str:
    audience = _validate_audience(str(summary.get("audience") or ""))
    calls = summary.get("calls", {})
    cost = summary.get("cost", {})
    anomalies = summary.get("anomalies", {})
    recommendation = html_escape(str(summary.get("recommendation") or ""))
    parts = [
        "<html><body>",
        f"<h1>ZROKY weekly digest</h1><p>{html_escape(audience)} view</p>",
        f"<p>Week: {html_escape(str(summary.get('week_start')))} to {html_escape(str(summary.get('week_end')))}</p>",
        f"<h2>Calls</h2><p>{calls.get('total', 0)} total, {calls.get('failed', 0)} failed</p>",
        f"<h2>Cost</h2><p>${cost.get('total_usd', 0)} total, ${cost.get('prevented_waste_usd', 0)} prevented waste</p>",
        f"<h2>Anomalies</h2><p>{anomalies.get('total', 0)} total</p>",
        f"<p>{recommendation}</p>",
    ]
    if audience in {"manager", "executive"}:
        pilot = summary.get("pilot", {})
        replay = summary.get("replay", {})
        parts.append("<h2>Autopilot</h2>")
        parts.append(f"<p>Tier-1 applied: {pilot.get('tier1_applied', 0)}; Tier-2 applied: {pilot.get('tier2_applied', 0)}</p>")
        for url in pilot.get("tier2_pr_urls", []) or []:
            parts.append(f"<p>{html_escape(str(url))}</p>")
        parts.append("<h2>Replay</h2>")
        parts.append(f"<p>{replay.get('passed_runs', 0)} / {replay.get('runs', 0)} runs passed</p>")
    if audience == "executive" and summary.get("trend"):
        parts.append("<h2>Week-over-week</h2>")
        for key, block in summary["trend"].items():
            parts.append(f"<p>{html_escape(str(key))}: {block.get('wow_pct')}</p>")
    parts.append("</body></html>")
    return "\n".join(parts)


def render_plain(summary: dict[str, Any]) -> str:
    audience = _validate_audience(str(summary.get("audience") or ""))
    calls = summary.get("calls", {})
    cost = summary.get("cost", {})
    anomalies = summary.get("anomalies", {})
    lines = [
        f"ZROKY weekly digest ({audience})",
        f"Calls: {calls.get('total', 0)} total, {calls.get('failed', 0)} failed",
        f"Cost: ${cost.get('total_usd', 0)} total, ${cost.get('prevented_waste_usd', 0)} prevented waste",
        f"Anoms: {anomalies.get('total', 0)} total",
        str(summary.get("recommendation") or ""),
    ]
    if audience in {"manager", "executive"}:
        pilot = summary.get("pilot", {})
        replay = summary.get("replay", {})
        lines.append(f"Pilot: tier1_applied={pilot.get('tier1_applied', 0)} tier2_applied={pilot.get('tier2_applied', 0)}")
        for url in pilot.get("tier2_pr_urls", []) or []:
            lines.append(str(url))
        lines.append(f"Replay: {replay.get('passed_runs', 0)} / {replay.get('runs', 0)} runs passed")
    if audience == "executive" and summary.get("trend"):
        lines.append("Week-over-week")
        for key, block in summary["trend"].items():
            lines.append(f"{key}: {block.get('wow_pct')}")
    return "\n".join(lines)


def resolve_audience(db: Session, project_id: str) -> str:
    try:
        resolved = entitlements_resolver.get(db, project_id, "digest.audience", default=DEFAULT_AUDIENCE)
    except Exception:
        return DEFAULT_AUDIENCE
    return resolved if resolved in AUDIENCES else DEFAULT_AUDIENCE


def generate_weekly_digest(
    db: Session,
    *,
    project_id: str,
    week_start: date,
    audience: str | None = None,
) -> Digest:
    effective_audience = _validate_audience(audience) if audience else resolve_audience(db, project_id)
    summary = compute_summary(
        db,
        project_id=project_id,
        week_start=week_start,
        audience=effective_audience,
    )
    html_blob = render_html(summary)
    digest = get_digest(db, project_id=project_id, week_start=week_start)
    if digest is None:
        digest = Digest(project_id=project_id, week_start=week_start)
        db.add(digest)
    digest.summary_json = json.dumps(summary, sort_keys=True)
    digest.html_blob = html_blob
    db.commit()
    db.refresh(digest)
    return digest


def list_pending_digests(
    db: Session,
    *,
    week_start: date | None = None,
    limit: int = 100,
) -> list[Digest]:
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be positive")
    query = select(Digest).where(Digest.sent_at.is_(None))
    if week_start is not None:
        query = query.where(Digest.week_start == week_start)
    query = query.order_by(Digest.week_start.desc(), Digest.created_at.asc()).limit(limit)
    return list(db.execute(query).scalars().all())


def mark_digest_sent(
    db: Session,
    *,
    digest: Digest,
    sent_to_emails: list[str],
    sent_at: datetime | None = None,
) -> Digest:
    recipients = [email.strip() for email in sent_to_emails if isinstance(email, str) and email.strip()]
    digest.sent_at = sent_at or datetime.now(timezone.utc)
    digest.sent_to_emails = json.dumps(recipients)
    db.add(digest)
    db.commit()
    db.refresh(digest)
    return digest


def resolve_recipient_emails(db: Session, project_id: str) -> list[str]:
    rows = list(
        db.execute(
            select(User.email)
            .join(ProjectMembership, ProjectMembership.user_id == User.id)
            .where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.is_active.is_(True),
                ProjectMembership.role.in_(["admin", "owner"]),
                User.is_active.is_(True),
                User.email.is_not(None),
            )
        ).all()
    )
    return [email.strip() for (email,) in rows if isinstance(email, str) and email.strip()]


def _check_audience_vocab_in_sync() -> None:
    if set(AUDIENCES) != set(billing_plans.DIGEST_AUDIENCE_VALUES):
        raise RuntimeError("digest audience vocabulary drift")
