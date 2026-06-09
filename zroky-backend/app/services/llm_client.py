"""Unified LLM client with OpenRouter and automatic DeepSeek V4 -> V3 fallback."""

from __future__ import annotations

import logging
from typing import Any

from openai import APIError, APITimeoutError, OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    """OpenRouter client with primary/fallback model switching.

    Primary:  deepseek/deepseek-chat   (DeepSeek V4)
    Fallback: deepseek/deepseek-chat-v3 (DeepSeek V3)

    If the primary model fails with APIError, APITimeoutError, or rate-limit
    errors, the client automatically retries once with the fallback model.
    """

    def __init__(self) -> None:
        settings = get_settings()
        api_key = settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY
        if not api_key:
            raise RuntimeError(
                "Missing API key: set OPENROUTER_API_KEY or OPENAI_API_KEY"
            )

        self.client = OpenAI(
            base_url=_OPENROUTER_BASE_URL,
            api_key=api_key,
            default_headers={
                "HTTP-Referer": settings.FRONTEND_URL or "https://zroky.com",
                "X-Title": settings.APP_NAME or "Zroky AI",
            },
        )
        self.primary_model = settings.OPENROUTER_PRIMARY_MODEL
        self.fallback_model = settings.OPENROUTER_FALLBACK_MODEL
        self.timeout = settings.OPENROUTER_REQUEST_TIMEOUT_SECONDS

    def _is_retryable(self, exc: Exception) -> bool:
        """Return True if the exception warrants a fallback attempt."""
        if isinstance(exc, (APIError, APITimeoutError)):
            return True
        if hasattr(exc, "status_code"):
            code = getattr(exc, "status_code", 0)
            return code in {429, 500, 502, 503, 504}
        return False

    def _call_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> Any:
        """Single chat-completion call (no retry)."""
        kwargs.setdefault("timeout", self.timeout)
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs,
        )

    def chat_completions_create(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Create a chat completion, falling back to V3 on failure.

        Parameters
        ----------
        messages: list of dicts with "role" and "content" keys.
        model: optional model override. When set, this exact model is used
            with no automatic fallback (caller has made a deliberate choice).
        **kwargs: forwarded to ``openai.chat.completions.create``
            (temperature, max_tokens, tools, stream, etc.).

        Returns
        -------
        openai.ChatCompletion or streaming iterator.
        """
        # ── Explicit model override — use directly, no fallback ──
        if model is not None:
            logger.debug("LLM request  model=%s (explicit override)", model)
            return self._call_chat(model, messages, **kwargs)

        # ── Try primary model ────────────────────────────────
        try:
            logger.debug(
                "LLM request  primary=%s fallback=%s",
                self.primary_model,
                self.fallback_model,
            )
            return self._call_chat(self.primary_model, messages, **kwargs)
        except Exception as exc:
            if not self._is_retryable(exc):
                raise
            logger.warning(
                "Primary model %s failed (%s: %s); trying fallback %s",
                self.primary_model,
                type(exc).__name__,
                exc,
                self.fallback_model,
            )

        # ── Try fallback model ─────────────────────────────────
        try:
            return self._call_chat(self.fallback_model, messages, **kwargs)
        except Exception as exc2:
            logger.error(
                "Fallback model %s also failed (%s: %s)",
                self.fallback_model,
                type(exc2).__name__,
                exc2,
            )
            raise


# Convenience singleton for simple imports
_openrouter_client: OpenRouterClient | None = None


def get_llm_client() -> OpenRouterClient:
    """Return a cached OpenRouterClient instance."""
    global _openrouter_client
    if _openrouter_client is None:
        _openrouter_client = OpenRouterClient()
    return _openrouter_client
