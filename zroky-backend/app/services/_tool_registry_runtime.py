from __future__ import annotations

from app.services._tool_registry_types import ALL_LAUNCH_ACTION_TYPES, ToolRegistryItem


RUNTIME_PATHS: tuple[ToolRegistryItem, ...] = (
    ToolRegistryItem(
        id="sdk",
        kind="runtime_path",
        label="SDK wrapper",
        description="Wrap JS or Python agent tool calls with Zroky runtime policy checks.",
        category="agent_runtime",
        implementation_status="available",
        supported_action_types=("refund", "customer_record_update", "ticket_close", "email_send", "deploy_change", "invoice_spend_approval", "internal_api_mutation", "database_record_update", "custom"),
        dashboard_href="/settings/keys",
        backend_capability="runtime_policy.check",
    ),
    ToolRegistryItem(
        id="customer_hosted_runner",
        kind="runtime_path",
        label="Customer-hosted protected runner",
        description="Claim approved protected actions, resolve credential refs locally, execute supported adapters, and report final execution state.",
        category="protected_runner",
        implementation_status="available",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        recommended_for_action_types=("refund", "internal_api_mutation", "custom"),
        requires_customer_credentials=True,
        dashboard_href="/settings/keys",
        backend_capability="action_runner.customer_hosted",
        availability_notes="Python runner ships generic REST and Stripe refund executors; more adapters remain callback-backed.",
    ),
    ToolRegistryItem(
        id="http_gateway",
        kind="runtime_path",
        label="HTTP Tool Gateway",
        description="Route arbitrary agent tool calls through a Zroky policy gate before execution.",
        category="agent_runtime",
        implementation_status="planned",
        supported_action_types=("refund", "customer_record_update", "ticket_close", "email_send", "deploy_change", "invoice_spend_approval", "internal_api_mutation", "database_record_update", "custom"),
        dashboard_href="/agents",
    ),
    ToolRegistryItem(
        id="mcp_gateway",
        kind="runtime_path",
        label="MCP Gateway",
        description="Run MCP tools behind Zroky's mandate, approval, and evidence controls.",
        category="agent_runtime",
        implementation_status="planned",
        supported_action_types=("refund", "customer_record_update", "ticket_close", "email_send", "deploy_change", "invoice_spend_approval", "internal_api_mutation", "database_record_update", "custom"),
        dashboard_href="/agents",
    ),
    ToolRegistryItem(
        id="webhook",
        kind="runtime_path",
        label="Webhook action intake",
        description="Let no-code or legacy agents submit action claims to the saved connector proof bridge.",
        category="agent_runtime",
        implementation_status="available",
        supported_action_types=("refund", "customer_record_update", "ticket_close", "email_send", "deploy_change", "invoice_spend_approval", "internal_api_mutation", "database_record_update", "custom"),
        dashboard_href="/integrations",
        backend_capability="outcome_reconciliation.saved_connector_bridge",
    ),
)


