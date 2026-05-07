from app.services.fix_generator import FixGenerationInput, generate_fix_suggestion


def test_token_overflow_generates_minimal_diff_and_pr_payload() -> None:
    suggestion = generate_fix_suggestion(
        FixGenerationInput(
            diagnosis_id="diag-token-1",
            diagnosis_type="TOKEN_OVERFLOW",
            diagnosis_confidence=0.97,
            evidence={
                "detected_by": "error_code",
                "estimated_tokens": 5000,
                "model_limit": 4096,
                "overflow_by": 904,
            },
            code_snippet="messages = request_messages",
            target_file="app/services/chat_handler.py",
            call_context={
                "fix_conflicts_with": ["custom_prompt_builder_v2"],
            },
        )
    )

    payload = suggestion.to_dict()
    assert payload["title"] == "Fix TOKEN_OVERFLOW by bounding prompt size"
    assert payload["fix_id"] == "fix-token_overflow-diag-token-1"
    assert payload["target_file"] == "app/services/chat_handler.py"
    assert payload["file_hint"] == "Review the target file around the anchor before applying the patch."
    assert payload["anchor"] == "messages = request_messages"
    assert "--- BEFORE ---" in payload["diff"]
    assert "messages = request_messages" in payload["diff"]
    assert "<existing_prompt_budget_helper>(request_messages" in payload["diff"]
    assert payload["patch_unified"].startswith(
        "diff --git a/app/services/chat_handler.py b/app/services/chat_handler.py"
    )
    assert "-messages = request_messages" in payload["patch_unified"]
    assert "+messages = <existing_prompt_budget_helper>(request_messages" in payload["patch_unified"]
    assert 0.85 <= payload["confidence"] <= 0.95
    assert payload["confidence_level"] == "high"
    assert payload["risk_level"] == "low"
    assert payload["fix_scope"] == "local"
    assert payload["blast_radius"] == "low"
    assert payload["time_to_apply_estimate"] == "5-10 minutes"
    assert payload["requires_tests_update"] is True
    assert payload["affected_paths"] == ["app/services/chat_handler.py"]
    assert payload["fix_conflicts_with"] == ["custom_prompt_builder_v2"]
    assert payload["rollout_strategy"] == "single-call"
    assert payload["observability_checks"][0] == "Monitor TOKEN_OVERFLOW error rate after deployment."
    assert payload["reversibility"] == "easy"
    assert payload["fix_category"] == "reliability"
    assert payload["recommended_priority"] == "P0"
    assert payload["fix_tags"] == ["token", "prompt", "context-limit"]
    assert payload["expected_impact"] == {
        "prevents": ["TOKEN_OVERFLOW errors", "provider context-length rejections"],
        "improves": ["request success rate", "latency stability"],
        "confidence": "high",
    }
    assert payload["fix_rationale"].startswith("Bounding prompt input")
    assert "preserves required user intent" in payload["review_points"][0]
    assert payload["apply_instructions"][0] == "Open `app/services/chat_handler.py`."
    assert payload["verification_steps"][0] == "Run the same request that previously failed with TOKEN_OVERFLOW."
    assert payload["rollback_instructions"][0] == "Revert the applied diff."
    assert payload["alternatives"][0]["option"] == "reduce_max_tokens"
    assert "tradeoff" in payload["alternatives"][0]
    assert payload["advisory_only"] is True
    assert payload["pr"]["branch_name"] == "zroky/fix-token_overflow-diag-token-1"
    assert "Advisory draft only" in payload["pr"]["pr_description"]
    assert "`overflow_by`: `904`" in payload["pr"]["pr_description"]
    assert "Target file: `app/services/chat_handler.py`" in payload["pr"]["pr_description"]
    assert "Anchor: `messages = request_messages`" in payload["pr"]["pr_description"]
    assert "Fix ID: `fix-token_overflow-diag-token-1`" in payload["pr"]["pr_description"]
    assert "Risk level: `low`" in payload["pr"]["pr_description"]
    assert "Fix scope: `local`" in payload["pr"]["pr_description"]
    assert "Blast radius: `low`" in payload["pr"]["pr_description"]
    assert "Time to apply estimate: `5-10 minutes`" in payload["pr"]["pr_description"]
    assert "Requires tests update: `true`" in payload["pr"]["pr_description"]
    assert "Potential conflicts: `custom_prompt_builder_v2`" in payload["pr"]["pr_description"]
    assert "Rollout strategy: `single-call`" in payload["pr"]["pr_description"]
    assert "Reversibility: `easy`" in payload["pr"]["pr_description"]
    assert "Fix category: `reliability`" in payload["pr"]["pr_description"]
    assert "Recommended priority: `P0`" in payload["pr"]["pr_description"]
    assert "Fix tags: `token`, `prompt`, `context-limit`" in payload["pr"]["pr_description"]
    assert "## Observability Checks" in payload["pr"]["pr_description"]
    assert "## Expected Impact" in payload["pr"]["pr_description"]
    assert "## Verification Steps" in payload["pr"]["pr_description"]
    assert "## Rollback" in payload["pr"]["pr_description"]
    assert "## Required Review Points" in payload["pr"]["pr_description"]
    assert "`reduce_max_tokens`" in payload["pr"]["pr_description"]


