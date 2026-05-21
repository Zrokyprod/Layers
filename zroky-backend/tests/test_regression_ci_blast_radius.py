"""Tests for `app.services.regression_ci.blast_radius`.

Coverage:
  - Declaration parsing (PR body + .zroky.yml) — happy path, target,
    case-insensitivity, invalid → falls back to None (not exception).
  - Auto-detection ordered rules — first match wins, system prompt
    beats tool prompt, hunk rules vs path rules.
  - `detect()` precedence: override > declared > auto-detect.
"""
from __future__ import annotations

import pytest

from app.services.regression_ci.blast_radius import (
    ChangedFile,
    auto_detect,
    detect,
    parse_declaration,
)
from app.services.regression_ci.models import (
    BlastRadius,
    BlastRadiusCategory,
    BlastRadiusSource,
)


# ── parse_declaration ───────────────────────────────────────────────────────


class TestParseDeclaration:
    def test_pr_body_simple_category(self) -> None:
        body = "This PR fixes refunds.\n\nzroky-blast-radius: tool_prompt"
        br = parse_declaration(body)
        assert br is not None
        assert br.category == BlastRadiusCategory.TOOL_PROMPT
        assert br.source == BlastRadiusSource.DECLARED
        assert br.target is None

    def test_pr_body_with_target(self) -> None:
        body = "zroky-blast-radius: tool_prompt:refund_handler"
        br = parse_declaration(body)
        assert br is not None
        assert br.target == "refund_handler"

    def test_zroky_yaml_format(self) -> None:
        yaml = "version: 1\nzroky-blast-radius: system_prompt\n"
        br = parse_declaration(yaml)
        assert br is not None
        assert br.category == BlastRadiusCategory.SYSTEM_PROMPT

    def test_case_insensitive(self) -> None:
        br = parse_declaration("ZROKY-Blast-Radius: Model_Swap")
        assert br is not None
        assert br.category == BlastRadiusCategory.MODEL_SWAP

    def test_no_declaration_returns_none(self) -> None:
        assert parse_declaration(None) is None
        assert parse_declaration("") is None
        assert parse_declaration("just a normal PR description") is None

    def test_invalid_category_falls_back_to_none(self) -> None:
        # Typos should not block CI; we let auto-detect take over.
        br = parse_declaration("zroky-blast-radius: typo_category")
        assert br is None

    def test_confidence_is_one_for_declared(self) -> None:
        br = parse_declaration("zroky-blast-radius: model_params")
        assert br is not None
        assert br.confidence == 1.0


# ── auto_detect ─────────────────────────────────────────────────────────────


