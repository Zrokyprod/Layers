from __future__ import annotations

from app.services.detectors.accuracy_regression import detect_entry


def test_accuracy_regression_contract_callable() -> None:
    assert callable(detect_entry)
