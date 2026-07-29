from __future__ import annotations

from app.domain.connector_manifest.schema import ConnectorManifest, validate_connector_manifest


_PRESET_PAYLOADS = [
    {
        "manifest_id": "stripe_refund.v1",
        "connector_id": "stripe_refund",
        "primitive": "generic_rest",
        "source_binding": "stripe_refund",
        "connector_capability": "refund.read",
        "auth": {"type": "bearer", "credential_ref": "vault://connectors/stripe/refund-read", "allowed_scopes": ["refunds.read"]},
        "read": {"method": "GET", "base_url": "https://api.stripe.com", "path_template": "/v1/refunds/{record_ref}"},
        "test_read": {"object_ref": "re_test"},
        "object_schema": {"id": "string", "status": "string", "amount": "integer"},
        "correlation": {"claim_field": "refund_id", "source_field": "id"},
        "expected_effect_mapping": {"refund.status": "status", "refund.amount": "amount"},
        "evidence_template_id": "stripe_refund_evidence.v1",
    },
    {
        "manifest_id": "github_ci.v1",
        "connector_id": "github_ci",
        "primitive": "generic_rest",
        "source_binding": "github",
        "connector_capability": "check_run.read",
        "auth": {"type": "oauth", "credential_ref": "vault://connectors/github/app-installation", "allowed_scopes": ["checks.read", "deployments.read", "pull_requests.read"]},
        "read": {
            "method": "GET",
            "base_url": "https://api.github.com",
            "path_template": "/repos/{owner}/{repo}/commits/{record_ref}/check-runs",
            "path_value_keys": ["owner", "repo"],
        },
        "test_read": {"object_ref": "HEAD"},
        "object_schema": {"total_count": "integer", "check_runs": "array"},
        "correlation": {"claim_field": "commit_sha", "source_field": "check_runs.head_sha"},
        "expected_effect_mapping": {"github.check_conclusion": "check_runs.conclusion"},
        "evidence_template_id": "github_ci_evidence.v1",
    },
    {
        "manifest_id": "jira_issue.v1",
        "connector_id": "jira_issue",
        "primitive": "generic_rest",
        "source_binding": "jira",
        "connector_capability": "issue.read",
        "auth": {"type": "oauth", "credential_ref": "vault://connectors/jira/read", "allowed_scopes": ["read:jira-work"]},
        "read": {"method": "GET", "base_url": "https://tenant.atlassian.net", "path_template": "/rest/api/3/issue/{record_ref}"},
        "test_read": {"object_ref": "DEMO-1"},
        "object_schema": {"key": "string", "fields": "object"},
        "correlation": {"claim_field": "issue_key", "source_field": "key"},
        "expected_effect_mapping": {"ticket.status": "fields.status.name"},
        "evidence_template_id": "jira_issue_evidence.v1",
    },
    {
        "manifest_id": "servicenow_change.v1",
        "connector_id": "servicenow_change",
        "primitive": "generic_rest",
        "source_binding": "servicenow",
        "connector_capability": "change.read",
        "auth": {"type": "oauth", "credential_ref": "vault://connectors/servicenow/read", "allowed_scopes": ["change_request.read", "incident.read"]},
        "read": {"method": "GET", "base_url": "https://tenant.service-now.com", "path_template": "/api/now/table/change_request/{record_ref}", "record_path": "result"},
        "test_read": {"object_ref": "sys_id"},
        "object_schema": {"sys_id": "string", "state": "string"},
        "correlation": {"claim_field": "change_sys_id", "source_field": "sys_id"},
        "expected_effect_mapping": {"change.state": "state"},
        "evidence_template_id": "servicenow_change_evidence.v1",
    },
    {
        "manifest_id": "salesforce_crm.v1",
        "connector_id": "salesforce_crm",
        "primitive": "generic_rest",
        "source_binding": "salesforce",
        "connector_capability": "sobject.read",
        "auth": {"type": "oauth", "credential_ref": "vault://connectors/salesforce/read", "allowed_scopes": ["api.read"]},
        "read": {
            "method": "GET",
            "base_url": "https://tenant.my.salesforce.com",
            "path_template": "/services/data/v61.0/sobjects/{object_type}/{record_ref}",
            "path_value_keys": ["object_type"],
        },
        "test_read": {"object_ref": "001000000000000AAA"},
        "object_schema": {"Id": "string", "LastModifiedDate": "string"},
        "correlation": {"claim_field": "record_id", "source_field": "Id"},
        "expected_effect_mapping": {"crm.updated_at": "LastModifiedDate"},
        "evidence_template_id": "salesforce_crm_evidence.v1",
    },
    {
        "manifest_id": "hubspot_crm.v1",
        "connector_id": "hubspot_crm",
        "primitive": "generic_rest",
        "source_binding": "hubspot",
        "connector_capability": "contact.read",
        "auth": {"type": "bearer", "credential_ref": "vault://connectors/hubspot/read", "allowed_scopes": ["crm.objects.contacts.read"]},
        "read": {"method": "GET", "base_url": "https://api.hubapi.com", "path_template": "/crm/v3/objects/contacts/{record_ref}"},
        "test_read": {"object_ref": "1"},
        "object_schema": {"id": "string", "properties": "object"},
        "correlation": {"claim_field": "contact_id", "source_field": "id"},
        "expected_effect_mapping": {"crm.updated_at": "updatedAt"},
        "evidence_template_id": "hubspot_crm_evidence.v1",
    },
    {
        "manifest_id": "zendesk_ticket.v1",
        "connector_id": "zendesk_ticket",
        "primitive": "generic_rest",
        "source_binding": "zendesk",
        "connector_capability": "ticket.read",
        "auth": {"type": "bearer", "credential_ref": "vault://connectors/zendesk/read", "allowed_scopes": ["tickets.read"]},
        "read": {"method": "GET", "base_url": "https://tenant.zendesk.com", "path_template": "/api/v2/tickets/{record_ref}.json", "record_path": "ticket"},
        "test_read": {"object_ref": "1"},
        "object_schema": {"id": "integer", "status": "string"},
        "correlation": {"claim_field": "ticket_id", "source_field": "id"},
        "expected_effect_mapping": {"ticket.status": "status"},
        "evidence_template_id": "zendesk_ticket_evidence.v1",
    },
    {
        "manifest_id": "shopify_admin.v1",
        "connector_id": "shopify_admin",
        "primitive": "generic_rest",
        "source_binding": "shopify",
        "connector_capability": "order.read",
        "auth": {"type": "bearer", "credential_ref": "vault://connectors/shopify/read", "allowed_scopes": ["read_orders", "read_inventory"]},
        "read": {"method": "GET", "base_url": "https://tenant.myshopify.com", "path_template": "/admin/api/2026-01/orders/{record_ref}.json", "record_path": "order"},
        "test_read": {"object_ref": "1"},
        "object_schema": {"id": "integer", "financial_status": "string", "fulfillment_status": "string"},
        "correlation": {"claim_field": "order_id", "source_field": "id"},
        "expected_effect_mapping": {"order.financial_status": "financial_status", "order.fulfillment_status": "fulfillment_status"},
        "evidence_template_id": "shopify_order_evidence.v1",
    },
]

CONNECTOR_MANIFEST_PRESETS: tuple[ConnectorManifest, ...] = tuple(
    validate_connector_manifest(payload) for payload in _PRESET_PAYLOADS
)


def get_connector_manifest_preset(manifest_id: str) -> ConnectorManifest | None:
    for preset in CONNECTOR_MANIFEST_PRESETS:
        if preset.manifest_id == manifest_id:
            return preset
    return None
