import { describe, expect, it } from "vitest";

import type {
  CustomerRecordConnectorStatusResponse,
  GenericRestConnectorStatusResponse,
  HubSpotCrmConnectorStatusResponse,
  JiraIssueConnectorStatusResponse,
  LedgerRefundConnectorStatusResponse,
  NetSuiteFinanceConnectorStatusResponse,
  OutcomeReconciliationView,
  PostgresReadConnectorStatusResponse,
  RazorpayRefundConnectorStatusResponse,
  SalesforceCrmConnectorStatusResponse,
  ToolRegistryResponse,
  ZohoCrmConnectorStatusResponse,
} from "@/lib/api";
import type { GithubConnectionStatusResponse, SlackInstallStatusResponse } from "@/lib/types";
import { buildConnectorInventory, connectorStateLabel, connectorUpdatedLabel } from "./connector-inventory";

function check(overrides: Partial<OutcomeReconciliationView> = {}): OutcomeReconciliationView {
  return {
    id: "check_1",
    project_id: "project_1",
    call_id: "call_1",
    trace_id: "trace_1",
    runtime_policy_decision_id: "decision_1",
    action_type: "inventory.item.delete",
    connector_type: "generic_rest_api",
    system_ref: "inventory:item_1",
    verdict: "matched",
    verification_status: "verified",
    reason: "all_compared_fields_matched",
    amount_usd: null,
    currency: null,
    claimed: { status: "deleted" },
    actual: { status: "deleted" },
    comparison: { compared_fields: [] },
    idempotency_key: "idem_1",
    metadata: {},
    checked_at: "2026-06-20T09:00:00Z",
    created_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function ledgerStatus(overrides: Partial<LedgerRefundConnectorStatusResponse> = {}): LedgerRefundConnectorStatusResponse {
  return {
    connected: true,
    connector_type: "ledger_refund_api",
    base_url: "https://ledger.example.com",
    path_template: "/refunds/{refund_id}",
    record_path: "data",
    query: null,
    has_bearer_token: true,
    bearer_token_last4: "1234",
    last_tested_at: "2026-06-20T09:00:00Z",
    health_status: "healthy",
    last_verdict: "matched",
    last_error: null,
    last_error_code: null,
    last_http_status: 200,
    last_attempts: 1,
    last_retryable: false,
    last_checked_at: "2026-06-20T09:00:00Z",
    readiness: { status: "ready" },
    created_at: "2026-06-20T08:00:00Z",
    updated_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function customerStatus(overrides: Partial<CustomerRecordConnectorStatusResponse> = {}): CustomerRecordConnectorStatusResponse {
  return {
    connected: true,
    connector_type: "customer_record_api",
    base_url: "https://crm.example.com",
    path_template: "/customers/{customer_id}",
    record_path: "data",
    query: null,
    has_bearer_token: true,
    bearer_token_last4: "9012",
    last_tested_at: "2026-06-20T09:00:00Z",
    health_status: "healthy",
    last_verdict: "matched",
    last_error: null,
    last_error_code: null,
    last_http_status: 200,
    last_attempts: 1,
    last_retryable: false,
    last_checked_at: "2026-06-20T09:00:00Z",
    readiness: { status: "ready" },
    created_at: "2026-06-20T08:00:00Z",
    updated_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function genericStatus(overrides: Partial<GenericRestConnectorStatusResponse> = {}): GenericRestConnectorStatusResponse {
  return {
    connected: true,
    connector_type: "generic_rest_api",
    base_url: "https://api.example.com",
    path_template: "/records/{record_ref}",
    record_path: "data",
    query: null,
    has_bearer_token: true,
    bearer_token_last4: "5678",
    last_tested_at: "2026-06-20T09:00:00Z",
    health_status: "healthy",
    last_verdict: "matched",
    last_error: null,
    last_error_code: null,
    last_http_status: 200,
    last_attempts: 1,
    last_retryable: false,
    last_checked_at: "2026-06-20T09:00:00Z",
    readiness: { status: "ready" },
    created_at: "2026-06-20T08:00:00Z",
    updated_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function razorpayStatus(overrides: Partial<RazorpayRefundConnectorStatusResponse> = {}): RazorpayRefundConnectorStatusResponse {
  return {
    connected: true,
    connector_type: "razorpay_refund",
    base_url: "https://api.razorpay.com",
    path_template: "/v1/refunds/{refund_id}",
    record_path: null,
    query: { key_id: "rzp_test_key" },
    has_bearer_token: true,
    bearer_token_last4: "r123",
    last_tested_at: "2026-06-20T09:00:00Z",
    health_status: "healthy",
    last_verdict: "matched",
    last_error: null,
    last_error_code: null,
    last_http_status: 200,
    last_attempts: 1,
    last_retryable: false,
    last_checked_at: "2026-06-20T09:00:00Z",
    readiness: { status: "ready" },
    created_at: "2026-06-20T08:00:00Z",
    updated_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function hubspotStatus(overrides: Partial<HubSpotCrmConnectorStatusResponse> = {}): HubSpotCrmConnectorStatusResponse {
  return {
    connected: true,
    connector_type: "hubspot_crm",
    base_url: "https://api.hubapi.com",
    path_template: "/crm/v3/objects/contacts/{record_ref}",
    record_path: null,
    query: { properties: "email,lifecyclestage,hs_object_id", idProperty: "email" },
    has_bearer_token: true,
    bearer_token_last4: "h123",
    last_tested_at: "2026-06-20T09:00:00Z",
    health_status: "healthy",
    last_verdict: "matched",
    last_error: null,
    last_error_code: null,
    last_http_status: 200,
    last_attempts: 1,
    last_retryable: false,
    last_checked_at: "2026-06-20T09:00:00Z",
    readiness: { status: "ready" },
    created_at: "2026-06-20T08:00:00Z",
    updated_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function salesforceStatus(overrides: Partial<SalesforceCrmConnectorStatusResponse> = {}): SalesforceCrmConnectorStatusResponse {
  return {
    connected: true,
    connector_type: "salesforce_crm",
    base_url: "https://example.my.salesforce.com",
    path_template: "/services/data/v60.0/sobjects/{object_type}/{record_ref}",
    record_path: null,
    query: { fields: "Id,Name,StageName,Amount" },
    has_bearer_token: true,
    bearer_token_last4: "s123",
    last_tested_at: "2026-06-20T09:00:00Z",
    health_status: "healthy",
    last_verdict: "matched",
    last_error: null,
    last_error_code: null,
    last_http_status: 200,
    last_attempts: 1,
    last_retryable: false,
    last_checked_at: "2026-06-20T09:00:00Z",
    readiness: { status: "ready" },
    created_at: "2026-06-20T08:00:00Z",
    updated_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function zohoStatus(overrides: Partial<ZohoCrmConnectorStatusResponse> = {}): ZohoCrmConnectorStatusResponse {
  return {
    connected: true,
    connector_type: "zoho_crm",
    base_url: "https://www.zohoapis.com",
    path_template: "/crm/v8/{module_name}/{record_ref}",
    record_path: "data.0",
    query: { fields: "id,Full_Name,Email,Stage,Amount" },
    has_bearer_token: true,
    bearer_token_last4: "z123",
    last_tested_at: "2026-06-20T09:00:00Z",
    health_status: "healthy",
    last_verdict: "matched",
    last_error: null,
    last_error_code: null,
    last_http_status: 200,
    last_attempts: 1,
    last_retryable: false,
    last_checked_at: "2026-06-20T09:00:00Z",
    readiness: { status: "ready" },
    created_at: "2026-06-20T08:00:00Z",
    updated_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function jiraStatus(overrides: Partial<JiraIssueConnectorStatusResponse> = {}): JiraIssueConnectorStatusResponse {
  return {
    connected: true,
    connector_type: "jira_issue",
    base_url: "https://example.atlassian.net",
    path_template: "/rest/api/3/issue/{record_ref}",
    record_path: null,
    query: { fields: "summary,status,assignee,reporter,issuetype,project,priority,updated,created,resolutiondate,labels" },
    has_bearer_token: true,
    bearer_token_last4: "j123",
    last_tested_at: "2026-06-20T09:00:00Z",
    health_status: "healthy",
    last_verdict: "matched",
    last_error: null,
    last_error_code: null,
    last_http_status: 200,
    last_attempts: 1,
    last_retryable: false,
    last_checked_at: "2026-06-20T09:00:00Z",
    readiness: { status: "ready" },
    created_at: "2026-06-20T08:00:00Z",
    updated_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function netsuiteStatus(overrides: Partial<NetSuiteFinanceConnectorStatusResponse> = {}): NetSuiteFinanceConnectorStatusResponse {
  return {
    connected: true,
    connector_type: "netsuite_finance",
    base_url: "https://example.suitetalk.api.netsuite.com",
    path_template: "/services/rest/record/v1/{record_type}/{record_ref}",
    record_path: null,
    query: null,
    has_bearer_token: true,
    bearer_token_last4: "n123",
    last_tested_at: "2026-06-20T09:00:00Z",
    health_status: "healthy",
    last_verdict: "matched",
    last_error: null,
    last_error_code: null,
    last_http_status: 200,
    last_attempts: 1,
    last_retryable: false,
    last_checked_at: "2026-06-20T09:00:00Z",
    readiness: { status: "ready" },
    created_at: "2026-06-20T08:00:00Z",
    updated_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function postgresStatus(overrides: Partial<PostgresReadConnectorStatusResponse> = {}): PostgresReadConnectorStatusResponse {
  return {
    connected: true,
    connector_type: "postgres_read",
    base_url: null,
    path_template: null,
    record_path: null,
    query: null,
    has_database_url: true,
    database_url_last4: "pg01",
    has_read_query: true,
    read_query_digest: "sha256:abc",
    has_bearer_token: false,
    bearer_token_last4: null,
    last_tested_at: "2026-06-20T09:00:00Z",
    health_status: "healthy",
    last_verdict: "matched",
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: 1,
    last_retryable: false,
    last_checked_at: "2026-06-20T09:00:00Z",
    readiness: { status: "ready" },
    created_at: "2026-06-20T08:00:00Z",
    updated_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function githubStatus(overrides: Partial<GithubConnectionStatusResponse> = {}): GithubConnectionStatusResponse {
  return {
    connected: true,
    github_id: "gh_1",
    github_login: "zroky",
    scopes: ["repo"],
    connected_at: "2026-06-20T08:00:00Z",
    updated_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function slackStatus(overrides: Partial<SlackInstallStatusResponse> = {}): SlackInstallStatusResponse {
  return {
    connected: true,
    team_id: "T1",
    team_name: "Zroky",
    channel_id: "C1",
    channel_name: "ops",
    bot_user_id: "B1",
    scopes: ["chat:write"],
    installed_by_user: "U1",
    installed_at: "2026-06-20T08:00:00Z",
    updated_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function registry(overrides: Partial<ToolRegistryResponse> = {}): ToolRegistryResponse {
  const base: ToolRegistryResponse = {
    schema_version: "zroky.agent_tool_control.v1",
    project_id: "project_1",
    agent_id: null,
    action_type: null,
    runtime_paths: [],
    verification_connectors: [
      {
        id: "generic_rest",
        kind: "verification_connector",
        label: "Generic REST",
        description: "Generic REST",
        category: "verification",
        phase: "phase1",
        implementation_status: "template",
        launch_tier: "p0",
        supported_action_types: ["inventory.item.delete"],
        recommended_for_action_types: ["internal_api.mutate"],
        requires_customer_credentials: true,
        dashboard_href: "/integrations#generic-rest-connector",
        backend_capability: "generic_rest",
        availability_notes: null,
      },
    ],
    native_tool_families: [
      {
        id: "stripe",
        kind: "native_tool_family",
        label: "Stripe",
        description: "Stripe",
        category: "payment",
        phase: "phase1",
        implementation_status: "planned",
        launch_tier: "p1",
        supported_action_types: ["finance.invoice.approve"],
        recommended_for_action_types: [],
        requires_customer_credentials: true,
        dashboard_href: null,
        backend_capability: null,
        availability_notes: null,
      },
    ],
    recommended: {
      action_types: ["crm.deal.update"],
      runtime_path_ids: [],
      verification_connector_ids: [],
      native_tool_family_ids: [],
      next_steps: [],
    },
  };
  return { ...base, ...overrides };
}

describe("connector-inventory", () => {
  it("groups REST templates under REST, Postgres under SQL, and Slack/GitHub under workflow", () => {
    const inventory = buildConnectorInventory({
      ledger: ledgerStatus(),
      customer: customerStatus(),
      generic: genericStatus(),
      postgres: postgresStatus(),
      github: githubStatus(),
      slack: slackStatus(),
      checks: [check({ connector_type: "generic_rest_api" })],
    });

    const rest = inventory.transportGroups.find((group) => group.transport === "rest_http");
    const sql = inventory.transportGroups.find((group) => group.transport === "sql_read");
    const workflow = inventory.transportGroups.find((group) => group.transport === "workflow");

    expect(rest?.rows.map((row) => row.id)).toEqual([
      "generic_rest",
      "hubspot_crm",
      "salesforce_crm",
      "zoho_crm",
      "zendesk_ticket",
      "jira_issue",
      "stripe_refund",
      "razorpay_refund",
      "netsuite_finance",
      "ledger_template",
      "customer_template",
    ]);
    expect(rest?.rows.map((row) => row.templateKind)).toEqual([
      "custom",
      "hubspot_crm",
      "salesforce_crm",
      "zoho_crm",
      "zendesk_ticket",
      "jira_issue",
      "stripe_refund",
      "razorpay_refund",
      "netsuite_finance",
      "refund_ledger",
      "customer_record",
    ]);
    expect(sql?.rows.map((row) => row.id)).toEqual(["postgres_read"]);
    expect(workflow?.rows.map((row) => row.id)).toEqual(["github", "slack"]);
    expect(inventory.supportRows.every((row) => row.kind === "support" && row.transport === "workflow")).toBe(true);
  });

  it("focuses counts on verifier health, not vertical connector names", () => {
    const inventory = buildConnectorInventory({
      ledger: ledgerStatus(),
      customer: null,
      generic: genericStatus(),
      postgres: postgresStatus(),
      github: githubStatus(),
      slack: slackStatus(),
      checks: [],
    });

    expect(inventory.counts).toMatchObject({
      proofTotal: 12,
      healthyVerifiers: 3,
      notConfigured: 9,
      failingVerifiers: 0,
      notTested: 0,
      supportTotal: 2,
      supportConnected: 2,
    });
  });

  it("marks configured connectors without matched proof as not tested", () => {
    const inventory = buildConnectorInventory({
      ledger: ledgerStatus({ last_verdict: null, readiness: { status: "not_ready" } }),
      customer: null,
      generic: null,
      postgres: null,
      github: null,
      slack: null,
      checks: [],
    });

    const ledger = inventory.proofRows.find((row) => row.id === "ledger_template");
    expect(ledger).toMatchObject({
      state: "not_tested",
      tone: "warning",
      statusLabel: "Needs preflight",
      transport: "rest_http",
      templateKind: "refund_ledger",
    });
    expect(inventory.counts.notTested).toBe(1);
  });

  it("prioritizes mismatched source-of-record proof as a blocked verifier", () => {
    const inventory = buildConnectorInventory({
      ledger: ledgerStatus({ last_verdict: "mismatched" }),
      customer: null,
      generic: null,
      postgres: null,
      github: null,
      slack: null,
      checks: [
        check({
          connector_type: "ledger_refund_api",
          verdict: "mismatched",
          reason: "amount_mismatch",
          checked_at: "2026-06-20T09:05:00Z",
        }),
      ],
    });

    const ledger = inventory.proofRows.find((row) => row.id === "ledger_template");
    expect(ledger).toMatchObject({
      state: "mismatched",
      tone: "danger",
      latestCheck: expect.objectContaining({ verdict: "mismatched" }),
    });
    expect(inventory.counts.failingVerifiers).toBe(1);
    expect(inventory.verdict).toMatchObject({
      tone: "danger",
      title: "Verification connector blocked",
    });
  });

  it("uses the healthy generic REST verifier as an honest fallback for unmapped action types", () => {
    const inventory = buildConnectorInventory({
      ledger: null,
      customer: null,
      generic: genericStatus(),
      postgres: null,
      github: null,
      slack: null,
      actionTypes: ["inventory.item.delete", "deploy.change"],
    });

    expect(inventory.coverageRows).toEqual([
      expect.objectContaining({
        actionType: "deploy.change",
        status: "generic_fallback",
        connectorId: "generic_rest",
        transport: "rest_http",
      }),
      expect.objectContaining({
        actionType: "inventory.item.delete",
        status: "generic_fallback",
        connectorId: "generic_rest",
      }),
    ]);
    expect(inventory.counts.coveragePercent).toBe(100);
    expect(inventory.counts.unverifiableActionTypes).toBe(0);
  });

  it("marks action types without any healthy verifier as unverifiable", () => {
    const inventory = buildConnectorInventory({
      ledger: null,
      customer: null,
      generic: null,
      postgres: null,
      github: null,
      slack: null,
      actionTypes: ["deploy.change", "finance.invoice.approve"],
    });

    expect(inventory.coverageRows).toEqual([
      expect.objectContaining({
        actionType: "deploy.change",
        status: "unverifiable",
        connectorId: null,
      }),
      expect.objectContaining({
        actionType: "finance.invoice.approve",
        status: "unverifiable",
        connectorId: null,
      }),
    ]);
    expect(inventory.counts.coveragePercent).toBe(0);
    expect(inventory.counts.unverifiableActionTypes).toBe(2);
    expect(inventory.verdict).toMatchObject({
      title: "Some agent actions are unverifiable",
      tone: "warning",
    });
  });

  it("prefers a healthy scoped template over generic fallback in the coverage map", () => {
    const baseRegistry = registry();
    const inventory = buildConnectorInventory({
      ledger: null,
      customer: customerStatus(),
      generic: genericStatus(),
      postgres: null,
      github: null,
      slack: null,
      actionTypes: ["crm.deal.update", "customer.record.update"],
      registry: registry({
        verification_connectors: [
          ...baseRegistry.verification_connectors,
          {
            id: "crm_record",
            kind: "verification_connector",
            label: "CRM customer record verifier",
            description: "CRM",
            category: "system_of_record",
            phase: "phase1",
            implementation_status: "available",
            launch_tier: "p0",
            supported_action_types: ["customer.record.update"],
            recommended_for_action_types: ["crm.deal.update"],
            requires_customer_credentials: true,
            dashboard_href: "/integrations#customer-record-connector",
            backend_capability: "system_of_record.customer_record_api",
            availability_notes: null,
          },
        ],
      }),
    });

    expect(inventory.coverageRows.find((row) => row.actionType === "crm.deal.update")).toMatchObject({
      status: "healthy",
      connectorId: "customer_template",
    });
    expect(inventory.coverageRows.find((row) => row.actionType === "customer.record.update")).toMatchObject({
      status: "healthy",
      connectorId: "customer_template",
    });
  });

  it("prefers the native HubSpot verifier for HubSpot CRM coverage", () => {
    const baseRegistry = registry();
    const inventory = buildConnectorInventory({
      ledger: null,
      customer: customerStatus(),
      generic: genericStatus(),
      hubspot: hubspotStatus(),
      postgres: null,
      github: null,
      slack: null,
      actionTypes: ["hubspot.contact.update"],
      registry: registry({
        verification_connectors: [
          ...baseRegistry.verification_connectors,
          {
            id: "hubspot_crm",
            kind: "verification_connector",
            label: "HubSpot CRM verifier",
            description: "HubSpot",
            category: "system_of_record",
            phase: "phase1",
            implementation_status: "available",
            launch_tier: "p1",
            supported_action_types: ["hubspot.contact.update"],
            recommended_for_action_types: ["customer_record_update"],
            requires_customer_credentials: true,
            dashboard_href: "/integrations",
            backend_capability: "system_of_record.hubspot_crm",
            availability_notes: null,
          },
        ],
      }),
    });

    expect(inventory.coverageRows.find((row) => row.actionType === "hubspot.contact.update")).toMatchObject({
      status: "healthy",
      connectorId: "hubspot_crm",
      transport: "rest_http",
    });
  });

  it("prefers the native Salesforce verifier for Salesforce CRM coverage", () => {
    const baseRegistry = registry();
    const inventory = buildConnectorInventory({
      ledger: null,
      customer: customerStatus(),
      generic: genericStatus(),
      salesforce: salesforceStatus(),
      postgres: null,
      github: null,
      slack: null,
      actionTypes: ["salesforce.opportunity.update"],
      registry: registry({
        verification_connectors: [
          ...baseRegistry.verification_connectors,
          {
            id: "salesforce_crm",
            kind: "verification_connector",
            label: "Salesforce CRM verifier",
            description: "Salesforce",
            category: "system_of_record",
            phase: "phase1",
            implementation_status: "available",
            launch_tier: "p1",
            supported_action_types: ["salesforce.opportunity.update"],
            recommended_for_action_types: ["customer_record_update"],
            requires_customer_credentials: true,
            dashboard_href: "/integrations",
            backend_capability: "system_of_record.salesforce_crm",
            availability_notes: null,
          },
        ],
      }),
    });

    expect(inventory.coverageRows.find((row) => row.actionType === "salesforce.opportunity.update")).toMatchObject({
      status: "healthy",
      connectorId: "salesforce_crm",
      transport: "rest_http",
    });
  });
  it("prefers the native Zoho verifier for Zoho CRM coverage", () => {
    const baseRegistry = registry();
    const inventory = buildConnectorInventory({
      ledger: null,
      customer: customerStatus(),
      generic: genericStatus(),
      zoho: zohoStatus(),
      postgres: null,
      github: null,
      slack: null,
      actionTypes: ["zoho.deal.update"],
      registry: registry({
        verification_connectors: [
          ...baseRegistry.verification_connectors,
          {
            id: "zoho_crm",
            kind: "verification_connector",
            label: "Zoho CRM verifier",
            description: "Zoho",
            category: "system_of_record",
            phase: "phase1",
            implementation_status: "available",
            launch_tier: "p1",
            supported_action_types: ["zoho.deal.update"],
            recommended_for_action_types: ["customer_record_update"],
            requires_customer_credentials: true,
            dashboard_href: "/integrations",
            backend_capability: "system_of_record.zoho_crm",
            availability_notes: null,
          },
        ],
      }),
    });

    expect(inventory.coverageRows.find((row) => row.actionType === "zoho.deal.update")).toMatchObject({
      status: "healthy",
      connectorId: "zoho_crm",
      transport: "rest_http",
    });
  });

  it("prefers the native Jira verifier for Jira and JSM coverage", () => {
    const baseRegistry = registry();
    const inventory = buildConnectorInventory({
      ledger: null,
      customer: null,
      generic: genericStatus(),
      jira: jiraStatus(),
      postgres: null,
      github: null,
      slack: null,
      actionTypes: ["jira.issue.transition"],
      registry: registry({
        verification_connectors: [
          ...baseRegistry.verification_connectors,
          {
            id: "jira_issue",
            kind: "verification_connector",
            label: "Jira / JSM issue verifier",
            description: "Jira",
            category: "system_of_record",
            phase: "phase1",
            implementation_status: "available",
            launch_tier: "p1",
            supported_action_types: ["jira.issue.transition"],
            recommended_for_action_types: ["ticket_close"],
            requires_customer_credentials: true,
            dashboard_href: "/integrations",
            backend_capability: "system_of_record.jira_issue",
            availability_notes: null,
          },
        ],
      }),
    });

    expect(inventory.coverageRows.find((row) => row.actionType === "jira.issue.transition")).toMatchObject({
      status: "healthy",
      connectorId: "jira_issue",
      transport: "rest_http",
    });
  });

  it("prefers the native NetSuite verifier for finance and procurement coverage", () => {
    const baseRegistry = registry();
    const inventory = buildConnectorInventory({
      ledger: null,
      customer: null,
      generic: genericStatus(),
      netsuite: netsuiteStatus(),
      postgres: null,
      github: null,
      slack: null,
      actionTypes: ["invoice_spend_approval"],
      registry: registry({
        verification_connectors: [
          ...baseRegistry.verification_connectors,
          {
            id: "netsuite_finance",
            kind: "verification_connector",
            label: "NetSuite finance verifier",
            description: "NetSuite",
            category: "system_of_record",
            phase: "phase1",
            implementation_status: "available",
            launch_tier: "p1",
            supported_action_types: ["invoice_spend_approval"],
            recommended_for_action_types: ["invoice_spend_approval"],
            requires_customer_credentials: true,
            dashboard_href: "/integrations",
            backend_capability: "system_of_record.netsuite_finance",
            availability_notes: null,
          },
        ],
      }),
    });

    expect(inventory.coverageRows.find((row) => row.actionType === "invoice_spend_approval")).toMatchObject({
      status: "healthy",
      connectorId: "netsuite_finance",
      transport: "rest_http",
    });
  });

  it("prefers the native Razorpay verifier for Razorpay refund coverage", () => {
    const baseRegistry = registry();
    const inventory = buildConnectorInventory({
      ledger: null,
      customer: null,
      generic: genericStatus(),
      razorpay: razorpayStatus(),
      postgres: null,
      github: null,
      slack: null,
      actionTypes: ["razorpay.refund.create"],
      registry: registry({
        verification_connectors: [
          ...baseRegistry.verification_connectors,
          {
            id: "razorpay_refund",
            kind: "verification_connector",
            label: "Razorpay refund verifier",
            description: "Razorpay",
            category: "system_of_record",
            phase: "phase1",
            implementation_status: "available",
            launch_tier: "p1",
            supported_action_types: ["razorpay.refund.create", "refund"],
            recommended_for_action_types: ["refund"],
            requires_customer_credentials: true,
            dashboard_href: "/integrations",
            backend_capability: "system_of_record.razorpay_refund",
            availability_notes: null,
          },
        ],
      }),
    });

    expect(inventory.coverageRows.find((row) => row.actionType === "razorpay.refund.create")).toMatchObject({
      status: "healthy",
      connectorId: "razorpay_refund",
      transport: "rest_http",
    });
  });

  it("uses SQL coverage for database-backed action types", () => {
    const baseRegistry = registry();
    const inventory = buildConnectorInventory({
      ledger: null,
      customer: null,
      generic: null,
      postgres: postgresStatus(),
      github: null,
      slack: null,
      actionTypes: ["database.record.update"],
      registry: registry({
        verification_connectors: [
          ...baseRegistry.verification_connectors,
          {
            id: "postgres_read",
            kind: "verification_connector",
            label: "Postgres SQL read verifier",
            description: "Postgres",
            category: "system_of_record",
            phase: "phase1",
            implementation_status: "available",
            launch_tier: "p0",
            supported_action_types: ["database.record.update"],
            recommended_for_action_types: [],
            requires_customer_credentials: true,
            dashboard_href: "/integrations#postgres-read-connector",
            backend_capability: "system_of_record.postgres_read",
            availability_notes: null,
          },
        ],
      }),
    });

    expect(inventory.coverageRows.find((row) => row.actionType === "database.record.update")).toMatchObject({
      status: "healthy",
      connectorId: "postgres_read",
      transport: "sql_read",
    });
  });

  it("pulls action types from registry and latest checks, and exposes registry counts", () => {
    const inventory = buildConnectorInventory({
      ledger: null,
      customer: null,
      generic: genericStatus(),
      postgres: null,
      github: null,
      slack: null,
      checks: [
        check({
          id: "old",
          connector_type: "other",
          metadata: { connector: { connector_kind: "generic_rest_api" } },
          checked_at: "2026-06-20T09:00:00Z",
        }),
        check({
          id: "new",
          action_type: "support.ticket.close",
          connector_type: "other",
          metadata: { connector_kind: "generic_rest_api" },
          checked_at: "2026-06-20T10:00:00Z",
        }),
      ],
      registry: registry(),
    });

    const generic = inventory.proofRows.find((row) => row.id === "generic_rest");
    expect(generic?.latestCheck?.id).toBe("new");
    expect(inventory.registry).toEqual({ available: 0, template: 1, planned: 1 });
    expect(inventory.coverageRows.map((row) => row.actionType)).toEqual([
      "crm.deal.update",
      "finance.invoice.approve",
      "internal_api.mutate",
      "inventory.item.delete",
      "support.ticket.close",
    ]);
  });

  it("reports all-ready when healthy verifiers cover all known action types", () => {
    const inventory = buildConnectorInventory({
      ledger: ledgerStatus(),
      customer: customerStatus(),
      generic: genericStatus(),
      postgres: postgresStatus(),
      github: null,
      slack: null,
      actionTypes: ["crm.deal.update", "database.record.update", "deploy.change", "finance.invoice.approve"],
    });

    expect(inventory.counts.healthyVerifiers).toBe(4);
    expect(inventory.counts.coveragePercent).toBe(100);
    expect(inventory.verdict).toMatchObject({
      tone: "success",
      title: "Systems of record ready",
    });
  });

  it("provides display helpers for state and timestamps", () => {
    expect(connectorStateLabel("not_tested")).toBe("Needs preflight");
    expect(connectorStateLabel("ready")).toBe("Healthy");
    expect(connectorUpdatedLabel({ updatedAt: null })).toBe("Not checked");
    expect(connectorUpdatedLabel({ updatedAt: "2026-06-20T09:00:00Z" })).toContain("Jun");
  });
});
