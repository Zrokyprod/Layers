import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  GenericRestConnectorStatusResponse,
  HubSpotCrmConnectorStatusResponse,
  JiraIssueConnectorStatusResponse,
  McpUpstreamBindingResponse,
  NetSuiteFinanceConnectorStatusResponse,
  OutcomeReconciliationView,
  PostgresReadConnectorStatusResponse,
  RazorpayRefundConnectorStatusResponse,
  SalesforceCrmConnectorStatusResponse,
  ShopifyConnectorStatusResponse,
  StripePaymentConnectorStatusResponse,
  StripeRefundConnectorStatusResponse,
  ToolRegistryResponse,
  ZendeskTicketConnectorStatusResponse,
  ZohoCrmConnectorStatusResponse,
} from "@/lib/api";
import IntegrationsPage from "./page";

const api = vi.hoisted(() => ({
  activateMcpUpstream: vi.fn(),
  disableMcpUpstream: vi.fn(),
  getCustomerRecordConnectorStatus: vi.fn(),
  getGenericRestConnectorStatus: vi.fn(),
  getGithubConnectionStatus: vi.fn(),
  getHubSpotCrmConnectorStatus: vi.fn(),
  getJiraIssueConnectorStatus: vi.fn(),
  getLedgerRefundConnectorStatus: vi.fn(),
  getMcpUpstreamBinding: vi.fn(),
  getNetSuiteFinanceConnectorStatus: vi.fn(),
  getPostgresReadConnectorStatus: vi.fn(),
  getRazorpayRefundConnectorStatus: vi.fn(),
  getSalesforceCrmConnectorStatus: vi.fn(),
  getShopifyConnectorStatus: vi.fn(),
  getStripePaymentConnectorStatus: vi.fn(),
  getStripeRefundConnectorStatus: vi.fn(),
  getZendeskTicketConnectorStatus: vi.fn(),
  getZohoCrmConnectorStatus: vi.fn(),
  getSlackInstallStatus: vi.fn(),
  getToolRegistry: vi.fn(),
  listSourceConnectors: vi.fn(),
  listOutcomeReconciliations: vi.fn(),
  preflightMcpUpstream: vi.fn(),
  saveGenericRestConnectorConfig: vi.fn(),
  saveHubSpotCrmConnectorConfig: vi.fn(),
  saveJiraIssueConnectorConfig: vi.fn(),
  saveMcpUpstreamDraft: vi.fn(),
  saveNetSuiteFinanceConnectorConfig: vi.fn(),
  savePostgresReadConnectorConfig: vi.fn(),
  saveRazorpayRefundConnectorConfig: vi.fn(),
  saveSalesforceCrmConnectorConfig: vi.fn(),
  saveShopifyConnectorConfig: vi.fn(),
  saveStripePaymentConnectorConfig: vi.fn(),
  saveStripeRefundConnectorConfig: vi.fn(),
  saveZendeskTicketConnectorConfig: vi.fn(),
  saveZohoCrmConnectorConfig: vi.fn(),
  startJiraIssueOAuth: vi.fn(),
  startZohoCrmOAuth: vi.fn(),
  testGenericRestConnector: vi.fn(),
  testHubSpotCrmConnector: vi.fn(),
  testJiraIssueConnector: vi.fn(),
  testNetSuiteFinanceConnector: vi.fn(),
  testPostgresReadConnector: vi.fn(),
  testRazorpayRefundConnector: vi.fn(),
  testSalesforceCrmConnector: vi.fn(),
  testShopifyConnector: vi.fn(),
  testStripePaymentConnector: vi.fn(),
  testStripeRefundConnector: vi.fn(),
  testZendeskTicketConnector: vi.fn(),
  testZohoCrmConnector: vi.fn(),
  upsertSourceConnector: vi.fn(),
}));

const clipboardWrite = vi.fn();

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    activateMcpUpstream: api.activateMcpUpstream,
    disableMcpUpstream: api.disableMcpUpstream,
    getCustomerRecordConnectorStatus: api.getCustomerRecordConnectorStatus,
    getGenericRestConnectorStatus: api.getGenericRestConnectorStatus,
    getGithubConnectionStatus: api.getGithubConnectionStatus,
    getHubSpotCrmConnectorStatus: api.getHubSpotCrmConnectorStatus,
    getJiraIssueConnectorStatus: api.getJiraIssueConnectorStatus,
    getLedgerRefundConnectorStatus: api.getLedgerRefundConnectorStatus,
    getMcpUpstreamBinding: api.getMcpUpstreamBinding,
    getNetSuiteFinanceConnectorStatus: api.getNetSuiteFinanceConnectorStatus,
    getPostgresReadConnectorStatus: api.getPostgresReadConnectorStatus,
    getRazorpayRefundConnectorStatus: api.getRazorpayRefundConnectorStatus,
    getSalesforceCrmConnectorStatus: api.getSalesforceCrmConnectorStatus,
    getShopifyConnectorStatus: api.getShopifyConnectorStatus,
    getStripePaymentConnectorStatus: api.getStripePaymentConnectorStatus,
    getStripeRefundConnectorStatus: api.getStripeRefundConnectorStatus,
    getZendeskTicketConnectorStatus: api.getZendeskTicketConnectorStatus,
    getZohoCrmConnectorStatus: api.getZohoCrmConnectorStatus,
    getSlackInstallStatus: api.getSlackInstallStatus,
    getToolRegistry: api.getToolRegistry,
    listSourceConnectors: api.listSourceConnectors,
    listOutcomeReconciliations: api.listOutcomeReconciliations,
    preflightMcpUpstream: api.preflightMcpUpstream,
    saveGenericRestConnectorConfig: api.saveGenericRestConnectorConfig,
    saveHubSpotCrmConnectorConfig: api.saveHubSpotCrmConnectorConfig,
    saveJiraIssueConnectorConfig: api.saveJiraIssueConnectorConfig,
    saveMcpUpstreamDraft: api.saveMcpUpstreamDraft,
    saveNetSuiteFinanceConnectorConfig: api.saveNetSuiteFinanceConnectorConfig,
    savePostgresReadConnectorConfig: api.savePostgresReadConnectorConfig,
    saveRazorpayRefundConnectorConfig: api.saveRazorpayRefundConnectorConfig,
    saveSalesforceCrmConnectorConfig: api.saveSalesforceCrmConnectorConfig,
    saveShopifyConnectorConfig: api.saveShopifyConnectorConfig,
    saveStripePaymentConnectorConfig: api.saveStripePaymentConnectorConfig,
    saveStripeRefundConnectorConfig: api.saveStripeRefundConnectorConfig,
    saveZendeskTicketConnectorConfig: api.saveZendeskTicketConnectorConfig,
    saveZohoCrmConnectorConfig: api.saveZohoCrmConnectorConfig,
    startJiraIssueOAuth: api.startJiraIssueOAuth,
    startZohoCrmOAuth: api.startZohoCrmOAuth,
    testGenericRestConnector: api.testGenericRestConnector,
    testHubSpotCrmConnector: api.testHubSpotCrmConnector,
    testJiraIssueConnector: api.testJiraIssueConnector,
    testNetSuiteFinanceConnector: api.testNetSuiteFinanceConnector,
    testPostgresReadConnector: api.testPostgresReadConnector,
    testRazorpayRefundConnector: api.testRazorpayRefundConnector,
    testSalesforceCrmConnector: api.testSalesforceCrmConnector,
    testShopifyConnector: api.testShopifyConnector,
    testStripePaymentConnector: api.testStripePaymentConnector,
    testStripeRefundConnector: api.testStripeRefundConnector,
    testZendeskTicketConnector: api.testZendeskTicketConnector,
    testZohoCrmConnector: api.testZohoCrmConnector,
    upsertSourceConnector: api.upsertSourceConnector,
  };
});

