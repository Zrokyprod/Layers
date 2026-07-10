from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    ActionExecutionAttempt,
    ActionIntent,
    ActionRunner,
    Project,
    SystemOfRecordConnectorConfig,
)
from app.services.connector_credentials import create_connector_credential
from app.services.private_runner_verification import (
    claim_private_runner_verification,
    enqueue_private_runner_verification,
    finish_private_runner_verification,
    sweep_stale_private_runner_verifications,
)


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PROVIDER_KEY_VAULT_KEK", "test-private-runner-kek-12345678901234567890")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_private_runner_verification_is_scoped_and_reconciles(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'private_runner_verification.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    try:
        with factory() as db:
            db.add(Project(id="project-a", name="project-a"))
            credential = create_connector_credential(
                db,
                project_id="project-a",
                name="stripe-runner",
                credential_kind="bearer_token",
                custody_mode="private_runner",
                plaintext_secret=None,
                secret_ref="customer-runner-secret://payments/stripe",
                scopes=["refunds:read"],
                allowed_connector_types=["stripe_refund"],
                expires_at=None,
                rotation_due_at=None,
                actor_subject="owner-a",
            )
            config = SystemOfRecordConnectorConfig(
                project_id="project-a",
                connector_type="stripe_refund",
                base_url="https://api.stripe.com",
                bearer_credential_id=credential.id,
                is_active=True,
            )
            runner = ActionRunner(
                project_id="project-a",
                name="payments-runner",
                runner_type="customer_hosted",
                environment="production",
                status="online",
                credential_scope_json=json.dumps(
                    {"allowed_prefixes": ["customer-runner-secret://payments/"]}
                ),
                heartbeat_payload_json=json.dumps({"verification_adapters": ["stripe_refund"]}),
            )
            intent = ActionIntent(
                project_id="project-a",
                contract_version_id="contract-1",
                contract_key="refund",
                contract_version="1",
                action_type="refund.create",
                operation_kind="TRANSFER",
                environment="production",
                idempotency_key="intent-1",
                intent_digest="sha256:intent-1",
                canonical_intent_json="{}",
                status="authorized",
            )
            db.add_all([config, runner, intent])
            db.flush()
            attempt = ActionExecutionAttempt(
                project_id="project-a",
                action_intent_id=intent.id,
                runner_id=runner.id,
                attempt_number=1,
                idempotency_key="attempt-1",
                status="succeeded",
                credential_ref="customer-runner-secret://payments/stripe",
                plan_digest="sha256:plan-1",
                plan_json="{}",
            )
            db.add(attempt)
            db.flush()

            job = enqueue_private_runner_verification(
                db,
                intent=intent,
                attempt=attempt,
                connector_type="stripe_refund",
                context={
                    "claimed": {
                        "refund_id": "re_123",
                        "status": "succeeded",
                        "amount_minor": 5000,
                        "currency": "usd",
                    },
                    "verification": {"refund_id": "re_123"},
                    "match_fields": ["refund_id", "status", "amount_minor", "currency"],
                },
            )
            assert job is not None
            assert json.loads(job.plan_json)["operation"] == "refund.read"
            assert "base_url" not in job.plan_json

            claimed = claim_private_runner_verification(
                db, project_id="project-a", runner_id=runner.id
            )
            assert claimed.id == job.id
            finished = finish_private_runner_verification(
                db,
                project_id="project-a",
                runner_id=runner.id,
                job_id=job.id,
                actual_record={
                    "refund_id": "re_123",
                    "status": "succeeded",
                    "amount_minor": 5000,
                    "currency": "usd",
                },
                record_found=True,
            )
            assert finished.status == "succeeded"
            assert intent.proof_status == "matched"
            assert intent.receipt_status == "pending"

            stale_attempt = ActionExecutionAttempt(
                project_id="project-a",
                action_intent_id=intent.id,
                runner_id=runner.id,
                attempt_number=2,
                idempotency_key="attempt-2",
                status="succeeded",
                credential_ref="customer-runner-secret://payments/stripe",
                plan_digest="sha256:plan-2",
                plan_json="{}",
            )
            db.add(stale_attempt)
            db.flush()
            stale_job = enqueue_private_runner_verification(
                db,
                intent=intent,
                attempt=stale_attempt,
                connector_type="stripe_refund",
                context={"claimed": {"refund_id": "re_456"}, "verification": {"refund_id": "re_456"}},
            )
            assert stale_job is not None
            stale_job.created_at = datetime.now(timezone.utc) - timedelta(seconds=301)
            swept = sweep_stale_private_runner_verifications(
                db,
                stale_after_seconds=300,
            )
            assert swept["expired"] == 1
            assert stale_job.status == "failed"
            assert stale_job.error_message == "runner_verification_timed_out"
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
