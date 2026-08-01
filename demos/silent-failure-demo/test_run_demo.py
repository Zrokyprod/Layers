from __future__ import annotations

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
