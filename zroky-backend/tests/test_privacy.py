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
