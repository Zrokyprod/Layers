from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.db.models import Agent
from app.services.agent_profiles import (
    SCHEMA_VERSION,
    json_list,
)


RegistryKind = Literal["runtime_path", "verification_connector", "native_tool_family"]
ImplementationStatus = Literal["available", "template", "planned"]
LaunchTier = Literal["p0", "p1", "p2"]


ALL_LAUNCH_ACTION_TYPES = (
    "refund",
    "payment_adjustment",
    "customer_record_update",
    "ticket_close",
    "email_send",
    "deploy_change",
    "invoice_spend_approval",
    "internal_api_mutation",
    "database_record_update",
    "custom",
)


@dataclass(frozen=True)
class ToolRegistryItem:
    id: str
    kind: RegistryKind
    label: str
    description: str
    category: str
    implementation_status: ImplementationStatus
    supported_action_types: tuple[str, ...]
    launch_tier: LaunchTier = "p0"
    recommended_for_action_types: tuple[str, ...] = ()
    requires_customer_credentials: bool = False
    dashboard_href: str | None = None
    backend_capability: str | None = None
    availability_notes: str | None = None


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


VERIFICATION_CONNECTORS: tuple[ToolRegistryItem, ...] = (
    ToolRegistryItem(
        id="ledger_refund",
        kind="verification_connector",
        label="Ledger / refund verifier",
        description="Verify refund claims against a saved ledger or payment-provider read endpoint.",
        category="system_of_record",
        implementation_status="available",
        supported_action_types=("refund", "payment_adjustment"),
        recommended_for_action_types=("refund", "payment_adjustment"),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
        backend_capability="system_of_record.ledger_refund_api",
    ),
    ToolRegistryItem(
        id="crm_record",
        kind="verification_connector",
        label="CRM customer record verifier",
        description="Verify claimed customer, account, or contact record changes against a CRM read endpoint.",
        category="system_of_record",
        implementation_status="available",
        supported_action_types=("customer_record_update",),
        recommended_for_action_types=("customer_record_update",),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
        backend_capability="system_of_record.customer_record_api",
    ),
    ToolRegistryItem(
        id="ticket_status",
        kind="verification_connector",
        label="Ticket status verifier",
        description="Verify ticket close, escalation, assignment, or status changes in the ticketing system.",
        category="system_of_record",
        implementation_status="planned",
        supported_action_types=("ticket_close",),
        recommended_for_action_types=("ticket_close",),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="email_delivery",
        kind="verification_connector",
        label="Email delivery verifier",
        description="Verify that an agent-sent email or provider message was actually accepted or delivered.",
        category="system_of_record",
        implementation_status="planned",
        supported_action_types=("email_send",),
        recommended_for_action_types=("email_send",),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="github_ci",
        kind="verification_connector",
        label="GitHub CI / deploy verifier",
        description="Verify pull request, check run, deployment, or change-management outcome proof.",
        category="system_of_record",
        implementation_status="planned",
        supported_action_types=("deploy_change",),
        recommended_for_action_types=("deploy_change",),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="generic_rest",
        kind="verification_connector",
        label="Generic REST/OpenAPI verifier",
        description="Map an internal API read endpoint into expected-vs-observed verification.",
        category="generic_verifier",
        implementation_status="available",
        supported_action_types=("refund", "payment_adjustment", "customer_record_update", "ticket_close", "email_send", "deploy_change", "invoice_spend_approval", "internal_api_mutation", "database_record_update", "custom"),
        recommended_for_action_types=("internal_api_mutation", "custom"),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
        backend_capability="system_of_record.generic_rest_api",
    ),
    ToolRegistryItem(
        id="webhook_callback",
        kind="verification_connector",
        label="Webhook outcome callback",
        description="Accept a customer-signed outcome callback when Zroky cannot read the source system directly.",
        category="generic_verifier",
        implementation_status="template",
        supported_action_types=("refund", "payment_adjustment", "customer_record_update", "ticket_close", "email_send", "deploy_change", "invoice_spend_approval", "internal_api_mutation", "database_record_update", "custom"),
        recommended_for_action_types=("invoice_spend_approval", "custom"),
        requires_customer_credentials=False,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="database_read",
        kind="verification_connector",
        label="Database read verifier",
        description="Read a customer database table or view for verification-only outcome proof.",
        category="generic_verifier",
        implementation_status="planned",
        supported_action_types=("customer_record_update", "ticket_close", "email_send", "deploy_change", "invoice_spend_approval", "internal_api_mutation", "database_record_update", "custom"),
        recommended_for_action_types=("database_record_update", "internal_api_mutation"),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
    ),
)


