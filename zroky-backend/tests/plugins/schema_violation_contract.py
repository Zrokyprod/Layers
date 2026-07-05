from __future__ import annotations

from app.services.detectors.schema_violation import detect


def test_schema_violation_contract_callable() -> None:
    assert callable(detect)
