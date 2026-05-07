"""Tests for prompt fingerprint normalization and hashing behavior."""

from zroky._internal.prompt_fingerprint import (
    generate_prompt_fingerprint,
    normalize_messages,
    normalize_text,
    normalize_tools,
)


def test_same_prompt_with_different_numbers_produces_same_fingerprint() -> None:
    messages_a = [{"role": "user", "content": "Summarize report id 123 for 2026-04-25T10:11:12Z"}]
    messages_b = [{"role": "user", "content": "Summarize report id 999 for 2027-01-01T08:00:00Z"}]
    tools = [{"type": "function", "function": {"name": "search"}}]

    fp_a = generate_prompt_fingerprint(messages_a, tools, "gpt-4o")
    fp_b = generate_prompt_fingerprint(messages_b, tools, "gpt-4o")

    assert fp_a == fp_b
    assert len(fp_a) == 64


def test_same_prompt_with_extra_whitespace_produces_same_fingerprint() -> None:
    messages_a = [{"role": "user", "content": "summarize report id 123"}]
    messages_b = [{"role": "user", "content": "   summarize    report   id   123   "}]
    tools = [{"name": "search"}]

    fp_a = generate_prompt_fingerprint(messages_a, tools, "gpt-4o")
    fp_b = generate_prompt_fingerprint(messages_b, tools, "gpt-4o")

    assert fp_a == fp_b


def test_different_intent_produces_different_fingerprint() -> None:
    messages_a = [{"role": "user", "content": "summarize this report"}]
    messages_b = [{"role": "user", "content": "delete this report"}]

    fp_a = generate_prompt_fingerprint(messages_a, [{"name": "search"}], "gpt-4o")
    fp_b = generate_prompt_fingerprint(messages_b, [{"name": "search"}], "gpt-4o")

    assert fp_a != fp_b


def test_five_same_intent_variants_share_single_fingerprint() -> None:
    tools = [{"name": "search"}]
    prompts = [
        "report id 123 summarize",
        "report id 456 summarize",
        "report id 789 summarize",
        "report id 999 summarize",
        "report id 1001 summarize",
    ]

    fingerprints = {
        generate_prompt_fingerprint(
            [{"role": "user", "content": prompt}],
            tools,
            "gpt-4o",
        )
        for prompt in prompts
    }

    assert len(fingerprints) == 1


def test_normalize_helpers_cover_dynamic_values() -> None:
    normalized = normalize_text(
        "Order 999 at 2026-04-25T12:22:01Z with request id "
        "550e8400-e29b-41d4-a716-446655440000 and key sk-abc1234567890abcdef123456"
    )
    assert "<num>" in normalized
    assert "<time>" in normalized
    assert "<id>" in normalized
    assert "<secret>" in normalized

    messages = [
        {"role": "system", "content": "A"},
        {"role": "user", "content": "B"},
        {"role": "assistant", "content": "C"},
        {"role": "user", "content": "D"},
    ]
    normalized_messages = normalize_messages(messages)
    assert normalized_messages.startswith("user:b|assistant:c|user:d")

    normalized_tools = normalize_tools(
        [
            {"name": "search"},
            {"type": "function", "function": {"name": "calculator"}},
            {"name": "search"},
        ]
    )
    assert normalized_tools == "tools:calculator|search"
