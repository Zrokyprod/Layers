from __future__ import annotations

from app.services._action_pack_types import ActionContractTemplate, ActionPackDefinition


SUPPORT_OPS_PACK = ActionPackDefinition(
    id="support-ops-v1",
    display_name="Support operations",
    summary=(
        "Guard customer refunds and customer-record updates with approval, "
        "source-of-record verification, and evidence packs."
    ),
    primary_runtime_path="sdk",
    recommended_connectors=("ledger_refund", "crm_record", "generic_rest", "slack_approval_alert"),
    native_tool_families=("stripe_refund", "razorpay_refund", "hubspot_customer", "salesforce_customer"),
    quickstart_steps=(
        "Install support-ops-v1 for the tenant.",
        "Configure Stripe/Razorpay refund or CRM record connector.",
        "Call guard() before refund or customer-record update.",
        "Verify outcome from saved connector and publish evidence pack.",
    ),
    contract_templates=(
        ActionContractTemplate(
            contract_key="customer.refund.transfer",
            version="1.0",
            action_type="refund",
            operation_kind="TRANSFER",
            domain_family="customer_operations",
            risk_class="R3",
            connector_family="ledger_refund",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["refund_id"],
                        "properties": {
                            "refund_id": {"type": "string", "minLength": 1},
                            "order_id": {"type": "string"},
                            "customer_id": {"type": "string"},
                            "account_id": {"type": "string"},
                            "provider": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["amount_minor", "currency"],
                        "properties": {
                            "amount_minor": {"type": "integer", "minimum": 1},
                            "currency": {"type": "string", "minLength": 3, "maxLength": 3},
                            "reason": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V4",
                "source_of_record": "ledger_refund",
                "positive_assertions": [
                    "equals(refund_id)",
                    "equals(amount_minor)",
                    "equals(currency)",
                    "one_of(status, posted, succeeded, captured)",
                ],
                "approval_policy": "dashboard_or_slack_required_for_r3",
            },
        ),
        ActionContractTemplate(
            contract_key="customer.record.update",
            version="1.0",
            action_type="customer_record_update",
            operation_kind="UPDATE",
            domain_family="customer_operations",
            risk_class="R2",
            connector_family="crm_record",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["customer_id"],
                        "properties": {
                            "customer_id": {"type": "string", "minLength": 1},
                            "account_id": {"type": "string"},
                            "crm_object": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["fields"],
                        "properties": {
                            "fields": {
                                "type": "object",
                                "minProperties": 1,
                                "additionalProperties": True,
                            },
                            "reason": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V3",
                "source_of_record": "crm_record",
                "positive_assertions": [
                    "equals(customer_id)",
                    "equals(updated_fields)",
                    "record_updated_after(action_created_at)",
                ],
                "approval_policy": "dashboard_required_when_sensitive_fields_change",
            },
        ),
    ),
)


DEVOPS_PACK = ActionPackDefinition(
    id="devops-release-v1",
    display_name="DevOps release control",
    summary=(
        "Guard deploy or infrastructure changes with CI verification, "
        "human approval, and auditable evidence."
    ),
    primary_runtime_path="sdk",
    recommended_connectors=("github_ci", "generic_rest", "slack_approval_alert"),
    native_tool_families=("github_pr_ci_deploy",),
    quickstart_steps=(
        "Install devops-release-v1 for the tenant.",
        "Connect CI/deploy source of record.",
        "Call guard() before deploy or infra change.",
        "Require CI proof and owner approval before release.",
    ),
    contract_templates=(
        ActionContractTemplate(
            contract_key="devops.deploy.change",
            version="1.0",
            action_type="deploy_change",
            operation_kind="DEPLOY",
            domain_family="devops",
            risk_class="R4",
            connector_family="github_ci",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["repository", "environment"],
                        "properties": {
                            "repository": {"type": "string", "minLength": 1},
                            "environment": {"type": "string", "minLength": 1},
                            "pull_request": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["head_sha"],
                        "properties": {
                            "head_sha": {"type": "string", "minLength": 7},
                            "base_sha": {"type": "string"},
                            "change_summary": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V4",
                "source_of_record": "github_ci",
                "positive_assertions": [
                    "ci_checks_passed(head_sha)",
                    "deployment_environment_matches(environment)",
                    "approval_linked_before_deploy",
                ],
                "approval_policy": "dashboard_or_slack_required_for_r4",
            },
        ),
    ),
)


ECOMMERCE_OPS_PACK = ActionPackDefinition(
    id="ecommerce-ops-v1",
    display_name="Ecommerce operations",
    summary=(
        "Guard order cancellations, inventory adjustments, and customer "
        "discounts with approval, source-of-record verification, and evidence."
    ),
    primary_runtime_path="sdk",
    recommended_connectors=("order_management", "inventory_system", "commerce_platform", "slack_approval_alert"),
    native_tool_families=("shopify_admin", "woocommerce_store", "generic_commerce"),
    quickstart_steps=(
        "Install ecommerce-ops-v1 for the tenant.",
        "Configure Shopify Admin or commerce source-of-record connector.",
        "Call guard() before order cancel, inventory adjust, or discount issue.",
        "Verify order/customer/inventory state before marking outcome verified.",
    ),
    contract_templates=(
        ActionContractTemplate(
            contract_key="commerce.order.cancel",
            version="1.0",
            action_type="order_cancel",
            operation_kind="UPDATE",
            domain_family="ecommerce_operations",
            risk_class="R3",
            connector_family="order_management",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["order_id"],
                        "properties": {
                            "order_id": {"type": "string", "minLength": 1},
                            "customer_id": {"type": "string"},
                            "channel": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["reason"],
                        "properties": {
                            "reason": {"type": "string", "minLength": 1},
                            "restock": {"type": "boolean"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V4",
                "source_of_record": "order_management",
                "positive_assertions": [
                    "equals(order_id)",
                    "one_of(status, cancelled, canceled, voided)",
                    "record_updated_after(action_created_at)",
                ],
                "approval_policy": "dashboard_or_slack_required_for_r3",
            },
        ),
        ActionContractTemplate(
            contract_key="commerce.inventory.adjust",
            version="1.0",
            action_type="inventory_adjust",
            operation_kind="UPDATE",
            domain_family="ecommerce_operations",
            risk_class="R2",
            connector_family="inventory_system",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["sku"],
                        "properties": {
                            "sku": {"type": "string", "minLength": 1},
                            "location_id": {"type": "string"},
                            "warehouse": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["quantity_delta"],
                        "properties": {
                            "quantity_delta": {"type": "integer"},
                            "reason": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V3",
                "source_of_record": "inventory_system",
                "positive_assertions": [
                    "equals(sku)",
                    "inventory_reflects(quantity_delta)",
                    "record_updated_after(action_created_at)",
                ],
                "approval_policy": "dashboard_required_when_large_adjustment",
            },
        ),
        ActionContractTemplate(
            contract_key="commerce.discount.issue",
            version="1.0",
            action_type="discount_issue",
            operation_kind="TRANSFER",
            domain_family="ecommerce_operations",
            risk_class="R3",
            connector_family="commerce_platform",
            schema={
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {
                        "type": "object",
                        "required": ["customer_id"],
                        "properties": {
                            "customer_id": {"type": "string", "minLength": 1},
                            "order_id": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "parameters": {
                        "type": "object",
                        "required": ["amount_minor", "currency"],
                        "properties": {
                            "amount_minor": {"type": "integer", "minimum": 1},
                            "currency": {"type": "string", "minLength": 3, "maxLength": 3},
                            "code": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            verification_profile={
                "minimum_level": "V4",
                "source_of_record": "commerce_platform",
                "positive_assertions": [
                    "equals(customer_id)",
                    "equals(amount_minor)",
                    "equals(currency)",
                    "discount_active(code)",
                ],
                "approval_policy": "dashboard_or_slack_required_for_r3",
            },
        ),
    ),
)

