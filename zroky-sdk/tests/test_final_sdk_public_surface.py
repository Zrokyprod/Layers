from __future__ import annotations

import zroky


def test_python_public_surface_excludes_old_capture_and_fingerprint_exports() -> None:
    for old_name in (
        "capture_handoff",
        "capture_memory",
        "capture_policy_decision",
        "capture_retrieval",
        "capture_tool_call",
        "generate_prompt_fingerprint",
    ):
        assert not hasattr(zroky, old_name), f"{old_name} must stay out of the final public SDK"


def test_python_public_surface_keeps_final_policy_action_and_outcome_entrypoints() -> None:
    for final_name in (
        "guard",
        "pre_execution_guard",
        "protect",
        "verified_action",
        "await_action_proof",
        "verify_outcome",
        "outcome",
    ):
        assert hasattr(zroky, final_name), f"{final_name} must remain public"
