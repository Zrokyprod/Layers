from __future__ import annotations

from app.services.detectors.rag_grounding_failure import detect


def test_rag_grounding_failure_contract_callable() -> None:
    assert callable(detect)
