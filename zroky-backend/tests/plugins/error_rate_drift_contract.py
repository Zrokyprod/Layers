from __future__ import annotations

from app.services.detectors.error_rate_drift import detect_entry


def test_error_rate_drift_contract_callable() -> None:
    assert callable(detect_entry)