class TestAutoDetect:
    def test_empty_returns_unknown(self) -> None:
        br = auto_detect([])
        assert br.category == BlastRadiusCategory.UNKNOWN
        assert br.source == BlastRadiusSource.AUTO_DETECTED
        assert br.confidence < 0.5  # low confidence on no-evidence fallback

    def test_system_prompt_path(self) -> None:
        files = [ChangedFile(path="prompts/system.md", hunks="+ new system prompt line")]
        br = auto_detect(files)
        assert br.category == BlastRadiusCategory.SYSTEM_PROMPT
        assert "prompts/system.md" in br.files

    def test_system_prompt_beats_tool_prompt(self) -> None:
        # A PR that touches both should classify as the BIGGER blast (SYSTEM_PROMPT).
        files = [
            ChangedFile(path="prompts/system.md", hunks="+x"),
            ChangedFile(path="prompts/tools/refund.md", hunks="+y"),
        ]
        br = auto_detect(files)
        assert br.category == BlastRadiusCategory.SYSTEM_PROMPT

    def test_model_swap_via_hunk(self) -> None:
        files = [ChangedFile(
            path="src/agent.py",
            hunks='+model = "claude-haiku-4"\n+# upgraded from haiku-3',
        )]
        br = auto_detect(files)
        assert br.category == BlastRadiusCategory.MODEL_SWAP

    def test_model_params_via_hunk(self) -> None:
        files = [ChangedFile(
            path="src/agent.py",
            hunks="+temperature = 0.2\n+max_tokens = 1024",
        )]
        br = auto_detect(files)
        # MODEL_SWAP rule comes first so let's give it a non-model-swap hunk
        # by making the diff only touch params:
        assert br.category == BlastRadiusCategory.MODEL_PARAMS

    def test_retrieval_config_path(self) -> None:
        files = [ChangedFile(path="config/rag_config.yaml", hunks="+chunk_size: 512")]
        br = auto_detect(files)
        assert br.category == BlastRadiusCategory.RETRIEVAL_CONFIG

    def test_tool_definition_path(self) -> None:
        files = [ChangedFile(path="tools/refund.py", hunks="+def refund(): pass")]
        br = auto_detect(files)
        assert br.category == BlastRadiusCategory.TOOL_DEFINITION
        assert br.target == "refund"

    def test_tool_prompt_path(self) -> None:
        files = [ChangedFile(path="prompts/tools/refund_handler.md", hunks="+x")]
        br = auto_detect(files)
        assert br.category == BlastRadiusCategory.TOOL_PROMPT
        assert br.target == "refund_handler"

    def test_unrelated_file_falls_back_to_unknown(self) -> None:
        files = [ChangedFile(path="README.md", hunks="+typo fix")]
        br = auto_detect(files)
        assert br.category == BlastRadiusCategory.UNKNOWN

    def test_path_rule_higher_confidence_than_hunk_rule(self) -> None:
        path_match = auto_detect([ChangedFile(path="prompts/system.md", hunks="+x")])
        hunk_match = auto_detect([ChangedFile(path="src/foo.py", hunks="+temperature = 0.5")])
        assert path_match.confidence >= hunk_match.confidence


# ── detect (precedence) ─────────────────────────────────────────────────────


class TestDetectPrecedence:
    def test_override_beats_declaration_and_auto(self) -> None:
        override = BlastRadius(
            category=BlastRadiusCategory.SYSTEM_PROMPT,
            source=BlastRadiusSource.OVERRIDE,
        )
        result = detect(
            changed_files=[ChangedFile(path="prompts/tools/x.md")],
            pr_body="zroky-blast-radius: tool_prompt",
            zroky_yaml="zroky-blast-radius: model_swap",
            operator_override=override,
        )
        assert result is override

    def test_yaml_beats_pr_body_beats_auto(self) -> None:
        result = detect(
            changed_files=[ChangedFile(path="prompts/tools/x.md")],
            pr_body="zroky-blast-radius: tool_prompt",
            zroky_yaml="zroky-blast-radius: system_prompt",
        )
        assert result.category == BlastRadiusCategory.SYSTEM_PROMPT
        assert result.source == BlastRadiusSource.DECLARED

    def test_pr_body_used_when_no_yaml(self) -> None:
        result = detect(
            changed_files=[ChangedFile(path="src/foo.py")],
            pr_body="zroky-blast-radius: model_params",
            zroky_yaml=None,
        )
        assert result.category == BlastRadiusCategory.MODEL_PARAMS
        assert result.source == BlastRadiusSource.DECLARED

    def test_auto_detect_when_nothing_declared(self) -> None:
        result = detect(
            changed_files=[ChangedFile(path="prompts/system.md")],
        )
        assert result.category == BlastRadiusCategory.SYSTEM_PROMPT
        assert result.source == BlastRadiusSource.AUTO_DETECTED

    def test_override_with_wrong_source_rejected(self) -> None:
        wrong = BlastRadius(
            category=BlastRadiusCategory.SYSTEM_PROMPT,
            source=BlastRadiusSource.AUTO_DETECTED,  # should be OVERRIDE
        )
        with pytest.raises(ValueError, match="must have source=OVERRIDE"):
            detect(
                changed_files=[],
                operator_override=wrong,
            )
