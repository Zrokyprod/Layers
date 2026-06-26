import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GenericRestConnectorStatusResponse, OutcomeReconciliationView, ToolRegistryResponse } from "@/lib/api";
import IntegrationsPage from "./page";

const api = vi.hoisted(() => ({
  getCustomerRecordConnectorStatus: vi.fn(),
  getGenericRestConnectorStatus: vi.fn(),
  getGithubConnectionStatus: vi.fn(),
  getLedgerRefundConnectorStatus: vi.fn(),
  getSlackInstallStatus: vi.fn(),
  getToolRegistry: vi.fn(),
  listOutcomeReconciliations: vi.fn(),
  saveGenericRestConnectorConfig: vi.fn(),
  testGenericRestConnector: vi.fn(),
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
    getLedgerRefundConnectorStatus: api.getLedgerRefundConnectorStatus,
    getSlackInstallStatus: api.getSlackInstallStatus,
    getToolRegistry: api.getToolRegistry,
    listOutcomeReconciliations: api.listOutcomeReconciliations,
    saveGenericRestConnectorConfig: api.saveGenericRestConnectorConfig,
    testGenericRestConnector: api.testGenericRestConnector,
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
    ],
    native_tool_families: [
      {
        id: "stripe_refund",
        kind: "native_tool_family",
        label: "Stripe refunds",
        description: "Template for guarding and verifying Stripe refund actions.",
        category: "payments",
        phase: "phase1",
        implementation_status: "planned",
        launch_tier: "p1",
        supported_action_types: ["refund"],
        recommended_for_action_types: ["refund"],
        requires_customer_credentials: true,
        dashboard_href: "/integrations",
        backend_capability: null,
        availability_notes: "Planned after launch partner demand.",
      },
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
      health_status: "not_verified",
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
  });

  it("keeps the overview focused on system-of-record proof and support integrations", async () => {
    render(<IntegrationsPage />);

    expect(
      await screen.findByRole("heading", { name: "Proof connectors need preflight" }),
    ).toBeInTheDocument();
    expect(screen.getByText("1 matched checks / 1 need action")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Configure ledger" }).getAttribute("href")).toBe("/integrations#ledger-refund-connector");
    expect(screen.getByRole("link", { name: "Configure CRM" }).getAttribute("href")).toBe("/integrations#customer-record-connector");
    expect(screen.getByRole("link", { name: "Open policies" }).getAttribute("href")).toBe("/policies");
    expect(screen.getByRole("link", { name: "Manage Slack" }).getAttribute("href")).toBe("/integrations/slack");
    expect(screen.getByRole("link", { name: "Open evidence" }).getAttribute("href")).toBe("/evidence");
    expect(screen.getByRole("link", { name: "Review reconciliation" }).getAttribute("href")).toBe("/outcomes");
    expect(screen.getByRole("heading", { name: "System-of-record connectors" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Phase 1 connector catalog" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Connector coverage" })).toBeInTheDocument();
    expect(screen.getByText("5 available now")).toBeInTheDocument();
    expect(screen.getByText("0 template")).toBeInTheDocument();
    expect(screen.getByText("2 planned")).toBeInTheDocument();
    expect(screen.getByLabelText("Connector launch truth")).toBeInTheDocument();
    expect(screen.getByText("Live proof connectors")).toBeInTheDocument();
    expect(screen.getByText("Fallback path")).toBeInTheDocument();
    expect(screen.getByText("Planned native adapters")).toBeInTheDocument();
    expect(screen.getByText("Use this for unsupported Stripe, Razorpay, Zendesk, Gmail, HubSpot, Salesforce, and internal tools.")).toBeInTheDocument();
    expect(screen.getByText("These can produce matched, mismatched, or not_verified outcome checks now.")).toBeInTheDocument();
    expect(screen.getByText("SDK wrapper")).toBeInTheDocument();
    expect(screen.getAllByText("Generic REST/OpenAPI verifier").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Stripe refunds").length).toBeGreaterThan(0);
    expect(screen.getByText("Slack approval and alert").closest("a")?.getAttribute("href")).toBe("/integrations/slack");
    expect(screen.getByRole("region", { name: "Generic REST verifier setup" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Generic REST/OpenAPI verifier" }).length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Generic REST webhook bridge request")).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("/v1/outcomes/reconciliation/saved"))).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("x-api-key: $ZROKY_API_KEY"))).toBeInTheDocument();
    expect((screen.getByRole("button", { name: /Run proof test/i }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("region", { name: "Integration status" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Manage providers" })).not.toBeInTheDocument();
    await waitFor(() => expect(api.listOutcomeReconciliations).toHaveBeenCalledWith({ limit: 25 }));
    await waitFor(() => expect(api.getGenericRestConnectorStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getToolRegistry).toHaveBeenCalledTimes(1));
  });

  it("saves and tests the Generic REST verifier setup path", async () => {
    render(<IntegrationsPage />);

    await screen.findByRole("heading", { name: "Generic REST/OpenAPI verifier" });
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
        claimed: {
          record_ref: "invoice_42",
          status: "approved",
          amount_usd: 4200,
        },
        match_fields: ["status"],
      });
    });
    expect(await screen.findByText("Generic REST test recorded matched.")).toBeInTheDocument();
  });
});
