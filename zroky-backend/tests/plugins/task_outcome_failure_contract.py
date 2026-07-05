from __future__ import annotations

from app.services.detectors.task_outcome_failure import detect


def test_task_outcome_failure_contract_callable() -> None:
    assert callable(detect)
