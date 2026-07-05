from __future__ import annotations

from app.services.detectors.empty_output import detect


def test_empty_output_contract_callable() -> None:
    assert callable(detect)
