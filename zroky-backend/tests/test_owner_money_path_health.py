from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    Anomaly,
    BillingEvent,
    Call,
    EventCount,
    GatewayCaptureHealth,
    GoldenSet,
    GoldenTrace,
    Issue,
    OutcomeReconciliationCheck,
    Project,
    ProjectAlert,
    ProviderKeyVault,
    ReplayJob,
    ReplayRun,
    RuntimePolicyDecision,
    Subscription,
    SupportTicket,
)
from app.db.session import get_db_session
from app.main import app


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "owner_money_path.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_db
    try:
        yield TestClient(app), session_factory
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        engine.dispose()


def _set_owner_auth(
    monkeypatch: pytest.MonkeyPatch, token: str = "owner-token"
) -> dict[str, str]:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "false")
    monkeypatch.setenv("PROVISIONING_TOKEN", token)
    get_settings.cache_clear()
    return {"x-zroky-admin-token": token}


def _call(
    project_id: str,
    call_id: str,
    *,
    created_at: datetime,
    agent_name: str = "agent",
    pricing_version: str | None = "test-pricing-v1",
    pricing_source: str | None = "test_contract",
    pricing_last_updated_at: datetime | None = None,
    cost_confidence: str = "high",
) -> Call:
    return Call(
        id=call_id,
        project_id=project_id,
        event_id=f"{call_id}:event",
        created_at=created_at,
        agent_name=agent_name,
        provider="openai",
        model="gpt-4.1-mini",
        status="completed",
        pricing_version=pricing_version,
        pricing_source=pricing_source,
        pricing_last_updated_at=pricing_last_updated_at
        if pricing_last_updated_at is not None
        else created_at,
        cost_confidence=cost_confidence,
        payload_json="{}",
        metadata_json=json.dumps({"source": "test"}),
    )


