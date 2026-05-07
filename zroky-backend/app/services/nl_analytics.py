"""Natural language query interface for dashboard analytics."""

from __future__ import annotations

import json
import re
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Call, DiagnosisJob, ProjectAlert
from app.services.llm_client import get_llm_client
from app.services.llm_observability import record_platform_llm_call


class NLAnalyticsService:
    """Service for natural language analytics queries."""

    def __init__(self) -> None:
        self.client = get_llm_client()
        self.model = get_settings().OPENROUTER_ANALYTICS_MODEL

    def parse_query(self, query: str, db: Session | None = None) -> dict[str, Any]:
        """Parse natural language query into structured analytics request."""

        system_prompt = """You are an analytics query parser. Convert natural language queries into structured analytics requests.

Available entity types:
- calls: API calls made to AI providers
- diagnoses: Diagnosis jobs for errors
- alerts: Active system alerts
- costs: Cost/spending data
- loops: Loop detection events
- fixes: Fix applications and events

Available time ranges:
- today, yesterday
- last_hour, last_4h, last_24h, last_7d, last_30d
- this_week, this_month
- specific dates: YYYY-MM-DD

Available filters:
- status: success, failed, error
- provider: openai, anthropic, etc.
- model: gpt-4, claude-3, etc.
- diagnosis_type: TOKEN_OVERFLOW, RATE_LIMIT, etc.
- severity: low, medium, high, critical

Available aggregations:
- count, sum, avg, max, min
- group_by: hour, day, provider, model, status

Respond in JSON:
{
  "intent": "query|summarize|compare|trend|anomaly",
  "entity_type": "calls|diagnoses|alerts|costs|loops|fixes",
  "time_range": {"from": "ISO8601", "to": "ISO8601"},
  "filters": [{"field": "status", "op": "eq|ne|gt|lt|in", "value": "failed"}],
  "aggregation": {"type": "count|sum|avg", "field": "cost_total"},
  "group_by": "hour|day|provider|model",
  "sort": {"field": "timestamp", "order": "desc"},
  "limit": 100,
  "natural_summary": "Human-readable description of the query"
}"""

        try:
            start = _time.perf_counter()
            response = self.client.chat_completions_create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Parse this query: {query}"},
                ],
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=500,
            )
            latency_ms = (_time.perf_counter() - start) * 1000.0
            if db is not None:
                record_platform_llm_call(
                    db,
                    purpose="nl_analytics_parse",
                    response=response,
                    latency_ms=latency_ms,
                    request_messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Parse this query: {query}"},
                    ],
                )

            result = json.loads(response.choices[0].message.content)

            # Post-process time ranges
            if "time_range" in result and isinstance(result["time_range"], str):
                result["time_range"] = self._parse_time_range(result["time_range"])

            return result

        except Exception as e:
            return {
                "error": f"Failed to parse query: {e}",
                "original_query": query,
            }

    def _parse_time_range(self, time_expr: str) -> dict[str, str]:
        """Convert time expression to ISO date range."""
        now = datetime.now(timezone.utc)

        ranges = {
            "today": (now.replace(hour=0, minute=0, second=0), now),
            "yesterday": (now - timedelta(days=1), now.replace(hour=0, minute=0, second=0)),
            "last_hour": (now - timedelta(hours=1), now),
            "last_4h": (now - timedelta(hours=4), now),
            "last_24h": (now - timedelta(days=1), now),
            "last_7d": (now - timedelta(days=7), now),
            "last_30d": (now - timedelta(days=30), now),
            "this_week": (now - timedelta(days=now.weekday()), now),
            "this_month": (now.replace(day=1), now),
        }
        
        if time_expr in ranges:
            start, end = ranges[time_expr]
            return {
                "from": start.isoformat(),
                "to": end.isoformat(),
            }
        
        # Try to parse as specific date
        try:
            date = datetime.strptime(time_expr, "%Y-%m-%d")
            next_day = date + timedelta(days=1)
            return {
                "from": date.isoformat(),
                "to": next_day.isoformat(),
            }
        except ValueError:
            pass
        
        return {"from": (now - timedelta(days=1)).isoformat(), "to": now.isoformat()}

    def execute_query(
        self,
        db: Session,
        project_id: str,
        parsed_query: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute parsed query against database."""
        
        entity_type = parsed_query.get("entity_type", "calls")
        time_range = parsed_query.get("time_range", {})
        filters = parsed_query.get("filters", [])
        aggregation = parsed_query.get("aggregation")
        group_by = parsed_query.get("group_by")
        limit = min(int(parsed_query.get("limit") or 100), 500)

        # Build base query
        if entity_type == "calls":
            return self._query_calls(db, project_id, time_range, filters, aggregation, group_by, limit)
        elif entity_type == "diagnoses":
            return self._query_diagnoses(db, project_id, time_range, filters, limit)
        elif entity_type == "alerts":
            return self._query_alerts(db, project_id, time_range, filters, limit)
        else:
            return {"error": f"Unknown entity type: {entity_type}"}

    def _query_calls(
        self,
        db: Session,
        project_id: str,
        time_range: dict[str, str],
        filters: list[dict],
        aggregation: dict[str, Any] | None,
        group_by: str | None,
        limit: int,
    ) -> dict[str, Any]:
        """Query calls with filters and aggregation."""
        
        # Base query
        stmt = select(Call).where(Call.project_id == project_id)
        
        # Apply time range
        if time_range.get("from"):
            stmt = stmt.where(Call.created_at >= time_range["from"])
        if time_range.get("to"):
            stmt = stmt.where(Call.created_at < time_range["to"])
        
        # Apply filters
        _ALLOWED_CALL_FILTER_FIELDS = {
            "status", "provider", "model", "error_code",
            "user_id", "call_type", "agent_name",
        }
        for f in filters:
            field = f.get("field")
            op = f.get("op", "eq")
            value = f.get("value")

            if field not in _ALLOWED_CALL_FILTER_FIELDS:
                continue
            column = getattr(Call, field)

            if op == "eq":
                stmt = stmt.where(column == value)
            elif op == "ne":
                stmt = stmt.where(column != value)
            elif op == "in" and isinstance(value, list):
                stmt = stmt.where(column.in_(value))
        
        # Aggregation
        if aggregation:
            agg_type = aggregation.get("type")
            agg_field = aggregation.get("field", "id")
            
            if agg_type == "count":
                stmt = select(func.count()).select_from(stmt.subquery())
            elif agg_type == "sum":
                column = getattr(Call, agg_field, Call.cost_total)
                stmt = select(func.sum(column)).select_from(stmt.subquery())
            elif agg_type == "avg":
                column = getattr(Call, agg_field, Call.latency_ms)
                stmt = select(func.avg(column)).select_from(stmt.subquery())
        
        # Group by
        if group_by and not aggregation:
            if group_by == "hour":
                stmt = (
                    select(
                        func.date_trunc("hour", Call.created_at).label("hour"),
                        func.count().label("count"),
                        func.sum(Call.cost_total).label("total_cost"),
                    )
                    .where(Call.project_id == project_id)
                    .group_by(func.date_trunc("hour", Call.created_at))
                    .order_by(func.date_trunc("hour", Call.created_at).desc())
                    .limit(limit)
                )
            elif group_by == "status":
                stmt = (
                    select(Call.status, func.count().label("count"))
                    .where(Call.project_id == project_id)
                    .group_by(Call.status)
                )
            elif group_by == "provider":
                stmt = (
                    select(Call.provider, func.count().label("count"))
                    .where(Call.project_id == project_id)
                    .group_by(Call.provider)
                )
        
        # Execute
        if aggregation:
            value = db.execute(stmt).scalar()
            return {
                "type": "aggregation",
                "aggregation": aggregation,
                "value": float(value) if value is not None else 0,
            }

        if group_by in {"hour", "status", "provider"}:
            # These stmts return named SQL aggregate rows — use _asdict()
            rows = [row._asdict() for row in db.execute(stmt)]
        else:
            # Plain ORM entity select — use scalars() for proper Call access
            calls = db.execute(stmt.limit(limit)).scalars().all()
            rows = [
                {
                    "id": c.id,
                    "status": c.status,
                    "provider": c.provider,
                    "model": c.model,
                    "cost": float(c.cost_total or 0),
                    "timestamp": c.created_at.isoformat() if c.created_at else None,
                }
                for c in calls
            ]

        return {
            "type": "list",
            "count": len(rows),
            "data": rows[:limit],
        }

    def _query_diagnoses(
        self,
        db: Session,
        project_id: str,
        time_range: dict[str, str],
        filters: list[dict],
        limit: int,
    ) -> dict[str, Any]:
        """Query diagnosis jobs."""
        
        stmt = select(DiagnosisJob).where(DiagnosisJob.tenant_id == project_id)
        
        if time_range.get("from"):
            stmt = stmt.where(DiagnosisJob.created_at >= time_range["from"])
        
        stmt = stmt.order_by(DiagnosisJob.created_at.desc()).limit(limit)
        
        jobs = db.execute(stmt).scalars().all()
        rows = [
            {
                "diagnosis_id": job.diagnosis_id,
                "status": job.status,
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }
            for job in jobs
        ]
        return {"type": "list", "count": len(rows), "data": rows}

    def _query_alerts(
        self,
        db: Session,
        project_id: str,
        time_range: dict[str, str],
        filters: list[dict],
        limit: int,
    ) -> dict[str, Any]:
        """Query alerts."""
        
        stmt = select(ProjectAlert).where(ProjectAlert.tenant_id == project_id)
        
        if time_range.get("from"):
            stmt = stmt.where(ProjectAlert.created_at >= time_range["from"])
        
        # Apply status filter
        for f in filters:
            if f.get("field") == "status":
                stmt = stmt.where(ProjectAlert.status == f.get("value"))
        
        stmt = stmt.order_by(ProjectAlert.created_at.desc()).limit(limit)
        
        alerts = db.execute(stmt).scalars().all()
        rows = [
            {
                "alert_id": a.id,
                "category": a.category,
                "severity": a.severity,
                "status": a.status,
                "title": a.title,
            }
            for a in alerts
        ]
        return {"type": "list", "count": len(rows), "data": rows}

    def generate_response(
        self,
        query: str,
        results: dict[str, Any],
        db: Session | None = None,
    ) -> dict[str, Any]:
        """Generate natural language response from query results."""

        system_prompt = """Generate a natural language response to a user's analytics query based on the results.
Be concise but informative. Highlight key insights."""

        context = json.dumps({
            "query": query,
            "results": results,
        }, default=str)

        try:
            start = _time.perf_counter()
            response = self.client.chat_completions_create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Generate response:\n{context}"},
                ],
                model=self.model,
                temperature=0.3,
                max_tokens=300,
            )
            latency_ms = (_time.perf_counter() - start) * 1000.0
            if db is not None:
                record_platform_llm_call(
                    db,
                    purpose="nl_analytics_response",
                    response=response,
                    latency_ms=latency_ms,
                    request_messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Generate response:\n{context}"},
                    ],
                )

            return {
                "answer": response.choices[0].message.content,
                "data": results,
            }

        except Exception as e:
            # Fallback to simple response
            result_type = results.get("type", "unknown")

            if result_type == "aggregation":
                value = results.get("value", 0)
                agg = results.get("aggregation", {})
                return {
                    "answer": f"The {agg.get('type', 'count')} is {value}.",
                    "data": results,
                }
            elif result_type == "list":
                count = results.get("count", 0)
                return {
                    "answer": f"Found {count} results for your query.",
                    "data": results,
                }
            else:
                return {
                    "answer": "Query executed successfully.",
                    "data": results,
                }


# Singleton instance
_nl_service: NLAnalyticsService | None = None


def get_nl_analytics_service() -> NLAnalyticsService:
    """Get or create NL analytics service singleton."""
    global _nl_service
    if _nl_service is None:
        _nl_service = NLAnalyticsService()
    return _nl_service