NATIVE_TOOL_FAMILIES: tuple[ToolRegistryItem, ...] = (
    ToolRegistryItem(
        id="stripe_refund",
        kind="native_tool_family",
        label="Stripe refunds",
        description="Guard and execute Stripe refund actions through the customer-hosted runner, then verify source-of-record state.",
        category="payments",
        implementation_status="available",
        supported_action_types=("refund", "payment_adjustment"),
        recommended_for_action_types=("refund",),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
        backend_capability="runner_adapter.stripe_refund",
        availability_notes="Available in the Python customer-hosted runner; managed-hosted execution packaging is still pending.",
    ),
    ToolRegistryItem(
        id="razorpay_refund",
        kind="native_tool_family",
        label="Razorpay refunds",
        description="Template for guarding and verifying Razorpay refund actions.",
        category="payments",
        implementation_status="planned",
        supported_action_types=("refund", "payment_adjustment"),
        recommended_for_action_types=("refund",),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="hubspot_customer",
        kind="native_tool_family",
        label="HubSpot customer records",
        description="Template for customer/contact record update verification in HubSpot.",
        category="crm",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=("customer_record_update",),
        recommended_for_action_types=("customer_record_update",),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="salesforce_customer",
        kind="native_tool_family",
        label="Salesforce customer records",
        description="Template for customer/account/contact update verification in Salesforce.",
        category="crm",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=("customer_record_update",),
        recommended_for_action_types=("customer_record_update",),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="zendesk_ticket",
        kind="native_tool_family",
        label="Zendesk tickets",
        description="Template for ticket close/status verification in Zendesk.",
        category="support",
        implementation_status="planned",
        supported_action_types=("ticket_close",),
        recommended_for_action_types=("ticket_close",),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="freshdesk_ticket",
        kind="native_tool_family",
        label="Freshdesk tickets",
        description="Template for ticket close/status verification in Freshdesk.",
        category="support",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=("ticket_close",),
        recommended_for_action_types=("ticket_close",),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="sendgrid_email",
        kind="native_tool_family",
        label="SendGrid email",
        description="Template for email send and delivery verification through SendGrid.",
        category="messaging",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=("email_send",),
        recommended_for_action_types=("email_send",),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="gmail_email",
        kind="native_tool_family",
        label="Gmail email",
        description="Template for email send verification through Gmail or Google Workspace.",
        category="messaging",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=("email_send",),
        recommended_for_action_types=("email_send",),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="github_pr_ci_deploy",
        kind="native_tool_family",
        label="GitHub PR, CI, and deploy",
        description="Template for repository, check-run, and deployment outcome verification.",
        category="devops",
        implementation_status="template",
        supported_action_types=("deploy_change",),
        recommended_for_action_types=("deploy_change",),
        requires_customer_credentials=True,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="slack_approval_alert",
        kind="native_tool_family",
        label="Slack approval and alert",
        description="Approval and alert surface for held actions; not a proof source unless message delivery is verified.",
        category="approval",
        implementation_status="available",
        supported_action_types=("refund", "payment_adjustment", "customer_record_update", "ticket_close", "email_send", "deploy_change", "invoice_spend_approval", "internal_api_mutation", "database_record_update", "custom"),
        recommended_for_action_types=("refund", "invoice_spend_approval", "deploy_change"),
        requires_customer_credentials=True,
        dashboard_href="/integrations/slack",
        backend_capability="slack.approval_alert",
    ),
    ToolRegistryItem(
        id="zroky_dashboard_approval",
        kind="native_tool_family",
        label="Zroky dashboard approvals",
        description="First-party approval surface for exact intent-digest-bound approve/reject decisions.",
        category="approval",
        implementation_status="available",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        recommended_for_action_types=("refund", "customer_record_update", "deploy_change", "internal_api_mutation"),
        requires_customer_credentials=False,
        dashboard_href="/approvals",
        backend_capability="approvals.dashboard",
    ),
    ToolRegistryItem(
        id="generic_rest_action",
        kind="native_tool_family",
        label="Generic REST protected action",
        description="Execute approved internal API or workflow actions through the customer-hosted runner.",
        category="execution",
        implementation_status="available",
        supported_action_types=("customer_record_update", "email_send", "internal_api_mutation", "custom"),
        recommended_for_action_types=("internal_api_mutation", "custom"),
        requires_customer_credentials=True,
        dashboard_href="/settings/keys",
        backend_capability="runner_adapter.generic_rest",
    ),
    ToolRegistryItem(
        id="custom_python_agent",
        kind="native_tool_family",
        label="Custom Python agents",
        description="Python agents using the Zroky SDK, protected runner, and saved connector verification helpers.",
        category="agent_framework",
        implementation_status="available",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        recommended_for_action_types=("refund", "internal_api_mutation", "custom"),
        dashboard_href="/settings/keys",
        backend_capability="sdk.python",
    ),
    ToolRegistryItem(
        id="custom_typescript_agent",
        kind="native_tool_family",
        label="Custom TypeScript agents",
        description="TypeScript agents using the Zroky JS SDK for policy guard and outcome verification.",
        category="agent_framework",
        implementation_status="available",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        recommended_for_action_types=("internal_api_mutation", "custom"),
        dashboard_href="/settings/keys",
        backend_capability="sdk.typescript",
    ),
    ToolRegistryItem(
        id="openai_agents_sdk",
        kind="native_tool_family",
        label="OpenAI Agents SDK",
        description="Template connector for wrapping OpenAI Agents SDK tool calls with Zroky action contracts.",
        category="agent_framework",
        implementation_status="template",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        recommended_for_action_types=("internal_api_mutation", "custom"),
        dashboard_href="/settings/keys",
        availability_notes="Use SDK guard/verify helpers today; framework-specific example polish remains pending.",
    ),
    ToolRegistryItem(
        id="langgraph",
        kind="native_tool_family",
        label="LangGraph",
        description="Template connector for routing LangGraph node/tool actions through Zroky policy and receipt workflows.",
        category="agent_framework",
        implementation_status="template",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        recommended_for_action_types=("refund", "internal_api_mutation", "custom"),
        dashboard_href="/settings/keys",
        availability_notes="Python integration path exists through the SDK; dedicated LangGraph examples remain pending.",
    ),
    ToolRegistryItem(
        id="openai_llm",
        kind="native_tool_family",
        label="OpenAI",
        description="LLM provider context for agents whose protected tool calls are guarded by Zroky.",
        category="llm_provider",
        implementation_status="template",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        launch_tier="p0",
        dashboard_href="/settings/providers",
    ),
    ToolRegistryItem(
        id="anthropic_llm",
        kind="native_tool_family",
        label="Anthropic",
        description="LLM provider context for agents whose protected tool calls are guarded by Zroky.",
        category="llm_provider",
        implementation_status="template",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        launch_tier="p0",
        dashboard_href="/settings/providers",
    ),
    ToolRegistryItem(
        id="azure_openai_llm",
        kind="native_tool_family",
        label="Azure OpenAI",
        description="Enterprise OpenAI deployment context for protected agent actions.",
        category="llm_provider",
        implementation_status="template",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        launch_tier="p0",
        dashboard_href="/settings/providers",
    ),
    ToolRegistryItem(
        id="google_gemini_llm",
        kind="native_tool_family",
        label="Google Gemini",
        description="LLM provider context for Gemini-backed agents guarded by Zroky.",
        category="llm_provider",
        implementation_status="template",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        launch_tier="p0",
        dashboard_href="/settings/providers",
    ),
    ToolRegistryItem(
        id="litellm_gateway",
        kind="native_tool_family",
        label="LiteLLM gateway",
        description="Gateway context for teams routing multiple model providers while Zroky controls high-risk actions.",
        category="llm_gateway",
        implementation_status="template",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        launch_tier="p0",
        dashboard_href="/settings/providers",
    ),
    ToolRegistryItem(
        id="sentry",
        kind="native_tool_family",
        label="Sentry",
        description="Production error tracking connector for protected action runner and control-plane failures.",
        category="observability",
        implementation_status="planned",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        launch_tier="p0",
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="posthog",
        kind="native_tool_family",
        label="PostHog",
        description="Product analytics connector for launch usage, approvals, verification outcomes, and bypass visibility.",
        category="observability",
        implementation_status="planned",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        launch_tier="p0",
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="opentelemetry",
        kind="native_tool_family",
        label="OpenTelemetry",
        description="Trace/metric/log context for the protected action control loop.",
        category="observability",
        implementation_status="template",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        launch_tier="p0",
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="crewai",
        kind="native_tool_family",
        label="CrewAI",
        description="Framework template for CrewAI agents whose delegated tools require Zroky approval and receipts.",
        category="agent_framework",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        dashboard_href="/settings/keys",
    ),
    ToolRegistryItem(
        id="autogen",
        kind="native_tool_family",
        label="AutoGen",
        description="Framework template for AutoGen multi-agent tool execution control.",
        category="agent_framework",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        dashboard_href="/settings/keys",
    ),
    ToolRegistryItem(
        id="llamaindex",
        kind="native_tool_family",
        label="LlamaIndex",
        description="Framework template for LlamaIndex agents and workflows that mutate business systems.",
        category="agent_framework",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        dashboard_href="/settings/keys",
    ),
    ToolRegistryItem(
        id="vercel_ai_sdk",
        kind="native_tool_family",
        label="Vercel AI SDK",
        description="TypeScript framework template for protecting tool calls in Vercel AI SDK applications.",
        category="agent_framework",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        dashboard_href="/settings/keys",
    ),
    ToolRegistryItem(
        id="intercom",
        kind="native_tool_family",
        label="Intercom",
        description="Support/customer messaging connector roadmap item for support operations agents.",
        category="support",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=("ticket_close", "email_send", "customer_record_update"),
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="linear",
        kind="native_tool_family",
        label="Linear",
        description="Issue/change-management connector roadmap item for DevOps and product operations workflows.",
        category="devops",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=("deploy_change", "internal_api_mutation", "custom"),
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="jira",
        kind="native_tool_family",
        label="Jira",
        description="Issue/change-management connector roadmap item for enterprise approval and audit workflows.",
        category="devops",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=("deploy_change", "internal_api_mutation", "custom"),
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="gitlab_ci",
        kind="native_tool_family",
        label="GitLab CI",
        description="CI/deployment verifier roadmap item for GitLab-hosted engineering workflows.",
        category="devops",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=("deploy_change",),
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="datadog",
        kind="native_tool_family",
        label="Datadog",
        description="Observability connector roadmap item for protected action incidents, traces, and metrics.",
        category="observability",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="grafana_cloud",
        kind="native_tool_family",
        label="Grafana Cloud",
        description="Observability connector roadmap item for action-loop metrics and incident dashboards.",
        category="observability",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="bigquery_read",
        kind="native_tool_family",
        label="BigQuery read verifier",
        description="Warehouse-backed source-of-record verifier roadmap item.",
        category="warehouse_verifier",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=("internal_api_mutation", "database_record_update", "custom"),
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="snowflake_read",
        kind="native_tool_family",
        label="Snowflake read verifier",
        description="Warehouse-backed source-of-record verifier roadmap item.",
        category="warehouse_verifier",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=("internal_api_mutation", "database_record_update", "custom"),
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="redis_audit_ingest",
        kind="native_tool_family",
        label="Redis audit ingestion",
        description="Event/audit ingestion roadmap item for mutation streams and bypass detection.",
        category="audit_ingestion",
        implementation_status="planned",
        launch_tier="p1",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        dashboard_href="/integrations",
    ),
    ToolRegistryItem(
        id="connector_marketplace",
        kind="native_tool_family",
        label="Connector marketplace",
        description="Deferred broad marketplace surface; launch should stay focused on first-party critical connectors.",
        category="platform",
        implementation_status="planned",
        launch_tier="p2",
        supported_action_types=ALL_LAUNCH_ACTION_TYPES,
        dashboard_href="/integrations",
    ),
)


