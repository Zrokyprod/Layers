from __future__ import annotations

from app.services.detectors.loop import detect_entry


def test_loop_contract_callable() -> None:
    assert callable(detect_entry)
