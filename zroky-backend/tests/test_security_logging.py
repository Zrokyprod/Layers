"""Tests for security logging and sensitive data redaction."""

import logging

import pytest

from app.core.security_logging import (
    SensitiveDataFilter,
    sanitize_exception,
)


class TestSensitiveDataFilter:
    """Tests for sensitive data filter."""

    def test_redacts_github_token_pattern(self, caplog):
        """Test that GitHub tokens are redacted from logs."""
        filter_instance = SensitiveDataFilter()
        
        with caplog.at_level(logging.INFO):
            logger = logging.getLogger("test_github")
            logger.addFilter(filter_instance)
            logger.info("Token value: ghp_1234567890abcdef")
        
        assert "***GITHUB_TOKEN_REDACTED***" in caplog.text
        assert "ghp_1234567890abcdef" not in caplog.text

    def test_redacts_authorization_header(self, caplog):
        """Test that authorization headers are redacted."""
        filter_instance = SensitiveDataFilter()
        
        with caplog.at_level(logging.INFO):
            logger = logging.getLogger("test_auth")
            logger.addFilter(filter_instance)
            logger.info("Header: Authorization: Bearer secret_token_123")
        
        assert "***REDACTED***" in caplog.text
        assert "secret_token_123" not in caplog.text

    def test_redacts_api_key(self, caplog):
        """Test that API keys are redacted."""
        filter_instance = SensitiveDataFilter()
        
        with caplog.at_level(logging.INFO):
            logger = logging.getLogger("test_api_key")
            logger.addFilter(filter_instance)
            logger.info("api_key=sk-abcdefghijklmnopqrstuvwxyz123456")
        
        assert "***OPENAI_KEY_REDACTED***" in caplog.text
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in caplog.text

    def test_preserves_safe_messages(self, caplog):
        """Test that safe messages are not modified."""
        filter_instance = SensitiveDataFilter()
        
        with caplog.at_level(logging.INFO):
            logger = logging.getLogger("test_safe")
            logger.addFilter(filter_instance)
            logger.info("This is a safe message with no sensitive data")
        
        assert "This is a safe message with no sensitive data" in caplog.text


class TestSanitizeException:
    """Tests for exception sanitization."""

    def test_sanitizes_github_token_in_exception(self):
        """Test that GitHub tokens are redacted from exception messages."""
        exc = Exception("Failed with token ghp_1234567890abcdef")
        sanitized = sanitize_exception(exc)
        
        assert "***GITHUB_TOKEN_REDACTED***" in str(sanitized)
        assert "ghp_1234567890abcdef" not in str(sanitized)

    def test_sanitizes_api_key_in_exception(self):
        """Test that API keys are redacted from exception messages."""
        exc = Exception("Invalid API key: sk-abcdefghijklmnopqrstuvwxyz123456")
        sanitized = sanitize_exception(exc)
        
        assert "***OPENAI_KEY_REDACTED***" in str(sanitized)
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in str(sanitized)

    def test_preserves_safe_exception_messages(self):
        """Test that safe exception messages are not modified."""
        exc = Exception("File not found: /path/to/file")
        sanitized = sanitize_exception(exc)
        
        assert str(sanitized) == "File not found: /path/to/file"

    def test_handles_empty_exception(self):
        """Test that empty exceptions are handled gracefully."""
        exc = Exception()
        sanitized = sanitize_exception(exc)
        
        assert sanitized is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
