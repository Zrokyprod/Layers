from __future__ import annotations

from app.domain.outcome_graph import classify_outcome_graph_snapshot


def test_outcome_graph_classifies_required_verdicts() -> None:
    cases = {
        "verified": [{"observed": True, "matched": True}],
        "missing": [{"observed": False, "matched": False}],
        "wrong": [{"observed": True, "matched": False}],
        "duplicate": [{"observed": True, "matched": True, "duplicate": True}],
        "forbidden": [{"observed": True, "matched": False, "forbidden": True}],
        "stale": [{"observed": True, "matched": True, "stale": True}],
        "conflicted": [{"observed": True, "matched": True, "conflicted": True}],
        "unknown": [{"observed": True, "matched": False, "predicate_error": "bad predicate"}],
    }

    for expected, effects in cases.items():
        assert classify_outcome_graph_snapshot({"actual_effects": effects}) == expected