def test_token_overflow_conversation_history_prefers_history_summary() -> None:
    suggestion = generate_fix_suggestion(
        FixGenerationInput(
            diagnosis_id="diag-token-history",
            diagnosis_type="TOKEN_OVERFLOW",
            diagnosis_confidence=0.90,
            evidence={
                "subtype": "conversation_accumulation",
                "estimated_tokens": 9000,
                "model_limit": 8192,
            },
            code_snippet="messages = conversation_history",
            target_file="app/services/chat_handler.py",
        )
    )

    assert "<existing_history_summary_helper>(conversation_history" in suggestion.diff


def test_loop_detected_generates_bounded_loop_diff() -> None:
    suggestion = generate_fix_suggestion(
        FixGenerationInput(
            diagnosis_id="diag-loop-1",
            diagnosis_type="LOOP_DETECTED",
            diagnosis_confidence=0.92,
            evidence={
                "repeat_count": 6,
                "repeat_window_seconds": 80,
                "prompt_fingerprint": "abc123",
            },
            code_snippet="while True:\n    run_agent_step()",
            target_file="app/agents/runner.py",
        )
    )

    assert suggestion.title == "Fix LOOP_DETECTED with a bounded no-progress guard"
    assert "while True:" in suggestion.diff
    assert "for _zroky_step in range(<configured_max_agent_steps>):" in suggestion.diff
    assert suggestion.target_file == "app/agents/runner.py"
    assert suggestion.anchor == "while True:"
    assert suggestion.patch_unified.startswith("diff --git a/app/agents/runner.py")
    assert suggestion.confidence_level == "medium"
    assert suggestion.risk_level == "medium"
    assert suggestion.fix_scope == "module"
    assert suggestion.blast_radius == "medium"
    assert suggestion.time_to_apply_estimate == "15-30 minutes"
    assert suggestion.requires_tests_update is True
    assert suggestion.affected_paths == ["app/agents/runner.py"]
    assert suggestion.rollout_strategy == "guarded"
    assert suggestion.reversibility == "moderate"
    assert suggestion.fix_category == "safety"
    assert suggestion.recommended_priority == "P1"
    assert suggestion.fix_tags == ["agent-loop", "guardrail", "no-progress"]
    assert suggestion.observability_checks[0] == "Monitor LOOP_DETECTED recurrence after deployment."
    assert "runaway agent loops" in suggestion.expected_impact["prevents"]
    assert "step limit" in suggestion.review_points[0]
    assert "loop reproduction" in suggestion.verification_steps[0]
    assert "Revert the applied loop-guard diff." in suggestion.rollback_instructions[0]
    assert suggestion.alternatives[0]["option"] == "max_tool_cycles"
    assert suggestion.pr.branch_name == "zroky/fix-loop_detected-diag-loop-1"
    assert "`repeat_count`: `6`" in suggestion.pr.pr_description


def test_no_code_snippet_returns_advisory_conceptual_fix() -> None:
    suggestion = generate_fix_suggestion(
        FixGenerationInput(
            diagnosis_id="diag-token-no-snippet",
            diagnosis_type="TOKEN_OVERFLOW",
            diagnosis_confidence=0.80,
            evidence={
                "estimated_tokens": 3900,
                "model_limit": 4096,
            },
        )
    )

    assert suggestion.diff.startswith("--- ADVISORY ---")
    assert suggestion.confidence < 0.60
    assert suggestion.confidence_level == "low"
    assert suggestion.risk_level == "high"
    assert suggestion.fix_scope == "local"
    assert suggestion.blast_radius == "medium"
    assert suggestion.time_to_apply_estimate == "15-30 minutes"
    assert suggestion.requires_tests_update is True
    assert suggestion.affected_paths == []
    assert suggestion.fix_conflicts_with == []
    assert suggestion.rollout_strategy == "single-call"
    assert suggestion.reversibility == "moderate"
    assert suggestion.fix_category == "reliability"
    assert suggestion.recommended_priority == "P2"
    assert "TOKEN_OVERFLOW errors" in suggestion.expected_impact["prevents"]
    assert suggestion.target_file == "unknown"
    assert suggestion.anchor == "messages construction before provider call"
    assert suggestion.file_hint == "Apply where messages/history/max_tokens are constructed before the provider call."
    assert suggestion.patch_unified == ""
    assert suggestion.apply_instructions[0] == "Locate the file described by file_hint."
    assert "Confirm no TOKEN_OVERFLOW" in suggestion.verification_steps[1]
    assert "No code snippet was provided" in suggestion.diff


def test_unknown_diagnosis_does_not_invent_patch() -> None:
    suggestion = generate_fix_suggestion(
        FixGenerationInput(
            diagnosis_id="diag-unknown-1",
            diagnosis_type="UNKNOWN_FAILURE",
            diagnosis_confidence=0.40,
            evidence={},
            code_snippet="dangerous_call()",
        )
    )

    assert suggestion.diff.startswith("--- ADVISORY ---")
    assert suggestion.target_file == "unknown"
    assert suggestion.anchor == "unknown"
    assert suggestion.patch_unified == ""
    assert suggestion.confidence_level == "low"
    assert suggestion.risk_level == "high"
    assert suggestion.expected_impact["confidence"] == "low"
    assert "Reproduce the diagnosed behavior" in suggestion.verification_steps[0]
    assert suggestion.confidence < 0.50
    assert "No deterministic code strategy" in suggestion.diff
