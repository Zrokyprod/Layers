import re

from app.services.privacy import mask_payload, mask_text


def test_free_form_name_and_address_are_masked() -> None:
    text = "Customer name is John Smith and address is 123 Main Street, Springfield, IL 62704."

    masked = mask_text(text)

    assert "John Smith" not in masked
    assert "123 Main Street" not in masked
    assert "[REDACTED_NAME]" in masked
    assert "[REDACTED_ADDRESS]" in masked


def test_natural_language_secret_is_masked() -> None:
    masked = mask_text("The recovery code is alpha-beta-gamma-123.")

    assert "alpha-beta-gamma-123" not in masked
    assert "[REDACTED]" in masked


def test_custom_pattern_layer_masks_project_specific_terms() -> None:
    payload = {
        "message": "Escalate AcmeInternalCodename and tenant phrase VIP-MIGRATION-42",
    }

    masked = mask_payload(
        payload,
        custom_patterns=[r"AcmeInternalCodename", r"VIP-MIGRATION-\d+"],
    )

    rendered = str(masked)
    assert "AcmeInternalCodename" not in rendered
    assert "VIP-MIGRATION-42" not in rendered
    assert rendered.count("[REDACTED]") == 2


def test_uuid_is_preserved_while_adjacent_pii_is_masked() -> None:
    identifier = "12345678-1234-1234-1234-123456789012"

    masked = mask_text(f"run {identifier} belongs to user@example.com")

    assert identifier in masked
    assert "user@example.com" not in masked


def test_custom_pattern_can_explicitly_mask_uuid() -> None:
    identifier = "12345678-1234-1234-1234-123456789012"

    masked = mask_text(identifier, custom_patterns=[re.escape(identifier)])

    assert masked == "[REDACTED]"


def test_opaque_tokens_are_masked_without_hiding_usage_counts() -> None:
    masked = mask_payload(
        {
            "access_token": "opaque-access-value",
            "refresh_token": "opaque-refresh-value",
            "prompt_tokens": 42,
        }
    )

    assert masked["access_token"] == "[REDACTED_KEY]"
    assert masked["refresh_token"] == "[REDACTED_KEY]"
    assert masked["prompt_tokens"] == 42