vi.mock("./system-of-record-connectors", () => ({
  default: () => (
    <section aria-label="Integration status">
      GitHub Slack system-of-record status
    </section>
  ),
}));

function mcpStatus(overrides: Partial<McpUpstreamBindingResponse> = {}): McpUpstreamBindingResponse {
  return {
    endpoint_url: "https://mcp.example.com/mcp",
    protocol_version: "2025-06-18",
    credential_configured: true,
    allowed_tools: ["refund.create"],
    status: "draft",
    test_status: "not_tested",
    tested_at: null,
    last_test_error: null,
    activated_at: null,
    version: 1,
    created_at: "2026-07-11T09:00:00Z",
    updated_at: "2026-07-11T09:00:00Z",
    ...overrides,
  };
}

function toolRegistry(overrides: Partial<ToolRegistryResponse> = {}): ToolRegistryResponse {
  return {
    schema_version: "zroky.agent_tool_control.v1",
    project_id: "project_1",
    agent_id: null,
    action_type: null,
    runtime_paths: [
      {
        id: "sdk",
        kind: "runtime_path",
        label: "SDK wrapper",
        description: "Wrap JS or Python agent tool calls with Zroky runtime policy checks.",
        category: "agent_runtime",
        phase: "phase1",
        implementation_status: "available",
        launch_tier: "p0",
        supported_action_types: ["refund"],
        recommended_for_action_types: [],
        requires_customer_credentials: false,
        dashboard_href: "/settings/keys",
        backend_capability: "runtime_policy.check",
        availability_notes: "Available for launch.",
      },
      {
        id: "http_gateway",
        kind: "runtime_path",
        label: "HTTP Tool Gateway",
        description: "Route arbitrary agent tool calls through Zroky before execution.",
        category: "agent_runtime",
        phase: "phase1",
        implementation_status: "planned",
        launch_tier: "p1",
        supported_action_types: ["custom"],
        recommended_for_action_types: [],
        requires_customer_credentials: false,
        dashboard_href: "/operations",
        backend_capability: null,
        availability_notes: "Planned after launch partner demand.",
      },
    ],
    verification_connectors: [
      {
        id: "ledger_refund",
        kind: "verification_connector",
        label: "Ledger / refund verifier",
        description: "Verify refund claims against a saved ledger or payment-provider read endpoint.",
        category: "system_of_record",
        phase: "phase1",
        implementation_status: "available",
        launch_tier: "p0",
        supported_action_types: ["refund"],
        recommended_for_action_types: ["refund"],
        requires_customer_credentials: true,
        dashboard_href: "/integrations",
        backend_capability: "system_of_record.ledger_refund_api",
        availability_notes: "Available for launch.",
      },
      {
        id: "crm_record",
        kind: "verification_connector",
        label: "CRM customer record verifier",
        description: "Verify claimed customer, account, or contact record changes against a CRM read endpoint.",
        category: "system_of_record",
        phase: "phase1",
        implementation_status: "available",
        launch_tier: "p0",
        supported_action_types: ["customer_record_update"],
        recommended_for_action_types: ["customer_record_update"],
        requires_customer_credentials: true,
        dashboard_href: "/integrations",
        backend_capability: "system_of_record.customer_record_api",
        availability_notes: "Available for launch.",
      },
      {
        id: "generic_rest",
        kind: "verification_connector",
        label: "Generic REST/OpenAPI verifier",
        description: "Map an internal API read endpoint into expected-vs-observed verification.",
        category: "generic_verifier",
        phase: "phase1",
        implementation_status: "available",
        launch_tier: "p0",
        supported_action_types: ["custom"],
        recommended_for_action_types: ["custom"],
        requires_customer_credentials: true,
        dashboard_href: "/integrations",
        backend_capability: "system_of_record.generic_rest_api",
        availability_notes: "Available for launch.",
      },
      {
        id: "stripe_refund",
        kind: "verification_connector",
        label: "Stripe refund verifier",
        description: "Verify refund claims against Stripe's read-only refund API.",
        category: "system_of_record",
        phase: "phase1",
        implementation_status: "available",
        launch_tier: "p0",
        supported_action_types: ["refund"],
        recommended_for_action_types: ["refund"],
        requires_customer_credentials: true,
        dashboard_href: "/integrations",
        backend_capability: "system_of_record.stripe_refund",
        availability_notes: "Available for launch.",
      },
    ],
    native_tool_families: [
      {
        id: "slack_approval_alert",
        kind: "native_tool_family",
        label: "Slack approval and alert",
        description: "Approval and alert surface for held actions.",
        category: "approval",
        phase: "phase1",
        implementation_status: "available",
        launch_tier: "p0",
        supported_action_types: ["refund"],
        recommended_for_action_types: ["refund"],
        requires_customer_credentials: true,
        dashboard_href: "/integrations/slack",
        backend_capability: "slack.approval_alert",
        availability_notes: "Available for launch.",
      },
    ],
    recommended: {
      action_types: [],
      runtime_path_ids: ["sdk"],
      verification_connector_ids: ["generic_rest"],
      native_tool_family_ids: [],
      next_steps: [],
    },
    ...overrides,
  };
}

