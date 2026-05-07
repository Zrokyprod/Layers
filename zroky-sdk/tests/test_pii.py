"""Tests for PII masking."""
from zroky._internal.pii import (
    hash_identifier,
    mask_error_message,
    mask_messages,
    mask_text,
    mask_value,
)


def test_masks_email():
    result = mask_text("Contact me at user@example.com please")
    assert "[REDACTED_EMAIL]" in result
    assert "user@example.com" not in result


def test_masks_phone():
    result = mask_text("Call 555-867-5309 for help")
    assert "[REDACTED_PHONE]" in result
    assert "555-867-5309" not in result


def test_masks_openai_key():
    result = mask_text("key=sk-proj-abcdefghijklmnopqrstuvwxyz1234567890")
    assert "[REDACTED_KEY]" in result


def test_masks_anthropic_key():
    result = mask_text("Here is sk-ant-api03-supersecretlongkeyvalue123456789")
    assert "[REDACTED_KEY]" in result


def test_preserves_clean_text():
    clean = "Hello, world. How are you?"
    assert mask_text(clean) == clean


def test_mask_messages_string_content():
    messages = [
        {"role": "user", "content": "My email is user@test.com"},
        {"role": "assistant", "content": "I cannot share that."},
    ]
    masked = mask_messages(messages)
    assert "[REDACTED_EMAIL]" in masked[0]["content"]
    assert masked[1]["content"] == "I cannot share that."


def test_mask_messages_does_not_mutate_original():
    messages = [{"role": "user", "content": "email@test.com"}]
    masked = mask_messages(messages)
    assert messages[0]["content"] == "email@test.com"
    assert "[REDACTED_EMAIL]" in masked[0]["content"]


def test_mask_messages_multipart_content():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "My phone is 555-123-4567"},
                {"type": "image_url", "image_url": {"url": "http://example.com/img.png"}},
            ],
        }
    ]
    masked = mask_messages(messages)
    text_part = masked[0]["content"][0]
    assert "[REDACTED_PHONE]" in text_part["text"]
    assert masked[0]["content"][1]["type"] == "image_url"


def test_mask_value_recurses_nested_tool_arguments():
    value = {
        "arguments": {
            "email": "nested@example.com",
            "api_key": "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890",
        }
    }

    masked = mask_value(value)

    rendered = str(masked)
    assert "nested@example.com" not in rendered
    assert "sk-proj-" not in rendered
    assert "[REDACTED_EMAIL]" in rendered
    assert "[REDACTED_KEY]" in rendered


def test_masks_base64_payloads():
    payload = "a" * 120
    assert mask_text(payload) == "[REDACTED]"


def test_masks_provider_error_message():
    masked = mask_error_message(
        "provider failed for user@example.com with key sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"
    )
    assert "user@example.com" not in masked
    assert "sk-proj-" not in masked
    assert "[REDACTED_EMAIL]" in masked
    assert "[REDACTED_KEY]" in masked


def test_hash_identifier_is_deterministic_and_irreversible():
    first = hash_identifier("customer-123")
    second = hash_identifier("customer-123")

    assert first == second
    assert first is not None
    assert first.startswith("hash:")
    assert "customer-123" not in first


def test_masks_free_form_name_address_and_secret():
    text = (
        "Customer name is John Smith. Ship to 123 Main Street, Springfield, IL 62704. "
        "The recovery code is alpha-beta-gamma-123."
    )

    masked = mask_text(text)

    assert "John Smith" not in masked
    assert "123 Main Street" not in masked
    assert "alpha-beta-gamma-123" not in masked
    assert "[REDACTED_NAME]" in masked
    assert "[REDACTED_ADDRESS]" in masked
    assert "[REDACTED]" in masked
