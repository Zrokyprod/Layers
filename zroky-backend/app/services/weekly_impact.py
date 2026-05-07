"""Weekly developer impact summary.

Computes the data needed for the weekly impact email and Slack digest for a
single project tenant.  All logic runs against the database directly so it
can be invoked from a Celery beat task without going through HTTP.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Call, DiagnosisJob, ProjectAlert, ProjectMembership, User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WeeklyImpactSummary:
    tenant_id: str
    week_start: str  # ISO date
    week_end: str    # ISO date

    total_calls: int
    failed_calls: int
    incidents_caught: int

    # Top failure categories with counts
    top_categories: list[dict[str, Any]]

    # Estimated prevented waste (USD) — cost of unresolved calls that got a fix
    prevented_waste_usd: float

    # Fix cycle times in hours (None when no data)
    fastest_fix_cycle_hours: float | None
    slowest_fix_cycle_hours: float | None

    # A single proactive recommendation based on the week's data
    recommendation: str

    # Recipient emails (admin / owner users of the project)
    recipient_emails: list[str]


def compute_weekly_impact(db: Session, tenant_id: str) -> WeeklyImpactSummary:
    """Build a WeeklyImpactSummary for the past 7 days."""
    now = _utcnow()
    week_start_dt = now - timedelta(days=7)

    # ── calls in the window ──────────────────────────────────────────────
    calls: list[Call] = list(
        db.execute(
            select(Call).where(
                Call.project_id == tenant_id,
                Call.created_at >= week_start_dt,
            )
        ).scalars().all()
    )

    total_calls = len(calls)
    failed_calls = sum(1 for c in calls if c.status not in ("success", "ok", "SUCCESS", "OK"))

    # ── diagnosis jobs in the window ────────────────────────────────────
    jobs: list[DiagnosisJob] = list(
        db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.created_at >= week_start_dt,
                DiagnosisJob.status.in_(["done", "completed"]),
            )
        ).scalars().all()
    )

    # ── alerts created in the window ────────────────────────────────────
    alerts: list[ProjectAlert] = list(
        db.execute(
            select(ProjectAlert).where(
                ProjectAlert.tenant_id == tenant_id,
                ProjectAlert.created_at >= week_start_dt,
            )
        ).scalars().all()
    )

    incidents_caught = len(alerts)

    # Top categories
    cat_counter: Counter[str] = Counter(a.category for a in alerts if a.category)
    top_categories = [
        {"category": cat, "count": cnt}
        for cat, cnt in cat_counter.most_common(5)
    ]

    # Prevented waste — cost of failed calls that have a resolved alert
    resolved_diagnosis_ids = {a.diagnosis_id for a in alerts if a.status in ("RESOLVED", "CONFIRMED")}
    resolved_jobs_by_diag: dict[str, DiagnosisJob] = {
        j.diagnosis_id: j for j in jobs if j.diagnosis_id in resolved_diagnosis_ids
    }
    call_ids_with_fix: set[str | None] = {j.call_id for j in resolved_jobs_by_diag.values() if j.call_id}
    prevented_waste_usd = sum(
        max(0.0, float(c.cost_total or 0.0))
        for c in calls
        if c.id in call_ids_with_fix
    )

    # Fix cycle times — time from job created_at to updated_at when done
    fix_cycles_hours: list[float] = []
    for job in jobs:
        if job.status in ("done", "completed") and job.updated_at and job.created_at:
            created = job.created_at if job.created_at.tzinfo else job.created_at.replace(tzinfo=timezone.utc)
            updated = job.updated_at if job.updated_at.tzinfo else job.updated_at.replace(tzinfo=timezone.utc)
            diff_hours = (updated - created).total_seconds() / 3600
            if diff_hours >= 0:
                fix_cycles_hours.append(diff_hours)

    fastest = min(fix_cycles_hours) if fix_cycles_hours else None
    slowest = max(fix_cycles_hours) if fix_cycles_hours else None

    # Proactive recommendation
    recommendation = _build_recommendation(top_categories, prevented_waste_usd, failed_calls, total_calls)

    # Recipient emails — admin members with an email address
    admin_memberships: list[ProjectMembership] = list(
        db.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == tenant_id,
                ProjectMembership.is_active == True,  # noqa: E712
                ProjectMembership.role.in_(["admin", "owner"]),
            )
        ).scalars().all()
    )
    user_ids = [m.user_id for m in admin_memberships]
    recipient_emails: list[str] = []
    if user_ids:
        users: list[User] = list(
            db.execute(
                select(User).where(
                    User.id.in_(user_ids),
                    User.email.is_not(None),
                    User.is_active == True,  # noqa: E712
                )
            ).scalars().all()
        )
        recipient_emails = [u.email for u in users if u.email and u.email.strip()]

    return WeeklyImpactSummary(
        tenant_id=tenant_id,
        week_start=week_start_dt.date().isoformat(),
        week_end=now.date().isoformat(),
        total_calls=total_calls,
        failed_calls=failed_calls,
        incidents_caught=incidents_caught,
        top_categories=top_categories,
        prevented_waste_usd=round(prevented_waste_usd, 4),
        fastest_fix_cycle_hours=round(fastest, 2) if fastest is not None else None,
        slowest_fix_cycle_hours=round(slowest, 2) if slowest is not None else None,
        recommendation=recommendation,
        recipient_emails=recipient_emails,
    )


def _build_recommendation(
    top_categories: list[dict[str, Any]],
    prevented_waste_usd: float,
    failed_calls: int,
    total_calls: int,
) -> str:
    if not top_categories:
        if total_calls == 0:
            return "No calls were ingested this week. Verify your SDK integration."
        return "No incidents were detected this week. Keep monitoring for anomalies."

    top_cat = top_categories[0]["category"]
    top_count = top_categories[0]["count"]

    failure_rate = failed_calls / total_calls if total_calls > 0 else 0.0

    if top_cat in ("LOOP_DETECTED", "LOOP"):
        return (
            f"{top_count} loop incidents were caught. "
            "Consider adding a turn limit or circuit breaker to your agent to reduce runaway costs."
        )
    if top_cat in ("COST_SPIKE", "COST"):
        return (
            f"{top_count} cost spike incidents were caught. "
            "Review your prompt sizes and reasoning model usage to tighten the cost envelope."
        )
    if top_cat in ("TOKEN_OVERFLOW",):
        return (
            f"{top_count} token overflow incidents were caught. "
            "Trim context windows or enable adaptive truncation in your SDK config."
        )
    if top_cat in ("AUTH_FAILURE",):
        return (
            f"{top_count} auth failure incidents were caught. "
            "Audit API key rotation schedules and ensure keys are not shared across environments."
        )
    if top_cat in ("RATE_LIMIT",):
        return (
            f"{top_count} rate limit incidents were caught. "
            "Implement exponential back-off or request batching to reduce limit breaches."
        )
    if failure_rate > 0.3:
        return (
            f"{round(failure_rate * 100)}% of calls failed this week. "
            f"Most incidents were {top_cat}. Prioritise a fix this sprint."
        )
    return (
        f"Most common incident this week: {top_cat} ({top_count} occurrences). "
        "Consider reviewing your agent configuration for this failure mode."
    )


def render_weekly_impact_html(summary: WeeklyImpactSummary) -> str:
    """Return a minimal HTML email body for the weekly impact summary."""
    cat_rows = "".join(
        f"<tr><td style='padding:4px 8px'>{item['category']}</td>"
        f"<td style='padding:4px 8px;text-align:right'>{item['count']}</td></tr>"
        for item in summary.top_categories
    )

    if summary.top_categories:
        categories_html = (
            "<table style='width:100%;border-collapse:collapse'>\n"
            "    <thead>\n"
            "      <tr style='background:#eee'>\n"
            "        <th style='padding:6px 8px;text-align:left'>Category</th>\n"
            "        <th style='padding:6px 8px;text-align:right'>Count</th>\n"
            "      </tr>\n"
            "    </thead>\n"
            "    <tbody>" + cat_rows + "</tbody>\n"
            "  </table>"
        )
    else:
        categories_html = "<p style='color:#888'>No incidents this week.</p>"

    def _fmt_cycle(hours: float | None) -> str:
        if hours is None:
            return "—"
        if hours < 1:
            return f"{round(hours * 60)}m"
        return f"{round(hours, 1)}h"

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>ZROKY Weekly Impact</title></head>
<body style="font-family:sans-serif;color:#111;max-width:600px;margin:0 auto;padding:24px">
  <h2 style="margin-bottom:4px">ZROKY saved you ${summary.prevented_waste_usd:.2f} this week</h2>
  <p style="color:#555;margin-top:0">{summary.week_start} → {summary.week_end}</p>

  <table style="width:100%;border-collapse:collapse;margin-bottom:24px">
    <tr>
      <td style="padding:8px;background:#f5f5f5;border-radius:4px;text-align:center">
        <strong style="font-size:22px">{summary.incidents_caught}</strong><br>
        <span style="font-size:12px;color:#555">incidents caught</span>
      </td>
      <td style="padding:8px;background:#f5f5f5;border-radius:4px;text-align:center">
        <strong style="font-size:22px">{summary.failed_calls}</strong><br>
        <span style="font-size:12px;color:#555">failed calls</span>
      </td>
      <td style="padding:8px;background:#f5f5f5;border-radius:4px;text-align:center">
        <strong style="font-size:22px">{summary.total_calls}</strong><br>
        <span style="font-size:12px;color:#555">total calls</span>
      </td>
    </tr>
  </table>

  <h3>Top Incident Categories</h3>
  {categories_html}

  <h3>Fix Cycle</h3>
  <p>
    Fastest: <strong>{_fmt_cycle(summary.fastest_fix_cycle_hours)}</strong>
    &nbsp;|&nbsp;
    Slowest: <strong>{_fmt_cycle(summary.slowest_fix_cycle_hours)}</strong>
  </p>

  <h3>Recommendation for Next Week</h3>
  <p style="background:#fffbe6;border-left:4px solid #f5a623;padding:12px;border-radius:2px">
    {summary.recommendation}
  </p>

  <hr style="border:none;border-top:1px solid #ddd;margin:32px 0">
  <p style="font-size:11px;color:#aaa">
    You received this because you are an admin of project <code>{summary.tenant_id}</code>.
    Manage notifications in ZROKY Settings → Notifications.
  </p>
</body>
</html>"""


def render_weekly_impact_plain(summary: WeeklyImpactSummary) -> str:
    """Return a plain-text fallback for the weekly impact email."""
    cats = "\n".join(
        f"  - {item['category']}: {item['count']}"
        for item in summary.top_categories
    ) or "  (none)"

    def _fmt(h: float | None) -> str:
        if h is None:
            return "N/A"
        return f"{round(h * 60)}m" if h < 1 else f"{round(h, 1)}h"

    return f"""ZROKY Weekly Impact: {summary.week_start} → {summary.week_end}
============================================================

Prevented waste:  ${summary.prevented_waste_usd:.2f}
Incidents caught: {summary.incidents_caught}
Failed calls:     {summary.failed_calls} / {summary.total_calls}

Top Incident Categories:
{cats}

Fix Cycle — Fastest: {_fmt(summary.fastest_fix_cycle_hours)} | Slowest: {_fmt(summary.slowest_fix_cycle_hours)}

Recommendation:
{summary.recommendation}

----
Manage notifications in ZROKY Settings → Notifications.
"""