def serialize_registry_item(item: ToolRegistryItem) -> dict[str, object]:
    return {
        "id": item.id,
        "kind": item.kind,
        "label": item.label,
        "description": item.description,
        "category": item.category,
        "phase": "phase1",
        "implementation_status": item.implementation_status,
        "launch_tier": item.launch_tier,
        "supported_action_types": list(item.supported_action_types),
        "recommended_for_action_types": list(item.recommended_for_action_types),
        "requires_customer_credentials": item.requires_customer_credentials,
        "dashboard_href": item.dashboard_href,
        "backend_capability": item.backend_capability,
        "availability_notes": item.availability_notes,
    }


def action_types_for_agent(agent: Agent | None, requested_action_type: str | None) -> list[str]:
    if requested_action_type:
        return [requested_action_type.strip().lower()]
    if agent is None:
        return []
    allowed = json_list(getattr(agent, "allowed_action_types_json", None))
    if allowed:
        return [item.lower() for item in allowed]
    return []


def recommendations_for_action_types(action_types: list[str]) -> dict[str, object]:
    action_set = {item.strip().lower() for item in action_types if item.strip()}
    if not action_set:
        return {
            "action_types": [],
            "runtime_path_ids": ["sdk"],
            "verification_connector_ids": ["generic_rest", "webhook_callback"],
            "native_tool_family_ids": [],
            "next_steps": [
                "Define the agent's risky action types.",
                "Start with the SDK wrapper unless the agent cannot use code changes.",
                "Use a generic REST verifier or webhook callback until a native verifier exists.",
            ],
        }

    runtime_ids = ["sdk", "customer_hosted_runner"]
    connector_ids = [
        item.id
        for item in VERIFICATION_CONNECTORS
        if item.launch_tier == "p0"
        and action_set.intersection(item.recommended_for_action_types or item.supported_action_types)
    ]
    native_ids = [
        item.id
        for item in NATIVE_TOOL_FAMILIES
        if item.launch_tier == "p0"
        and action_set.intersection(item.recommended_for_action_types)
    ]
    if not connector_ids:
        connector_ids = ["generic_rest", "webhook_callback"]

    next_steps = [
        "Wrap this agent's tool call with the SDK or route it through a gateway.",
        "Choose one verifier that can prove the real system outcome.",
        "Run one real action and confirm Evidence Pack status becomes matched, mismatched, or not_verified.",
    ]
    return {
        "action_types": sorted(action_set),
        "runtime_path_ids": runtime_ids,
        "verification_connector_ids": _dedupe(connector_ids),
        "native_tool_family_ids": _dedupe(native_ids),
        "next_steps": next_steps,
    }


def build_tool_registry(agent: Agent | None = None, requested_action_type: str | None = None) -> dict[str, object]:
    action_types = action_types_for_agent(agent, requested_action_type)
    return {
        "schema_version": SCHEMA_VERSION,
        "agent_id": agent.id if agent is not None else None,
        "action_type": requested_action_type,
        "runtime_paths": [serialize_registry_item(item) for item in RUNTIME_PATHS],
        "verification_connectors": [serialize_registry_item(item) for item in VERIFICATION_CONNECTORS],
        "native_tool_families": [serialize_registry_item(item) for item in NATIVE_TOOL_FAMILIES],
        "recommended": recommendations_for_action_types(action_types),
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out
