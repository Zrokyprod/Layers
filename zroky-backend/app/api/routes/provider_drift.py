"""Public Provider Drift Watch surface.

Anonymous, rate-limited endpoints that expose the current drift status,
historical metrics, and RSS/Atom feeds so external consumers and the
dashboard can surface silent-update alerts without authentication.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from html import escape
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import case, desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.models import ProviderDriftAlert, ProviderDriftModel, ProviderDriftProbe, ProviderDriftRun
from app.db.session import SessionLocal

router = APIRouter(prefix="/v1/drift", tags=["provider-drift"])

# ── Response schemas ──────────────────────────────────────────────────────────


class DriftModelView(BaseModel):
    id: str
    provider: str
    model_id: str
    display_name: str
    family: str
    active: bool


class AlertView(BaseModel):
    id: str
    model_id: str
    category: str
    severity: str
    headline: str
    evidence: dict[str, Any]
    created_at: datetime


class MetricPoint(BaseModel):
    run_date: date
    judge_pass_rate: float | None = None
    embedding_mean_cosine: float | None = None
    probe_count: int = 0
    ok_count: int = 0


class ModelHistoryResponse(BaseModel):
    model_id: str
    display_name: str
    category: str
    points: list[MetricPoint]


class StatusResponse(BaseModel):
    date: date
    models: list[DriftModelView]
    alerts: list[AlertView]
    total_alerts: int
    critical_count: int
    warn_count: int
    info_count: int


# ── Helpers ───────────────────────────────────────────────────────────────────


def _db() -> Session:
    return SessionLocal()


def _latest_run_date(db: Session) -> date | None:
    row = db.execute(
        select(ProviderDriftRun.run_date)
        .order_by(desc(ProviderDriftRun.run_date))
        .limit(1)
    ).scalar_one_or_none()
    return row


def _alerts_for_date(db: Session, current_date: date) -> list[ProviderDriftAlert]:
    return list(
        db.execute(
            select(ProviderDriftAlert)
            .where(ProviderDriftAlert.current_date == current_date)
            .order_by(
                case(
                    (ProviderDriftAlert.severity == "critical", 0),
                    (ProviderDriftAlert.severity == "warn", 1),
                    (ProviderDriftAlert.severity == "info", 2),
                    else_=3,
                ),
                desc(ProviderDriftAlert.published_at),
            )
        ).scalars().all()
    )


def _serialize_alert(a: ProviderDriftAlert) -> AlertView:
    import json

    ev = a.evidence_json
    if isinstance(ev, str):
        try:
            ev = json.loads(ev)
        except json.JSONDecodeError:
            ev = {}
    return AlertView(
        id=a.id,
        model_id=a.model_id,
        category=a.category,
        severity=a.severity,
        headline=a.headline,
        evidence=ev or {},
        created_at=a.created_at,
    )


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/models", response_model=list[DriftModelView])
@limiter.limit("30/minute")
def list_models(request: Request) -> list[DriftModelView]:
    """Return all tracked models (active and inactive)."""
    db = _db()
    try:
        rows = db.execute(
            select(ProviderDriftModel).order_by(ProviderDriftModel.provider, ProviderDriftModel.model_id)
        ).scalars().all()
        return [
            DriftModelView(
                id=r.id,
                provider=r.provider,
                model_id=r.model_id,
                display_name=r.display_name,
                family=r.family,
                active=r.active,
            )
            for r in rows
        ]
    finally:
        db.close()


@router.get("/status", response_model=StatusResponse)
@limiter.limit("30/minute")
def get_status(request: Request) -> StatusResponse:
    """Latest drift snapshot: today's alerts and tracked models."""
    settings = get_settings()
    if not settings.PROVIDER_DRIFT_WATCH_ENABLED:
        return StatusResponse(
            date=date.today(),
            models=[],
            alerts=[],
            total_alerts=0,
            critical_count=0,
            warn_count=0,
            info_count=0,
        )

    db = _db()
    try:
        latest_date = _latest_run_date(db) or date.today()
        alerts = _alerts_for_date(db, latest_date)
        models = db.execute(
            select(ProviderDriftModel).where(ProviderDriftModel.active.is_(True))
        ).scalars().all()

        crit = sum(1 for a in alerts if a.severity == "critical")
        warn = sum(1 for a in alerts if a.severity == "warn")
        info = sum(1 for a in alerts if a.severity == "info")

        return StatusResponse(
            date=latest_date,
            models=[
                DriftModelView(
                    id=m.id,
                    provider=m.provider,
                    model_id=m.model_id,
                    display_name=m.display_name,
                    family=m.family,
                    active=m.active,
                )
                for m in models
            ],
            alerts=[_serialize_alert(a) for a in alerts],
            total_alerts=len(alerts),
            critical_count=crit,
            warn_count=warn,
            info_count=info,
        )
    finally:
        db.close()


