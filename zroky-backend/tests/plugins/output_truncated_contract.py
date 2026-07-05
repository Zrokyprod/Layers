from __future__ import annotations

from app.services.detectors.output_truncated import detect


def test_output_truncated_contract_callable() -> None:
    assert callable(detect)
