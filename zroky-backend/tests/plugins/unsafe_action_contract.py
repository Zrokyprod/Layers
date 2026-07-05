from __future__ import annotations

from app.services.detectors.unsafe_action import detect


def test_unsafe_action_contract_callable() -> None:
    assert callable(detect)
