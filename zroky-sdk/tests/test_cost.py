# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Tests for cost calculation engine."""
import pytest

from zroky._internal.cost import calculate_cost


def test_basic_gpt4o_cost():
    result = calculate_cost(
        model="gpt-4o",
        prompt_tokens=1000,
        completion_tokens=500,
        status="success",
    )
    assert result["total_cost_usd"] > 0
    assert result["wasted_cost_usd"] == 0.0
    # input: 1000 * 2.50 / 1M = 0.0025
    assert abs(result["input_cost_usd"] - 0.0025) < 1e-6


def test_failed_call_marks_wasted():
    result = calculate_cost(
        model="gpt-4o",
        prompt_tokens=1000,
        completion_tokens=0,
        status="failed",
    )
    assert result["wasted_cost_usd"] == result["total_cost_usd"]
    assert result["wasted_cost_usd"] > 0


def test_reasoning_tokens_cost_o3():
    result = calculate_cost(
        model="o3",
        prompt_tokens=0,
        completion_tokens=0,
        reasoning_tokens=1000,
        status="success",
    )
    # reasoning: 1000 tokens * $60.00/1M tokens = 1000 * 60 / 1_000_000 = $0.06
    assert abs(result["reasoning_cost_usd"] - 0.06) < 1e-8


def test_cache_savings_anthropic():
    result = calculate_cost(
        model="claude-3-5-sonnet-20241022",
        prompt_tokens=0,
        completion_tokens=0,
        cache_read_tokens=1000,
        status="success",
    )
    # full input rate = 3.00, cache_read rate = 0.30
    # savings = 1000 * (3.00 - 0.30) / 1M = 0.0000027
    assert result["cache_savings_usd"] > 0


def test_zero_tokens_zero_cost():
    result = calculate_cost(
        model="gpt-4o",
        prompt_tokens=0,
        completion_tokens=0,
        status="success",
    )
    assert result["total_cost_usd"] == 0.0
    assert result["wasted_cost_usd"] == 0.0


def test_unknown_model_does_not_raise():
    result = calculate_cost(
        model="totally-unknown-model-xyz",
        prompt_tokens=1000,
        completion_tokens=500,
        status="success",
    )
    assert result["total_cost_usd"] == 0.0  # fallback rates are 0 for unknown


def test_prefix_match():
    """gpt-4o-2024-11-20 should match gpt-4o rates."""
    r1 = calculate_cost(model="gpt-4o", prompt_tokens=1000, completion_tokens=0, status="success")
    r2 = calculate_cost(model="gpt-4o-2024-11-20", prompt_tokens=1000, completion_tokens=0, status="success")
    assert r1["input_cost_usd"] == r2["input_cost_usd"]