def test_owner_money_path_health_aggregates_real_backend_state(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    now = datetime.now(UTC)

    with session_factory() as db:
        db.add_all(
            [
                Project(
                    id="proj_good", name="Good Tenant", owner_ref="good", is_active=True
                ),
                Project(
                    id="proj_gap", name="Gap Tenant", owner_ref="gap", is_active=True
                ),
                Subscription(
                    id="sub_good",
                    org_id="proj_good",
                    plan_code="pro",
                    status="active",
                    current_period_end=now + timedelta(days=30),
                ),
                Subscription(
                    id="sub_gap",
                    org_id="proj_gap",
                    plan_code="starter",
                    status="past_due",
                    current_period_end=now + timedelta(days=30),
                ),
                EventCount(
                    id="ec_good",
                    tenant_id="proj_good",
                    month=now.strftime("%Y-%m"),
                    event_count=10,
                    last_event_at=now,
                ),
                EventCount(
                    id="ec_gap",
                    tenant_id="proj_gap",
                    month=now.strftime("%Y-%m"),
                    event_count=50_000,
                    last_event_at=now,
                ),
                ProjectAlert(
                    id="alert_meter_gap",
                    tenant_id="proj_gap",
                    diagnosis_id="billing-metering",
                    category="BILLING_METERING_FAILURE",
                    severity="high",
                    status="OPEN",
                    source="billing_metering",
                    title="Billing metering failed; quota or usage evidence is degraded.",
                    evidence_json=json.dumps(
                        {
                            "failure_type": "event_counter_increment_failed",
                            "failure_count": 3,
                            "last_failure_at": now.isoformat(),
                        },
                        separators=(",", ":"),
                    ),
                ),
                BillingEvent(
                    id="be_good",
                    provider="razorpay",
                    provider_event_id="razorpay_verify:pay_good",
                    event_type="payment.succeeded",
                    provider_created_at=now,
                    processed_at=now,
                    result="applied",
                    affected_org_id="proj_good",
                    payload_json="{}",
                ),
                _call("proj_good", "call_good", created_at=now - timedelta(hours=1)),
                _call(
                    "proj_gap",
                    "call_old",
                    created_at=now - timedelta(days=3),
                    pricing_version=None,
                    pricing_source="fallback_default",
                    pricing_last_updated_at=None,
                    cost_confidence="stale",
                ),
                Issue(
                    id="issue_good",
                    project_id="proj_good",
                    failure_code="SCHEMA_VIOLATION",
                    prompt_fingerprint="fp_good",
                    agent_name="agent",
                    status="open",
                    severity="high",
                    occurrence_count=3,
                    first_seen_at=now - timedelta(hours=2),
                    last_seen_at=now - timedelta(hours=1),
                    sample_call_id="call_good",
                ),
                Anomaly(
                    id="anom_gap",
                    project_id="proj_gap",
                    fingerprint="fp-gap",
                    detector="SCHEMA_VIOLATION",
                    severity="medium",
                    status="open",
                    first_seen_at=now - timedelta(days=3),
                    last_seen_at=now - timedelta(days=3),
                    occurrence_count=2,
                ),
                ProviderKeyVault(
                    id="pk_good",
                    project_id="proj_good",
                    provider="openai",
                    ciphertext=b"encrypted",
                    key_fingerprint="fp_provider_good",
                    key_last4="1234",
                    is_active=True,
                ),
                GoldenSet(
                    id="gs_good",
                    project_id="proj_good",
                    name="Good Golden",
                    created_at=now,
                    updated_at=now,
                ),
                GoldenTrace(
                    id="gt_good",
                    golden_set_id="gs_good",
                    project_id="proj_good",
                    call_id="call_good",
                    status="active",
                    expected_output_text="ok",
                    created_at=now,
                    updated_at=now,
                ),
                ReplayRun(
                    id="rr_verified",
                    project_id="proj_good",
                    golden_set_id="gs_good",
                    trigger="manual",
                    status="pass",
                    summary_json=json.dumps(
                        {
                            "verified_fix": True,
                            "verification_status": "verified_fix",
                        },
                        separators=(",", ":"),
                    ),
                    created_at=now - timedelta(hours=1),
                ),
                ReplayRun(
                    id="rr_ci_fail",
                    project_id="proj_good",
                    golden_set_id="gs_good",
                    trigger="github",
                    git_sha="abc123",
                    status="fail",
                    summary_json=json.dumps({"verdict": "fail"}, separators=(",", ":")),
                    created_at=now - timedelta(hours=1),
                ),
                ReplayJob(
                    id="job_good",
                    tenant_id="proj_good",
                    call_id="call_good",
                    status="completed",
                    created_at=now - timedelta(hours=1),
                ),
                ReplayJob(
                    id="job_gap_stale",
                    tenant_id="proj_gap",
                    call_id="call_old",
                    status="running",
                    claimed_by="worker-old",
                    claimed_at=now - timedelta(hours=3),
                    lease_expires_at=now - timedelta(hours=2),
                    created_at=now - timedelta(hours=3),
                ),
                SupportTicket(
                    id="ticket_gap",
                    tenant_id="proj_gap",
                    title="Replay is blocked",
                    category="replay",
                    priority="urgent",
                    status="open",
                    created_at=now - timedelta(minutes=30),
                    updated_at=now - timedelta(minutes=30),
                ),
            ]
        )
        db.commit()

    response = test_client.get("/v1/owner/money-path-health", headers=owner_headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["platform"]["captures_24h"] == 1
    assert payload["platform"]["issues_open"] == 2
    assert payload["platform"]["replay_runs_7d"] == 2
    assert payload["platform"]["verified_replay_runs_7d"] == 1
    assert payload["platform"]["golden_traces_active"] == 1
    assert payload["platform"]["ci_runs_7d"] == 1
    assert payload["platform"]["ci_blocks_7d"] == 1
    assert payload["platform"]["tenants_missing_provider_key"] == 1
    assert payload["platform"]["tenants_without_recent_capture"] == 1
    assert payload["platform"]["tenants_without_goldens"] == 1
    assert payload["platform"]["tenants_with_failed_ci"] == 1
    assert payload["platform"]["tenants_with_stale_replay_workers"] == 1
    assert payload["platform"]["tenants_with_stale_pricing"] == 1
    assert payload["platform"]["tenants_with_billing_risk"] == 1
    assert payload["platform"]["metering_failure_tenants"] == 1
    assert payload["platform"]["event_counter_failure_count"] == 3
    assert payload["platform"]["billing_provider_verification"]["state"] == "verified"
    assert "event_metering_failure" in payload["platform"]["billing_launch_blockers"]
    assert payload["platform"]["support_tickets_open"] == 1
    assert payload["platform"]["support_tickets_urgent"] == 1
    assert payload["platform"]["blocked_regressions_7d"] == 1
    assert payload["platform"]["verified_fixes_7d"] == 1
    assert payload["platform"]["last_deployed_smoke"]["status"] == "not_configured"

    tenants = {row["project_id"]: row for row in payload["tenants"]}
    assert set(tenants) == {"proj_good", "proj_gap"}

    good = tenants["proj_good"]
    assert good["plan_code"] == "pro"
    assert good["captures_24h"] == 1
    assert good["open_issue_count"] == 1
    assert good["replay_run_count_7d"] == 2
    assert good["verified_replay_count_7d"] == 1
    assert good["golden_trace_count"] == 1
    assert good["ci_run_count_7d"] == 1
    assert good["blocking_ci_failures_7d"] == 1
    assert good["provider_key_status"] == {
        "state": "configured",
        "active_provider_count": 1,
    }
    assert good["replay_quota_status"]["state"] == "ok"
    assert good["replay_quota_status"]["used"] == 3
    assert good["event_metering_status"]["state"] == "ok"
    assert good["event_metering_status"]["used"] == 10
    assert good["pricing_cost_status"]["state"] == "ok"
    assert good["billing_status"]["state"] == "ok"
    assert good["support_status"]["state"] == "none"
    assert good["blocked_regressions_7d"] == 1
    assert good["verified_fixes_7d"] == 1
    assert good["value_status"] == "blocked"
    assert "failed_ci" in good["money_path_breaks"]
    assert good["tenant_priority_score"] > 0
    assert good["next_owner_action"] == "review_blocked_ci"

    gap = tenants["proj_gap"]
    assert gap["plan_code"] == "starter"
    assert gap["captures_24h"] == 0
    assert gap["open_issue_count"] == 1
    assert gap["provider_key_status"]["state"] == "missing"
    assert gap["replay_jobs_stale"] == 1
    assert gap["event_metering_status"]["state"] == "failure"
    assert gap["event_metering_status"]["failure_count"] == 3
    assert gap["pricing_cost_status"]["state"] in {"missing", "fallback", "stale"}
    assert gap["billing_status"]["state"] == "risk"
    assert gap["support_status"]["state"] == "urgent"
    assert gap["value_status"] == "blocked"
    assert "replay_worker_stale" in gap["money_path_breaks"]
    assert "event_metering_failure" in gap["money_path_breaks"]
    assert "billing_risk" in gap["money_path_breaks"]
    assert gap["next_owner_action"] == "restore_capture"


def test_owner_money_path_health_reports_deployment_smoke_evidence(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    now = datetime.now(UTC)

    with session_factory() as db:
        db.add(
            Project(
                id="proj_smoke", name="Smoke Tenant", owner_ref="smoke", is_active=True
            )
        )
        db.add(
            _call(
                "proj_smoke",
                "call_smoke",
                created_at=now - timedelta(minutes=5),
                agent_name="deployment-smoke-agent",
            )
        )
        db.add(
            GoldenSet(
                id="gs_smoke",
                project_id="proj_smoke",
                name="Deployment smoke",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            GoldenTrace(
                id="gt_smoke",
                golden_set_id="gs_smoke",
                project_id="proj_smoke",
                call_id="call_smoke",
                status="active",
                source_evidence_json=json.dumps({"source": "deployment-smoke"}),
                expected_output_text='{"status":"smoke-ok"}',
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            ReplayRun(
                id="rr_smoke_ci",
                project_id="proj_smoke",
                golden_set_id="gs_smoke",
                trigger="github",
                git_sha="deploy-smoke-regression",
                status="pass",
                created_at=now,
                summary_json=json.dumps({"verdict": "pass"}, separators=(",", ":")),
            )
        )
        db.commit()

    response = test_client.get("/v1/owner/money-path-health", headers=owner_headers)
    assert response.status_code == 200
    smoke = response.json()["platform"]["last_deployed_smoke"]
    assert smoke["status"] == "passed"
    assert smoke["project_id"] == "proj_smoke"
    assert smoke["call_id"] == "call_smoke"
    assert smoke["golden_trace_id"] == "gt_smoke"
    assert smoke["ci_run_id"] == "rr_smoke_ci"


def test_owner_launch_readiness_allows_paid_launch_only_when_every_gate_has_proof(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    now = datetime.now(UTC)

    with session_factory() as db:
        db.add(
            Project(
                id="proj_launch",
                name="Launch Tenant",
                owner_ref="launch",
                is_active=True,
            )
        )
        db.add(
            Subscription(
                id="sub_launch",
                org_id="proj_launch",
                plan_code="pro",
                status="active",
                current_period_end=now + timedelta(days=30),
            )
        )
        db.add(
            EventCount(
                id="ec_launch",
                tenant_id="proj_launch",
                month=now.strftime("%Y-%m"),
                event_count=25,
                last_event_at=now,
            )
        )
        db.add(
            BillingEvent(
                id="be_launch",
                provider="razorpay",
                provider_event_id="razorpay_verify:pay_launch",
                event_type="payment.succeeded",
                provider_created_at=now,
                processed_at=now,
                result="applied",
                affected_org_id="proj_launch",
                payload_json="{}",
            )
        )
        db.add(
            _call(
                "proj_launch",
                "call_launch",
                created_at=now - timedelta(minutes=20),
                agent_name="deployment-smoke-agent",
            )
        )
        db.add(
            Issue(
                id="issue_launch",
                project_id="proj_launch",
                failure_code="TOOL_ARGUMENT_MISMATCH",
                prompt_fingerprint="fp_launch",
                agent_name="refund-agent",
                status="open",
                severity="high",
                occurrence_count=12,
                first_seen_at=now - timedelta(hours=2),
                last_seen_at=now - timedelta(minutes=30),
                sample_call_id="call_launch",
            )
        )
        db.add(
            ProviderKeyVault(
                id="pk_launch",
                project_id="proj_launch",
                provider="openai",
                ciphertext=b"encrypted",
                key_fingerprint="fp_launch_provider",
                key_last4="9999",
                is_active=True,
            )
        )
        db.add(
            GoldenSet(
                id="gs_launch",
                project_id="proj_launch",
                name="Launch Golden",
                blocks_ci=True,
                is_flaky=False,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            GoldenTrace(
                id="gt_launch",
                golden_set_id="gs_launch",
                project_id="proj_launch",
                call_id="call_launch",
                status="active",
                expected_output_text="policy checked before refund",
                criteria_json=json.dumps(
                    {
                        "golden_contract_v1": {
                            "final_output_assertion": {"contains": "policy checked"},
                            "tool_sequence": ["lookup_policy", "refund_customer"],
                            "tool_args": {
                                "refund_customer": {
                                    "requires": ["customer_id", "amount"]
                                }
                            },
                            "policy_checks": ["refund_policy_approved"],
                            "rag_grounding": {"required": True},
                            "business_outcome": {"status": "success"},
                        }
                    },
                    separators=(",", ":"),
                ),
                source_evidence_json=json.dumps({"source": "deployment-smoke"}),
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            ReplayRun(
                id="rr_launch_ci",
                project_id="proj_launch",
                golden_set_id="gs_launch",
                trigger="github",
                git_sha="deploy-smoke-launch",
                status="pass",
                summary_json=json.dumps(
                    {
                        "verified_fix": True,
                        "verification_status": "verified_fix",
                        "requested_replay_mode": "real_llm",
                        "replay_mode": "real_llm",
                    },
                    separators=(",", ":"),
                ),
                created_at=now - timedelta(minutes=10),
            )
        )
        db.add(
            RuntimePolicyDecision(
                id="rpd_launch",
                project_id="proj_launch",
                trace_id="trace_launch",
                call_id="call_launch",
                agent_name="refund-agent",
                action_type="refund",
                tool_name="refund_customer",
                decision="block",
                status="blocked",
                reasons_json=json.dumps(["refund requires approval"]),
                created_at=now - timedelta(minutes=5),
            )
        )
        db.add(
            OutcomeReconciliationCheck(
                id="orc_launch",
                project_id="proj_launch",
                call_id="call_launch",
                trace_id="trace_launch",
                runtime_policy_decision_id="rpd_launch",
                action_type="refund",
                connector_type="ledger_api",
                system_ref="ledger:rf_launch",
                verdict="matched",
                reason="all_compared_fields_matched",
                amount_usd=42.5,
                currency="USD",
                claimed_json=json.dumps(
                    {"refund_id": "rf_launch", "amount_usd": 42.5, "currency": "USD"},
                    separators=(",", ":"),
                ),
                actual_json=json.dumps(
                    {
                        "refund_id": "rf_launch",
                        "amount_usd": "42.50",
                        "currency": "usd",
                    },
                    separators=(",", ":"),
                ),
                comparison_json=json.dumps(
                    {
                        "verdict": "matched",
                        "compared_fields": [
                            {
                                "field": "amount_usd",
                                "claimed": 42.5,
                                "actual": "42.50",
                                "matched": True,
                            }
                        ],
                    },
                    separators=(",", ":"),
                ),
                checked_at=now - timedelta(minutes=4),
            )
        )
        db.commit()

    response = test_client.get("/v1/owner/launch-readiness", headers=owner_headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["product_standard"] == (
        "Did Zroky prevent an important AI agent failure from silently repeating?"
    )
    assert payload["paid_launch_allowed"] is True
    assert payload["overall_status"] == "pass"
    assert payload["hard_blockers"] == []
    gates = {gate["code"]: gate for gate in payload["gates"]}
    assert set(gates) == {
        "durable_capture",
        "tenant_isolation",
        "failure_intelligence",
        "honest_replay_proof",
        "behavioral_goldens",
        "durable_ci_gate",
        "runtime_risk_stop",
        "outcome_verification",
        "billing_quota",
        "owner_value_proof",
        "single_source_of_truth",
    }
    assert all(gate["status"] == "pass" for gate in gates.values())
    assert gates["behavioral_goldens"]["evidence"][2]["value"] == 1
    assert gates["runtime_risk_stop"]["evidence"][0]["value"] == 1
    assert gates["outcome_verification"]["evidence"][1]["value"] == 1
    assert any(
        "verify_paid_launch_readiness.ps1" in command
        for command in payload["verification_commands"]
    )


def test_owner_launch_readiness_blocks_on_fake_stub_replay_and_text_only_golden(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    now = datetime.now(UTC)

    with session_factory() as db:
        db.add(
            Project(id="proj_bad", name="Bad Tenant", owner_ref="bad", is_active=True)
        )
        db.add(_call("proj_bad", "call_bad", created_at=now - timedelta(minutes=10)))
        db.add(
            Issue(
                id="issue_bad",
                project_id="proj_bad",
                failure_code="SCHEMA_VIOLATION",
                prompt_fingerprint="fp_bad",
                agent_name="agent",
                status="open",
                severity="high",
                occurrence_count=4,
                first_seen_at=now - timedelta(hours=1),
                last_seen_at=now - timedelta(minutes=10),
                sample_call_id="call_bad",
            )
        )
        db.add(
            GoldenSet(
                id="gs_bad",
                project_id="proj_bad",
                name="Text Golden",
                blocks_ci=True,
                is_flaky=False,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            GoldenTrace(
                id="gt_bad",
                golden_set_id="gs_bad",
                project_id="proj_bad",
                call_id="call_bad",
                status="active",
                expected_output_text="ok",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            ReplayRun(
                id="rr_bad_stub",
                project_id="proj_bad",
                golden_set_id="gs_bad",
                trigger="github",
                git_sha="stub-bad",
                status="pass",
                summary_json=json.dumps(
                    {
                        "verified_fix": True,
                        "verification_status": "verified_fix",
                        "requested_replay_mode": "stub",
                        "replay_mode": "stub",
                    },
                    separators=(",", ":"),
                ),
                created_at=now,
            )
        )
        db.add_all(
            [
                OutcomeReconciliationCheck(
                    id="orc_bad_mismatch",
                    project_id="proj_bad",
                    call_id="call_bad",
                    trace_id="trace_bad",
                    action_type="refund",
                    connector_type="ledger_api",
                    system_ref="ledger:rf_bad",
                    verdict="mismatched",
                    reason="field_mismatch",
                    amount_usd=99,
                    currency="USD",
                    claimed_json=json.dumps(
                        {"refund_id": "rf_bad", "amount_usd": 99}, separators=(",", ":")
                    ),
                    actual_json=json.dumps(
                        {"refund_id": "rf_bad", "amount_usd": 12}, separators=(",", ":")
                    ),
                    comparison_json=json.dumps(
                        {
                            "mismatches": [
                                {"field": "amount_usd", "claimed": 99, "actual": 12}
                            ]
                        },
                        separators=(",", ":"),
                    ),
                    checked_at=now,
                ),
                OutcomeReconciliationCheck(
                    id="orc_bad_missing_record",
                    project_id="proj_bad",
                    call_id="call_bad",
                    trace_id="trace_bad",
                    action_type="payment",
                    connector_type="ledger_api",
                    system_ref="ledger:pay_missing",
                    verdict="not_verified",
                    reason="system_of_record_missing",
                    amount_usd=40,
                    currency="USD",
                    claimed_json=json.dumps(
                        {"payment_id": "pay_missing", "amount_usd": 40},
                        separators=(",", ":"),
                    ),
                    actual_json=None,
                    comparison_json=json.dumps(
                        {"reason": "system_of_record_missing"}, separators=(",", ":")
                    ),
                    checked_at=now,
                ),
            ]
        )
        db.commit()

    response = test_client.get("/v1/owner/launch-readiness", headers=owner_headers)
    assert response.status_code == 200
    payload = response.json()
    gates = {gate["code"]: gate for gate in payload["gates"]}

    assert payload["paid_launch_allowed"] is False
    assert payload["overall_status"] == "blocked"
    assert gates["honest_replay_proof"]["status"] == "fail"
    assert "stub_replay_marked_verified" in gates["honest_replay_proof"]["blockers"]
    assert gates["behavioral_goldens"]["status"] == "fail"
    assert "blocking_text_only_goldens" in gates["behavioral_goldens"]["blockers"]
    assert gates["outcome_verification"]["status"] == "fail"
    assert "outcome_mismatch_detected" in gates["outcome_verification"]["blockers"]
    assert "outcome_not_verified" in gates["outcome_verification"]["blockers"]


def test_owner_money_path_health_reports_gateway_capture_durability_blockers(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    now = datetime.now(UTC)

    with session_factory() as db:
        db.add(
            Project(
                id="proj_gateway_loss",
                name="Gateway Loss",
                owner_ref="loss",
                is_active=True,
            )
        )
        db.add(
            _call(
                "proj_gateway_loss",
                "call_gateway_loss",
                created_at=now - timedelta(minutes=5),
            )
        )
        db.add(
            GatewayCaptureHealth(
                id="gch_loss",
                project_id="proj_gateway_loss",
                gateway_id="gw-loss",
                emit_mode="http",
                durability_mode="fail_closed",
                capture_status="loss_detected",
                spool_enabled=True,
                spool_backlog=3,
                spool_bytes=4096,
                spool_max_bytes=104857600,
                spool_reserved_bytes=0,
                spool_oldest_age_seconds=90,
                spool_high_watermark=False,
                emit_failures=2,
                enqueue_failures=0,
                flush_failures=1,
                flushed=0,
                loss_count=1,
                backpressure_rejections=0,
                heartbeat_at=now,
                payload_json="{}",
            )
        )
        db.commit()

    response = test_client.get("/v1/owner/money-path-health", headers=owner_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"]["gateway_unhealthy_tenants"] == 1
    assert payload["platform"]["gateway_loss_tenants"] == 1
    assert "capture_loss_detected" in payload["platform"]["launch_blockers"]

    row = payload["tenants"][0]
    assert row["project_id"] == "proj_gateway_loss"
    assert row["capture_durability_status"]["state"] == "loss_detected"
    assert row["capture_durability_status"]["spool_backlog"] == 3
    assert "capture_loss_detected" in row["launch_blockers"]
    assert row["next_owner_action"] == "restore_capture"


def test_owner_money_path_health_requires_owner_credentials(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, _ = client
    _set_owner_auth(monkeypatch)

    response = test_client.get("/v1/owner/money-path-health")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid owner credentials."
