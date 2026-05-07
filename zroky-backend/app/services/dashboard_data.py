from __future__ import annotations

import json
import math
from collections import defaultdict
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Mapping

from app.db.models import Call, DiagnosisJob
from app.services.currency import (
    BASE_CURRENCY,
    TOKEN_UNIT,
    append_confidence_reason,
    build_currency_context,
    convert_usd_amount,
)
from app.services.cost_trust import isoformat_utc, pricing_age_days
from app.services.privacy import mask_payload


def safe_load_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return mask_payload(parsed)


def extract_payload(job: DiagnosisJob) -> dict[str, Any]:
    if job.call is not None and job.call.payload_json:
        return safe_load_json(job.call.payload_json)
    return safe_load_json(job.payload_json)


def extract_call_payload(call: Call) -> dict[str, Any]:
    return safe_load_json(call.payload_json)


def extract_result(job: DiagnosisJob) -> dict[str, Any]:
    return safe_load_json(job.result_json)


def extract_diagnosis_categories(result_payload: Mapping[str, Any]) -> list[str]:
    diagnoses = result_payload.get("diagnoses")
    if not isinstance(diagnoses, list):
        return []
    categories: list[str] = []
    for diagnosis in diagnoses:
        if isinstance(diagnosis, Mapping):
            category = diagnosis.get("category")
            if isinstance(category, str) and category.strip():
                categories.append(category)
    return categories


def severity_for_category(category: str) -> str:
    normalized = category.strip().upper()
    if normalized in {"AUTH_FAILURE", "COST_SPIKE", "LOOP_DETECTED"}:
        return "high"
    if normalized in {"RATE_LIMIT", "TOKEN_OVERFLOW", "PROVIDER_ERROR"}:
        return "medium"
    return "low"


