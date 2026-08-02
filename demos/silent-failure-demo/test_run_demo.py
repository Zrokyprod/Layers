from __future__ import annotations

from types import SimpleNamespace

import seed
from run_demo import wait_for_graph_classification


def test_waits_for_automatic_graph_without_calling_legacy_build_endpoint() -> None:
    class Api:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []
            self.reads = 0

        def request(self, method: str, path: str, **_: object) -> dict:
            self.calls.append((method, path))
            if method == "GET":
                self.reads += 1
                classification = "pending" if self.reads == 1 else "missing"
                return {"items": [{"classification": classification, "graph": {"run_id": "run-1"}}]}
            return {"checked": 1, "updated": 1}

    api = Api()
    graph = wait_for_graph_classification(api, "run-1", "missing", poll_seconds=0)

    assert graph["classification"] == "missing"
    assert ("POST", "/v1/outcome-graphs/recheck-due") in api.calls
    assert all("/runs/" not in path for _, path in api.calls)


def test_seed_registers_only_the_active_pull_secret_reference(monkeypatch) -> None:
    calls: list[tuple[str, str, dict]] = []

    class Api:
        def request(self, method: str, path: str, **kwargs: object) -> dict:
            calls.append((method, path, kwargs))
            if path == "/v1/source-connectors":
                return {"capability": "stripe_refund.read", "secret_ref": "STRIPE_KEY_PROJ_DEMO"}
            return {"id": "pack-1", "workflow_key": "refund_flow_v1", "version": "1.0.0"}

    config = SimpleNamespace(
        project="proj-demo",
        amount_minor=450_000,
        currency="inr",
        stripe_secret_ref="STRIPE_KEY_PROJ_DEMO",
    )
    monkeypatch.setattr(seed.DemoConfig, "from_env", staticmethod(lambda: config))
    monkeypatch.setattr(seed, "ApiClient", lambda _: Api())
    monkeypatch.setattr(seed, "create_test_charge", lambda *_: {"id": "ch_test"})
    monkeypatch.setattr(seed, "demo_id", lambda: "demo-1")
    monkeypatch.setattr(seed, "load_state", lambda: {})
    monkeypatch.setattr(seed, "save_state", lambda _: None)

    seed.setup()

    assert [path for _, path, _ in calls] == ["/v1/source-connectors", "/v1/assurance-packs"]
    connector_body = calls[0][2]["body"]
    assert connector_body["secret_ref"] == "STRIPE_KEY_PROJ_DEMO"
