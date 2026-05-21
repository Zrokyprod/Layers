"""Tests for outcome_attribution service.

Covers:
  - ingest_outcome: basic + idempotency
  - get_attribution_summary: empty / by-type / by-cluster
  - normalise_stripe_refund / normalise_zendesk_ticket / normalise_salesforce_event
  - get_replay_prevented_savings
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services.outcome_attribution import (
    _extract_detector,
    get_attribution_summary,
    get_call_outcomes,
    get_replay_prevented_savings,
    ingest_outcome,
    normalise_salesforce_event,
    normalise_stripe_refund,
    normalise_zendesk_ticket,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_outcome(
    *,
    id="evt-1",
    project_id="proj-1",
    call_id="call-1",
    outcome_type="refund_issued",
    amount_usd=Decimal("49.00"),
    source="api",
    external_ref=None,
    idempotency_key=None,
    occurred_at=None,
    metadata_json=None,
    created_at=None,
):
    o = MagicMock()
    o.id = id
    o.project_id = project_id
    o.call_id = call_id
    o.outcome_type = outcome_type
    o.amount_usd = amount_usd
    o.source = source
    o.external_ref = external_ref
    o.idempotency_key = idempotency_key
    o.occurred_at = occurred_at or datetime.now(timezone.utc)
    o.metadata_json = metadata_json
    o.created_at = created_at or datetime.now(timezone.utc)
    return o


def _db_empty():
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    db.execute.return_value.scalars.return_value.all.return_value = []
    return db


# ── ingest_outcome ─────────────────────────────────────────────────────────────


class TestIngestOutcome:
    def test_creates_new_event(self):
        db = _db_empty()
        with patch("app.services.outcome_attribution.uuid4", return_value="uuid-1"):
            evt = ingest_outcome(
                db,
                project_id="proj-1",
                outcome_type="refund_issued",
                amount_usd=49.0,
                call_id="call-1",
            )
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_idempotent_returns_existing(self):
        existing = _make_outcome(idempotency_key="key-1")
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = existing

        result = ingest_outcome(
            db,
            project_id="proj-1",
            outcome_type="refund_issued",
            amount_usd=49.0,
            idempotency_key="key-1",
        )

        assert result is existing
        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_no_idempotency_key_always_inserts(self):
        db = _db_empty()
        ingest_outcome(
            db,
            project_id="proj-1",
            outcome_type="ticket_escalated",
            amount_usd=18.0,
        )
        db.add.assert_called_once()

    def test_metadata_serialised(self):
        db = _db_empty()
        ingest_outcome(
            db,
            project_id="proj-1",
            outcome_type="custom",
            amount_usd=5.0,
            metadata={"order_id": "ORD-1"},
        )
        added = db.add.call_args[0][0]
        assert json.loads(added.metadata_json) == {"order_id": "ORD-1"}


# ── get_attribution_summary ────────────────────────────────────────────────────


class TestAttributionSummary:
    def test_empty_returns_zeros(self):
        db = _db_empty()
        summary = get_attribution_summary(db, project_id="proj-1", days=30)

        assert summary.total_outcome_usd == 0.0
        assert summary.linked_outcome_count == 0
        assert summary.unlinked_outcome_count == 0
        assert summary.by_type == []
        assert summary.by_cluster == []

    def test_by_type_aggregation(self):
        o1 = _make_outcome(id="e1", outcome_type="refund_issued", amount_usd=Decimal("100.00"))
        o2 = _make_outcome(id="e2", outcome_type="refund_issued", amount_usd=Decimal("50.00"))
        o3 = _make_outcome(id="e3", outcome_type="ticket_escalated", amount_usd=Decimal("18.00"))

        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = [o1, o2, o3]

        # Secondary queries return empty
        db.execute.side_effect = [
            MagicMock(**{"scalars.return_value.all.return_value": [o1, o2, o3]}),
            MagicMock(**{"scalars.return_value.all.return_value": []}),
            MagicMock(**{"scalars.return_value.all.return_value": []}),
        ]

        summary = get_attribution_summary(db, project_id="proj-1", days=30)

        assert summary.total_outcome_usd == pytest.approx(168.0)
        assert len(summary.by_type) == 2
        refund_row = next(t for t in summary.by_type if t.outcome_type == "refund_issued")
        assert refund_row.total_usd == pytest.approx(150.0)
        assert refund_row.count == 2
        assert refund_row.avg_usd == pytest.approx(75.0)

    def test_unlinked_vs_linked_split(self):
        linked = _make_outcome(id="e1", call_id="call-A", amount_usd=Decimal("50.00"))
        unlinked = _make_outcome(id="e2", call_id=None, amount_usd=Decimal("20.00"))

        db = MagicMock()
        db.execute.side_effect = [
            MagicMock(**{"scalars.return_value.all.return_value": [linked, unlinked]}),
            MagicMock(**{"scalars.return_value.all.return_value": []}),
            MagicMock(**{"scalars.return_value.all.return_value": []}),
        ]

        summary = get_attribution_summary(db, project_id="proj-1", days=30)

        assert summary.linked_outcome_count == 1
        assert summary.unlinked_outcome_count == 1
        assert summary.total_outcome_usd == pytest.approx(70.0)

    def test_monthly_savings_extrapolation(self):
        o = _make_outcome(call_id="c1", amount_usd=Decimal("300.00"))

        db = MagicMock()
        db.execute.side_effect = [
            MagicMock(**{"scalars.return_value.all.return_value": [o]}),
            MagicMock(**{"scalars.return_value.all.return_value": []}),
            MagicMock(**{"scalars.return_value.all.return_value": []}),
        ]

        summary = get_attribution_summary(db, project_id="proj-1", days=30)

        assert len(summary.by_cluster) >= 1
        cluster = summary.by_cluster[0]
        assert cluster.estimated_monthly_savings_usd == pytest.approx(300.0)


# ── Webhook normalisation ──────────────────────────────────────────────────────


class TestNormaliseStripe:
    def test_basic_refund(self):
        payload = {
            "type": "charge.refund.created",
            "data": {
                "object": {
                    "id": "re_abc",
                    "amount": 4900,
                    "currency": "usd",
                    "reason": "fraudulent",
                    "metadata": {"zroky_call_id": "call-xyz"},
                }
            },
        }
        fields = normalise_stripe_refund(payload)
        assert fields["outcome_type"] == "refund_issued"
        assert fields["amount_usd"] == pytest.approx(49.0)
        assert fields["call_id"] == "call-xyz"
        assert fields["source"] == "stripe"
        assert fields["idempotency_key"] == "stripe:re_abc"

    def test_no_call_id_metadata(self):
        payload = {"data": {"object": {"id": "re_def", "amount": 1000, "currency": "usd"}}}
        fields = normalise_stripe_refund(payload)
        assert fields["call_id"] is None

    def test_non_usd_amount_passthrough(self):
        payload = {"data": {"object": {"id": "re_eur", "amount": 2000, "currency": "EUR"}}}
        fields = normalise_stripe_refund(payload)
        assert fields["amount_usd"] == pytest.approx(20.0)


class TestNormaliseZendesk:
    def test_basic_ticket(self):
        payload = {"ticket": {"id": 99, "status": "open", "priority": "high"}}
        fields = normalise_zendesk_ticket(payload)
        assert fields["outcome_type"] == "ticket_escalated"
        assert fields["amount_usd"] == pytest.approx(18.0)
        assert fields["idempotency_key"] == "zendesk:99"
        assert fields["source"] == "zendesk"

    def test_call_id_from_custom_field(self):
        payload = {
            "ticket": {
                "id": 77,
                "custom_fields": [{"id": "zroky_call_id", "value": "call-zzz"}],
            }
        }
        fields = normalise_zendesk_ticket(payload)
        assert fields["call_id"] == "call-zzz"


class TestNormaliseSalesforce:
    def test_basic_churn(self):
        payload = {
            "sobject": {
                "Id": "sf-001",
                "Amount": 15000,
                "StageName": "Closed Lost",
                "Zroky_Call_Id__c": "call-sf",
            }
        }
        fields = normalise_salesforce_event(payload)
        assert fields["outcome_type"] == "churn"
        assert fields["amount_usd"] == pytest.approx(15000.0)
        assert fields["call_id"] == "call-sf"
        assert fields["source"] == "salesforce"
        assert fields["idempotency_key"] == "salesforce:sf-001"

    def test_no_amount(self):
        payload = {"sobject": {"Id": "sf-002"}}
        fields = normalise_salesforce_event(payload)
        assert fields["amount_usd"] == pytest.approx(0.0)


# ── _extract_detector ──────────────────────────────────────────────────────────


class TestExtractDetector:
    def test_detector_key(self):
        assert _extract_detector('{"detector": "HALLUCINATION_RISK"}') == "HALLUCINATION_RISK"

    def test_detector_type_key(self):
        assert _extract_detector('{"detector_type": "COST_SPIKE"}') == "COST_SPIKE"

    def test_invalid_json(self):
        assert _extract_detector("{not valid json}") is None

    def test_empty(self):
        assert _extract_detector("{}") is None


# ── get_call_outcomes ──────────────────────────────────────────────────────────


class TestGetCallOutcomes:
    def test_returns_call_views(self):
        o = _make_outcome(call_id="call-A", amount_usd=Decimal("30.00"))
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = [o]

        views = get_call_outcomes(db, project_id="proj-1", call_id="call-A")

        assert len(views) == 1
        assert views[0].amount_usd == pytest.approx(30.0)
        assert views[0].outcome_type == "refund_issued"

    def test_empty_call(self):
        db = _db_empty()
        views = get_call_outcomes(db, project_id="proj-1", call_id="call-unknown")
        assert views == []


# ── get_replay_prevented_savings ───────────────────────────────────────────────


class TestReplayPreventedSavings:
    def test_returns_scalar(self):
        db = MagicMock()
        db.execute.return_value.scalar.return_value = Decimal("290.00")

        savings = get_replay_prevented_savings(db, project_id="proj-1", run_id="run-1")
        assert savings == pytest.approx(290.0)

    def test_returns_zero_when_none(self):
        db = MagicMock()
        db.execute.return_value.scalar.return_value = None

        savings = get_replay_prevented_savings(db, project_id="proj-1", run_id="run-99")
        assert savings == pytest.approx(0.0)
