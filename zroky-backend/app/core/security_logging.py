"""Security-focused logging utilities to prevent sensitive data exposure.

This module provides:
1. Sensitive data filters for logging
2. Safe exception handling
3. Httpx client configuration that prevents token logging
"""

from __future__ import annotations

import logging
import re
from typing import Any


# Patterns that might indicate sensitive data
# Order matters - more specific patterns should come before general ones
SENSITIVE_PATTERNS = [
    # Match OpenAI-style API keys (sk-xxx) - check before general token patterns
    (re.compile(r'sk-[a-zA-Z0-9]{20,}', re.IGNORECASE), '***OPENAI_KEY_REDACTED***'),
    # Match GitHub tokens (ghp_xxx, gho_xxx, etc.) - check before general token patterns
    (re.compile(r'gh[pousr]_[a-zA-Z0-9_]{10,}', re.IGNORECASE), '***GITHUB_TOKEN_REDACTED***'),
    # Match Authorization: Bearer <token> or authorization=<token>
    (re.compile(r'(authorization[\s]*:[\s]*(?:bearer|token|basic)[\s]+)([\w-]+)', re.IGNORECASE), r'\1***REDACTED***'),
    # Match token=<value> patterns
    (re.compile(r'((?:^|\s)(?:token|api_key|apikey|password|secret)[\s]*[=:][\s]*)([\w-]+)', re.IGNORECASE), r'\1***REDACTED***'),
    # Match general bearer tokens
    (re.compile(r'\bbearer\s+([\w-]+)', re.IGNORECASE), r'Bearer ***REDACTED***'),
]

# Headers that should never be logged
SENSITIVE_HEADERS = frozenset({
    'authorization',
    'x-api-key',
    'x-zroky-admin-token',
    'x-zroky-internal-token',
    'x-zroky-metrics-token',
    'cookie',
    'set-cookie',
    'proxy-authorization',
    'x-github-token',
    'x-token',
    'api-key',
    'x-api-key',
})


class SensitiveDataFilter(logging.Filter):
    """Logging filter that redacts sensitive data from log records."""

    def __init__(self, name: str = "") -> None:
        super().__init__(name)
        self._patterns = SENSITIVE_PATTERNS

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter and redact sensitive data from log record."""
        # Redact from message
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = self._redact(record.msg)

        # Redact from args
        if record.args:
            record.args = tuple(
                self._redict_sensitive_in_value(arg) for arg in record.args
            )

        # Redact from exception info
        if record.exc_info and record.exc_info[1]:
            exc_msg = str(record.exc_info[1])
            redacted_msg = self._redact(exc_msg)
            if exc_msg != redacted_msg:
                # Create new exception with redacted message
                exc_type = type(record.exc_info[1])
                try:
                    new_exc = exc_type(redacted_msg)
                    record.exc_info = (exc_type, new_exc, record.exc_info[2])
                except Exception:
                    pass

        # Redact from extra fields
        for attr in dir(record):
            if not attr.startswith('_') and attr not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                'filename', 'module', 'lineno', 'funcName', 'created', 'msecs',
                'relativeCreated', 'thread', 'threadName', 'processName',
                'process', 'exc_info', 'exc_text', 'stack_info', 'getMessage'
            }:
                value = getattr(record, attr, None)
                if isinstance(value, str):
                    try:
                        setattr(record, attr, self._redact(value))
                    except AttributeError:
                        pass

        return True

    def _redact(self, text: str) -> str:
        """Redact sensitive patterns from text."""
        for pattern, replacement in self._patterns:
            text = pattern.sub(replacement, text)
        return text

    def _redict_sensitive_in_value(self, value: Any) -> Any:
        """Recursively redact sensitive data from a value."""
        if isinstance(value, str):
            return self._redact(value)
        if isinstance(value, dict):
            return {
                k: (self._redict_sensitive_in_value(v) if k.lower() not in SENSITIVE_HEADERS else '***REDACTED***')
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            return type(value)(self._redict_sensitive_in_value(item) for item in value)
        return value


def install_sensitive_data_filters() -> None:
    """Install sensitive data filters on all relevant loggers."""
    filter_instance = SensitiveDataFilter()

    # Install on root logger
    root = logging.getLogger()
    root.addFilter(filter_instance)

    # Install on httpx loggers
    for logger_name in ['httpx', 'httpcore', 'httpx.client', 'httpcore.connection']:
        logger = logging.getLogger(logger_name)
        logger.addFilter(filter_instance)
        # Set httpx loggers to INFO level to prevent DEBUG logging of requests
        logger.setLevel(logging.INFO)

    # Install on urllib3 loggers
    for logger_name in ['urllib3', 'urllib3.connectionpool']:
        logger = logging.getLogger(logger_name)
        logger.addFilter(filter_instance)


def sanitize_exception(exc: Exception) -> Exception:
    """Create a new exception with sensitive data redacted from the message."""
    exc_str = str(exc)

    # Redact known sensitive patterns
    for pattern, replacement in SENSITIVE_PATTERNS:
        exc_str = pattern.sub(replacement, exc_str)

    # Create new exception of same type
    try:
        new_exc = type(exc)(exc_str)
        new_exc.__cause__ = exc.__cause__
        new_exc.__context__ = exc.__context__
        return new_exc
    except Exception:
        # If we can't create new exception, return original
        return exc


class SafeHttpxClient:
    """Wrapper for httpx client that ensures no sensitive data is logged."""

    @staticmethod
    def get_client(*args: Any, **kwargs: Any) -> Any:
        """Get configured httpx client with security settings."""
        import httpx

        # Ensure no event hooks that might log sensitive data
        kwargs.pop('event_hooks', None)

        # Create client with secure defaults
        client = httpx.Client(*args, **kwargs)

        return client

    @staticmethod
    def get_async_client(*args: Any, **kwargs: Any) -> Any:
        """Get configured async httpx client with security settings."""
        import httpx

        kwargs.pop('event_hooks', None)
        return httpx.AsyncClient(*args, **kwargs)
