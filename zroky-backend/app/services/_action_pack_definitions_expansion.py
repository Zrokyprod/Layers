from __future__ import annotations

from app.services._action_pack_types import ActionContractTemplate, ActionPackDefinition


FINANCE_OPS_PACK = ActionPackDefinition(
    id="finance-ops-v1",
    display_name="Finance operations",
    summary=(
        "Guard invoice approvals, journal entries, and vendor payouts with "
        "approval, source-of-record verification, and audit-grade evidence."
    ),
    primary_runtime_path="sdk",
    recommended_connectors=("erp_finance", "accounting_system", "payments_ledger", "slack_approval_alert"),
    native_tool_families=("netsuite_finance", "stripe_payment", "quickbooks_ledger", "generic_finance"),
    quickstart_steps=(
        "Install finance-ops-v1 for the tenant.",
        "Configure NetSuite, ledger, or payment source-of-record connector.",
        "Call protect() before invoice approval, journal entry, or vendor payout.",
        "Verify finance record state and payment reference before closing evidence.",
    ),
    contract_templates=(
        ActionContractTemplate(
            contract_key="finance.invoice.approve",
            version="1.0",
            action_type="invoice_approve",
            operation_kind="UPDATE",
            domain_family="finance_operations",
            risk_class="R3",
            connector_family="erp_finance",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["invoice_id"],
                        "properties": {
                            "invoice_id": {"type": "string", "minLength": 1},
                            "vendor_id": {"type": "string"},
                            "po_number": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["amount_minor", "currency"],
                        "properties": {
                            "amount_minor": {"type": "integer", "minimum": 1},
                            "currency": {"type": "string", "minLength": 3, "maxLength": 3},
                            "approval_note": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V4",
                "source_of_record": "erp_finance",
                "positive_assertions": [
                    "equals(invoice_id)",
                    "equals(amount_minor)",
                    "equals(currency)",
                    "one_of(status, approved, scheduled, paid)",
                ],
                "approval_policy": "dashboard_or_slack_required_for_r3",
            },
        ),
        ActionContractTemplate(
            contract_key="finance.journal.entry",
            version="1.0",
            action_type="journal_entry",
            operation_kind="UPDATE",
            domain_family="finance_operations",
            risk_class="R3",
            connector_family="accounting_system",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["account_code"],
                        "properties": {
                            "account_code": {"type": "string", "minLength": 1},
                            "entity": {"type": "string"},
                            "period": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["amount_minor", "currency", "direction"],
                        "properties": {
                            "amount_minor": {"type": "integer", "minimum": 1},
                            "currency": {"type": "string", "minLength": 3, "maxLength": 3},
                            "direction": {"type": "string", "enum": ["debit", "credit"]},
                            "memo": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V3",
                "source_of_record": "accounting_system",
                "positive_assertions": [
                    "equals(account_code)",
                    "equals(amount_minor)",
                    "equals(direction)",
                    "record_updated_after(action_created_at)",
                ],
                "approval_policy": "dashboard_required_when_period_closed",
            },
        ),
        ActionContractTemplate(
            contract_key="finance.vendor.payout",
            version="1.0",
            action_type="vendor_payout",
            operation_kind="TRANSFER",
            domain_family="finance_operations",
            risk_class="R4",
            connector_family="payments_ledger",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["vendor_id"],
                        "properties": {
                            "vendor_id": {"type": "string", "minLength": 1},
                            "invoice_id": {"type": "string"},
                            "bank_ref": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["amount_minor", "currency"],
                        "properties": {
                            "amount_minor": {"type": "integer", "minimum": 1},
                            "currency": {"type": "string", "minLength": 3, "maxLength": 3},
                            "reference": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V4",
                "source_of_record": "payments_ledger",
                "positive_assertions": [
                    "equals(vendor_id)",
                    "equals(amount_minor)",
                    "equals(currency)",
                    "one_of(status, paid, settled, sent)",
                ],
                "approval_policy": "dashboard_or_slack_required_for_r4",
            },
        ),
    ),
)


OUTREACH_OPS_PACK = ActionPackDefinition(
    id="outreach-ops-v1",
    display_name="Outreach operations",
    summary=(
        "Guard customer emails, sequence enrollment, and campaign sends with "
        "approval, delivery verification, and audit-grade evidence."
    ),
    primary_runtime_path="sdk",
    recommended_connectors=("email_delivery", "sales_engagement", "campaign_platform", "slack_approval_alert"),
    native_tool_families=("sendgrid_email", "salesforce_engagement", "generic_outreach"),
    quickstart_steps=(
        "Install outreach-ops-v1 for the tenant.",
        "Configure email delivery or sales-engagement source-of-record connector.",
        "Call protect() before email send, sequence enrollment, or campaign launch.",
        "Verify recipient, campaign, and delivery state before evidence publish.",
    ),
    contract_templates=(
        ActionContractTemplate(
            contract_key="outreach.email.send",
            version="1.0",
            action_type="email_send",
            operation_kind="SEND",
            domain_family="outreach_operations",
            risk_class="R2",
            connector_family="email_delivery",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["recipient"],
                        "properties": {
                            "recipient": {"type": "string", "minLength": 3},
                            "contact_id": {"type": "string"},
                            "thread_id": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["subject", "body"],
                        "properties": {
                            "subject": {"type": "string", "minLength": 1},
                            "body": {"type": "string", "minLength": 1},
                            "template_id": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V3",
                "source_of_record": "email_delivery",
                "positive_assertions": [
                    "equals(recipient)",
                    "one_of(status, sent, delivered, queued)",
                    "recipient_unchanged_after_intent",
                ],
                "approval_policy": "dashboard_required_when_recipient_external",
            },
        ),
        ActionContractTemplate(
            contract_key="outreach.sequence.enroll",
            version="1.0",
            action_type="sequence_enroll",
            operation_kind="UPDATE",
            domain_family="outreach_operations",
            risk_class="R2",
            connector_family="sales_engagement",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["contact_id"],
                        "properties": {
                            "contact_id": {"type": "string", "minLength": 1},
                            "account_id": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["sequence_id"],
                        "properties": {
                            "sequence_id": {"type": "string", "minLength": 1},
                            "reason": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V3",
                "source_of_record": "sales_engagement",
                "positive_assertions": [
                    "equals(contact_id)",
                    "equals(sequence_id)",
                    "record_updated_after(action_created_at)",
                ],
                "approval_policy": "dashboard_required_when_sensitive_segment",
            },
        ),
        ActionContractTemplate(
            contract_key="outreach.campaign.launch",
            version="1.0",
            action_type="campaign_launch",
            operation_kind="SEND",
            domain_family="outreach_operations",
            risk_class="R3",
            connector_family="campaign_platform",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["campaign_id"],
                        "properties": {
                            "campaign_id": {"type": "string", "minLength": 1},
                            "segment_id": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["audience_size"],
                        "properties": {
                            "audience_size": {"type": "integer", "minimum": 1},
                            "send_at": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V4",
                "source_of_record": "campaign_platform",
                "positive_assertions": [
                    "equals(campaign_id)",
                    "audience_matches(audience_size)",
                    "one_of(status, launched, scheduled, sending)",
                ],
                "approval_policy": "dashboard_or_slack_required_for_bulk_send",
            },
        ),
    ),
)


DATA_OPS_PACK = ActionPackDefinition(
    id="data-ops-v1",
    display_name="Data operations",
    summary=(
        "Guard pipeline runs, record purges, and dataset exports with approval, "
        "warehouse verification, and audit-grade evidence."
    ),
    primary_runtime_path="sdk",
    recommended_connectors=("warehouse_orchestrator", "data_warehouse", "data_platform", "slack_approval_alert"),
    native_tool_families=("airflow_orchestrator", "dbt_warehouse", "generic_warehouse"),
    quickstart_steps=(
        "Install data-ops-v1 for the tenant.",
        "Configure warehouse, orchestrator, or read-only Postgres connector.",
        "Call protect() before pipeline run, record purge, or data export.",
        "Verify dataset, run status, and destination before evidence publish.",
    ),
    contract_templates=(
        ActionContractTemplate(
            contract_key="data.pipeline.run",
            version="1.0",
            action_type="pipeline_run",
            operation_kind="EXECUTE",
            domain_family="data_operations",
            risk_class="R2",
            connector_family="warehouse_orchestrator",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["pipeline_id"],
                        "properties": {
                            "pipeline_id": {"type": "string", "minLength": 1},
                            "environment": {"type": "string"},
                            "dataset": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["run_mode"],
                        "properties": {
                            "run_mode": {"type": "string", "enum": ["full", "incremental", "backfill"]},
                            "reason": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V3",
                "source_of_record": "warehouse_orchestrator",
                "positive_assertions": [
                    "equals(pipeline_id)",
                    "one_of(status, succeeded, running, queued)",
                    "record_updated_after(action_created_at)",
                ],
                "approval_policy": "dashboard_required_when_backfill",
            },
        ),
        ActionContractTemplate(
            contract_key="data.records.purge",
            version="1.0",
            action_type="records_purge",
            operation_kind="EXECUTE",
            domain_family="data_operations",
            risk_class="R4",
            connector_family="data_warehouse",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["dataset", "table"],
                        "properties": {
                            "dataset": {"type": "string", "minLength": 1},
                            "table": {"type": "string", "minLength": 1},
                            "environment": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["filter", "expected_row_count"],
                        "properties": {
                            "filter": {"type": "string", "minLength": 1},
                            "expected_row_count": {"type": "integer", "minimum": 0},
                            "reason": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V4",
                "source_of_record": "data_warehouse",
                "positive_assertions": [
                    "equals(dataset)",
                    "equals(table)",
                    "rows_deleted_matches(expected_row_count)",
                    "one_of(status, purged, deleted, completed)",
                ],
                "approval_policy": "dashboard_or_slack_required_for_r4",
            },
        ),
        ActionContractTemplate(
            contract_key="data.export.transfer",
            version="1.0",
            action_type="data_export",
            operation_kind="TRANSFER",
            domain_family="data_operations",
            risk_class="R3",
            connector_family="data_platform",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["dataset"],
                        "properties": {
                            "dataset": {"type": "string", "minLength": 1},
                            "table": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["destination", "format"],
                        "properties": {
                            "destination": {"type": "string", "minLength": 1},
                            "format": {"type": "string", "enum": ["csv", "parquet", "json"]},
                            "reason": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V4",
                "source_of_record": "data_platform",
                "positive_assertions": [
                    "equals(dataset)",
                    "equals(destination)",
                    "one_of(status, exported, completed, delivered)",
                    "destination_unchanged_after_intent",
                ],
                "approval_policy": "dashboard_or_slack_required_for_r3",
            },
        ),
    ),
)
