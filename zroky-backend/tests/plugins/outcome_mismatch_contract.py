from __future__ import annotations

from app.services.detectors.outcome_mismatch import detect


def test_outcome_mismatch_contract_callable() -> None:
    assert callable(detect)
