from __future__ import annotations

from collections import Counter
from typing import Any

from app.domain.assurance_pack.predicate import PredicateError, evaluate_predicate
from app.domain.assurance_pack.schema import validate_assurance_pack


REQUIRED_CASES = ("success", "missing", "wrong", "duplicate", "stale", "conflict")


def simulate_pack(pack_payload: dict[str, Any], cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pack = validate_assurance_pack(pack_payload)
    results: dict[str, dict[str, Any]] = {}
    missing_cases = [case for case in REQUIRED_CASES if case not in cases]

    for case_name, case in cases.items():
        objects = case.get("objects") if isinstance(case.get("objects"), dict) else {}
        stale = set(case.get("stale_bindings") or [])
        conflicts = set(case.get("conflicts") or [])
        counts = Counter(effect.object_type for effect in pack.effects)
        case_failures: list[str] = []

        for effect in pack.effects:
            if effect.object_type not in objects:
                case_failures.append(f"missing:{effect.object_type}")
                continue
            if counts[effect.object_type] > 1 and case_name == "duplicate":
                case_failures.append(f"duplicate:{effect.object_type}")
            try:
                if not evaluate_predicate(effect.predicate, objects):
                    case_failures.append(f"wrong:{effect.key}")
            except PredicateError:
                case_failures.append(f"wrong:{effect.key}")

        for binding in pack.source_bindings:
            if binding.key in stale:
                case_failures.append(f"stale:{binding.key}")
        for item in conflicts:
            case_failures.append(f"conflict:{item}")

        results[case_name] = {"passed": not case_failures, "failures": case_failures}

    return {"valid": not missing_cases and all(item["passed"] for item in results.values()), "missing_cases": missing_cases, "results": results}