function genericStatus(
  overrides: Partial<GenericRestConnectorStatusResponse> = {},
): GenericRestConnectorStatusResponse {
  return {
    connected: false,
    connector_type: "generic_rest_api",
    base_url: null,
    path_template: null,
    record_path: null,
    query: null,
    has_bearer_token: false,
    bearer_token_last4: null,
    last_tested_at: null,
    health_status: "not_configured",
    last_verdict: null,
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: null,
    last_retryable: null,
    last_checked_at: null,
    readiness: { status: "not_ready" },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function stripeStatus(
  overrides: Partial<StripeRefundConnectorStatusResponse> = {},
): StripeRefundConnectorStatusResponse {
  return {
    connected: false,
    connector_type: "stripe_refund",
    base_url: "https://api.stripe.com",
    path_template: "/v1/refunds/{refund_id}",
    record_path: null,
    query: null,
    has_bearer_token: false,
    bearer_token_last4: null,
    last_tested_at: null,
    health_status: "not_configured",
    last_verdict: null,
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: null,
    last_retryable: null,
    last_checked_at: null,
    readiness: { status: "not_ready" },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function stripePaymentStatus(
  overrides: Partial<StripePaymentConnectorStatusResponse> = {},
): StripePaymentConnectorStatusResponse {
  return {
    connected: false,
    connector_type: "stripe_payment",
    base_url: "https://api.stripe.com",
    path_template: "/v1/payment_intents/{payment_id}",
    record_path: null,
    query: null,
    has_bearer_token: false,
    bearer_token_last4: null,
    last_tested_at: null,
    health_status: "not_configured",
    last_verdict: null,
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: null,
    last_retryable: null,
    last_checked_at: null,
    readiness: { status: "not_ready" },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function razorpayStatus(
  overrides: Partial<RazorpayRefundConnectorStatusResponse> = {},
): RazorpayRefundConnectorStatusResponse {
  return {
    connected: false,
    connector_type: "razorpay_refund",
    base_url: "https://api.razorpay.com",
    path_template: "/v1/refunds/{refund_id}",
    record_path: null,
    query: { key_id: "rzp_test_key" },
    has_bearer_token: false,
    bearer_token_last4: null,
    last_tested_at: null,
    health_status: "not_configured",
    last_verdict: null,
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: null,
    last_retryable: null,
    last_checked_at: null,
    readiness: { status: "not_ready" },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function shopifyStatus(
  overrides: Partial<ShopifyConnectorStatusResponse> = {},
): ShopifyConnectorStatusResponse {
  return {
    connected: false,
    connector_type: "shopify_admin",
    base_url: "https://example.myshopify.com",
    path_template: "/admin/api/2025-01/orders/{record_ref}.json",
    record_path: "order",
    query: null,
    has_bearer_token: false,
    bearer_token_last4: null,
    last_tested_at: null,
    health_status: "not_configured",
    last_verdict: null,
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: null,
    last_retryable: null,
    last_checked_at: null,
    readiness: { status: "not_ready" },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function netsuiteStatus(
  overrides: Partial<NetSuiteFinanceConnectorStatusResponse> = {},
): NetSuiteFinanceConnectorStatusResponse {
  return {
    connected: false,
    connector_type: "netsuite_finance",
    base_url: "https://example.suitetalk.api.netsuite.com",
    path_template: "/services/rest/record/v1/{record_type}/{record_ref}",
    record_path: null,
    query: null,
    has_bearer_token: false,
    bearer_token_last4: null,
    last_tested_at: null,
    health_status: "not_configured",
    last_verdict: null,
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: null,
    last_retryable: null,
    last_checked_at: null,
    readiness: { status: "not_ready" },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function hubspotStatus(
  overrides: Partial<HubSpotCrmConnectorStatusResponse> = {},
): HubSpotCrmConnectorStatusResponse {
  return {
    connected: false,
    connector_type: "hubspot_crm",
    base_url: null,
    path_template: null,
    record_path: null,
    query: null,
    has_bearer_token: false,
    bearer_token_last4: null,
    last_tested_at: null,
    health_status: "not_configured",
    last_verdict: null,
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: null,
    last_retryable: null,
    last_checked_at: null,
    readiness: { status: "not_ready" },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function salesforceStatus(
  overrides: Partial<SalesforceCrmConnectorStatusResponse> = {},
): SalesforceCrmConnectorStatusResponse {
  return {
    connected: false,
    connector_type: "salesforce_crm",
    base_url: null,
    path_template: null,
    record_path: null,
    query: null,
    has_bearer_token: false,
    bearer_token_last4: null,
    last_tested_at: null,
    health_status: "not_configured",
    last_verdict: null,
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: null,
    last_retryable: null,
    last_checked_at: null,
    readiness: { status: "not_ready" },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}
function zohoStatus(
  overrides: Partial<ZohoCrmConnectorStatusResponse> = {},
): ZohoCrmConnectorStatusResponse {
  return {
    connected: false,
    connector_type: "zoho_crm",
    base_url: null,
    path_template: null,
    record_path: null,
    query: null,
    has_bearer_token: false,
    bearer_token_last4: null,
    has_oauth_refresh_token: false,
    oauth_refresh_token_last4: null,
    last_tested_at: null,
    health_status: "not_configured",
    last_verdict: null,
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: null,
    last_retryable: null,
    last_checked_at: null,
    readiness: { status: "not_ready" },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function zendeskStatus(
  overrides: Partial<ZendeskTicketConnectorStatusResponse> = {},
): ZendeskTicketConnectorStatusResponse {
  return {
    connected: false,
    connector_type: "zendesk_ticket",
    base_url: null,
    path_template: null,
    record_path: null,
    query: null,
    has_bearer_token: false,
    bearer_token_last4: null,
    last_tested_at: null,
    health_status: "not_configured",
    last_verdict: null,
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: null,
    last_retryable: null,
    last_checked_at: null,
    readiness: { status: "not_ready" },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function jiraStatus(
  overrides: Partial<JiraIssueConnectorStatusResponse> = {},
): JiraIssueConnectorStatusResponse {
  return {
    connected: false,
    connector_type: "jira_issue",
    base_url: null,
    path_template: null,
    record_path: null,
    query: null,
    has_bearer_token: false,
    bearer_token_last4: null,
    last_tested_at: null,
    health_status: "not_configured",
    last_verdict: null,
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: null,
    last_retryable: null,
    last_checked_at: null,
    readiness: { status: "not_ready" },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function postgresStatus(
  overrides: Partial<PostgresReadConnectorStatusResponse> = {},
): PostgresReadConnectorStatusResponse {
  return {
    connected: false,
    connector_type: "postgres_read",
    base_url: null,
    path_template: null,
    record_path: null,
    query: null,
    has_database_url: false,
    database_url_last4: null,
    has_read_query: false,
    read_query_digest: null,
    has_bearer_token: false,
    bearer_token_last4: null,
    last_tested_at: null,
    health_status: "not_configured",
    last_verdict: null,
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: null,
    last_retryable: null,
    last_checked_at: null,
    readiness: { status: "not_ready" },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function genericCheck(overrides: Partial<OutcomeReconciliationView> = {}): OutcomeReconciliationView {
  return {
    id: "check_generic_1",
    project_id: "project_1",
    call_id: null,
    trace_id: null,
    runtime_policy_decision_id: null,
    action_type: "internal_api_mutation",
    connector_type: "generic_rest_api",
    system_ref: "generic:record_1001",
    verdict: "matched",
    reason: "all_compared_fields_matched",
    amount_usd: null,
    currency: null,
    claimed: { record_ref: "record_1001", status: "approved" },
    actual: { record_ref: "record_1001", status: "approved" },
    comparison: { compared_fields: ["status"], mismatches: [] },
    idempotency_key: null,
    metadata: { connector_kind: "generic_rest_api" },
    checked_at: "2026-06-24T09:02:00Z",
    created_at: "2026-06-24T09:02:00Z",
    ...overrides,
  };
}

function renderWithConnector(connector: string) {
  window.history.pushState({}, "", `/integrations?connector=${connector}`);
  render(<IntegrationsPage />);
}

function clickFirstButton(name: string) {
  fireEvent.click(screen.getAllByRole("button", { name })[0]);
}

describe("IntegrationsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.pushState({}, "", "/integrations");
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: clipboardWrite },
    });
    clipboardWrite.mockResolvedValue(undefined);
    api.getMcpUpstreamBinding.mockResolvedValue(null);
    api.getGithubConnectionStatus.mockResolvedValue({
      connected: true,
      github_id: "gh_1",
      github_login: "zroky",
      scopes: ["repo"],
      connected_at: "2026-06-24T09:00:00Z",
      updated_at: "2026-06-24T09:00:00Z",
    });
    api.getSlackInstallStatus.mockResolvedValue({
      connected: false,
      team_id: null,
      team_name: null,
      channel_id: null,
      channel_name: null,
      bot_user_id: null,
      scopes: [],
      installed_by_user: null,
      installed_at: null,
      updated_at: null,
    });
    api.getLedgerRefundConnectorStatus.mockResolvedValue({
      connected: true,
      connector_type: "ledger_refund_api",
      base_url: "https://ledger.internal",
      path_template: "/refunds/{refund_id}",
      record_path: "refund",
      query: null,
      has_bearer_token: true,
      bearer_token_last4: "1234",
      last_tested_at: "2026-06-24T09:01:00Z",
      health_status: "healthy",
      last_verdict: "matched",
      last_error: null,
      last_error_code: null,
      last_http_status: 200,
      last_attempts: 1,
      last_retryable: false,
      last_checked_at: "2026-06-24T09:01:00Z",
      readiness: { status: "ready" },
      created_at: "2026-06-24T09:00:00Z",
      updated_at: "2026-06-24T09:01:00Z",
    });
    api.getCustomerRecordConnectorStatus.mockResolvedValue({
      connected: true,
      connector_type: "customer_record_api",
      base_url: "https://crm.internal",
      path_template: "/customers/{customer_id}",
      record_path: "customer",
      query: null,
      has_bearer_token: true,
      bearer_token_last4: "9876",
      last_tested_at: null,
      health_status: "healthy",
      last_verdict: null,
      last_error: null,
      last_error_code: null,
      last_http_status: null,
      last_attempts: null,
      last_retryable: null,
      last_checked_at: null,
      readiness: {
        status: "not_ready",
        blockers: ["Latest connector test did not reconcile as matched."],
      },
      created_at: "2026-06-24T09:00:00Z",
      updated_at: "2026-06-24T09:00:00Z",
    });
    api.getGenericRestConnectorStatus.mockResolvedValue(genericStatus());
    api.getStripeRefundConnectorStatus.mockResolvedValue(stripeStatus());
    api.getStripePaymentConnectorStatus.mockResolvedValue(stripePaymentStatus());
    api.getRazorpayRefundConnectorStatus.mockResolvedValue(razorpayStatus());
    api.getNetSuiteFinanceConnectorStatus.mockResolvedValue(netsuiteStatus());
    api.getShopifyConnectorStatus.mockResolvedValue(shopifyStatus());
    api.getHubSpotCrmConnectorStatus.mockResolvedValue(hubspotStatus());
    api.getSalesforceCrmConnectorStatus.mockResolvedValue(salesforceStatus());
    api.getZendeskTicketConnectorStatus.mockResolvedValue(zendeskStatus());
    api.getJiraIssueConnectorStatus.mockResolvedValue(jiraStatus());
    api.getZohoCrmConnectorStatus.mockResolvedValue(zohoStatus());
    api.startZohoCrmOAuth.mockResolvedValue({
      authorization_url: "https://accounts.zoho.com/oauth/v2/auth?state=test",
    });
    api.startJiraIssueOAuth.mockResolvedValue({
      authorization_url: "https://auth.atlassian.com/authorize?state=test",
    });
    api.getPostgresReadConnectorStatus.mockResolvedValue(postgresStatus({
      connected: true,
      has_database_url: true,
      has_read_query: true,
      read_query_digest: "sha256:query",
      health_status: "healthy",
      last_verdict: "matched",
      readiness: { status: "ready" },
      last_checked_at: "2026-06-24T09:03:00Z",
    }));
    api.savePostgresReadConnectorConfig.mockResolvedValue(postgresStatus({
      connected: true,
      has_database_url: true,
      has_read_query: true,
      read_query_digest: "sha256:replacement",
      health_status: "not_verified",
    }));
    api.testPostgresReadConnector.mockResolvedValue({
      ok: true,
      check: genericCheck({
        connector_type: "postgres_read",
        system_ref: "record_1001",
        action_type: "database_record_update",
        metadata: { connector_kind: "postgres_read" },
      }),
      connector: postgresStatus({
        connected: true,
        has_database_url: true,
        has_read_query: true,
        read_query_digest: "sha256:replacement",
        health_status: "healthy",
        last_verdict: "matched",
        readiness: { status: "ready" },
      }),
    });
    api.listOutcomeReconciliations.mockResolvedValue({
      items: [
        {
          id: "check_1",
          project_id: "project_1",
          call_id: "call_1",
          trace_id: "trace_1",
          runtime_policy_decision_id: "decision_1",
          action_type: "refund",
          connector_type: "ledger_refund_api",
          system_ref: "refund_1",
          verdict: "matched",
          reason: null,
          amount_usd: 122,
          currency: "USD",
          claimed: { status: "refunded" },
          actual: { status: "refunded" },
          comparison: { status: true },
          idempotency_key: null,
          metadata: { connector_kind: "ledger_refund_api" },
          checked_at: "2026-06-24T09:01:00Z",
          created_at: "2026-06-24T09:01:00Z",
        },
      ],
      total_in_page: 1,
    });
    api.getToolRegistry.mockResolvedValue(toolRegistry());
    api.listSourceConnectors.mockResolvedValue({ items: [] });
    api.saveGenericRestConnectorConfig.mockResolvedValue(genericStatus({
      connected: true,
      base_url: "https://internal.example.com/api",
      path_template: "/records/{record_ref}",
      record_path: "data",
      has_bearer_token: true,
      bearer_token_last4: "7890",
      health_status: "not_verified",
    }));
    api.testGenericRestConnector.mockResolvedValue({
      ok: true,
      check: genericCheck(),
      connector: genericStatus({
        connected: true,
        base_url: "https://internal.example.com/api",
        path_template: "/records/{record_ref}",
        record_path: "data",
        has_bearer_token: true,
        bearer_token_last4: "7890",
        health_status: "healthy",
        last_verdict: "matched",
        readiness: { status: "ready" },
      }),
    });
    api.saveStripeRefundConnectorConfig.mockResolvedValue(stripeStatus({
      connected: true,
      has_bearer_token: true,
      bearer_token_last4: "7890",
      health_status: "not_verified",
    }));
    api.testStripeRefundConnector.mockResolvedValue({
      ok: true,
      check: genericCheck({
        connector_type: "stripe_refund",
        system_ref: "stripe:refund:re_123",
        action_type: "refund",
        actual: {
          refund_id: "re_123",
          stripe_refund_id: "re_123",
          amount_minor: 4250,
          amount_major: "42.5",
          amount_usd: 42.5,
          currency: "USD",
          status: "succeeded",
        },
        metadata: { connector_kind: "stripe_refund" },
      }),
      connector: stripeStatus({
        connected: true,
        has_bearer_token: true,
        bearer_token_last4: "7890",
        health_status: "healthy",
        last_verdict: "matched",
        readiness: { status: "ready" },
      }),
    });
    api.saveStripePaymentConnectorConfig.mockResolvedValue(stripePaymentStatus({
      connected: true,
      has_bearer_token: true,
      bearer_token_last4: "7890",
      health_status: "not_verified",
    }));
    api.testStripePaymentConnector.mockResolvedValue({
      ok: true,
      check: genericCheck({
        connector_type: "stripe_payment",
        system_ref: "stripe:payment_intent:pi_123",
        action_type: "payment_adjustment",
        claimed: {
          payment_id: "pi_123",
          amount_minor: 4250,
          amount_major: "42.5",
          currency: "USD",
          status: "succeeded",
        },
        actual: {
          payment_id: "pi_123",
          stripe_payment_intent_id: "pi_123",
          amount_minor: 4250,
          amount_major: "42.5",
          amount_usd: 42.5,
          currency: "USD",
          status: "succeeded",
        },
        metadata: { connector_kind: "stripe_payment" },
      }),
      connector: stripePaymentStatus({
        connected: true,
        has_bearer_token: true,
        bearer_token_last4: "7890",
        health_status: "healthy",
        last_verdict: "matched",
        readiness: { status: "ready" },
      }),
    });
    api.saveRazorpayRefundConnectorConfig.mockResolvedValue(razorpayStatus({
      connected: true,
      has_bearer_token: true,
      bearer_token_last4: "cret",
      health_status: "not_verified",
    }));
    api.testRazorpayRefundConnector.mockResolvedValue({
      ok: true,
      check: genericCheck({
        connector_type: "razorpay_refund",
        system_ref: "razorpay:refund:rfnd_123",
        action_type: "refund",
        actual: {
          refund_id: "rfnd_123",
          razorpay_refund_id: "rfnd_123",
          amount_minor: 4250,
          amount_major: "42.5",
          currency: "INR",
          status: "processed",
        },
        metadata: { connector_kind: "razorpay_refund" },
      }),
      connector: razorpayStatus({
        connected: true,
        has_bearer_token: true,
        bearer_token_last4: "cret",
        health_status: "healthy",
        last_verdict: "matched",
        readiness: { status: "ready" },
      }),
    });
    api.saveHubSpotCrmConnectorConfig.mockResolvedValue(hubspotStatus({
      connected: true,
      base_url: "https://api.hubapi.com",
      path_template: "/crm/v3/objects/contacts/{record_ref}",
      query: {
        properties: "email,firstname,lifecyclestage,hs_object_id",
        idProperty: "email",
      },
      has_bearer_token: true,
      bearer_token_last4: "7890",
      health_status: "not_verified",
    }));
    api.testHubSpotCrmConnector.mockResolvedValue({
      ok: true,
      check: genericCheck({
        connector_type: "hubspot_crm",
        system_ref: "hubspot:contact:owner@example.com",
        action_type: "customer_record_update",
        metadata: { connector_kind: "hubspot_crm" },
      }),
      connector: hubspotStatus({
        connected: true,
        base_url: "https://api.hubapi.com",
        path_template: "/crm/v3/objects/contacts/{record_ref}",
        query: {
          properties: "email,firstname,lifecyclestage,hs_object_id",
          idProperty: "email",
        },
        has_bearer_token: true,
        bearer_token_last4: "7890",
        health_status: "healthy",
        last_verdict: "matched",
        readiness: { status: "ready" },
      }),
    });
    api.saveSalesforceCrmConnectorConfig.mockResolvedValue(salesforceStatus({
      connected: true,
      base_url: "https://example.my.salesforce.com",
      path_template: "/services/data/v60.0/sobjects/{object_type}/{record_ref}",
      query: {
        fields: "Id,Name,StageName,Amount",
      },
      has_bearer_token: true,
      bearer_token_last4: "7890",
      health_status: "not_verified",
    }));
    api.testSalesforceCrmConnector.mockResolvedValue({
      ok: true,
      check: genericCheck({
        connector_type: "salesforce_crm",
        system_ref: "salesforce:Account:001000000000000AAA",
        action_type: "customer_record_update",
        metadata: { connector_kind: "salesforce_crm" },
      }),
      connector: salesforceStatus({
        connected: true,
        base_url: "https://example.my.salesforce.com",
        path_template: "/services/data/v60.0/sobjects/{object_type}/{record_ref}",
        query: {
          fields: "Id,Name,StageName,Amount",
        },
        has_bearer_token: true,
        bearer_token_last4: "7890",
        health_status: "healthy",
        last_verdict: "matched",
        readiness: { status: "ready" },
      }),
    });
    api.saveZohoCrmConnectorConfig.mockResolvedValue(zohoStatus({
      connected: true,
      base_url: "https://www.zohoapis.com",
      path_template: "/crm/v8/{module_name}/{record_ref}",
      record_path: "data.0",
      query: {
        fields: "id,Full_Name,Email,Phone,Company,Stage,Amount,Lead_Status,Owner,Modified_Time",
      },
      has_bearer_token: true,
      bearer_token_last4: "7890",
      health_status: "not_verified",
    }));
    api.testZohoCrmConnector.mockResolvedValue({
      ok: true,
      check: genericCheck({
        connector_type: "zoho_crm",
        system_ref: "zoho:Contacts:1234567890000000001",
        action_type: "customer_record_update",
        metadata: { connector_kind: "zoho_crm" },
      }),
      connector: zohoStatus({
        connected: true,
        base_url: "https://www.zohoapis.com",
        path_template: "/crm/v8/{module_name}/{record_ref}",
        record_path: "data.0",
        query: {
          fields: "id,Full_Name,Email,Phone,Company,Stage,Amount,Lead_Status,Owner,Modified_Time",
        },
        has_bearer_token: true,
        bearer_token_last4: "7890",
        health_status: "healthy",
        last_verdict: "matched",
        readiness: { status: "ready" },
      }),
    });
    api.saveZendeskTicketConnectorConfig.mockResolvedValue(zendeskStatus({
      connected: true,
      base_url: "https://example.zendesk.com",
      path_template: "/api/v2/tickets/{record_ref}.json",
      record_path: "ticket",
      query: { auth_username: "agent@example.com" },
      has_bearer_token: true,
      bearer_token_last4: "7890",
      health_status: "not_verified",
    }));
    api.testZendeskTicketConnector.mockResolvedValue({
      ok: true,
      check: genericCheck({
        connector_type: "zendesk_ticket",
        system_ref: "zendesk:ticket:12345",
        action_type: "ticket_close",
        metadata: { connector_kind: "zendesk_ticket" },
      }),
      connector: zendeskStatus({
        connected: true,
        base_url: "https://example.zendesk.com",
        path_template: "/api/v2/tickets/{record_ref}.json",
        record_path: "ticket",
        query: { auth_username: "agent@example.com" },
        has_bearer_token: true,
        bearer_token_last4: "7890",
        health_status: "healthy",
        last_verdict: "matched",
        readiness: { status: "ready" },
      }),
    });
    api.saveJiraIssueConnectorConfig.mockResolvedValue(jiraStatus({
      connected: true,
      base_url: "https://example.atlassian.net",
      path_template: "/rest/api/3/issue/{record_ref}",
      query: { auth_username: "agent@example.com" },
      has_bearer_token: true,
      bearer_token_last4: "7890",
      health_status: "not_verified",
    }));
    api.testJiraIssueConnector.mockResolvedValue({
      ok: true,
      check: genericCheck({
        connector_type: "jira_issue",
        system_ref: "jira:issue:JSM-123",
        action_type: "ticket_close",
        metadata: { connector_kind: "jira_issue" },
      }),
      connector: jiraStatus({
        connected: true,
        base_url: "https://example.atlassian.net",
        path_template: "/rest/api/3/issue/{record_ref}",
        query: { auth_username: "agent@example.com" },
        has_bearer_token: true,
        bearer_token_last4: "7890",
        health_status: "healthy",
        last_verdict: "matched",
        readiness: { status: "ready" },
      }),
    });
    api.saveNetSuiteFinanceConnectorConfig.mockResolvedValue(netsuiteStatus({
      connected: true,
      has_bearer_token: true,
      bearer_token_last4: "oken",
      health_status: "not_verified",
    }));
    api.testNetSuiteFinanceConnector.mockResolvedValue({
      ok: true,
      check: genericCheck({
        connector_type: "netsuite_finance",
        system_ref: "netsuite:vendorBill:12345",
        action_type: "invoice_spend_approval",
        claimed: {
          netsuite_record_id: "12345",
          record_type: "vendorBill",
          tran_id: "VB1001",
          amount_minor: 125000,
          amount_major: "1250",
          currency: "USD",
          status: "approved",
        },
        actual: {
          netsuite_record_id: "12345",
          record_type: "vendorBill",
          tran_id: "VB1001",
          amount_minor: 125000,
          amount_major: "1250",
          currency: "USD",
          status: "approved",
        },
        metadata: { connector_kind: "netsuite_finance" },
      }),
      connector: netsuiteStatus({
        connected: true,
        has_bearer_token: true,
        bearer_token_last4: "oken",
        health_status: "healthy",
        last_verdict: "matched",
        readiness: { status: "ready" },
      }),
    });
    api.saveShopifyConnectorConfig.mockResolvedValue(shopifyStatus({
      connected: true,
      has_bearer_token: true,
      bearer_token_last4: "oken",
      health_status: "not_verified",
    }));
    api.testShopifyConnector.mockResolvedValue({
      ok: true,
      check: genericCheck({
        connector_type: "shopify_admin",
        system_ref: "shopify:order:1001",
        action_type: "shopify_record",
        claimed: {
          order_id: "1001",
          amount_major: "42.5",
          currency: "USD",
          financial_status: "paid",
          fulfillment_status: "fulfilled",
        },
        actual: {
          order_id: "1001",
          amount_major: "42.5",
          currency: "USD",
          financial_status: "paid",
          fulfillment_status: "fulfilled",
        },
        metadata: { connector_kind: "shopify_admin" },
      }),
      connector: shopifyStatus({
        connected: true,
        has_bearer_token: true,
        bearer_token_last4: "oken",
        health_status: "healthy",
        last_verdict: "matched",
        readiness: { status: "ready" },
      }),
    });
    api.saveMcpUpstreamDraft.mockResolvedValue(mcpStatus());
    api.preflightMcpUpstream.mockResolvedValue({
      binding: mcpStatus({
        test_status: "succeeded",
        tested_at: "2026-07-11T09:01:00Z",
        version: 2,
      }),
      discovered_tools: ["refund.create", "refund.read"],
    });
    api.activateMcpUpstream.mockResolvedValue(mcpStatus({
      status: "active",
      test_status: "succeeded",
      tested_at: "2026-07-11T09:01:00Z",
      activated_at: "2026-07-11T09:02:00Z",
      version: 3,
    }));
    api.disableMcpUpstream.mockResolvedValue(mcpStatus({
      status: "disabled",
      test_status: "succeeded",
      version: 4,
    }));
  });

  it("frames connectors as a simple verifier inventory with search", async () => {
    render(<IntegrationsPage />);

    expect(
      await screen.findByRole("heading", { name: "Connectors" }),
    ).toBeInTheDocument();

    expect(screen.getByRole("region", { name: "Recent test-reads" })).toBeInTheDocument();
    expect(screen.getByText("Primitive")).toBeInTheDocument();
    expect(screen.queryByText("Action")).not.toBeInTheDocument();
    expect(screen.getByText("Selected")).toBeInTheDocument();
    expect(screen.getAllByText("Available").length).toBeGreaterThan(0);

    expect(screen.getByRole("heading", { name: "Available systems" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Stripe refund verifier setup" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Payments · Transactions · Refunds").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Missing / Not connected").length).toBeGreaterThan(0);
    clickFirstButton("Connect Stripe");
    expect(screen.getByRole("region", { name: "Stripe refund verifier setup" })).toBeInTheDocument();
    await waitFor(() => expect(api.listSourceConnectors).toHaveBeenCalled());
    expect(screen.getByRole("region", { name: "Payments" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Workflow" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Developer / Custom APIs" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Commerce" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "CRM" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Support & ITSM" })).toBeInTheDocument();
    expect(screen.getAllByText("Custom REST API").length).toBeGreaterThan(0);
    expect(screen.getAllByText("HubSpot CRM").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Salesforce CRM").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Zendesk ticket").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Jira / JSM").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Stripe").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Payments · Transactions · Refunds").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Shopify Admin").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SQL database").length).toBeGreaterThan(0);
    expect(screen.getAllByText("GitHub").length).toBeGreaterThan(0);
    expect(screen.queryByRole("region", { name: "Finance & ERP" })).not.toBeInTheDocument();
    expect(screen.queryByText("Razorpay")).not.toBeInTheDocument();
    expect(screen.queryByText("Slack")).not.toBeInTheDocument();
    expect(screen.queryByText("Zoho CRM")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search connectors"), { target: { value: "stripe" } });
    expect(screen.getByRole("button", { name: /Stripe.*Payments.*Transactions.*Refunds/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Stripe payment/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /HubSpot CRM/i })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search connectors"), { target: { value: "OAuth" } });
    expect(screen.getByRole("button", { name: /GitHub.*One-click OAuth/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Slack.*One-click OAuth/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Zoho CRM.*OAuth/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Jira.*Available/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Stripe.*Restricted key/i })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search connectors"), { target: { value: "no matching connector" } });
    expect(screen.getByText("No connectors match this search")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search connectors"), { target: { value: "" } });

    expect(screen.queryByRole("heading", { name: "Native verifier coverage" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Connector readiness diagnostics" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Integration status" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Detailed connector controls" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Detailed controls" })).not.toBeInTheDocument();

    await waitFor(() => expect(api.listOutcomeReconciliations).toHaveBeenCalledWith({ limit: 50 }));
    await waitFor(() => expect(api.getGenericRestConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getStripePaymentConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getRazorpayRefundConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getShopifyConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getHubSpotCrmConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getSalesforceCrmConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getZohoCrmConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getPostgresReadConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getToolRegistry).toHaveBeenCalledTimes(1));
  });

  it("keeps connect primary and lets refresh retry connector feeds", async () => {
    api.getGenericRestConnectorStatus.mockRejectedValueOnce(new Error("feed unavailable"));
    render(<IntegrationsPage />);

    await screen.findByRole("heading", { name: "Connectors" });
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Connect Stripe" }).length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => expect(api.getGenericRestConnectorStatus).toHaveBeenCalledTimes(2));
  });

  it("shows only launch connector test-read activity", async () => {
    api.listOutcomeReconciliations.mockResolvedValueOnce({
      items: [
        genericCheck({
          connector_type: "stripe_refund",
          metadata: { connector_kind: "stripe_refund" },
          verdict: "mismatched",
          checked_at: "2026-06-24T09:11:00Z",
        }),
        genericCheck({
          connector_type: "razorpay_refund",
          metadata: { connector_kind: "razorpay_refund" },
          checked_at: "2026-06-24T09:12:00Z",
        }),
      ],
      total_in_page: 2,
    });
    render(<IntegrationsPage />);

    const audit = await screen.findByRole("region", { name: "Recent test-reads" });
    await waitFor(() => expect(within(audit).getByText("Stripe")).toBeInTheDocument());

    expect(within(audit).getByText("Mismatched")).toBeInTheDocument();
    expect(within(audit).queryByText("Razorpay")).not.toBeInTheDocument();
    expect(within(audit).queryByText("No test-reads yet.")).not.toBeInTheDocument();
  });

  it("saves and tests the Generic REST verifier setup path", async () => {
    render(<IntegrationsPage />);

    await screen.findByRole("heading", { name: "Connectors" });
    fireEvent.click(screen.getByRole("button", { name: /Custom REST API/i }));
    clickFirstButton("Connect custom REST");
    fireEvent.change(screen.getByLabelText("Base URL"), {
      target: { value: "https://internal.example.com/api" },
    });
    fireEvent.change(screen.getByLabelText("Path template"), {
      target: { value: "/records/{record_ref}" },
    });
    fireEvent.change(screen.getByLabelText("Bearer token"), {
      target: { value: "generic-secret-token" },
    });
    fireEvent.change(screen.getByLabelText("Record ref"), {
      target: { value: "invoice_42" },
    });
    fireEvent.change(screen.getByLabelText("Action type"), {
      target: { value: "invoice_spend_approval" },
    });
    fireEvent.change(screen.getByLabelText("Claimed JSON"), {
      target: {
        value: JSON.stringify(
          {
            record_ref: "invoice_42",
            status: "approved",
            amount_usd: 4200,
          },
          null,
          2,
        ),
      },
    });

    fireEvent.click(screen.getByText("Advanced: webhook bridge request"));
    fireEvent.click(screen.getByRole("button", { name: "Copy bridge request" }));
    await waitFor(() => {
      expect(clipboardWrite).toHaveBeenCalledWith(expect.stringContaining("/v1/outcomes/reconciliation/saved"));
      expect(clipboardWrite).toHaveBeenCalledWith(expect.stringContaining('"connector": "generic_rest"'));
      expect(clipboardWrite).toHaveBeenCalledWith(expect.stringContaining('"record_ref": "invoice_42"'));
      expect(clipboardWrite).toHaveBeenCalledWith(expect.stringContaining('"action_type": "invoice_spend_approval"'));
    });
    expect(String(clipboardWrite.mock.calls[0]?.[0])).not.toContain("generic-secret-token");
    expect(String(clipboardWrite.mock.calls[0]?.[0])).not.toContain("bearer_token");

    fireEvent.click(screen.getByRole("button", { name: /Save verifier/i }));

    await waitFor(() => {
      expect(api.saveGenericRestConnectorConfig).toHaveBeenCalledWith({
        base_url: "https://internal.example.com/api",
        path_template: "/records/{record_ref}",
        record_path: "data",
        bearer_token: "generic-secret-token",
      });
    });

    fireEvent.click(await screen.findByRole("button", { name: /Run proof test/i }));

    await waitFor(() => {
      expect(api.testGenericRestConnector).toHaveBeenCalledWith({
        record_ref: "invoice_42",
        action_type: "invoice_spend_approval",
        system_ref: "invoice_42",
        claimed: {
          record_ref: "invoice_42",
          status: "approved",
          amount_usd: 4200,
        },
        match_fields: ["status"],
      });
    });
    expect(await screen.findByText("REST verifier test recorded matched.")).toBeInTheDocument();
  });

  it("saves and tests the native Stripe payment verifier setup path", async () => {
    renderWithConnector("stripe_payment");

    await screen.findByRole("heading", { name: "Connectors" });
    clickFirstButton("Connect Stripe");
    fireEvent.change(screen.getByLabelText("Stripe secret key"), {
      target: { value: "sk_live_payment" },
    });
    fireEvent.change(screen.getByLabelText("PaymentIntent ID"), {
      target: { value: "pi_123" },
    });
    fireEvent.change(screen.getByLabelText("Claimed JSON"), {
      target: {
        value: JSON.stringify(
          {
            payment_id: "pi_123",
            amount_minor: 4250,
            amount_major: "42.5",
            currency: "USD",
            status: "succeeded",
          },
          null,
          2,
        ),
      },
    });

    fireEvent.click(screen.getByRole("button", { name: /Save access/i }));

    await waitFor(() => {
      expect(api.saveStripePaymentConnectorConfig).toHaveBeenCalledWith({
        bearer_token: "sk_live_payment",
      });
    });

    fireEvent.click(await screen.findByRole("button", { name: /Run preflight/i }));

    await waitFor(() => {
      expect(api.testStripePaymentConnector).toHaveBeenCalledWith({
        payment_id: "pi_123",
        action_type: "payment_adjustment",
        claimed: {
          payment_id: "pi_123",
          amount_minor: 4250,
          amount_major: "42.5",
          currency: "USD",
          status: "succeeded",
        },
        match_fields: ["payment_id", "amount_minor", "currency", "status"],
      });
    });
    expect(await screen.findByText("Stripe payment verifier test recorded matched.")).toBeInTheDocument();
  });

  it("configures automatic Stripe refund proof using only a credential reference", async () => {
    const connector = {
      id: "source_connector_1",
      project_id: "project_1",
      environment: "production",
      capability: "stripe_refund.read",
      connector_kind: "stripe",
      secret_ref: "STRIPE_KEY_OLD",
      config: {},
      status: "disabled",
      created_at: "2026-08-04T09:00:00Z",
      updated_at: "2026-08-04T09:00:00Z",
    };
    api.listSourceConnectors.mockResolvedValue({ items: [connector] });
    api.upsertSourceConnector
      .mockResolvedValueOnce({ ...connector, secret_ref: "STRIPE_KEY_DEMO", status: "active" })
      .mockResolvedValueOnce({ ...connector, secret_ref: "STRIPE_KEY_DEMO", status: "disabled" });

    renderWithConnector("stripe_refund");
    await screen.findByRole("heading", { name: "Connectors" });
    clickFirstButton("Connect Stripe");

    const panel = await screen.findByRole("region", { name: "Stripe refund automatic source check" });
    await waitFor(() => {
      expect(api.listSourceConnectors).toHaveBeenCalledWith(
        { environment: "production", capability: "stripe_refund.read" },
        expect.any(AbortSignal),
      );
      expect((within(panel).getByLabelText("Credential environment variable") as HTMLInputElement).value).toBe("STRIPE_KEY_OLD");
    });

    fireEvent.change(within(panel).getByLabelText("Credential environment variable"), {
      target: { value: "STRIPE_KEY_DEMO" },
    });
    fireEvent.click(within(panel).getByRole("button", { name: "Enable automatic checks" }));

    await waitFor(() => {
      expect(api.upsertSourceConnector).toHaveBeenCalledWith({
        environment: "production",
        capability: "stripe_refund.read",
        connector_kind: "stripe",
        secret_ref: "STRIPE_KEY_DEMO",
        config: {},
        status: "active",
      });
    });

    fireEvent.click(await within(panel).findByRole("button", { name: "Disable automatic checks" }));
    await waitFor(() => {
      expect(api.upsertSourceConnector).toHaveBeenLastCalledWith({
        environment: "production",
        capability: "stripe_refund.read",
        connector_kind: "stripe",
        secret_ref: "STRIPE_KEY_DEMO",
        config: {},
        status: "disabled",
      });
    });
  });

  it("shows an active automatic Stripe source check as configured", async () => {
    api.listSourceConnectors.mockResolvedValue({
      items: [{
        id: "source_connector_active",
        project_id: "project_1",
        environment: "production",
        capability: "stripe_refund.read",
        connector_kind: "stripe",
        secret_ref: "STRIPE_KEY_DEMO",
        config: {},
        status: "active",
        created_at: "2026-08-04T09:00:00Z",
        updated_at: "2026-08-04T10:00:00Z",
      }],
    });

    renderWithConnector("stripe_refund");

    const inspector = await screen.findByRole("region", { name: "Selected connector" });
    expect(within(inspector).queryByText("Missing / Not connected")).not.toBeInTheDocument();
    expect(within(inspector).getByText("Saved")).toBeInTheDocument();
    expect(within(inspector).getByRole("button", { name: "Manage Stripe" })).toBeInTheDocument();
  });

  it("saves and tests the native Shopify Admin verifier setup path", async () => {
    renderWithConnector("shopify_admin");

    await screen.findByRole("heading", { name: "Connectors" });
    clickFirstButton("Connect Shopify Admin");
    fireEvent.change(screen.getByLabelText("Shop Admin base URL"), {
      target: { value: "https://example.myshopify.com" },
    });
    fireEvent.change(screen.getByLabelText("Admin API access token"), {
      target: { value: "shopify-read-token" },
    });
    fireEvent.change(screen.getByLabelText("Order ID"), {
      target: { value: "1001" },
    });
    fireEvent.change(screen.getByLabelText("Claimed JSON"), {
      target: {
        value: JSON.stringify(
          {
            order_id: "1001",
            amount_major: "42.5",
            currency: "USD",
            financial_status: "paid",
            fulfillment_status: "fulfilled",
          },
          null,
          2,
        ),
      },
    });

    fireEvent.click(screen.getByRole("button", { name: /Save access/i }));

    await waitFor(() => {
      expect(api.saveShopifyConnectorConfig).toHaveBeenCalledWith({
        base_url: "https://example.myshopify.com",
        bearer_token: "shopify-read-token",
      });
    });

    fireEvent.click(await screen.findByRole("button", { name: /Run preflight/i }));

    await waitFor(() => {
      expect(api.testShopifyConnector).toHaveBeenCalledWith({
        record_ref: "1001",
        action_type: "shopify_record",
        claimed: {
          order_id: "1001",
          amount_major: "42.5",
          currency: "USD",
          financial_status: "paid",
          fulfillment_status: "fulfilled",
        },
        match_fields: ["order_id", "amount_major", "currency", "financial_status"],
      });
    });
    expect(await screen.findByText("Shopify verifier test recorded matched.")).toBeInTheDocument();
  });

  it("saves and tests the native HubSpot verifier setup path", async () => {
    renderWithConnector("hubspot_crm");

    await screen.findByRole("heading", { name: "Connectors" });
    clickFirstButton("Connect HubSpot CRM");
    fireEvent.change(screen.getByLabelText("Private app token"), {
      target: { value: "hubspot-private-app-token" },
    });
    fireEvent.change(screen.getByLabelText("Contact ref"), {
      target: { value: "owner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Claimed JSON"), {
      target: {
        value: JSON.stringify(
          {
            email: "owner@example.com",
            lifecyclestage: "customer",
          },
          null,
          2,
        ),
      },
    });

    fireEvent.click(screen.getByRole("button", { name: /Save access/i }));

    await waitFor(() => {
      expect(api.saveHubSpotCrmConnectorConfig).toHaveBeenCalledWith({
        query: {
          properties: "email,firstname,lastname,lifecyclestage,hs_lead_status,hs_object_id",
          idProperty: "email",
        },
        bearer_token: "hubspot-private-app-token",
      });
    });

    fireEvent.click(await screen.findByRole("button", { name: /Run preflight/i }));

    await waitFor(() => {
      expect(api.testHubSpotCrmConnector).toHaveBeenCalledWith({
        record_ref: "owner@example.com",
        action_type: "customer_record_update",
        claimed: {
          email: "owner@example.com",
          lifecyclestage: "customer",
        },
        match_fields: ["email", "lifecyclestage"],
      });
    });
    expect(await screen.findByText("HubSpot verifier test recorded matched.")).toBeInTheDocument();
  });

  it("saves and tests the native Jira issue verifier setup path", async () => {
    renderWithConnector("jira_issue");

    await screen.findByRole("heading", { name: "Connectors" });
    clickFirstButton("Connect Jira / JSM");
    fireEvent.change(screen.getByLabelText("Atlassian email"), {
      target: { value: "agent@example.com" },
    });
    fireEvent.change(screen.getByLabelText("API token or bearer token"), {
      target: { value: "jira-api-token" },
    });
    fireEvent.change(screen.getByLabelText("Issue key"), {
      target: { value: "JSM-123" },
    });
    fireEvent.change(screen.getByLabelText("Claimed JSON"), {
      target: {
        value: JSON.stringify(
          {
            jira_issue_key: "JSM-123",
            status: "Done",
          },
          null,
          2,
        ),
      },
    });

    fireEvent.click(screen.getByRole("button", { name: /Save access/i }));

    await waitFor(() => {
      expect(api.saveJiraIssueConnectorConfig).toHaveBeenCalledWith({
        base_url: "https://example.atlassian.net",
        auth_username: "agent@example.com",
        bearer_token: "jira-api-token",
      });
    });

    fireEvent.click(await screen.findByRole("button", { name: /Run preflight/i }));

    await waitFor(() => {
      expect(api.testJiraIssueConnector).toHaveBeenCalledWith({
        record_ref: "JSM-123",
        action_type: "ticket_close",
        claimed: {
          jira_issue_key: "JSM-123",
          status: "Done",
        },
        match_fields: ["jira_issue_key", "status"],
      });
    });
    expect(await screen.findByText("Jira verifier test recorded matched.")).toBeInTheDocument();
  });

});
