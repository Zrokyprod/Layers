"""Self-observability for ZROKY's own LLM usage.

Tracks every LLM call made by the platform (fix generation, assistant, analytics,
error parsing, embeddings) into the ``platform_llm_usage`` table so operators can
monitor platform spend, latency, and token volume independently from tenant data.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import PlatformLlmUsage

logger = logging.getLogger(__name__)


def extract_usage(response: Any) -> dict[str, Any]:
    """Extract token usage and model from an OpenAI-style completion response."""
    result: dict[str, Any] = {
        "model": None,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    if hasattr(response, "model"):
        result["model"] = response.model
    if hasattr(response, "usage") and response.usage:
        usage = response.usage
        if hasattr(usage, "prompt_tokens"):
            result["prompt_tokens"] = usage.prompt_tokens or 0
        if hasattr(usage, "completion_tokens"):
            result["completion_tokens"] = usage.completion_tokens or 0
        if hasattr(usage, "total_tokens"):
            result["total_tokens"] = usage.total_tokens or 0
    return result


def estimate_cost_usd(
    *,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Return a rough cost estimate in USD based on known per-token rates.

    This is intentionally conservative and over-estimates slightly so
    dashboard numbers are never under-reported.
    """
    if model is None:
        return 0.0

    model_lower = model.lower()
    # DeepSeek via OpenRouter (approximate market rates)
    if "deepseek-chat-v3" in model_lower or "deepseek-chat" in model_lower:
        # ~$0.14 / 1M input tokens, ~$0.28 / 1M output tokens
        return (prompt_tokens * 0.14 + completion_tokens * 0.28) / 1_000_000
    if "deepseek" in model_lower:
        return (prompt_tokens * 0.14 + completion_tokens * 0.28) / 1_000_000
    # OpenAI GPT-4o
    if "gpt-4o" in model_lower and "mini" not in model_lower:
        return (prompt_tokens * 2.50 + completion_tokens * 10.00) / 1_000_000
    if "gpt-4o-mini" in model_lower:
        return (prompt_tokens * 0.15 + completion_tokens * 0.60) / 1_000_000
    # Anthropic Claude 3
    if "claude-3-opus" in model_lower:
        return (prompt_tokens * 15.00 + completion_tokens * 75.00) / 1_000_000
    if "claude-3-sonnet" in model_lower:
        return (prompt_tokens * 3.00 + completion_tokens * 15.00) / 1_000_000
    if "claude-3-haiku" in model_lower:
        return (prompt_tokens * 0.25 + completion_tokens * 1.25) / 1_000_000
    # Embeddings
    if "embedding" in model_lower:
        return (prompt_tokens * 0.02) / 1_000_000
    # Fallback: cheap default
    return (prompt_tokens * 0.50 + completion_tokens * 1.50) / 1_000_000


def tracked_chat_completion(
    db: Session,
    *,
    purpose: str,
    messages: list[dict[str, Any]],
    tenant_id: str | None = None,
    diagnosis_id: str | None = None,
    provider: str = "openrouter",
    **kwargs: Any,
) -> Any:
    """Call the LLM client, time the request, and record usage automatically.

    Parameters match ``OpenRouterClient.chat_completions_create`` plus
    ``purpose``, ``tenant_id``, and ``diagnosis_id`` for observability.
    """
    from app.services.llm_client import get_llm_client

    client = get_llm_client()
    start = datetime.now(timezone.utc)
    response = None
    try:
        response = client.chat_completions_create(messages=messages, **kwargs)
    finally:
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000.0
        record_platform_llm_call(
            db,
            purpose=purpose,
            response=response,
            latency_ms=latency_ms,
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
            provider=provider,
            request_messages=messages,
        )
    return response


def record_platform_llm_call(
    db: Session,
    *,
    purpose: str,
    response: Any,
    latency_ms: float,
    tenant_id: str | None = None,
    diagnosis_id: str | None = None,
    provider: str = "openrouter",
    request_messages: list[dict[str, Any]] | None = None,
) -> PlatformLlmUsage | None:
    """Record a platform LLM call into ``platform_llm_usage``.

    Safe to call even if ``response`` is malformed — failures are logged, not raised.
    """
    try:
        usage = extract_usage(response)
        model = usage.get("model") or "unknown"
        prompt_tokens: int = usage.get("prompt_tokens", 0) or 0
        completion_tokens: int = usage.get("completion_tokens", 0) or 0
        total_tokens: int = usage.get("total_tokens", 0) or 0

        cost_usd = estimate_cost_usd(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        record = PlatformLlmUsage(
            purpose=purpose,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            request_json=json.dumps({"messages": request_messages}, default=str) if request_messages else None,
            response_json=json.dumps({"model": model, "usage": usage}, default=str),
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
        )
        db.add(record)
        db.commit()
        return record
    except Exception:
        logger.exception("Failed to record platform LLM usage for purpose=%s", purpose)
        # Do not re-raise: observability must never break the product path.
        return None
