from __future__ import annotations

from app.services.detectors.token_usage_drift import detect_entry


def test_token_usage_drift_contract_callable() -> None:
    assert callable(detect_entry)
