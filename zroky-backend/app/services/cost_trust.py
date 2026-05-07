from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, load_only

from app.db.models import Call
from app.services.currency import (
    BASE_CURRENCY,
    TOKEN_UNIT,
    append_confidence_reason,
    build_currency_context,
    convert_usd_amount,
)

COST_ANALYTICS_WINDOW_DAYS = 14
PRICING_STALE_THRESHOLD_DAYS = 14
CostConfidence = Literal["high", "stale", "degraded"]


@dataclass(frozen=True)
class CostTrustMetadata:
    pricing_version: str | None
    pricing_source: str | None
    pricing_last_updated_at: str | None
    pricing_age_days: int | None
    cost_confidence: CostConfidence
    confidence_reason: str
    baseline_window_days: int = COST_ANALYTICS_WINDOW_DAYS

    def as_dict(self) -> dict[str, str | int | None]:
        return {
            "pricing_version": self.pricing_version,
            "pricing_source": self.pricing_source,
            "pricing_last_updated_at": self.pricing_last_updated_at,
            "pricing_age_days": self.pricing_age_days,
            "cost_confidence": self.cost_confidence,
            "confidence_reason": self.confidence_reason,
            "cost_baseline_window_days": self.baseline_window_days,
        }


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def isoformat_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return as_utc(dt).isoformat()


def cost_window_start(now: datetime) -> datetime:
    return as_utc(now) - timedelta(days=COST_ANALYTICS_WINDOW_DAYS)


def production_call_filters() -> list[Any]:
    """Return SQLAlchemy WHERE clauses that exclude non-production calls.

    Uses the indexed ``is_production`` boolean column written at ingest time,
    replacing the former LIKE scans on large TEXT columns (payload_json /
    metadata_json) which were unindexable and expensive at scale.
    """
    return [Call.is_production == True]  # noqa: E712


def production_calls_query(
    tenant_id: str,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
):
    query = select(Call).where(Call.project_id == tenant_id, *production_call_filters())
    if start_time is not None:
        query = query.where(Call.created_at >= as_utc(start_time))
    if end_time is not None:
        query = query.where(Call.created_at <= as_utc(end_time))
    return query


def fetch_cost_calls(db: Session, tenant_id: str, *, now: datetime) -> list[Call]:
    start = cost_window_start(now)
    return list(
        db.execute(
            production_calls_query(tenant_id, start_time=start, end_time=now)
            .options(load_only(
                Call.provider,
                Call.input_tokens,
                Call.output_tokens,
                Call.total_tokens,
                Call.cost_total,
                Call.reasoning_cost_total,
                Call.cache_savings_total,
                Call.pricing_version,
                Call.pricing_source,
                Call.pricing_last_updated_at,
                Call.cost_confidence,
                Call.confidence_reason,
            ))
            .order_by(Call.created_at.asc())
        )
        .scalars()
        .all()
    )


def earliest_production_call_at(db: Session, tenant_id: str, *, now: datetime) -> datetime | None:
    value = db.execute(
        select(func.min(Call.created_at)).where(
            Call.project_id == tenant_id,
            Call.created_at <= as_utc(now),
            *production_call_filters(),
        )
    ).scalar_one_or_none()
    return value if isinstance(value, datetime) else None


def _metadata_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def user_key_from_call(call: Call) -> str:
    if call.user_id and str(call.user_id).strip():
        return str(call.user_id).strip()

    metadata = _metadata_dict(call.metadata_json)
    user = metadata.get("user_id") or metadata.get("user") or "unknown"
    return str(user) if str(user).strip() else "unknown"


def agent_key_from_call(call: Call) -> str:
    if call.agent_name and str(call.agent_name).strip():
        return str(call.agent_name).strip()

    metadata = _metadata_dict(call.metadata_json)
    agent = metadata.get("agent_name") or metadata.get("agent") or "unknown"
    return str(agent) if str(agent).strip() else "unknown"


