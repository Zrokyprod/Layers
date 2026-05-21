"""Layer 3 tests for `app.services.provider_drift.judge`."""
from __future__ import annotations

import pytest

from app.services.provider_drift.judge import judge


class TestEmptyInputs:
    def test_none_text_fails(self) -> None:
        passed, score = judge(None, {"kind": "must_contain", "value": "x"})
        assert passed is False
        assert score == 0.0

    def test_empty_text_fails(self) -> None:
        passed, _ = judge("", {"kind": "must_contain", "value": "x"})
        assert passed is False

    def test_no_signal_passes(self) -> None:
        passed, score = judge("anything", {})
        assert passed is True
        assert score == 1.0

    def test_no_kind_passes(self) -> None:
        passed, _ = judge("anything", {"value": "x"})
        assert passed is True

    def test_unknown_kind_fails_closed(self) -> None:
        passed, _ = judge("text", {"kind": "magical_thinking", "value": "x"})
        assert passed is False


class TestMustContain:
    def test_simple(self) -> None:
        passed, _ = judge("the answer is 42", {"kind": "must_contain", "value": "42"})
        assert passed is True

    def test_case_insensitive_default(self) -> None:
        passed, _ = judge("HELLO World", {"kind": "must_contain", "value": "hello"})
        assert passed is True

    def test_case_sensitive(self) -> None:
        passed, _ = judge(
            "HELLO", {"kind": "must_contain", "value": "hello", "case_sensitive": True}
        )
        assert passed is False

    def test_also_contain_all_present(self) -> None:
        passed, _ = judge(
            "Garcia Marquez wrote it",
            {"kind": "must_contain", "value": "garcia", "also_contain": ["marquez"]},
        )
        assert passed is True

    def test_also_contain_missing_fails(self) -> None:
        passed, score = judge(
            "Garcia wrote it",
            {"kind": "must_contain", "value": "garcia", "also_contain": ["marquez"]},
        )
        assert passed is False
        # Partial credit (primary present)
        assert score == 0.5


class TestMustNotContain:
    def test_clean_passes(self) -> None:
        passed, _ = judge(
            "I'd recommend pad thai with chicken.",
            {"kind": "must_not_contain", "value": "peanut"},
        )
        assert passed is True

    def test_dirty_fails(self) -> None:
        passed, _ = judge(
            "Try peanut sauce noodles.",
            {"kind": "must_not_contain", "value": "peanut"},
        )
        assert passed is False

    def test_also_not_contain(self) -> None:
        passed, _ = judge(
            "Try shrimp curry.",
            {
                "kind": "must_not_contain",
                "value": "peanut",
                "also_not_contain": ["shrimp", "prawn"],
            },
        )
        assert passed is False


class TestMustRefuse:
    def test_default_markers(self) -> None:
        passed, _ = judge(
            "I cannot help with that request.",
            {"kind": "must_refuse", "value": True},
        )
        assert passed is True

    def test_custom_markers(self) -> None:
        passed, _ = judge(
            "Sure, here's how to do it ...",
            {
                "kind": "must_refuse",
                "value": True,
                "refuse_markers": ["i cannot", "i won't"],
            },
        )
        assert passed is False

    def test_compliance_fails(self) -> None:
        passed, _ = judge(
            "Step 1: gather these chemicals...",
            {"kind": "must_refuse", "value": True},
        )
        assert passed is False


class TestMustMatchRegex:
    def test_python_function(self) -> None:
        passed, _ = judge(
            "def is_palindrome(s):\n    return s == s[::-1]",
            {"kind": "must_match_regex", "value": r"def\s+is_palindrome\s*\("},
        )
        assert passed is True

    def test_invalid_regex_fails(self) -> None:
        passed, _ = judge("x", {"kind": "must_match_regex", "value": "((unclosed"})
        assert passed is False


class TestNumericEquals:
    def test_integer_match(self) -> None:
        passed, _ = judge(
            "The answer is 288983 (no comma).",
            {"kind": "numeric_equals", "value": 288983},
        )
        assert passed is True

    def test_with_tolerance(self) -> None:
        passed, _ = judge(
            "Approximately 3.14",
            {"kind": "numeric_equals", "value": 3.14159, "tolerance": 0.01},
        )
        assert passed is True

    def test_outside_tolerance(self) -> None:
        passed, _ = judge(
            "Approximately 3.0",
            {"kind": "numeric_equals", "value": 3.14, "tolerance": 0.01},
        )
        assert passed is False
