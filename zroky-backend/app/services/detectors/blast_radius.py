"""Blast-radius enrichment builder."""
from __future__ import annotations

from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_float,
    _as_int,
    _as_str,
    _pick,
)


def build(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _build_blast_radius(payload)


def _build_blast_radius(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    trace_id = _as_str(_pick(payload, ("trace_id",)), fallback="")
    if not trace_id:
        return None

    downstream_calls_any = _pick(
        payload, ("downstream_calls",), ("blast_radius", "downstream_calls"),
    )
    downstream_calls = (
        downstream_calls_any if isinstance(downstream_calls_any, list) else []
    )

    affected_count = _as_int(_pick(payload, ("blast_radius", "downstream_affected_calls")))
    if affected_count <= 0:
        affected_count = len(downstream_calls)

    wasted_cost_usd = _as_float(_pick(payload, ("blast_radius", "wasted_cost_usd")))
    if wasted_cost_usd <= 0:
        wasted_cost_usd = sum(
            _as_float(item.get("wasted_cost_usd"))
            for item in downstream_calls
            if isinstance(item, Mapping)
        )

    if affected_count <= 0 and wasted_cost_usd <= 0:
        return None

    failed_agent = _as_str(
        _pick(payload, ("blast_radius", "failed_agent"), ("agent_name",)),
        fallback="unknown-agent",
    )

    return {
        "trace_id": trace_id,
        "failed_agent": failed_agent,
        "downstream_affected_calls": affected_count,
        "wasted_cost_usd": round(wasted_cost_usd, 6),
        "summary": (
            f"{failed_agent} failure impacted {affected_count} downstream calls"
            f" with estimated wasted cost ${wasted_cost_usd:.2f}."
        ),
    }