def to_float(value: Any, *, fallback: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback
        try:
            return float(text)
        except ValueError:
            return fallback
    return fallback


def to_int(value: Any, *, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback
        try:
            return int(float(text))
        except ValueError:
            return fallback
    return fallback


def _pick(payload: Mapping[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        current: Any = payload
        for segment in path:
            if not isinstance(current, Mapping) or segment not in current:
                current = None
                break
            current = current[segment]
        if current is not None:
            return current
    return None


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate:
        return None

    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_call_metrics(payload: Mapping[str, Any]) -> dict[str, Any]:
    prompt_tokens = to_int(_pick(payload, ("prompt_tokens",), ("usage", "prompt_tokens")))
    completion_tokens = to_int(
        _pick(payload, ("completion_tokens",), ("usage", "completion_tokens")),
    )
    total_tokens = to_int(
        _pick(payload, ("total_tokens",), ("usage", "total_tokens")),
        fallback=prompt_tokens + completion_tokens,
    )

    cost_usd = to_float(
        _pick(
            payload,
            ("cost_usd",),
            ("total_cost_usd",),
            ("cost", "per_call_breakdown", "total_cost_usd"),
            ("cost", "total_usd"),
            ("usage", "total_cost_usd"),
        )
    )
    reasoning_cost_usd = to_float(
        _pick(
            payload,
            ("reasoning_cost_usd",),
            ("cost", "reasoning_cost_usd"),
            ("cost", "per_call_breakdown", "reasoning_cost_usd"),
            ("usage", "reasoning_cost_usd"),
        ),
    )
    cache_savings_usd = to_float(
        _pick(
            payload,
            ("cache_savings_usd",),
            ("cost", "cache_savings_usd"),
            ("cost", "per_call_breakdown", "cache_savings_usd"),
            ("usage", "cache_savings_usd"),
        ),
    )
    pricing_version = _pick(payload, ("pricing_version",), ("cost", "pricing_version"), ("cost", "per_call_breakdown", "pricing_version"))
    pricing_source = _pick(payload, ("pricing_source",), ("cost", "pricing_source"), ("cost", "per_call_breakdown", "pricing_source"))
    pricing_last_updated_at = _pick(
        payload,
        ("pricing_last_updated_at",),
        ("cost", "pricing_last_updated_at"),
        ("cost", "per_call_breakdown", "pricing_last_updated_at"),
    )
    pricing_age_days_raw = _pick(
        payload,
        ("pricing_age_days",),
        ("cost", "pricing_age_days"),
        ("cost", "per_call_breakdown", "pricing_age_days"),
    )
    cost_confidence = _pick(payload, ("cost_confidence",), ("cost", "cost_confidence"), ("cost", "per_call_breakdown", "cost_confidence"))

    pricing_age_days = to_int(pricing_age_days_raw, fallback=-1)
    if pricing_age_days < 0 and isinstance(pricing_last_updated_at, str) and pricing_last_updated_at.strip():
        parsed_last_updated_at = _parse_iso_datetime(pricing_last_updated_at)
        if parsed_last_updated_at is not None:
            age = utc_now() - parsed_last_updated_at
            pricing_age_days = max(0, int(age.total_seconds() // (24 * 60 * 60)))

    latency_ms = to_int(
        _pick(
            payload,
            ("latency_ms",),
            ("response_latency_ms",),
            ("timings", "latency_ms"),
            ("provider_latency_ms",),
        ),
        fallback=-1,
    )

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": max(total_tokens, 0),
        "cost_usd": max(cost_usd, 0.0),
        "reasoning_cost_usd": max(reasoning_cost_usd, 0.0),
        "cache_savings_usd": max(cache_savings_usd, 0.0),
        "latency_ms": None if latency_ms < 0 else latency_ms,
        "pricing_version": str(pricing_version) if pricing_version is not None else None,
        "pricing_source": str(pricing_source) if pricing_source is not None else None,
        "pricing_last_updated_at": str(pricing_last_updated_at) if pricing_last_updated_at is not None else None,
        "pricing_age_days": None if pricing_age_days < 0 else pricing_age_days,
        "cost_confidence": str(cost_confidence) if cost_confidence is not None else None,
    }


def build_call_item(job: DiagnosisJob) -> dict[str, Any]:
    payload = extract_payload(job)
    result_payload = extract_result(job)
    metrics = extract_call_metrics(payload)

    provider = _pick(payload, ("provider",), ("request", "provider"))
    model = _pick(payload, ("model",), ("request", "model"))
    agent_name = _pick(payload, ("agent_name",), ("agent",), ("meta", "agent_name"))
    user_id = _pick(payload, ("user_id",), ("user",), ("meta", "user_id"))
    call_type = _pick(payload, ("call_type",), ("request", "call_type"), ("meta", "call_type"))

    categories = extract_diagnosis_categories(result_payload)
    has_blast_radius = isinstance(result_payload.get("blast_radius"), Mapping)

    return {
        "call_id": job.diagnosis_id,
        "tenant_id": job.tenant_id,
        "status": job.status,
        "provider": str(provider) if provider is not None else None,
        "model": str(model) if model is not None else None,
        "agent_name": str(agent_name) if agent_name is not None else None,
        "user_id": str(user_id) if user_id is not None else None,
        "call_type": str(call_type) if call_type is not None else None,
        "total_tokens": metrics["total_tokens"],
        "cost_usd": round(metrics["cost_usd"], 6),
        "cost_total_usd": round(metrics["cost_usd"], 6),
        "cost_total_display": round(metrics["cost_usd"], 6),
        "display_currency": BASE_CURRENCY,
        "requested_display_currency": BASE_CURRENCY,
        "exchange_rate_used": None,
        "exchange_rate_timestamp": None,
        "exchange_rate_source": None,
        "exchange_rates_mixed": False,
        "pricing_version": metrics["pricing_version"],
        "pricing_source": metrics["pricing_source"],
        "pricing_last_updated_at": metrics["pricing_last_updated_at"],
        "pricing_age_days": metrics["pricing_age_days"],
        "cost_currency": BASE_CURRENCY,
        "token_unit": TOKEN_UNIT,
        "cost_confidence": metrics["cost_confidence"],
        "latency_ms": metrics["latency_ms"],
        "error_code": None,
        "diagnoses": categories,
        "has_blast_radius": has_blast_radius,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def build_call_item_from_call(
    call: Call,
    job: DiagnosisJob | None = None,
    *,
    display_currency: str | None = "USD",
) -> dict[str, Any]:
    payload = extract_call_payload(call)
    metadata = safe_load_json(call.metadata_json)
    result_payload = extract_result(job) if job is not None else {}
    metrics = extract_call_metrics(payload)

    agent_name = call.agent_name or _pick(payload, ("agent_name",), ("agent",), ("meta", "agent_name"))
    if agent_name is None:
        agent_name = metadata.get("agent_name")

    user_id = call.user_id or _pick(payload, ("user_id",), ("user",), ("meta", "user_id"))
    if user_id is None:
        user_id = metadata.get("user_id")

    call_type = call.call_type or _pick(payload, ("call_type",), ("request", "call_type"), ("meta", "call_type"))
    if call_type is None:
        call_type = metadata.get("call_type")

    categories = extract_diagnosis_categories(result_payload)
    has_blast_radius = isinstance(result_payload.get("blast_radius"), Mapping)
    total_tokens = call.total_tokens if call.total_tokens is not None else metrics["total_tokens"]
    cost_usd = call.cost_total if call.cost_total is not None else metrics["cost_usd"]
    latency_ms = call.latency_ms if call.latency_ms is not None else metrics["latency_ms"]
    age_days = pricing_age_days(call.pricing_last_updated_at, now=utc_now())
    currency_context = build_currency_context([call], display_currency)
    cost_total_usd = round(max(to_float(cost_usd), 0.0), 6)
    response_confidence = call.cost_confidence
    response_reason = call.confidence_reason
    if currency_context.missing_exchange_rate:
        response_confidence = "degraded"
        response_reason = append_confidence_reason(response_reason, "missing_exchange_rate")

    return {
        "call_id": call.id,
        "tenant_id": call.project_id,
        "status": call.status,
        "provider": call.provider,
        "model": call.model,
        "agent_name": str(agent_name) if agent_name is not None else None,
        "user_id": str(user_id) if user_id is not None else None,
        "call_type": str(call_type) if call_type is not None else None,
        "total_tokens": max(to_int(total_tokens), 0),
        "cost_usd": cost_total_usd,
        "cost_total_usd": cost_total_usd,
        "cost_total_display": convert_usd_amount(cost_total_usd, call=call, context=currency_context),
        **currency_context.as_dict(),
        "pricing_version": call.pricing_version,
        "pricing_source": call.pricing_source,
        "pricing_last_updated_at": isoformat_utc(call.pricing_last_updated_at),
        "pricing_age_days": age_days,
        "cost_currency": call.cost_currency or BASE_CURRENCY,
        "token_unit": call.token_unit or TOKEN_UNIT,
        "cost_confidence": response_confidence,
        "confidence_reason": response_reason,
        "latency_ms": int(latency_ms) if isinstance(latency_ms, (int, float)) else None,
        "error_code": call.error_code or None,
        "diagnoses": categories,
        "has_blast_radius": has_blast_radius,
        "created_at": call.created_at,
        "updated_at": job.updated_at if job is not None else call.created_at,
    }


def percentile(values: list[float], target: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = (len(sorted_values) - 1) * target
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return float(sorted_values[int(index)])
    lower_value = sorted_values[lower]
    upper_value = sorted_values[upper]
    weight = index - lower
    return float(lower_value + (upper_value - lower_value) * weight)


def aggregate_cost_by_key(jobs: list[DiagnosisJob], key: str) -> dict[str, dict[str, float | int]]:
    aggregated: dict[str, dict[str, float | int]] = defaultdict(lambda: {"total_cost_usd": 0.0, "call_count": 0})
    for job in jobs:
        payload = extract_payload(job)
        metrics = extract_call_metrics(payload)
        raw_value = payload.get(key)
        if raw_value is None and isinstance(payload.get("request"), Mapping):
            raw_value = payload["request"].get(key)
        label = str(raw_value) if raw_value else "unknown"
        aggregated[label]["total_cost_usd"] = float(aggregated[label]["total_cost_usd"]) + metrics["cost_usd"]
        aggregated[label]["call_count"] = int(aggregated[label]["call_count"]) + 1
    return aggregated


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
