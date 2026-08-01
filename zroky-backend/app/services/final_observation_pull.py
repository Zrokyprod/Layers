from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FinalObservation, FinalOutcomeGraph, FinalSourceConnector, FinalWorkflowIntent
from app.services.final_observations import create_final_observation_row
from app.services.stripe_refunds import refund_observation_state


class ObservationPullError(RuntimeError):
    pass


def active_source_connector(db: Session, *, graph: FinalOutcomeGraph, binding: dict[str, Any]) -> FinalSourceConnector | None:
    capability = str(binding.get("connector_capability") or "").strip()
    if not capability:
        return None
    return db.execute(
        select(FinalSourceConnector).where(
            FinalSourceConnector.project_id == graph.project_id,
            FinalSourceConnector.environment == graph.environment,
            FinalSourceConnector.capability == capability,
            FinalSourceConnector.status == "active",
        )
    ).scalar_one_or_none()


def pull_observation(db: Session, *, graph: FinalOutcomeGraph, binding: dict[str, Any]) -> FinalObservation | None:
    connector = active_source_connector(db, graph=graph, binding=binding)
    if connector is None:
        return None
    if connector.connector_kind != "stripe":
        return None
    intent = db.execute(
        select(FinalWorkflowIntent).where(
            FinalWorkflowIntent.id == graph.intent_id,
            FinalWorkflowIntent.project_id == graph.project_id,
        )
    ).scalar_one_or_none()
    if intent is None:
        return None
    secret = os.environ.get(connector.secret_ref, "").strip()
    if not secret:
        raise ObservationPullError(f"Stripe credential secret_ref {connector.secret_ref} is not configured.")
    intent_payload = _loads(intent.intent_json)
    refund_id = _first_text(intent_payload, "refund_id", "stripe_refund_id")
    charge_id = _first_text(intent_payload, "charge_id", "stripe_charge_id")
    if not refund_id and not charge_id:
        return None
    now = datetime.now(UTC)
    config = _loads(connector.config_json)
    source_binding = str(binding.get("key") or "")
    max_freshness = int(binding.get("freshness_seconds") or config.get("max_freshness_seconds") or 300)

    refund = _stripe_refund(secret, refund_id=refund_id, charge_id=charge_id, secret_ref=connector.secret_ref)
    observed_state = refund_observation_state(refund) if refund is not None else None
    observed_at = _stripe_time(refund.get("created")) if refund is not None else now
    observed_ref = f"stripe:refund:{refund_id}" if refund_id else f"stripe:charge:{charge_id}:refunds"
    return create_final_observation_row(
        db,
        project_id=graph.project_id,
        environment=graph.environment,
        run_id=str(_loads(graph.graph_json).get("run_id") or "") or None,
        intent_id=graph.intent_id,
        source_kind="stripe_refund",
        observed_object_ref=observed_ref,
        observed_state=observed_state,
        provenance={
            "source_binding": source_binding,
            "connector_capability": connector.capability,
            "connector_kind": connector.connector_kind,
            "acquired_via": "server_pull",
            "stripe_object": "refund",
            "record_found": refund is not None,
        },
        observed_at=observed_at,
        read_at=now,
        max_freshness_seconds=max_freshness,
        commit=False,
    )


def _stripe_refund(secret: str, *, refund_id: str | None, charge_id: str | None, secret_ref: str) -> dict[str, Any] | None:
    if refund_id:
        try:
            return _stripe_get_json(secret, f"https://api.stripe.com/v1/refunds/{refund_id}", secret_ref=secret_ref)
        except ObservationPullError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
    if not charge_id:
        return None
    result = _stripe_get_json(
        secret,
        "https://api.stripe.com/v1/refunds",
        params={"charge": charge_id, "limit": "10"},
        secret_ref=secret_ref,
    )
    rows = result.get("data")
    if not isinstance(rows, list) or not rows:
        return None
    first = rows[0]
    return first if isinstance(first, dict) else None


def _stripe_get_json(
    secret: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    secret_ref: str,
) -> dict[str, Any]:
    try:
        response = httpx.get(url, auth=(secret, ""), params=params, timeout=10.0)
        if response.status_code >= 400:
            raise ObservationPullError(f"Stripe fetch failed for secret_ref {secret_ref}: HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ObservationPullError(f"Stripe fetch failed for secret_ref {secret_ref}: invalid response") from exc
    except httpx.HTTPError as exc:
        raise ObservationPullError(f"Stripe fetch failed for secret_ref {secret_ref}: {exc.__class__.__name__}") from exc
    if not isinstance(payload, dict):
        raise ObservationPullError(f"Stripe fetch failed for secret_ref {secret_ref}: invalid response")
    return payload


def _stripe_time(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except Exception:
        return datetime.now(UTC)


def _first_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
