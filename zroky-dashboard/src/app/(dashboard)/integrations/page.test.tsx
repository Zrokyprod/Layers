import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  GenericRestConnectorStatusResponse,
  HubSpotCrmConnectorStatusResponse,
  JiraIssueConnectorStatusResponse,
  NetSuiteFinanceConnectorStatusResponse,
  OutcomeReconciliationView,
  PostgresReadConnectorStatusResponse,
  RazorpayRefundConnectorStatusResponse,
  SalesforceCrmConnectorStatusResponse,
  StripeRefundConnectorStatusResponse,
  ToolRegistryResponse,
  ZendeskTicketConnectorStatusResponse,
  ZohoCrmConnectorStatusResponse,
} from "@/lib/api";
import { externalNavigator } from "@/lib/external-navigation";
import IntegrationsPage from "./page";

const api = vi.hoisted(() => ({
  getCustomerRecordConnectorStatus: vi.fn(),
  getGenericRestConnectorStatus: vi.fn(),
  getGithubConnectionStatus: vi.fn(),
  getHubSpotCrmConnectorStatus: vi.fn(),
  getJiraIssueConnectorStatus: vi.fn(),
  getLedgerRefundConnectorStatus: vi.fn(),
  getNetSuiteFinanceConnectorStatus: vi.fn(),
  getPostgresReadConnectorStatus: vi.fn(),
  getRazorpayRefundConnectorStatus: vi.fn(),
  getSalesforceCrmConnectorStatus: vi.fn(),
  getStripeRefundConnectorStatus: vi.fn(),
  getZendeskTicketConnectorStatus: vi.fn(),
  getZohoCrmConnectorStatus: vi.fn(),
  getSlackInstallStatus: vi.fn(),
  getToolRegistry: vi.fn(),
  listOutcomeReconciliations: vi.fn(),
  saveGenericRestConnectorConfig: vi.fn(),
  saveHubSpotCrmConnectorConfig: vi.fn(),
  saveJiraIssueConnectorConfig: vi.fn(),
  saveNetSuiteFinanceConnectorConfig: vi.fn(),
  saveRazorpayRefundConnectorConfig: vi.fn(),
  saveSalesforceCrmConnectorConfig: vi.fn(),
  saveStripeRefundConnectorConfig: vi.fn(),
  saveZendeskTicketConnectorConfig: vi.fn(),
  saveZohoCrmConnectorConfig: vi.fn(),
  startZohoCrmOAuth: vi.fn(),
  testGenericRestConnector: vi.fn(),
  testHubSpotCrmConnector: vi.fn(),
  testJiraIssueConnector: vi.fn(),
  testNetSuiteFinanceConnector: vi.fn(),
  testRazorpayRefundConnector: vi.fn(),
  testSalesforceCrmConnector: vi.fn(),
  testStripeRefundConnector: vi.fn(),
  testZendeskTicketConnector: vi.fn(),
  testZohoCrmConnector: vi.fn(),
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
    getCustomerRecordConnectorStatus: api.getCustomerRecordConnectorStatus,
    getGenericRestConnectorStatus: api.getGenericRestConnectorStatus,
    getGithubConnectionStatus: api.getGithubConnectionStatus,
    getHubSpotCrmConnectorStatus: api.getHubSpotCrmConnectorStatus,
    getJiraIssueConnectorStatus: api.getJiraIssueConnectorStatus,
    getLedgerRefundConnectorStatus: api.getLedgerRefundConnectorStatus,
    getNetSuiteFinanceConnectorStatus: api.getNetSuiteFinanceConnectorStatus,
    getPostgresReadConnectorStatus: api.getPostgresReadConnectorStatus,
    getRazorpayRefundConnectorStatus: api.getRazorpayRefundConnectorStatus,
    getSalesforceCrmConnectorStatus: api.getSalesforceCrmConnectorStatus,
    getStripeRefundConnectorStatus: api.getStripeRefundConnectorStatus,
    getZendeskTicketConnectorStatus: api.getZendeskTicketConnectorStatus,
    getZohoCrmConnectorStatus: api.getZohoCrmConnectorStatus,
    getSlackInstallStatus: api.getSlackInstallStatus,
    getToolRegistry: api.getToolRegistry,
    listOutcomeReconciliations: api.listOutcomeReconciliations,
    saveGenericRestConnectorConfig: api.saveGenericRestConnectorConfig,
    saveHubSpotCrmConnectorConfig: api.saveHubSpotCrmConnectorConfig,
    saveJiraIssueConnectorConfig: api.saveJiraIssueConnectorConfig,
    saveNetSuiteFinanceConnectorConfig: api.saveNetSuiteFinanceConnectorConfig,
    saveRazorpayRefundConnectorConfig: api.saveRazorpayRefundConnectorConfig,
    saveSalesforceCrmConnectorConfig: api.saveSalesforceCrmConnectorConfig,
    saveStripeRefundConnectorConfig: api.saveStripeRefundConnectorConfig,
    saveZendeskTicketConnectorConfig: api.saveZendeskTicketConnectorConfig,
    saveZohoCrmConnectorConfig: api.saveZohoCrmConnectorConfig,
    startZohoCrmOAuth: api.startZohoCrmOAuth,
    testGenericRestConnector: api.testGenericRestConnector,
    testHubSpotCrmConnector: api.testHubSpotCrmConnector,
    testJiraIssueConnector: api.testJiraIssueConnector,
    testNetSuiteFinanceConnector: api.testNetSuiteFinanceConnector,
    testRazorpayRefundConnector: api.testRazorpayRefundConnector,
    testSalesforceCrmConnector: api.testSalesforceCrmConnector,
    testStripeRefundConnector: api.testStripeRefundConnector,
    testZendeskTicketConnector: api.testZendeskTicketConnector,
    testZohoCrmConnector: api.testZohoCrmConnector,
  };
});

