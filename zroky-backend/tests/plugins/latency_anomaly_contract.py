from __future__ import annotations

from app.services.detectors.latency_anomaly import detect


def test_latency_anomaly_contract_callable() -> None:
    assert callable(detect)
