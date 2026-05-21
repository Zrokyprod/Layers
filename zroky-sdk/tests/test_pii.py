# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

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


# ── India-specific PII patterns ──────────────────────────────────────────────
# DPDP Act / Aadhaar Act compliance — these identifiers must never leave the
# SDK boundary in plaintext.


def test_masks_aadhaar_with_space_separators():
    masked = mask_text("Aadhaar number on file: 1234 5678 9012")
    assert "1234 5678 9012" not in masked
    assert "[REDACTED_AADHAAR]" in masked


def test_masks_aadhaar_with_hyphen_separators():
    masked = mask_text("UID: 1234-5678-9012 verified.")
    assert "1234-5678-9012" not in masked
    assert "[REDACTED_AADHAAR]" in masked


def test_masks_unformatted_aadhaar_when_context_label_present():
    masked = mask_text("aadhaar 123456789012 on the file")
    assert "123456789012" not in masked
    assert "[REDACTED_AADHAAR]" in masked


def test_does_not_mask_unformatted_12_digit_run_without_aadhaar_context():
    # Plain 12-digit timestamps / IDs must not be over-redacted.
    masked = mask_text("transaction id 123456789012 logged at server")
    assert "123456789012" in masked


def test_masks_pan_number():
    masked = mask_text("My PAN is ABCDE1234F for tax filing.")
    assert "ABCDE1234F" not in masked
    assert "[REDACTED_PAN]" in masked


def test_masks_pan_number_lowercase():
    masked = mask_text("pan abcde1234f noted.")
    assert "abcde1234f" not in masked
    assert "[REDACTED_PAN]" in masked


def test_masks_gstin_number():
    masked = mask_text("Vendor GSTIN: 27AAPFU0939F1ZV — invoice #123")
    assert "27AAPFU0939F1ZV" not in masked
    assert "[REDACTED_GSTIN]" in masked


def test_masks_ifsc_code():
    masked = mask_text("Branch routing IFSC HDFC0001234 confirmed.")
    assert "HDFC0001234" not in masked
    assert "[REDACTED_IFSC]" in masked


def test_masks_indian_phone_with_plus_91_prefix():
    masked = mask_text("Call me on +91 9876543210 anytime.")
    assert "9876543210" not in masked
    assert "[REDACTED_PHONE]" in masked


def test_masks_indian_phone_with_91_dash_prefix():
    masked = mask_text("Helpdesk: +91-9876543210 (24x7)")
    assert "9876543210" not in masked
    assert "[REDACTED_PHONE]" in masked


def test_masks_bare_indian_mobile_via_generic_phone_regex():
    # Bare 10-digit Indian mobile gets caught by the generic US-style phone
    # regex (10 digits in 3-3-4 grouping) — same redaction outcome.
    masked = mask_text("Reach 9876543210 for support.")
    assert "9876543210" not in masked
    assert "[REDACTED_PHONE]" in masked


def test_india_patterns_compose_in_a_single_message():
    text = (
        "Customer Aadhaar 1234 5678 9012, PAN ABCDE1234F, "
        "GSTIN 27AAPFU0939F1ZV, paid into HDFC0001234 from +919876543210."
    )
    masked = mask_text(text)

    for raw in ("1234 5678 9012", "ABCDE1234F", "27AAPFU0939F1ZV", "HDFC0001234", "9876543210"):
        assert raw not in masked
    assert "[REDACTED_AADHAAR]" in masked
    assert "[REDACTED_PAN]" in masked
    assert "[REDACTED_GSTIN]" in masked
    assert "[REDACTED_IFSC]" in masked
    assert "[REDACTED_PHONE]" in masked
