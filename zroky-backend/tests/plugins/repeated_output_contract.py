from __future__ import annotations

from app.services.detectors.repeated_output import detect_entry


def test_repeated_output_contract_callable() -> None:
    assert callable(detect_entry)