@router.get("/history/{model_id}", response_model=list[ModelHistoryResponse])
@limiter.limit("30/minute")
def get_history(
    request: Request,
    model_id: str,
) -> list[ModelHistoryResponse]:
    """Historical metric points per category for a given model."""
    db = _db()
    try:
        # Verify model exists
        model = db.execute(
            select(ProviderDriftModel).where(ProviderDriftModel.id == model_id)
        ).scalar_one_or_none()
        if model is None:
            raise HTTPException(status_code=404, detail="Model not found")

        # Pull runs for last 30 days
        since = date.today() - timedelta(days=30)
        runs = db.execute(
            select(ProviderDriftRun)
            .where(
                ProviderDriftRun.model_id == model_id,
                ProviderDriftRun.run_date >= since,
            )
            .order_by(ProviderDriftRun.run_date)
        ).scalars().all()

        if not runs:
            return []

        run_ids = [r.id for r in runs]
        probes = db.execute(
            select(ProviderDriftProbe)
            .where(ProviderDriftProbe.run_id.in_(run_ids))
        ).scalars().all()

        # Group by (run_date, category)
        from collections import defaultdict

        by_run_cat: dict[tuple[date, str], list[ProviderDriftProbe]] = defaultdict(list)
        for p in probes:
            by_run_cat[(p.run_date, p.category)].append(p)

        # Categories present
        categories = sorted({cat for _, cat in by_run_cat})

        out: list[ModelHistoryResponse] = []
        for cat in categories:
            points: list[MetricPoint] = []
            for r in runs:
                ps = by_run_cat.get((r.run_date, cat), [])
                ok = sum(1 for p in ps if p.judge_pass is True)
                total = len(ps)
                scores = [p.judge_score for p in ps if p.judge_score is not None]
                mean_score = round(sum(scores) / len(scores), 6) if scores else None
                points.append(
                    MetricPoint(
                        run_date=r.run_date,
                        judge_pass_rate=round(ok / total, 4) if total else None,
                        embedding_mean_cosine=mean_score,
                        probe_count=total,
                        ok_count=ok,
                    )
                )
            out.append(
                ModelHistoryResponse(
                    model_id=model_id,
                    display_name=model.display_name,
                    category=cat,
                    points=points,
                )
            )
        return out
    finally:
        db.close()


# ── RSS / Atom feeds ──────────────────────────────────────────────────────────


_DASHBOARD_PROVIDER_DRIFT_URL = "https://zroky.com/home?source=provider_drift"


_RSS_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Zroky Provider Drift Watch</title>
    <link>{dashboard_url}</link>
    <description>Silent-update alerts for major LLM providers.</description>
    <language>en-us</language>
    <lastBuildDate>{build_date}</lastBuildDate>
{items}
  </channel>
</rss>
"""

_ATOM_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Zroky Provider Drift Watch</title>
  <link href="{dashboard_url}" />
  <updated>{updated}</updated>
  <id>tag:zroky.com,2026:/drift</id>
{entries}
</feed>
"""


def _rfc822(dt: datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def _iso8601(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _xml_url(url: str) -> str:
    return escape(url, quote=True)


def _rss_item(a: ProviderDriftAlert) -> str:
    url = _xml_url(f"{_DASHBOARD_PROVIDER_DRIFT_URL}&provider_drift_alert_id={a.id}")
    return f"""    <item>
      <title>{a.headline}</title>
      <link>{url}</link>
      <guid>{a.id}</guid>
      <pubDate>{_rfc822(a.created_at)}</pubDate>
      <category>{a.severity}</category>
      <description>Model: {a.model_id} | Category: {a.category} | Severity: {a.severity}</description>
    </item>"""


def _atom_entry(a: ProviderDriftAlert) -> str:
    url = _xml_url(f"{_DASHBOARD_PROVIDER_DRIFT_URL}&provider_drift_alert_id={a.id}")
    return f"""  <entry>
    <title>{a.headline}</title>
    <link href="{url}" />
    <id>tag:zroky.com,2026:{a.id}</id>
    <updated>{_iso8601(a.created_at)}</updated>
    <summary>Model: {a.model_id} | Category: {a.category} | Severity: {a.severity}</summary>
  </entry>"""


@router.get("/rss")
@limiter.limit("10/minute")
def rss_feed(request: Request) -> Response:
    """RSS 2.0 feed of the last 30 days of drift alerts."""
    db = _db()
    try:
        since = date.today() - timedelta(days=30)
        alerts = db.execute(
            select(ProviderDriftAlert)
            .where(ProviderDriftAlert.current_date >= since)
            .order_by(desc(ProviderDriftAlert.published_at))
        ).scalars().all()

        items = "\n".join(_rss_item(a) for a in alerts) if alerts else ""
        build_date = _rfc822(datetime.now(timezone.utc))
        body = _RSS_TEMPLATE.format(
            dashboard_url=_xml_url(_DASHBOARD_PROVIDER_DRIFT_URL),
            build_date=build_date,
            items=items,
        )
        return Response(content=body, media_type="application/rss+xml")
    finally:
        db.close()


@router.get("/atom")
@limiter.limit("10/minute")
def atom_feed(request: Request) -> Response:
    """Atom feed of the last 30 days of drift alerts."""
    db = _db()
    try:
        since = date.today() - timedelta(days=30)
        alerts = db.execute(
            select(ProviderDriftAlert)
            .where(ProviderDriftAlert.current_date >= since)
            .order_by(desc(ProviderDriftAlert.published_at))
        ).scalars().all()

        entries = "\n".join(_atom_entry(a) for a in alerts) if alerts else ""
        updated = _iso8601(datetime.now(timezone.utc))
        body = _ATOM_TEMPLATE.format(
            dashboard_url=_xml_url(_DASHBOARD_PROVIDER_DRIFT_URL),
            updated=updated,
            entries=entries,
        )
        return Response(content=body, media_type="application/atom+xml")
    finally:
        db.close()
