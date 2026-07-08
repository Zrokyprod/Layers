from __future__ import annotations

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import SourceMutationPollState, SourceMutationRecord, SystemOfRecordConnectorConfig
from app.services.source_mutation_polling import poll_source_mutations_once
from app.services.system_of_record_connector_config import (
    STRIPE_REFUND_CONNECTOR_TYPE,
    upsert_stripe_refund_connector_config,
)


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'source_mutation_polling.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_stripe_poll_ingests_unreceipted_refund_as_policy_bypass(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROVIDER_KEY_VAULT_KEK", "test-kek-for-source-mutation-polling")
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    upsert_stripe_refund_connector_config(
        db_session,
        project_id="proj_poll",
        bearer_token="sk_test_source_mutation",
        query={"event_path": "data", "type": "refund.updated"},
    )

    class FakeClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, *, headers, params, auth=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["params"] = params
            captured["auth"] = auth
            request = httpx.Request("GET", url, headers=headers, params=params)
            return httpx.Response(
                200,
                request=request,
                json={
                    "data": [
                        {
                            "id": "evt_refund_bypass",
                            "type": "refund.updated",
                            "created": 1_785_000_000,
                            "data": {
                                "object": {
                                    "id": "re_bypass",
                                    "object": "refund",
                                    "status": "succeeded",
                                    "actor_type": "ai_agent",
                                    "actor_id": "refund-agent",
                                }
                            },
                        }
                    ],
                    "has_more": False,
                },
            )

    monkeypatch.setattr("app.services.source_mutation_polling.httpx.Client", FakeClient)

    result = poll_source_mutations_once(db_session, project_limit=10, per_connector_limit=25, timeout_seconds=3.0)

    assert result.scanned == 1
    assert result.succeeded == 1
    assert result.failed == 0
    assert result.ingested == 1
    assert captured["url"] == "https://api.stripe.com/v1/events"
    assert captured["headers"] == {"Accept": "application/json", "Authorization": "Bearer sk_test_source_mutation"}
    assert captured["params"] == {"type": "refund.updated", "limit": 25}

    mutation = db_session.execute(select(SourceMutationRecord)).scalar_one()
    assert mutation.project_id == "proj_poll"
    assert mutation.source_system == "stripe"
    assert mutation.mutation_id == "evt_refund_bypass"
    assert mutation.action_type == "refund"
    assert mutation.resource_id == "re_bypass"
    assert mutation.actor_type == "ai_agent"
    assert mutation.classification == "policy_bypass"

    state = db_session.execute(select(SourceMutationPollState)).scalar_one()
    assert state.project_id == "proj_poll"
    assert state.connector_type == STRIPE_REFUND_CONNECTOR_TYPE
    assert "evt_refund_bypass" in (state.cursor_json or "")
    assert state.last_success_at is not None
    assert state.last_error is None


def test_poll_skips_http_connectors_without_credentials(db_session) -> None:
    db_session.add(
        SystemOfRecordConnectorConfig(
            project_id="proj_poll",
            connector_type=STRIPE_REFUND_CONNECTOR_TYPE,
            base_url="https://api.stripe.com",
            path_template="/v1/refunds/{refund_id}",
            is_active=True,
        )
    )
    db_session.commit()

    result = poll_source_mutations_once(db_session)

    assert result.scanned == 1
    assert result.skipped == 1
    assert result.succeeded == 0
    assert db_session.execute(select(SourceMutationRecord)).scalars().all() == []