vi.mock("./system-of-record-connectors", () => ({
  default: () => (
    <section aria-label="Integration status">
      GitHub Slack system-of-record status
    </section>
  ),
}));

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
        dashboard_href: "/agents",
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

describe("IntegrationsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: clipboardWrite },
    });
    clipboardWrite.mockResolvedValue(undefined);
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
    api.getRazorpayRefundConnectorStatus.mockResolvedValue(razorpayStatus());
    api.getNetSuiteFinanceConnectorStatus.mockResolvedValue(netsuiteStatus());
    api.getHubSpotCrmConnectorStatus.mockResolvedValue(hubspotStatus());
    api.getSalesforceCrmConnectorStatus.mockResolvedValue(salesforceStatus());
    api.getZendeskTicketConnectorStatus.mockResolvedValue(zendeskStatus());
    api.getJiraIssueConnectorStatus.mockResolvedValue(jiraStatus());
    api.getZohoCrmConnectorStatus.mockResolvedValue(zohoStatus());
    api.startZohoCrmOAuth.mockResolvedValue({
      authorization_url: "https://accounts.zoho.com/oauth/v2/auth?state=test",
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
  });

  it("frames connectors as transport-first verifier inventory with coverage", async () => {
    render(<IntegrationsPage />);

    expect(
      await screen.findByRole("heading", { name: "Some agent actions are unverifiable" }),
    ).toBeInTheDocument();

    expect(screen.getByRole("region", { name: "Verifier coverage map" })).toBeInTheDocument();
    expect(screen.getByText("refund")).toBeInTheDocument();
    expect(screen.getAllByText("Verifier healthy").length).toBeGreaterThan(0);
    expect(screen.getByText("custom")).toBeInTheDocument();
    expect(screen.getByText("No verifier")).toBeInTheDocument();

    expect(screen.getByRole("region", { name: "REST / HTTP JSON verifier" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "SQL / database read verifier" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Webhook / bridge verifier" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Workflow integrations" })).toBeInTheDocument();
    expect(screen.getAllByText("REST / HTTP JSON verifier").length).toBeGreaterThan(0);
    expect(screen.getAllByText("HubSpot CRM verifier").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Salesforce CRM verifier").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Zoho CRM verifier").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Zendesk ticket verifier").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Jira / JSM verifier").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Razorpay refund verifier").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Refund ledger template").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Customer / CRM record template").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SQL / Postgres read verifier").length).toBeGreaterThan(0);
    expect(screen.getByText("Slack")).toBeInTheDocument();
    expect(screen.getByText("GitHub")).toBeInTheDocument();

    expect(screen.getByRole("heading", { name: "Backend coverage stays honest" })).toBeInTheDocument();
    expect(screen.getByText("one saved config per verifier type", { exact: false })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Integration status" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show controls" }));
    expect(screen.getByRole("region", { name: "Integration status" })).toBeInTheDocument();

    await waitFor(() => expect(api.listOutcomeReconciliations).toHaveBeenCalledWith({ limit: 50 }));
    await waitFor(() => expect(api.getGenericRestConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getRazorpayRefundConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getHubSpotCrmConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getSalesforceCrmConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getZohoCrmConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getPostgresReadConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getToolRegistry).toHaveBeenCalledTimes(1));
  });

  it("saves and tests the Generic REST verifier setup path", async () => {
    render(<IntegrationsPage />);

    await screen.findByRole("heading", { name: "Some agent actions are unverifiable" });
    fireEvent.click(screen.getByRole("button", { name: /REST \/ HTTP JSON verifier/i }));
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

  it("saves and tests the native Razorpay refund verifier setup path", async () => {
    render(<IntegrationsPage />);

    await screen.findByRole("heading", { name: "Some agent actions are unverifiable" });
    fireEvent.click(screen.getByRole("button", { name: /Razorpay refund verifier/i }));
    fireEvent.change(screen.getByLabelText("Razorpay key id"), {
      target: { value: "rzp_test_key" },
    });
    fireEvent.change(screen.getByLabelText("Razorpay key secret"), {
      target: { value: "razorpay-secret" },
    });
    fireEvent.change(screen.getByLabelText("Refund ID"), {
      target: { value: "rfnd_123" },
    });
    fireEvent.change(screen.getByLabelText("Claimed JSON"), {
      target: {
        value: JSON.stringify(
          {
            refund_id: "rfnd_123",
            amount_minor: 4250,
            amount_major: "42.5",
            currency: "INR",
            status: "processed",
          },
          null,
          2,
        ),
      },
    });

    fireEvent.click(screen.getByRole("button", { name: /Save Razorpay verifier/i }));

    await waitFor(() => {
      expect(api.saveRazorpayRefundConnectorConfig).toHaveBeenCalledWith({
        key_id: "rzp_test_key",
        key_secret: "razorpay-secret",
      });
    });

    fireEvent.click(await screen.findByRole("button", { name: /Run Razorpay preflight/i }));

    await waitFor(() => {
      expect(api.testRazorpayRefundConnector).toHaveBeenCalledWith({
        refund_id: "rfnd_123",
        action_type: "refund",
        claimed: {
          refund_id: "rfnd_123",
          amount_minor: 4250,
          amount_major: "42.5",
          currency: "INR",
          status: "processed",
        },
        match_fields: ["refund_id", "amount_minor", "currency", "status"],
      });
    });
    expect(await screen.findByText("Razorpay verifier test recorded matched.")).toBeInTheDocument();
  });

  it("saves and tests the native HubSpot verifier setup path", async () => {
    render(<IntegrationsPage />);

    await screen.findByRole("heading", { name: "Some agent actions are unverifiable" });
    fireEvent.click(screen.getByRole("button", { name: /HubSpot CRM verifier/i }));
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

    fireEvent.click(screen.getByRole("button", { name: /Save HubSpot verifier/i }));

    await waitFor(() => {
      expect(api.saveHubSpotCrmConnectorConfig).toHaveBeenCalledWith({
        query: {
          properties: "email,firstname,lastname,lifecyclestage,hs_lead_status,hs_object_id",
          idProperty: "email",
        },
        bearer_token: "hubspot-private-app-token",
      });
    });

    fireEvent.click(await screen.findByRole("button", { name: /Run HubSpot preflight/i }));

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

  it("saves and tests the native Zoho CRM verifier setup path", async () => {
    render(<IntegrationsPage />);

    await screen.findByRole("heading", { name: "Some agent actions are unverifiable" });
    fireEvent.click(screen.getByRole("button", { name: /Zoho CRM verifier/i }));
    fireEvent.change(screen.getByLabelText("Manual bearer token"), {
      target: { value: "zoho-oauth-access-token" },
    });
    fireEvent.change(screen.getByLabelText("Module name"), {
      target: { value: "Contacts" },
    });
    fireEvent.change(screen.getByLabelText("Record ID"), {
      target: { value: "1234567890000000001" },
    });
    fireEvent.change(screen.getByLabelText("Claimed JSON"), {
      target: {
        value: JSON.stringify(
          {
            zoho_record_id: "1234567890000000001",
            Email: "owner@example.com",
          },
          null,
          2,
        ),
      },
    });

    fireEvent.click(screen.getByRole("button", { name: /Save Zoho CRM verifier/i }));

    await waitFor(() => {
      expect(api.saveZohoCrmConnectorConfig).toHaveBeenCalledWith({
        base_url: "https://www.zohoapis.com",
        query: {
          fields: "id,Full_Name,Email,Phone,Company,Stage,Amount,Lead_Status,Owner,Modified_Time",
        },
        bearer_token: "zoho-oauth-access-token",
      });
    });

    fireEvent.click(await screen.findByRole("button", { name: /Run Zoho preflight/i }));

    await waitFor(() => {
      expect(api.testZohoCrmConnector).toHaveBeenCalledWith({
        module_name: "Contacts",
        record_ref: "1234567890000000001",
        action_type: "customer_record_update",
        claimed: {
          zoho_record_id: "1234567890000000001",
          Email: "owner@example.com",
        },
        match_fields: ["zoho_record_id", "Email"],
      });
    });
    expect(await screen.findByText("Zoho CRM verifier test recorded matched.")).toBeInTheDocument();
  });

  it("saves and tests the native Jira issue verifier setup path", async () => {
    render(<IntegrationsPage />);

    await screen.findByRole("heading", { name: "Some agent actions are unverifiable" });
    fireEvent.click(screen.getByRole("button", { name: /Jira \/ JSM verifier/i }));
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

    fireEvent.click(screen.getByRole("button", { name: /Save Jira verifier/i }));

    await waitFor(() => {
      expect(api.saveJiraIssueConnectorConfig).toHaveBeenCalledWith({
        base_url: "https://example.atlassian.net",
        auth_username: "agent@example.com",
        bearer_token: "jira-api-token",
      });
    });

    fireEvent.click(await screen.findByRole("button", { name: /Run Jira preflight/i }));

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

  it("saves and tests the native NetSuite finance verifier setup path", async () => {
    render(<IntegrationsPage />);

    await screen.findByRole("heading", { name: "Some agent actions are unverifiable" });
    fireEvent.click(screen.getByRole("button", { name: /NetSuite finance verifier/i }));
    fireEvent.change(screen.getByLabelText("Bearer token"), {
      target: { value: "netsuite-token" },
    });
    fireEvent.change(screen.getByLabelText("Record type"), {
      target: { value: "vendorBill" },
    });
    fireEvent.change(screen.getByLabelText("Record ID"), {
      target: { value: "12345" },
    });
    fireEvent.change(screen.getByLabelText("Claimed JSON"), {
      target: {
        value: JSON.stringify(
          {
            netsuite_record_id: "12345",
            record_type: "vendorBill",
            tran_id: "VB1001",
            amount_minor: 125000,
            amount_major: "1250",
            currency: "USD",
            status: "approved",
          },
          null,
          2,
        ),
      },
    });

    fireEvent.click(screen.getByRole("button", { name: /Save NetSuite verifier/i }));

    await waitFor(() => {
      expect(api.saveNetSuiteFinanceConnectorConfig).toHaveBeenCalledWith({
        base_url: "https://example.suitetalk.api.netsuite.com",
        bearer_token: "netsuite-token",
      });
    });

    fireEvent.click(await screen.findByRole("button", { name: /Run NetSuite preflight/i }));

    await waitFor(() => {
      expect(api.testNetSuiteFinanceConnector).toHaveBeenCalledWith({
        record_type: "vendorBill",
        record_ref: "12345",
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
        match_fields: ["netsuite_record_id", "record_type", "tran_id", "amount_minor", "currency", "status"],
      });
    });
    expect(await screen.findByText("NetSuite verifier test recorded matched.")).toBeInTheDocument();
  });

  it("starts the Zoho CRM OAuth connection flow", async () => {
    const assignSpy = vi.spyOn(externalNavigator, "assign").mockImplementation(() => undefined);
    try {
      render(<IntegrationsPage />);

      await screen.findByRole("heading", { name: "Some agent actions are unverifiable" });
      fireEvent.click(screen.getByRole("button", { name: /Zoho CRM verifier/i }));
      fireEvent.click(await screen.findByRole("button", { name: /Connect Zoho CRM/i }));

      await waitFor(() => expect(api.startZohoCrmOAuth).toHaveBeenCalledTimes(1));
      expect(assignSpy).toHaveBeenCalledWith(
        "https://accounts.zoho.com/oauth/v2/auth?state=test",
      );
    } finally {
      assignSpy.mockRestore();
    }
  });
});
