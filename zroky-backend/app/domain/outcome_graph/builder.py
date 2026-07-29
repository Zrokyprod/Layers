from __future__ import annotations

from typing import Any

from app.domain.assurance_pack.predicate import PredicateError, evaluate_predicate
from app.domain.assurance_pack.schema import validate_assurance_pack


CLASSIFICATION_PRIORITY = ("unknown", "conflicted", "stale", "duplicate", "missing", "wrong", "forbidden", "verified")


def build_outcome_graph_snapshot(
    *,
    intent: dict[str, Any],
    assurance_pack: dict[str, Any],
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    pack = validate_assurance_pack(assurance_pack)
    observations_by_binding: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        provenance = observation.get("provenance")
        if isinstance(provenance, dict):
            observations_by_binding.setdefault(str(provenance.get("source_binding")), []).append(observation)
    actual_effects: list[dict[str, Any]] = []
    expected_binding_keys = {binding.key for binding in pack.source_bindings}

    for effect in pack.effects:
        binding = next((item for item in pack.source_bindings if item.object_type == effect.object_type), None)
        binding_observations = observations_by_binding.get(binding.key, []) if binding else []
        observation = _latest_observation(binding_observations)
        observed_state = observation.get("observed_state") if isinstance(observation, dict) else None
        context = {"intent": intent, effect.object_type: observed_state or {}}
        matched = False
        error: str | None = None
        if observed_state is not None:
            try:
                matched = bool(evaluate_predicate(effect.predicate, context))
            except PredicateError as exc:
                error = str(exc)
        stale = observation is not None and observation.get("freshness", {}).get("fresh") is False
        conflicted = observation is not None and (
            bool(observation.get("conflicts"))
            or bool(observation.get("provenance", {}).get("conflicted"))
        )
        distinct_refs = {str(item.get("observed_object_ref")) for item in binding_observations if item.get("observed_object_ref")}
        actual_effects.append(
            {
                "effect_key": effect.key,
                "object_type": effect.object_type,
                "source_binding": binding.key if binding else None,
                "observed": observed_state is not None,
                "matched": matched,
                "duplicate": len(distinct_refs) > 1,
                "stale": stale,
                "conflicted": conflicted,
                "predicate_error": error,
                "observation_digest": observation.get("observation_digest") if isinstance(observation, dict) else None,
            }
        )

    for source_binding, binding_observations in observations_by_binding.items():
        if source_binding not in expected_binding_keys:
            actual_effects.append(
                {
                    "effect_key": None,
                    "object_type": None,
                    "source_binding": source_binding,
                    "observed": True,
                    "matched": False,
                    "duplicate": len({str(item.get("observed_object_ref")) for item in binding_observations if item.get("observed_object_ref")}) > 1,
                    "stale": any(item.get("freshness", {}).get("fresh") is False for item in binding_observations),
                    "conflicted": any(bool(item.get("conflicts")) for item in binding_observations),
                    "predicate_error": None,
                    "observation_digest": binding_observations[0].get("observation_digest"),
                    "forbidden": True,
                }
            )

    classification = classify_outcome_graph_snapshot({"actual_effects": actual_effects})
    return {
        "schema_version": "zroky.outcome_graph_snapshot.v1",
        "workflow_key": pack.workflow_key,
        "pack_version": pack.version,
        "expected_effects": [
            {"effect_key": effect.key, "object_type": effect.object_type, "predicate": effect.predicate}
            for effect in pack.effects
        ],
        "actual_effects": actual_effects,
        "classification": classification,
        "observation_count": len(observations),
    }


def _latest_observation(observations: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not observations:
        return None
    return max(observations, key=lambda item: str(item.get("read_at") or item.get("observed_at") or ""))


def classify_outcome_graph_snapshot(snapshot: dict[str, Any]) -> str:
    effects = snapshot.get("actual_effects")
    if not isinstance(effects, list) or not effects:
        return "unknown"
    seen: set[str] = set()
    for classification, predicate in (
        ("unknown", lambda effect: bool(effect.get("predicate_error"))),
        ("conflicted", lambda effect: bool(effect.get("conflicted"))),
        ("stale", lambda effect: bool(effect.get("stale"))),
        ("duplicate", lambda effect: bool(effect.get("duplicate"))),
        ("missing", lambda effect: effect.get("observed") is False),
        ("wrong", lambda effect: effect.get("observed") is True and effect.get("matched") is False and not effect.get("forbidden")),
        ("forbidden", lambda effect: bool(effect.get("forbidden"))),
    ):
        if any(predicate(effect) for effect in effects if isinstance(effect, dict)):
            seen.add(classification)
    if seen:
        return next(item for item in CLASSIFICATION_PRIORITY if item in seen)
    if all(isinstance(effect, dict) and effect.get("matched") is True for effect in effects):
        return "verified"
    return "unknown"
