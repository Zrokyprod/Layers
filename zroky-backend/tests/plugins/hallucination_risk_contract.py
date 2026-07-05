from __future__ import annotations

from app.services.detectors.hallucination_risk import detect_entry


def test_hallucination_risk_contract_callable() -> None:
    assert callable(detect_entry)
