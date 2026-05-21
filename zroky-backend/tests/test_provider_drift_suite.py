"""Layer 2 tests for prompt suite + model registry loaders & DB sync."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import ProviderDriftModel, ProviderDriftPrompt
from app.services.provider_drift.categories import CATEGORIES
from app.services.provider_drift.prompt_suite import (
    filter_active_by_category,
    load_prompt_suite,
    sync_prompts_to_db,
)
from app.services.provider_drift.registry import (
    load_model_registry,
    sync_models_to_db,
)


@pytest.fixture()
def session(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pdw.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = factory()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


class TestLoadPromptSuite:
    def test_default_suite_loads(self) -> None:
        suite = load_prompt_suite()
        assert len(suite) >= 40
        # Every category must have at least one active prompt.
        for cat in CATEGORIES:
            assert any(s.category == cat for s in suite), (
                f"category {cat} missing from suite"
            )

    def test_ids_unique(self) -> None:
        suite = load_prompt_suite()
        ids = [s.id for s in suite]
        assert len(ids) == len(set(ids))

    def test_sorted_by_id(self) -> None:
        suite = load_prompt_suite()
        ids = [s.id for s in suite]
        assert ids == sorted(ids)

    def test_filter_active_by_category(self) -> None:
        suite = load_prompt_suite()
        math = filter_active_by_category(suite, "math")
        assert all(s.category == "math" for s in math)
        assert all(s.active for s in math)

    def test_duplicate_id_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "p.json"
        bad.write_text(json.dumps({
            "version": 1,
            "prompts": [
                {"id": "x", "category": "math", "prompt_text": "1", "expected_signal": {}},
                {"id": "x", "category": "math", "prompt_text": "2", "expected_signal": {}},
            ],
        }))
        with pytest.raises(ValueError, match="Duplicate prompt id"):
            load_prompt_suite(bad)

    def test_invalid_category_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "p.json"
        bad.write_text(json.dumps({
            "version": 1,
            "prompts": [
                {"id": "x", "category": "nonsense", "prompt_text": "1", "expected_signal": {}},
            ],
        }))
        with pytest.raises(ValueError, match="category invalid"):
            load_prompt_suite(bad)


class TestSyncPromptsToDb:
    def test_initial_insert(self, session) -> None:
        result = sync_prompts_to_db(session)
        assert result["inserted"] >= 40
        assert result["updated"] == 0
        rows = session.execute(select(ProviderDriftPrompt)).scalars().all()
        assert len(rows) == result["inserted"]

    def test_idempotent(self, session) -> None:
        sync_prompts_to_db(session)
        result = sync_prompts_to_db(session)
        assert result["inserted"] == 0
        assert result["updated"] == 0

    def test_update_propagates(self, session, tmp_path: Path) -> None:
        # Initial sync from default suite
        sync_prompts_to_db(session)

        # Override suite with a smaller set; expect deactivation of orphans
        from app.services.provider_drift.models import PromptSpec
        custom = (
            PromptSpec(
                id="math_001",
                category="math",
                prompt_text="EDITED PROMPT",
                expected_signal={"kind": "must_contain", "value": "1"},
            ),
        )
        result = sync_prompts_to_db(session, suite=custom)
        assert result["updated"] == 1
        assert result["deactivated"] >= 39

        row = session.execute(
            select(ProviderDriftPrompt).where(ProviderDriftPrompt.id == "math_001")
        ).scalar_one()
        assert row.prompt_text == "EDITED PROMPT"
        assert row.active is True


class TestLoadModelRegistry:
    def test_default_registry(self) -> None:
        regs = load_model_registry()
        assert len(regs) >= 6
        # Must cover at least 3 distinct providers
        providers = {r.provider for r in regs}
        assert len(providers) >= 3

    def test_ids_unique_and_sorted(self) -> None:
        regs = load_model_registry()
        ids = [r.id for r in regs]
        assert len(ids) == len(set(ids))
        assert ids == sorted(ids)


class TestSyncModelsToDb:
    def test_initial_insert(self, session) -> None:
        result = sync_models_to_db(session)
        assert result["inserted"] >= 6
        rows = session.execute(select(ProviderDriftModel)).scalars().all()
        assert len(rows) == result["inserted"]

    def test_idempotent(self, session) -> None:
        sync_models_to_db(session)
        result = sync_models_to_db(session)
        assert result == {"inserted": 0, "updated": 0, "deactivated": 0}
