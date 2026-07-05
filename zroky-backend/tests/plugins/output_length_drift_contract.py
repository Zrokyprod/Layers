from __future__ import annotations

from app.services.detectors.output_length_drift import detect_entry


def test_output_length_drift_contract_callable() -> None:
    assert callable(detect_entry)
