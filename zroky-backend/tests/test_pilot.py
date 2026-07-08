"""Tests for the Pilot-tier autopilot service + 4 endpoints (Module 4.3):

  - GET  /v1/pilot/actions               list with filters + pagination
  - POST /v1/pilot/actions/{id}/revert   tier-1 revert (409 on bad state)
  - GET  /v1/pilot/policy                seeds §6.3 default on first read
  - PUT  /v1/pilot/policy                validate + upsert

Service-level coverage: validation, action read/list filters,
revert state transitions, policy seed/upsert/defensive parser.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Anomaly, PilotAction, PilotPolicy
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.pilot import (
    DEFAULT_POLICY,
    REVERTIBLE_TIER,
    VALID_ACTION_STATUSES,
    VALID_TIERS,
    PilotActionRevertError,
    PolicyValidationError,
    get_or_create_policy,
    get_pilot_action,
    list_pilot_actions,
    parse_policy_json,
    revert_pilot_action,
    upsert_policy,
    validate_policy_payload,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_pilot_svc.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_pilot_route.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def override_get_db_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session

    with TestClient(app) as test_client:
        test_client._session_factory = session_factory  # type: ignore[attr-defined]
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


PROJECT_HEADER = "X-Project-Id"


# Module 6 added a router-level plan-gate on /v1/pilot/* that 402s when
# `pilot.autopilot_enabled` is false. These tests pre-date that gate
# and exercise the route surface itself — the gate is tested
# independently in tests/test_plan_gates.py. Bypass via monkeypatch.
@pytest.fixture(autouse=True)
def _grant_pilot_tier(monkeypatch):
    from app.services import entitlements_resolver
    from app.services.billing_plans import PLAN_ENTITLEMENTS

    pro_dict = dict(PLAN_ENTITLEMENTS["pro"])
    monkeypatch.setattr(
        entitlements_resolver, "has", lambda db, org_id, key: True
    )
    monkeypatch.setattr(
        entitlements_resolver,
        "get",
        lambda db, org_id, key, default=None: pro_dict.get(key, default),
    )
    monkeypatch.setattr(
        entitlements_resolver, "resolve_all", lambda db, org_id: dict(pro_dict)
    )
    monkeypatch.setattr(
        entitlements_resolver, "get_plan_code", lambda db, org_id: "pro"
    )


# ── helpers ──────────────────────────────────────────────────────────────────


def _seed_anomaly(session, *, project_id: str, anomaly_id: str = "anom-1") -> Anomaly:
    now = datetime.now(timezone.utc)
    a = Anomaly(
        id=anomaly_id,
        project_id=project_id,
        fingerprint=f"fp-{anomaly_id}",
        detector="SCHEMA_VIOLATION",
        severity="medium",
        status="open",
        first_seen_at=now,
        last_seen_at=now,
        occurrence_count=1,
    )
    session.add(a)
    session.commit()
    return a


def _seed_action(
    session,
    *,
    project_id: str,
    anomaly_id: str = "anom-1",
    tier: int = 1,
    action_type: str = "model_rollback",
    status_value: str = "applied",
    audit_user: str | None = None,
    created_at: datetime | None = None,
) -> PilotAction:
    action = PilotAction(
        project_id=project_id,
        anomaly_id=anomaly_id,
        tier=tier,
        action_type=action_type,
        status=status_value,
        audit_user=audit_user,
        applied_at=datetime.now(timezone.utc) if status_value == "applied" else None,
    )
    if created_at is not None:
        action.created_at = created_at
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


# ── service: policy validation ───────────────────────────────────────────────


class TestPolicyValidation:
    def test_default_policy_is_valid(self) -> None:
        # Round-trip: DEFAULT_POLICY → validate → should succeed and
        # return an equal dict (after type coercion).
        result = validate_policy_payload(dict(DEFAULT_POLICY))
        assert result["tier1_enabled"] is False
        assert result["tier1_min_confidence"] == pytest.approx(0.95)
        assert result["tier1_daily_cap"] == 5
        assert result["kill_switch"] is False

    def test_non_dict_payload_raises(self) -> None:
        with pytest.raises(PolicyValidationError, match="JSON object"):
            validate_policy_payload([1, 2, 3])  # type: ignore[arg-type]

    def test_missing_key_raises(self) -> None:
        payload = dict(DEFAULT_POLICY)
        del payload["kill_switch"]
        with pytest.raises(PolicyValidationError, match="missing required key"):
            validate_policy_payload(payload)

    def test_wrong_type_raises(self) -> None:
        payload = dict(DEFAULT_POLICY)
        payload["tier1_enabled"] = "yes"
        with pytest.raises(PolicyValidationError, match="boolean"):
            validate_policy_payload(payload)

    def test_bool_rejected_for_numeric_field(self) -> None:
        # bool is a subclass of int — explicit guard required
        payload = dict(DEFAULT_POLICY)
        payload["tier1_daily_cap"] = True
        with pytest.raises(PolicyValidationError, match="got bool"):
            validate_policy_payload(payload)

    def test_confidence_out_of_range_raises(self) -> None:
        payload = dict(DEFAULT_POLICY)
        payload["tier1_min_confidence"] = 1.5
        with pytest.raises(PolicyValidationError, match="\\[0, 1\\]"):
            validate_policy_payload(payload)

    def test_negative_daily_cap_raises(self) -> None:
        payload = dict(DEFAULT_POLICY)
        payload["tier1_daily_cap"] = -1
        with pytest.raises(PolicyValidationError, match="non-negative"):
            validate_policy_payload(payload)

    def test_empty_blast_radius_raises(self) -> None:
        payload = dict(DEFAULT_POLICY)
        payload["tier1_max_blast_radius"] = "   "
        with pytest.raises(PolicyValidationError, match="non-empty"):
            validate_policy_payload(payload)

    def test_empty_string_in_action_list_raises(self) -> None:
        payload = dict(DEFAULT_POLICY)
        payload["tier1_actions"] = ["model_rollback", ""]
        with pytest.raises(PolicyValidationError, match="non-empty strings"):
            validate_policy_payload(payload)

    def test_non_string_in_action_list_raises(self) -> None:
        payload = dict(DEFAULT_POLICY)
        payload["tier2_actions"] = ["ok", 42]
        with pytest.raises(PolicyValidationError, match="non-empty strings"):
            validate_policy_payload(payload)

    def test_extra_keys_dropped(self) -> None:
        payload = dict(DEFAULT_POLICY)
        payload["extra_key"] = "ignored"
        result = validate_policy_payload(payload)
        assert "extra_key" not in result

    def test_action_strings_stripped(self) -> None:
        payload = dict(DEFAULT_POLICY)
        payload["tier1_actions"] = ["  model_rollback  ", "fallback_swap"]
        result = validate_policy_payload(payload)
        assert result["tier1_actions"] == ["model_rollback", "fallback_swap"]


# ── service: defensive parser ────────────────────────────────────────────────


class TestParsePolicyJson:
    def test_none_returns_default(self) -> None:
        result = parse_policy_json(None)
        assert result["kill_switch"] is False
        assert result["tier1_enabled"] is False

    def test_malformed_returns_default(self) -> None:
        result = parse_policy_json("{not-json")
        assert result == parse_policy_json(None)

    def test_non_object_returns_default(self) -> None:
        result = parse_policy_json("[1,2,3]")
        assert result["tier1_actions"] == DEFAULT_POLICY["tier1_actions"]

    def test_partial_row_filled_with_defaults(self) -> None:
        partial = json.dumps({"kill_switch": True})
        result = parse_policy_json(partial)
        assert result["kill_switch"] is True
        # Every other key still populated from DEFAULT_POLICY
        assert result["tier1_min_confidence"] == DEFAULT_POLICY["tier1_min_confidence"]
        assert result["tier3_alert_channels"] == DEFAULT_POLICY["tier3_alert_channels"]

    def test_extra_keys_in_stored_row_dropped(self) -> None:
        stored = json.dumps({**DEFAULT_POLICY, "rogue_key": "x"})
        result = parse_policy_json(stored)
        assert "rogue_key" not in result


# ── service: action reads ────────────────────────────────────────────────────


class TestActionReads:
    def test_get_missing_returns_none(self, db_session) -> None:
        assert get_pilot_action(
            db_session, project_id="proj-1", action_id="missing"
        ) is None

    def test_get_cross_tenant_returns_none(self, db_session) -> None:
        _seed_anomaly(db_session, project_id="proj-A")
        action = _seed_action(db_session, project_id="proj-A")
        assert get_pilot_action(
            db_session, project_id="proj-B", action_id=action.id
        ) is None

    def test_list_tenant_isolation(self, db_session) -> None:
        _seed_anomaly(db_session, project_id="proj-A", anomaly_id="a")
        _seed_anomaly(db_session, project_id="proj-B", anomaly_id="b")
        _seed_action(db_session, project_id="proj-A", anomaly_id="a")
        _seed_action(db_session, project_id="proj-B", anomaly_id="b")

        rows = list_pilot_actions(db_session, project_id="proj-A", limit=10)
        assert len(rows) == 1
        assert rows[0].project_id == "proj-A"

    def test_filter_by_status(self, db_session) -> None:
        _seed_anomaly(db_session, project_id="proj-1")
        _seed_action(db_session, project_id="proj-1", status_value="applied")
        _seed_action(db_session, project_id="proj-1", status_value="pending")

        applied = list_pilot_actions(
            db_session, project_id="proj-1", status="applied"
        )
        pending = list_pilot_actions(
            db_session, project_id="proj-1", status="pending"
        )
        assert len(applied) == 1 and applied[0].status == "applied"
        assert len(pending) == 1 and pending[0].status == "pending"

    def test_filter_by_tier(self, db_session) -> None:
        _seed_anomaly(db_session, project_id="proj-1")
        _seed_action(db_session, project_id="proj-1", tier=1)
        _seed_action(db_session, project_id="proj-1", tier=2, action_type="prompt_revert_pr")
        _seed_action(db_session, project_id="proj-1", tier=3, action_type="alert")

        tier2 = list_pilot_actions(db_session, project_id="proj-1", tier=2)
        assert len(tier2) == 1 and tier2[0].tier == 2

    def test_filter_by_anomaly_id(self, db_session) -> None:
        _seed_anomaly(db_session, project_id="proj-1", anomaly_id="a")
        _seed_anomaly(db_session, project_id="proj-1", anomaly_id="b")
        _seed_action(db_session, project_id="proj-1", anomaly_id="a")
        _seed_action(db_session, project_id="proj-1", anomaly_id="b")

        only_a = list_pilot_actions(
            db_session, project_id="proj-1", anomaly_id="a"
        )
        assert len(only_a) == 1 and only_a[0].anomaly_id == "a"

    def test_invalid_status_raises(self, db_session) -> None:
        with pytest.raises(ValueError, match="status"):
            list_pilot_actions(
                db_session, project_id="proj-1", status="bogus"
            )

    def test_invalid_tier_raises(self, db_session) -> None:
        with pytest.raises(ValueError, match="tier"):
            list_pilot_actions(
                db_session, project_id="proj-1", tier=99
            )


# ── service: revert ──────────────────────────────────────────────────────────


class TestRevertAction:
    def test_revert_tier1_applied(self, db_session) -> None:
        _seed_anomaly(db_session, project_id="proj-1")
        action = _seed_action(
            db_session, project_id="proj-1", tier=1, status_value="applied"
        )
        result = revert_pilot_action(
            db_session,
            project_id="proj-1",
            action_id=action.id,
            audit_user="user@example.com",
        )
        assert result is not None
        assert result.status == "reverted"
        assert result.reverted_at is not None
        assert result.audit_user == "user@example.com"

    def test_revert_missing_returns_none(self, db_session) -> None:
        assert revert_pilot_action(
            db_session,
            project_id="proj-1",
            action_id="missing",
            audit_user=None,
        ) is None

    def test_revert_cross_tenant_returns_none(self, db_session) -> None:
        _seed_anomaly(db_session, project_id="proj-A")
        action = _seed_action(db_session, project_id="proj-A")
        result = revert_pilot_action(
            db_session,
            project_id="proj-B",
            action_id=action.id,
            audit_user=None,
        )
        assert result is None

    def test_revert_not_applied_raises(self, db_session) -> None:
        _seed_anomaly(db_session, project_id="proj-1")
        action = _seed_action(
            db_session, project_id="proj-1", status_value="pending"
        )
        with pytest.raises(PilotActionRevertError, match="applied"):
            revert_pilot_action(
                db_session,
                project_id="proj-1",
                action_id=action.id,
                audit_user=None,
            )

    def test_revert_already_reverted_raises(self, db_session) -> None:
        _seed_anomaly(db_session, project_id="proj-1")
        action = _seed_action(
            db_session, project_id="proj-1", status_value="reverted"
        )
        with pytest.raises(PilotActionRevertError, match="applied"):
            revert_pilot_action(
                db_session,
                project_id="proj-1",
                action_id=action.id,
                audit_user=None,
            )

    def test_revert_tier2_rejected(self, db_session) -> None:
        _seed_anomaly(db_session, project_id="proj-1")
        action = _seed_action(
            db_session,
            project_id="proj-1",
            tier=2,
            action_type="prompt_revert_pr",
            status_value="applied",
        )
        with pytest.raises(PilotActionRevertError, match="reversible"):
            revert_pilot_action(
                db_session,
                project_id="proj-1",
                action_id=action.id,
                audit_user=None,
            )

    def test_revert_tier3_rejected(self, db_session) -> None:
        _seed_anomaly(db_session, project_id="proj-1")
        action = _seed_action(
            db_session,
            project_id="proj-1",
            tier=3,
            action_type="alert",
            status_value="applied",
        )
        with pytest.raises(PilotActionRevertError, match="reversible"):
            revert_pilot_action(
                db_session,
                project_id="proj-1",
                action_id=action.id,
                audit_user=None,
            )


# ── service: policy CRUD ─────────────────────────────────────────────────────


class TestPolicyServices:
    def test_get_or_create_seeds_default(self, db_session) -> None:
        policy = get_or_create_policy(db_session, project_id="proj-1")
        assert policy.project_id == "proj-1"
        parsed = parse_policy_json(policy.policy_json)
        assert parsed == DEFAULT_POLICY

    def test_get_or_create_idempotent(self, db_session) -> None:
        first = get_or_create_policy(db_session, project_id="proj-1")
        second = get_or_create_policy(db_session, project_id="proj-1")
        assert first.id == second.id

    def test_get_or_create_tenant_isolation(self, db_session) -> None:
        a = get_or_create_policy(db_session, project_id="proj-A")
        b = get_or_create_policy(db_session, project_id="proj-B")
        assert a.id != b.id
        assert a.project_id == "proj-A"
        assert b.project_id == "proj-B"

    def test_upsert_creates_when_absent(self, db_session) -> None:
        payload = dict(DEFAULT_POLICY)
        payload["tier1_enabled"] = True
        payload["tier1_daily_cap"] = 10

        policy = upsert_policy(
            db_session,
            project_id="proj-1",
            payload=payload,
            updated_by="admin@example.com",
        )
        parsed = parse_policy_json(policy.policy_json)
        assert parsed["tier1_enabled"] is True
        assert parsed["tier1_daily_cap"] == 10
        assert policy.updated_by == "admin@example.com"

    def test_upsert_updates_in_place(self, db_session) -> None:
        first = get_or_create_policy(db_session, project_id="proj-1")
        original_id = first.id

        payload = dict(DEFAULT_POLICY)
        payload["kill_switch"] = True
        updated = upsert_policy(
            db_session,
            project_id="proj-1",
            payload=payload,
            updated_by="admin",
        )
        # Same row id — update in place
        assert updated.id == original_id
        parsed = parse_policy_json(updated.policy_json)
        assert parsed["kill_switch"] is True

    def test_upsert_merges_partial_patch_with_runtime_mandate(self, db_session) -> None:
        payload = dict(DEFAULT_POLICY)
        payload.update(
            {
                "runtime_enabled": True,
                "runtime_allowed_tools": ["refund_payment", "customer_record_update"],
                "runtime_sensitive_tools": ["refund_payment"],
                "runtime_amount_approval_threshold_usd": 250.0,
                "runtime_amount_deny_threshold_usd": 2500.0,
                "runtime_approval_ttl_minutes": 15,
            }
        )
        created = upsert_policy(
            db_session,
            project_id="proj-runtime",
            payload=payload,
            updated_by="agent-setup",
        )
        original_id = created.id

        updated = upsert_policy(
            db_session,
            project_id="proj-runtime",
            payload={"tier1_enabled": True, "tier1_daily_cap": 11},
            updated_by="policies-page",
        )

        assert updated.id == original_id
        parsed = parse_policy_json(updated.policy_json)
        assert parsed["tier1_enabled"] is True
        assert parsed["tier1_daily_cap"] == 11
        assert parsed["runtime_allowed_tools"] == [
            "refund_payment",
            "customer_record_update",
        ]
        assert parsed["runtime_sensitive_tools"] == ["refund_payment"]
        assert parsed["runtime_amount_approval_threshold_usd"] == pytest.approx(250.0)
        assert parsed["runtime_amount_deny_threshold_usd"] == pytest.approx(2500.0)
        assert parsed["runtime_approval_ttl_minutes"] == 15

    def test_upsert_rejects_invalid_payload(self, db_session) -> None:
        bad = dict(DEFAULT_POLICY)
        bad["tier1_min_confidence"] = 2.0
        with pytest.raises(PolicyValidationError):
            upsert_policy(
                db_session,
                project_id="proj-1",
                payload=bad,
                updated_by=None,
            )


# ── route: GET /v1/pilot/actions ─────────────────────────────────────────────


class TestListActionsRoute:
    def test_empty(self, client: TestClient) -> None:
        response = client.get(
            "/v1/pilot/actions", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["next_cursor"] is None
        assert body["total_in_page"] == 0

    def test_list_basic(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_anomaly(session, project_id="proj-1")
            _seed_action(session, project_id="proj-1", action_type="model_rollback")
            _seed_action(session, project_id="proj-1", action_type="fallback_swap")

        response = client.get(
            "/v1/pilot/actions", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 2

    def test_filter_by_status(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_anomaly(session, project_id="proj-1")
            _seed_action(session, project_id="proj-1", status_value="applied")
            _seed_action(session, project_id="proj-1", status_value="pending")

        response = client.get(
            "/v1/pilot/actions?status=applied",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "applied"

    def test_filter_by_tier(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_anomaly(session, project_id="proj-1")
            _seed_action(session, project_id="proj-1", tier=1)
            _seed_action(
                session, project_id="proj-1", tier=2, action_type="prompt_revert_pr"
            )

        response = client.get(
            "/v1/pilot/actions?tier=2",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["tier"] == 2

    def test_filter_by_anomaly_id(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_anomaly(session, project_id="proj-1", anomaly_id="a")
            _seed_anomaly(session, project_id="proj-1", anomaly_id="b")
            _seed_action(session, project_id="proj-1", anomaly_id="a")
            _seed_action(session, project_id="proj-1", anomaly_id="b")

        response = client.get(
            "/v1/pilot/actions?anomaly_id=a",
            headers={PROJECT_HEADER: "proj-1"},
        )
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["anomaly_id"] == "a"

    def test_invalid_status_422(self, client: TestClient) -> None:
        response = client.get(
            "/v1/pilot/actions?status=bogus",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_invalid_tier_422(self, client: TestClient) -> None:
        response = client.get(
            "/v1/pilot/actions?tier=99",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_invalid_cursor_422(self, client: TestClient) -> None:
        response = client.get(
            "/v1/pilot/actions?cursor=not-base64",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_pagination(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_anomaly(session, project_id="proj-page")
            base = datetime.now(timezone.utc)
            for n in range(5):
                _seed_action(
                    session,
                    project_id="proj-page",
                    created_at=base - timedelta(seconds=10 * (5 - n)),
                )

        first = client.get(
            "/v1/pilot/actions?limit=2",
            headers={PROJECT_HEADER: "proj-page"},
        ).json()
        assert len(first["items"]) == 2
        assert first["next_cursor"] is not None

        second = client.get(
            f"/v1/pilot/actions?limit=2&cursor={first['next_cursor']}",
            headers={PROJECT_HEADER: "proj-page"},
        ).json()
        assert len(second["items"]) == 2

        third = client.get(
            f"/v1/pilot/actions?limit=2&cursor={second['next_cursor']}",
            headers={PROJECT_HEADER: "proj-page"},
        ).json()
        assert len(third["items"]) == 1
        assert third["next_cursor"] is None

        seen = (
            [i["id"] for i in first["items"]]
            + [i["id"] for i in second["items"]]
            + [i["id"] for i in third["items"]]
        )
        assert len(set(seen)) == 5

    def test_tenant_isolation(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_anomaly(session, project_id="proj-A", anomaly_id="a")
            _seed_anomaly(session, project_id="proj-B", anomaly_id="b")
            _seed_action(session, project_id="proj-A", anomaly_id="a")
            _seed_action(session, project_id="proj-B", anomaly_id="b")

        response = client.get(
            "/v1/pilot/actions",
            headers={PROJECT_HEADER: "proj-A"},
        )
        items = response.json()["items"]
        assert {i["project_id"] for i in items} == {"proj-A"}


# ── route: POST /v1/pilot/actions/{id}/revert ────────────────────────────────


class TestRevertActionRoute:
    def test_revert_200(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_anomaly(session, project_id="proj-1")
            action = _seed_action(
                session, project_id="proj-1", tier=1, status_value="applied"
            )
            action_id = action.id

        response = client.post(
            f"/v1/pilot/actions/{action_id}/revert",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "reverted"
        assert body["reverted_at"] is not None

    def test_revert_missing_404(self, client: TestClient) -> None:
        response = client.post(
            "/v1/pilot/actions/missing/revert",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 404

    def test_revert_cross_tenant_404(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_anomaly(session, project_id="proj-A")
            action = _seed_action(session, project_id="proj-A")
            action_id = action.id

        response = client.post(
            f"/v1/pilot/actions/{action_id}/revert",
            headers={PROJECT_HEADER: "proj-B"},
        )
        assert response.status_code == 404

    def test_revert_pending_409(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_anomaly(session, project_id="proj-1")
            action = _seed_action(
                session, project_id="proj-1", status_value="pending"
            )
            action_id = action.id

        response = client.post(
            f"/v1/pilot/actions/{action_id}/revert",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 409

    def test_revert_tier2_409(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_anomaly(session, project_id="proj-1")
            action = _seed_action(
                session,
                project_id="proj-1",
                tier=2,
                action_type="prompt_revert_pr",
                status_value="applied",
            )
            action_id = action.id

        response = client.post(
            f"/v1/pilot/actions/{action_id}/revert",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 409


# ── route: GET /v1/pilot/policy ──────────────────────────────────────────────


class TestGetPolicyRoute:
    def test_first_read_seeds_default(self, client: TestClient) -> None:
        response = client.get(
            "/v1/pilot/policy", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["project_id"] == "proj-1"
        assert body["policy"]["kill_switch"] is False
        assert body["policy"]["tier1_min_confidence"] == pytest.approx(0.95)
        assert body["policy"]["tier1_actions"] == DEFAULT_POLICY["tier1_actions"]

    def test_idempotent(self, client: TestClient) -> None:
        first = client.get(
            "/v1/pilot/policy", headers={PROJECT_HEADER: "proj-1"}
        ).json()
        second = client.get(
            "/v1/pilot/policy", headers={PROJECT_HEADER: "proj-1"}
        ).json()
        assert first["id"] == second["id"]

    def test_tenant_isolation(self, client: TestClient) -> None:
        a = client.get(
            "/v1/pilot/policy", headers={PROJECT_HEADER: "proj-A"}
        ).json()
        b = client.get(
            "/v1/pilot/policy", headers={PROJECT_HEADER: "proj-B"}
        ).json()
        assert a["id"] != b["id"]
        assert a["project_id"] == "proj-A"
        assert b["project_id"] == "proj-B"


# ── route: PUT /v1/pilot/policy ──────────────────────────────────────────────


class TestPutPolicyRoute:
    def test_put_creates_when_absent(self, client: TestClient) -> None:
        payload = dict(DEFAULT_POLICY)
        payload["tier1_enabled"] = True
        payload["kill_switch"] = True

        response = client.put(
            "/v1/pilot/policy",
            headers={PROJECT_HEADER: "proj-1"},
            json=payload,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["policy"]["tier1_enabled"] is True
        assert body["policy"]["kill_switch"] is True

    def test_put_updates_existing(self, client: TestClient) -> None:
        # Seed
        client.get("/v1/pilot/policy", headers={PROJECT_HEADER: "proj-1"})

        payload = dict(DEFAULT_POLICY)
        payload["tier1_daily_cap"] = 99
        response = client.put(
            "/v1/pilot/policy",
            headers={PROJECT_HEADER: "proj-1"},
            json=payload,
        )
        assert response.status_code == 200
        assert response.json()["policy"]["tier1_daily_cap"] == 99

    def test_put_accepts_matching_update_precondition(self, client: TestClient) -> None:
        seeded = client.get(
            "/v1/pilot/policy", headers={PROJECT_HEADER: "proj-1"}
        ).json()

        payload = dict(DEFAULT_POLICY)
        payload["tier1_daily_cap"] = 42
        payload["expected_updated_at"] = seeded["updated_at"]
        response = client.put(
            "/v1/pilot/policy",
            headers={PROJECT_HEADER: "proj-1"},
            json=payload,
        )

        assert response.status_code == 200
        assert response.json()["policy"]["tier1_daily_cap"] == 42

    def test_put_rejects_stale_update_precondition(self, client: TestClient) -> None:
        client.get("/v1/pilot/policy", headers={PROJECT_HEADER: "proj-1"})

        payload = dict(DEFAULT_POLICY)
        payload["tier1_daily_cap"] = 42
        payload["expected_updated_at"] = "2000-01-01T00:00:00Z"
        response = client.put(
            "/v1/pilot/policy",
            headers={PROJECT_HEADER: "proj-1"},
            json=payload,
        )

        assert response.status_code == 409
        assert "Refresh before saving" in response.json()["detail"]

    def test_put_partial_patch_preserves_runtime_mandate(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            payload = dict(DEFAULT_POLICY)
            payload.update(
                {
                    "runtime_allowed_tools": ["refund_payment"],
                    "runtime_sensitive_tools": ["refund_payment"],
                    "runtime_amount_approval_threshold_usd": 300.0,
                    "runtime_amount_deny_threshold_usd": 3000.0,
                    "runtime_approval_ttl_minutes": 20,
                }
            )
            upsert_policy(
                session,
                project_id="proj-runtime",
                payload=payload,
                updated_by="agent-setup",
            )

        response = client.put(
            "/v1/pilot/policy",
            headers={PROJECT_HEADER: "proj-runtime"},
            json={"tier2_enabled": True, "tier2_daily_cap": 4},
        )

        assert response.status_code == 200
        policy = response.json()["policy"]
        assert policy["tier2_enabled"] is True
        assert policy["tier2_daily_cap"] == 4
        assert policy["runtime_allowed_tools"] == ["refund_payment"]
        assert policy["runtime_sensitive_tools"] == ["refund_payment"]
        assert policy["runtime_amount_approval_threshold_usd"] == pytest.approx(300.0)
        assert policy["runtime_amount_deny_threshold_usd"] == pytest.approx(3000.0)
        assert policy["runtime_approval_ttl_minutes"] == 20

    def test_put_invalid_confidence_422(self, client: TestClient) -> None:
        payload = dict(DEFAULT_POLICY)
        payload["tier1_min_confidence"] = 1.5  # > 1.0
        response = client.put(
            "/v1/pilot/policy",
            headers={PROJECT_HEADER: "proj-1"},
            json=payload,
        )
        assert response.status_code == 422

    def test_put_negative_cap_422(self, client: TestClient) -> None:
        payload = dict(DEFAULT_POLICY)
        payload["tier1_daily_cap"] = -1
        response = client.put(
            "/v1/pilot/policy",
            headers={PROJECT_HEADER: "proj-1"},
            json=payload,
        )
        assert response.status_code == 422

    def test_put_empty_blast_radius_422(self, client: TestClient) -> None:
        payload = dict(DEFAULT_POLICY)
        payload["tier1_max_blast_radius"] = ""
        response = client.put(
            "/v1/pilot/policy",
            headers={PROJECT_HEADER: "proj-1"},
            json=payload,
        )
        assert response.status_code == 422

    def test_put_tenant_isolation(self, client: TestClient) -> None:
        a_payload = dict(DEFAULT_POLICY)
        a_payload["tier1_daily_cap"] = 7
        client.put(
            "/v1/pilot/policy",
            headers={PROJECT_HEADER: "proj-A"},
            json=a_payload,
        )
        # proj-B sees its own seeded default (cap=5), not proj-A's cap=7
        b_response = client.get(
            "/v1/pilot/policy", headers={PROJECT_HEADER: "proj-B"}
        ).json()
        assert b_response["policy"]["tier1_daily_cap"] == 5


# ── invariants ───────────────────────────────────────────────────────────────


class TestInvariants:
    def test_valid_action_statuses_match_db_check(self) -> None:
        assert VALID_ACTION_STATUSES == frozenset(
            {"pending", "applied", "reverted", "failed", "skipped"}
        )

    def test_valid_tiers_match_db_check(self) -> None:
        assert VALID_TIERS == frozenset({1, 2, 3})

    def test_revertible_tier_is_one(self) -> None:
        assert REVERTIBLE_TIER == 1

    def test_default_policy_passes_own_validator(self) -> None:
        # DEFAULT_POLICY must always be a valid payload under
        # validate_policy_payload — protects against accidental drift.
        result = validate_policy_payload(dict(DEFAULT_POLICY))
        for key in DEFAULT_POLICY:
            assert key in result