def has_missing_tokens(call: Call) -> bool:
    input_tokens = int(call.input_tokens or 0)
    output_tokens = int(call.output_tokens or 0)
    total_tokens = int(call.total_tokens or 0)
    return total_tokens <= 0 and (input_tokens + output_tokens) <= 0


def has_unknown_provider(call: Call) -> bool:
    provider = (call.provider or "").strip().lower()
    return provider in {"", "unknown"}


def pricing_age_days(latest_pricing_at: datetime | None, *, now: datetime) -> int | None:
    if latest_pricing_at is None:
        return None
    age = as_utc(now) - as_utc(latest_pricing_at)
    return max(0, int(age.total_seconds() // (24 * 60 * 60)))


def _aggregate_pricing_source(calls: list[Call]) -> str | None:
    sources = {
        str(call.pricing_source).strip()
        for call in calls
        if call.pricing_source and str(call.pricing_source).strip()
    }
    if not sources:
        return None
    if "fallback_default" in sources:
        return "fallback_default"
    if "cached_rate_card" in sources:
        return "cached_rate_card"
    if "official_provider" in sources:
        return "official_provider"
    return sorted(sources)[0]


def evaluate_cost_trust(
    db: Session,
    tenant_id: str,
    *,
    calls: list[Call],
    now: datetime,
) -> CostTrustMetadata:
    now_utc = as_utc(now)
    start = cost_window_start(now_utc)
    earliest = earliest_production_call_at(db, tenant_id, now=now_utc)

    latest_pricing_call = max(
        (call for call in calls if call.pricing_last_updated_at is not None),
        key=lambda call: as_utc(call.pricing_last_updated_at),
        default=None,
    )
    pricing_last_updated_at = latest_pricing_call.pricing_last_updated_at if latest_pricing_call else None
    pricing_version = latest_pricing_call.pricing_version if latest_pricing_call else None
    pricing_source = _aggregate_pricing_source(calls)
    age_days = pricing_age_days(pricing_last_updated_at, now=now_utc)

    if earliest is None or as_utc(earliest) > start:
        return CostTrustMetadata(
            pricing_version=pricing_version,
            pricing_source=pricing_source,
            pricing_last_updated_at=isoformat_utc(pricing_last_updated_at),
            pricing_age_days=age_days,
            cost_confidence="degraded",
            confidence_reason="insufficient_data",
        )

    if any(has_unknown_provider(call) for call in calls):
        return CostTrustMetadata(
            pricing_version=pricing_version,
            pricing_source=pricing_source,
            pricing_last_updated_at=isoformat_utc(pricing_last_updated_at),
            pricing_age_days=age_days,
            cost_confidence="degraded",
            confidence_reason="provider_unknown",
        )

    if any(has_missing_tokens(call) for call in calls):
        return CostTrustMetadata(
            pricing_version=pricing_version,
            pricing_source=pricing_source,
            pricing_last_updated_at=isoformat_utc(pricing_last_updated_at),
            pricing_age_days=age_days,
            cost_confidence="degraded",
            confidence_reason="missing_tokens",
        )

    if any(not call.pricing_version or call.pricing_last_updated_at is None for call in calls):
        return CostTrustMetadata(
            pricing_version=pricing_version,
            pricing_source=pricing_source,
            pricing_last_updated_at=isoformat_utc(pricing_last_updated_at),
            pricing_age_days=age_days,
            cost_confidence="degraded",
            confidence_reason="missing_pricing",
        )

    if any(not call.pricing_source for call in calls):
        return CostTrustMetadata(
            pricing_version=pricing_version,
            pricing_source=pricing_source,
            pricing_last_updated_at=isoformat_utc(pricing_last_updated_at),
            pricing_age_days=age_days,
            cost_confidence="degraded",
            confidence_reason="missing_pricing_source",
        )

    if any(call.pricing_source == "fallback_default" for call in calls):
        return CostTrustMetadata(
            pricing_version=pricing_version,
            pricing_source=pricing_source,
            pricing_last_updated_at=isoformat_utc(pricing_last_updated_at),
            pricing_age_days=age_days,
            cost_confidence="degraded",
            confidence_reason="fallback_rate_card",
        )

    degraded_call = next((call for call in calls if call.cost_confidence == "degraded"), None)
    if degraded_call is not None:
        return CostTrustMetadata(
            pricing_version=pricing_version,
            pricing_source=pricing_source,
            pricing_last_updated_at=isoformat_utc(pricing_last_updated_at),
            pricing_age_days=age_days,
            cost_confidence="degraded",
            confidence_reason=degraded_call.confidence_reason or "stored_degraded_cost",
        )

    if age_days is None:
        return CostTrustMetadata(
            pricing_version=pricing_version,
            pricing_source=pricing_source,
            pricing_last_updated_at=None,
            pricing_age_days=None,
            cost_confidence="degraded",
            confidence_reason="missing_pricing",
        )

    if age_days > PRICING_STALE_THRESHOLD_DAYS or any(call.cost_confidence == "stale" for call in calls):
        return CostTrustMetadata(
            pricing_version=pricing_version,
            pricing_source=pricing_source,
            pricing_last_updated_at=isoformat_utc(pricing_last_updated_at),
            pricing_age_days=age_days,
            cost_confidence="stale",
            confidence_reason="pricing_catalog_stale",
        )

    return CostTrustMetadata(
        pricing_version=pricing_version,
        pricing_source=pricing_source,
        pricing_last_updated_at=isoformat_utc(pricing_last_updated_at),
        pricing_age_days=age_days,
        cost_confidence="high",
        confidence_reason="fresh_pricing_full_baseline",
    )


def cost_audit_from_call(call: Call, *, display_currency: str | None = "USD") -> dict[str, Any]:
    age_days = pricing_age_days(call.pricing_last_updated_at, now=datetime.now(timezone.utc))
    currency_context = build_currency_context([call], display_currency)
    total_cost_usd = round(float(call.cost_total or 0.0), 6)
    reasoning_cost_usd = round(float(call.reasoning_cost_total or 0.0), 6)
    cache_savings_usd = round(float(call.cache_savings_total or 0.0), 6)
    response_confidence = call.cost_confidence
    response_reason = call.confidence_reason
    if currency_context.missing_exchange_rate:
        response_confidence = "degraded"
        response_reason = append_confidence_reason(response_reason, "missing_exchange_rate")
    per_call_breakdown = {
        "provider": call.provider,
        "model": call.model,
        "status": call.status,
        "total_cost_usd": total_cost_usd,
        "total_cost_display": convert_usd_amount(total_cost_usd, call=call, context=currency_context),
        "display_currency": currency_context.display_currency,
        "currency": BASE_CURRENCY,
        "token_unit": TOKEN_UNIT,
        "reasoning_cost_usd": reasoning_cost_usd,
        "cache_savings_usd": cache_savings_usd,
        "cost_confidence": response_confidence,
        "confidence_reason": response_reason,
        "pricing_source": call.pricing_source,
    }
    return {
        "total_cost_usd": total_cost_usd,
        "cost_total_usd": total_cost_usd,
        "total_cost_display": convert_usd_amount(total_cost_usd, call=call, context=currency_context),
        "cost_total_display": convert_usd_amount(total_cost_usd, call=call, context=currency_context),
        **currency_context.as_dict(),
        "input_tokens": int(call.input_tokens or 0),
        "output_tokens": int(call.output_tokens or 0),
        "reasoning_tokens": int(call.reasoning_tokens or 0),
        "total_tokens": int(call.total_tokens or 0),
        "reasoning_cost_usd": reasoning_cost_usd,
        "cache_savings_usd": cache_savings_usd,
        "pricing_version": call.pricing_version,
        "pricing_source": call.pricing_source,
        "pricing_last_updated_at": isoformat_utc(call.pricing_last_updated_at),
        "pricing_age_days": age_days,
        "cost_currency": call.cost_currency or BASE_CURRENCY,
        "token_unit": call.token_unit or TOKEN_UNIT,
        "cost_confidence": response_confidence,
        "confidence_reason": response_reason,
        "per_call_breakdown": per_call_breakdown,
        "source_of_truth": "calls",
    }
