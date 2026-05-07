"""Pure DB tool functions for the assistant engine.

Each function returns serialisable plain-dict data only.
No LLM calls happen here — these are the ground-truth data sources
that prevent hallucination.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Call, DiagnosisJob, ProjectAlert
from app.services.predictive_cost import PredictiveCostService
from app.services.weekly_impact import compute_weekly_impact

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Tool 1 — Recent calls
# ---------------------------------------------------------------------------

def get_recent_calls(
    db: Session,
    project_id: str,
    hours: int = 24,
    model: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return the most recent LLM calls for this project with real call IDs."""
    hours = _clamp(hours, 1, 168)
    limit = _clamp(limit, 1, 50)
    since = _utcnow() - timedelta(hours=hours)

    q = (
        select(Call)
        .where(Call.project_id == project_id, Call.created_at >= since)
        .order_by(Call.created_at.desc())
        .limit(limit)
    )
    if model:
        q = q.where(func.lower(Call.model) == model.strip().lower())
    if status:
        q = q.where(func.lower(Call.status) == status.strip().lower())

    rows = db.execute(q).scalars().all()
    results = []
    for c in rows:
        payload = _safe_json(c.payload_json)
        results.append(
            {
                "call_id": c.id,
                "provider": c.provider,
                "model": c.model,
                "status": c.status,
                "cost_usd": round(float(c.cost_total or 0), 6),
                "total_tokens": c.total_tokens,
                "latency_ms": c.latency_ms,
                "agent_name": payload.get("agent_name"),
                "error_code": c.error_code,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Tool 2 — Cost breakdown
# ---------------------------------------------------------------------------

def get_cost_breakdown(
    db: Session,
    project_id: str,
    group_by: str = "model",
    hours: int = 24,
) -> list[dict[str, Any]]:
    """Return cost aggregated by model or provider for a time window."""
    hours = _clamp(hours, 1, 720)
    allowed = {"model", "provider"}
    group_by = group_by if group_by in allowed else "model"
    since = _utcnow() - timedelta(hours=hours)

    col = Call.model if group_by == "model" else Call.provider

    rows = db.execute(
        select(
            col.label("group_value"),
            func.sum(Call.cost_total).label("total_cost"),
            func.count().label("call_count"),
            func.sum(Call.total_tokens).label("total_tokens"),
        )
        .where(Call.project_id == project_id, Call.created_at >= since)
        .group_by(col)
        .order_by(func.sum(Call.cost_total).desc())
    ).all()

    return [
        {
            group_by: row.group_value or "unknown",
            "total_cost_usd": round(float(row.total_cost or 0), 6),
            "call_count": row.call_count,
            "total_tokens": row.total_tokens or 0,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Tool 3 — Active alerts
# ---------------------------------------------------------------------------

def get_active_alerts(
    db: Session,
    project_id: str,
    severity: str | None = None,
) -> list[dict[str, Any]]:
    """Return open alerts for this project with real alert IDs."""
    q = (
        select(ProjectAlert)
        .where(
            ProjectAlert.tenant_id == project_id,
            ProjectAlert.status == "OPEN",
        )
        .order_by(ProjectAlert.created_at.desc())
        .limit(20)
    )
    if severity:
        q = q.where(func.lower(ProjectAlert.severity) == severity.strip().lower())

    rows = db.execute(q).scalars().all()
    return [
        {
            "alert_id": a.id,
            "category": a.category,
            "severity": a.severity,
            "title": a.title,
            "diagnosis_id": a.diagnosis_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]


# ---------------------------------------------------------------------------
# Tool 4 — Diagnosis summary
# ---------------------------------------------------------------------------

def get_diagnosis_summary(
    db: Session,
    project_id: str,
    days: int = 7,
) -> dict[str, Any]:
    """Return diagnosis category counts over a recent window."""
    days = _clamp(days, 1, 30)
    since = _utcnow() - timedelta(days=days)

    rows = db.execute(
        select(DiagnosisJob)
        .where(
            DiagnosisJob.tenant_id == project_id,
            DiagnosisJob.created_at >= since,
            DiagnosisJob.status.in_(["done", "completed"]),
        )
        .order_by(DiagnosisJob.created_at.desc())
        .limit(500)
    ).scalars().all()

    categories: Counter[str] = Counter()
    for job in rows:
        result = _safe_json(job.result_json)
        for diag in result.get("diagnoses", []):
            if isinstance(diag, dict):
                cat = diag.get("category")
                if isinstance(cat, str) and cat:
                    categories[cat.upper()] += 1

    return {
        "total_jobs": len(rows),
        "window_days": days,
        "by_category": [
            {"category": cat, "count": cnt}
            for cat, cnt in categories.most_common(10)
        ],
    }


# ---------------------------------------------------------------------------
# Tool 5 — Call detail
# ---------------------------------------------------------------------------

def get_call_detail(
    db: Session,
    project_id: str,
    call_id: str,
) -> dict[str, Any] | None:
    """Return full detail for a single call by its ID."""
    call = db.execute(
        select(Call).where(Call.id == call_id, Call.project_id == project_id)
    ).scalar_one_or_none()

    if call is None:
        return None

    payload = _safe_json(call.payload_json)
    return {
        "call_id": call.id,
        "provider": call.provider,
        "model": call.model,
        "status": call.status,
        "error_code": call.error_code,
        "cost_usd": round(float(call.cost_total or 0), 6),
        "input_tokens": call.input_tokens,
        "output_tokens": call.output_tokens,
        "reasoning_tokens": call.reasoning_tokens,
        "total_tokens": call.total_tokens,
        "latency_ms": call.latency_ms,
        "agent_name": payload.get("agent_name"),
        "trace_id": payload.get("trace_id"),
        "cost_confidence": call.cost_confidence,
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }


# ---------------------------------------------------------------------------
# Tool 6 — Semantic error search via pgvector
# ---------------------------------------------------------------------------

def search_similar_errors(
    db: Session,
    project_id: str,
    query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Find past similar errors/fixes using vector similarity (pgvector)."""
    try:
        from app.services.embedding_service import get_embedding_service

        svc = get_embedding_service()
        results = svc.find_similar_fixes(
            db=db,
            project_id=project_id,
            query_text=query,
            limit=_clamp(limit, 1, 10),
            min_similarity=0.65,
        )
        return results or []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Tool 7 — Cost forecast (EWMA + linear regression)
# ---------------------------------------------------------------------------

def get_cost_forecast(db: Session, project_id: str) -> dict[str, Any]:
    """Return cost forecast and anomaly risk for the next 4 hours."""
    try:
        svc = PredictiveCostService(forecast_horizon_hours=4)
        return svc.detect_anomaly_risk(db, project_id)
    except Exception as exc:
        logger.warning("Cost forecast failed: %s", exc)
        return {"error": f"Forecast unavailable: {exc}"}


# ---------------------------------------------------------------------------
# Tool 8 — Weekly impact summary
# ---------------------------------------------------------------------------

def get_weekly_impact_summary(db: Session, project_id: str) -> dict[str, Any]:
    """Return the weekly impact digest for the last 7 days.

    Deliberately excludes recipient_emails (PII — never send to LLM).
    """
    try:
        summary = compute_weekly_impact(db, project_id)
        return {
            "week_start": summary.week_start,
            "week_end": summary.week_end,
            "total_calls": summary.total_calls,
            "failed_calls": summary.failed_calls,
            "incidents_caught": summary.incidents_caught,
            "top_categories": summary.top_categories,
            "prevented_waste_usd": summary.prevented_waste_usd,
            "fastest_fix_cycle_hours": summary.fastest_fix_cycle_hours,
            "slowest_fix_cycle_hours": summary.slowest_fix_cycle_hours,
            "recommendation": summary.recommendation,
        }
    except Exception as exc:
        logger.warning("Weekly impact failed: %s", exc)
        return {"error": f"Weekly impact unavailable: {exc}"}


# ---------------------------------------------------------------------------
# Tool registry — used by the engine dispatcher
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_recent_calls",
            "description": (
                "Fetch the most recent AI provider calls for this project. "
                "Returns real call_ids, provider, model, status, cost_usd, tokens, "
                "latency_ms, agent_name, error_code, and timestamp. "
                "Use this to answer questions about recent activity, failures, or spend."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "integer",
                        "description": "How many hours back to look (1–168). Default 24.",
                        "default": 24,
                    },
                    "model": {
                        "type": "string",
                        "description": "Filter by model name (e.g. gpt-4o, claude-3-7-sonnet).",
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by call status: success, failed, error.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (1–50). Default 20.",
                        "default": 20,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cost_breakdown",
            "description": (
                "Return cost aggregated by model or provider for a time window. "
                "Use this to answer questions like 'which model is costing the most' "
                "or 'what did I spend in the last 24 hours'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "group_by": {
                        "type": "string",
                        "enum": ["model", "provider"],
                        "description": "Dimension to group cost by. Default 'model'.",
                        "default": "model",
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Look-back window in hours (1–720). Default 24.",
                        "default": 24,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_alerts",
            "description": (
                "Return currently OPEN alerts for this project with real alert_ids. "
                "Use this to answer questions about current incidents, problems, or warnings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Filter by severity level.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_diagnosis_summary",
            "description": (
                "Return diagnosis category counts over a recent window. "
                "Categories include TOKEN_OVERFLOW, RATE_LIMIT, AUTH_FAILURE, "
                "LOOP_DETECTED, COST_SPIKE. Use this to answer questions about "
                "what types of errors are happening and how often."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Look-back window in days (1–30). Default 7.",
                        "default": 7,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_call_detail",
            "description": (
                "Return full details for a single call by its call_id. "
                "Use this when the user asks about a specific call or when you have "
                "a call_id from another tool result and need more context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "call_id": {
                        "type": "string",
                        "description": "The call_id to look up (exact string from a previous tool result).",
                    },
                },
                "required": ["call_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_similar_errors",
            "description": (
                "Use vector semantic search to find past similar errors and their fixes "
                "in this project's history. Use this when the user describes an error "
                "message or wants to know if a similar issue occurred before."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The error message or description to search for.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (1–10). Default 5.",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cost_forecast",
            "description": (
                "Forecast AI cost for the next 4 hours using EWMA and linear regression. "
                "Returns risk_level (normal/low/medium/high), predicted hourly cost, "
                "baseline vs current spend rate, risk_factors, and a recommendation. "
                "Use this when the user asks about future costs, cost predictions, "
                "upcoming spend, or whether a cost spike is likely."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weekly_impact_summary",
            "description": (
                "Return a comprehensive weekly impact digest for the last 7 days. "
                "Includes total_calls, failed_calls, incidents_caught, top_categories, "
                "prevented_waste_usd (cost saved by catching issues), fix cycle times, "
                "and a proactive recommendation. "
                "Use this when the user asks about weekly summary, this week's performance, "
                "prevented waste, or overall project health."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


def dispatch_tool(
    name: str,
    arguments_json: str,
    db: Session,
    project_id: str,
) -> Any:
    """Execute a tool by name with parsed arguments. Returns serialisable data."""
    try:
        args: dict[str, Any] = json.loads(arguments_json) if arguments_json.strip() else {}
    except (json.JSONDecodeError, ValueError):
        args = {}

    if name == "get_recent_calls":
        return get_recent_calls(
            db, project_id,
            hours=int(args.get("hours", 24)),
            model=args.get("model"),
            status=args.get("status"),
            limit=int(args.get("limit", 20)),
        )
    if name == "get_cost_breakdown":
        return get_cost_breakdown(
            db, project_id,
            group_by=str(args.get("group_by", "model")),
            hours=int(args.get("hours", 24)),
        )
    if name == "get_active_alerts":
        return get_active_alerts(db, project_id, severity=args.get("severity"))
    if name == "get_diagnosis_summary":
        return get_diagnosis_summary(db, project_id, days=int(args.get("days", 7)))
    if name == "get_call_detail":
        return get_call_detail(db, project_id, call_id=str(args.get("call_id", "")))
    if name == "search_similar_errors":
        return search_similar_errors(
            db, project_id,
            query=str(args.get("query", "")),
            limit=int(args.get("limit", 5)),
        )
    if name == "get_cost_forecast":
        return get_cost_forecast(db, project_id)
    if name == "get_weekly_impact_summary":
        return get_weekly_impact_summary(db, project_id)

    return {"error": f"Unknown tool: {name}"}
