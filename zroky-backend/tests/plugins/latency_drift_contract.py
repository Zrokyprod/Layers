from __future__ import annotations

from app.services.detectors.latency_drift import detect_entry


def test_latency_drift_contract_callable() -> None:
    assert callable(detect_entry)
