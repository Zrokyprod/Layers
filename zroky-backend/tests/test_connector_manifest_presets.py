from __future__ import annotations

import httpx

from app.domain.connector_manifest import (
    CONNECTOR_MANIFEST_PRESETS,
    execute_connector_manifest_read,
    get_connector_manifest_preset,
)
from app.infrastructure.relay_protocol import RelayReadCommandRequest, prepare_read_command
from app.services._tool_registry_verification import VERIFICATION_CONNECTORS


BRANDED_PRESET_IDS = {
    "stripe_refund.v1",
    "github_ci.v1",
    "jira_issue.v1",
    "servicenow_change.v1",
    "salesforce_crm.v1",
    "hubspot_crm.v1",
    "zendesk_ticket.v1",
    "shopify_admin.v1",
}


def test_branded_connector_presets_are_manifest_data() -> None:
    presets = {preset.manifest_id: preset for preset in CONNECTOR_MANIFEST_PRESETS}

    assert BRANDED_PRESET_IDS.issubset(presets)
    for preset_id in BRANDED_PRESET_IDS:
        preset = presets[preset_id]
        assert preset.primitive == "generic_rest"
        assert preset.read.method == "GET"
        assert preset.read.base_url
        assert preset.read.path_template
        assert preset.correlation.claim_field
        assert preset.freshness.max_age_seconds <= 86_400
        assert preset.expected_effect_mapping
        assert preset.evidence_template_id.endswith(".v1")


def test_verification_registry_manifest_ids_resolve_to_presets_for_branded_connectors() -> None:
    registry_manifest_ids = {item.manifest_id for item in VERIFICATION_CONNECTORS if item.manifest_id}

    assert BRANDED_PRESET_IDS.issubset(registry_manifest_ids)
    for manifest_id in BRANDED_PRESET_IDS:
        assert get_connector_manifest_preset(manifest_id) is not None


def test_github_preset_uses_manifest_declared_path_values_only() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"total_count": 1, "check_runs": [{"head_sha": "abc", "conclusion": "success"}]})

    preset = get_connector_manifest_preset("github_ci.v1")
    assert preset is not None
    command = prepare_read_command(
        "proj_1",
        RelayReadCommandRequest(
            source_binding="github",
            connector_capability="check_run.read",
            object_ref="abc",
            selector={
                "record_ref": "abc",
                "owner": "acme",
                "repo": "refund-agent",
                "ignored": "../secret",
            },
        ),
    )

    source = execute_connector_manifest_read(command, preset, bearer_token="secret-token", transport=httpx.MockTransport(handler))

    assert str(requests[0].url) == "https://api.github.com/repos/acme/refund-agent/commits/abc/check-runs"
    assert source.record is not None
    assert source.record["check_runs"][0]["conclusion"] == "success"
    assert "ignored" not in str(requests[0].url)
