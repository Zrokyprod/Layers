import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IntegrationsSettingsPage from "./page";

const api = vi.hoisted(() => ({
  disconnectGithubRepoConnection: vi.fn(),
  getCustomerRecordConnectorStatus: vi.fn(),
  getGithubConnectionStatus: vi.fn(),
  getLedgerRefundConnectorStatus: vi.fn(),
  getRuntimePolicyEvidencePack: vi.fn(),
  getSlackInstallStatus: vi.fn(),
  listOutcomeReconciliations: vi.fn(),
  saveCustomerRecordConnectorConfig: vi.fn(),
  saveLedgerRefundConnectorConfig: vi.fn(),
  testCustomerRecordConnector: vi.fn(),
  testLedgerRefundConnector: vi.fn(),
}));

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
    ...api,
  };
});

describe("IntegrationsSettingsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:connector-evidence-pack"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    api.getGithubConnectionStatus.mockResolvedValue({
      connected: true,
      github_id: "123",
      github_login: "zroky",
      scopes: ["repo"],
      connected_at: "2026-06-17T10:00:00.000Z",
      updated_at: "2026-06-17T10:30:00.000Z",
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
      base_url: "https://ledger.example.com/api",
      path_template: "/refunds/{refund_id}",
      record_path: "data.0",
      query: null,
      has_bearer_token: true,
      bearer_token_last4: "oken",
      last_tested_at: "2026-06-20T09:00:00Z",
      health_status: "healthy",
      last_verdict: "matched",
      last_error: null,
      last_error_code: null,
      last_http_status: 200,
      last_attempts: 2,
      last_retryable: false,
      last_checked_at: "2026-06-20T09:00:00Z",
      created_at: "2026-06-20T08:00:00Z",
      updated_at: "2026-06-20T08:30:00Z",
    });
    api.getCustomerRecordConnectorStatus.mockResolvedValue({
      connected: true,
      connector_type: "customer_record_api",
      base_url: "https://crm.example.com/api",
      path_template: "/customers/{customer_id}",
      record_path: "data",
      query: null,
      has_bearer_token: true,
      bearer_token_last4: "oken",
      last_tested_at: "2026-06-20T09:10:00Z",
      health_status: "not_verified",
      last_verdict: null,
      last_error: null,
      last_error_code: null,
      last_http_status: null,
      last_attempts: null,
      last_retryable: null,
      last_checked_at: null,
      created_at: "2026-06-20T08:00:00Z",
      updated_at: "2026-06-20T08:30:00Z",
    });
    api.saveLedgerRefundConnectorConfig.mockResolvedValue({
      connected: true,
      connector_type: "ledger_refund_api",
      base_url: "https://ledger.example.com/api",
      path_template: "/refunds/{refund_id}",
      record_path: "data.0",
      query: null,
      has_bearer_token: true,
      bearer_token_last4: "oken",
      last_tested_at: "2026-06-20T09:00:00Z",
      created_at: "2026-06-20T08:00:00Z",
      updated_at: "2026-06-20T08:30:00Z",
    });
    api.saveCustomerRecordConnectorConfig.mockResolvedValue({
      connected: true,
      connector_type: "customer_record_api",
      base_url: "https://crm.example.com/api",
      path_template: "/customers/{customer_id}",
      record_path: "data",
      query: null,
      has_bearer_token: true,
      bearer_token_last4: "oken",
      last_tested_at: "2026-06-20T09:10:00Z",
      created_at: "2026-06-20T08:00:00Z",
      updated_at: "2026-06-20T08:30:00Z",
    });
    api.testLedgerRefundConnector.mockResolvedValue({
      ok: true,
      connector: {
        connected: true,
        connector_type: "ledger_refund_api",
        base_url: "https://ledger.example.com/api",
        path_template: "/refunds/{refund_id}",
        record_path: "data.0",
        query: null,
        has_bearer_token: true,
        bearer_token_last4: "oken",
        last_tested_at: "2026-06-20T09:05:00Z",
        created_at: "2026-06-20T08:00:00Z",
        updated_at: "2026-06-20T09:05:00Z",
      },
      check: {
        id: "check_ledger_test",
        project_id: "proj_1",
        call_id: null,
        trace_id: null,
        runtime_policy_decision_id: null,
        action_type: "refund",
        connector_type: "ledger_refund_api",
        system_ref: "ledger:RF-1001",
        verdict: "matched",
        reason: "all_compared_fields_matched",
        amount_usd: 42.5,
        currency: "USD",
        claimed: { refund_id: "RF-1001", amount_usd: 42.5, currency: "USD", status: "posted" },
        actual: { refund_id: "RF-1001", amount_usd: 42.5, currency: "USD", status: "posted" },
        comparison: { compared_fields: [], mismatches: [] },
        idempotency_key: null,
        metadata: { connector_kind: "ledger_refund_api" },
        checked_at: "2026-06-20T09:05:00Z",
        created_at: "2026-06-20T09:05:00Z",
      },
    });
    api.testCustomerRecordConnector.mockResolvedValue({
      ok: true,
      connector: {
        connected: true,
        connector_type: "customer_record_api",
        base_url: "https://crm.example.com/api",
        path_template: "/customers/{customer_id}",
        record_path: "data",
        query: null,
        has_bearer_token: true,
        bearer_token_last4: "oken",
        last_tested_at: "2026-06-20T09:15:00Z",
        created_at: "2026-06-20T08:00:00Z",
        updated_at: "2026-06-20T09:15:00Z",
      },
      check: {
        id: "check_customer_test",
        project_id: "proj_1",
        call_id: null,
        trace_id: null,
        runtime_policy_decision_id: null,
        action_type: "customer_record_update",
        connector_type: "customer_record_api",
        system_ref: "crm:CUS-1001",
        verdict: "matched",
        reason: "all_compared_fields_matched",
        amount_usd: null,
        currency: null,
        claimed: { customer_id: "CUS-1001", email: "owner@example.com", status: "active", account_id: "acct_1001" },
        actual: { customer_id: "CUS-1001", email: "owner@example.com", status: "active", account_id: "acct_1001" },
        comparison: { compared_fields: [], mismatches: [] },
        idempotency_key: null,
        metadata: { connector_kind: "customer_record_api" },
        checked_at: "2026-06-20T09:15:00Z",
        created_at: "2026-06-20T09:15:00Z",
      },
    });
    api.getRuntimePolicyEvidencePack.mockResolvedValue({
      schema_version: "runtime_policy_evidence.v1",
      project_id: "proj_1",
      decision_id: "decision_1",
      verification_status: "pass",
      decision: { id: "decision_1" },
      related_decisions: [],
      audit_log: [],
      trace_policy_spans: [],
      outcome_reconciliation: [
        {
          id: "check_ledger_refund",
          project_id: "proj_1",
          call_id: "call_refund_api",
          trace_id: "trace_refund_api",
          runtime_policy_decision_id: "decision_1",
          action_type: "refund",
          connector_type: "ledger_refund_api",
          system_ref: "ledger:rf_999",
          verdict: "matched",
          reason: "all_compared_fields_matched",
          amount_usd: 42.5,
          currency: "USD",
          claimed: { refund_id: "rf_999", amount_usd: 42.5, currency: "USD" },
          actual: { refund_id: "rf_999", amount_usd: 42.5, currency: "USD" },
          comparison: { compared_fields: [], mismatches: [] },
          idempotency_key: "call_refund_api:rf_999",
          metadata: { connector_kind: "ledger_refund_api" },
          checked_at: "2026-06-20T09:00:00Z",
          created_at: "2026-06-20T09:00:00Z",
        },
      ],
      call: null,
      generated_at: "2026-06-20T09:01:00Z",
      hash_algorithm: "sha256",
      evidence_hash: "abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abcd",
      hash_payload_excludes: ["generated_at"],
    });
    api.listOutcomeReconciliations.mockResolvedValue({
      total_in_page: 1,
      items: [
        {
          id: "check_ledger_refund",
          project_id: "proj_1",
          call_id: "call_refund_api",
          trace_id: "trace_refund_api",
          runtime_policy_decision_id: "decision_1",
          action_type: "refund",
          connector_type: "ledger_refund_api",
          system_ref: "ledger:rf_999",
          verdict: "matched",
          reason: "all_compared_fields_matched",
          amount_usd: 42.5,
          currency: "USD",
          claimed: { refund_id: "rf_999", amount_usd: 42.5, currency: "USD" },
          actual: { refund_id: "rf_999", amount_usd: 42.5, currency: "USD" },
          comparison: { compared_fields: [], mismatches: [] },
          idempotency_key: "call_refund_api:rf_999",
          metadata: {
            connector_kind: "ledger_refund_api",
            connector: {
              request_url: "https://ledger.example.com/api/refunds/rf_999",
              http_status: 200,
              record_path: "data.0",
              bearer_token: "ledger-secret-token",
            },
          },
          checked_at: "2026-06-20T09:00:00Z",
          created_at: "2026-06-20T09:00:00Z",
        },
      ],
    });
  });

  it("shows GitHub beside alert delivery integrations", async () => {
    render(<IntegrationsSettingsPage />);

    expect(await screen.findByRole("heading", { name: "GitHub" })).toBeInTheDocument();
    expect((await screen.findAllByText("@zroky")).length).toBeGreaterThan(0);
    expect(await screen.findByRole("button", { name: "Reconnect GitHub" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Slack" })).toBeInTheDocument();
    expect(await screen.findByText("2/4")).toBeInTheDocument();
    expect(screen.getByText("Connect source control, alert delivery, and system-of-record connectors for outcome proof.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Pilot handoff" }).getAttribute("href")).toBe(
      "/pilot?source=dashboard&intent=connector-proof"
    );
    expect(api.getSlackInstallStatus).toHaveBeenCalledTimes(1);
    expect(api.getLedgerRefundConnectorStatus).toHaveBeenCalledTimes(1);
    expect(api.getCustomerRecordConnectorStatus).toHaveBeenCalledTimes(1);
    expect(api.listOutcomeReconciliations).toHaveBeenCalledWith({ limit: 25 });
  });

  it("surfaces ledger refund connector proof without leaking secrets", async () => {
    render(<IntegrationsSettingsPage />);

    const heading = await screen.findByRole("heading", { name: "Ledger refund connector" });
    expect(heading).toBeInTheDocument();
    expect(heading.closest("article")?.getAttribute("id")).toBe("ledger-refund-connector");
    expect(screen.getAllByText("Verified").length).toBeGreaterThan(0);
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(screen.getAllByText("Matched").length).toBeGreaterThan(0);
    expect(screen.getByText("https://ledger.***/...")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.getByText("data.0")).toBeInTheDocument();
    expect(screen.getAllByText("Stored token ending oken").length).toBeGreaterThan(0);
    expect(screen.getByText("ledger:rf_999")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("ledger-secret-token");
  });

  it("loads and downloads the ledger evidence pack from the latest connector proof", async () => {
    render(<IntegrationsSettingsPage />);

    const heading = await screen.findByRole("heading", { name: "Ledger refund connector" });
    const connectorCard = heading.closest("article");
    expect(connectorCard).not.toBeNull();

    fireEvent.click(within(connectorCard as HTMLElement).getByRole("button", { name: "View ledger evidence" }));

    await waitFor(() => expect(api.getRuntimePolicyEvidencePack).toHaveBeenCalledWith("decision_1"));
    const evidence = await within(connectorCard as HTMLElement).findByLabelText("Ledger evidence pack");
    expect(within(evidence).getByText("Pass")).toBeInTheDocument();
    expect(within(evidence).getByText("ledger:rf_999")).toBeInTheDocument();
    expect(within(evidence).getByText("abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abcd")).toBeInTheDocument();

    fireEvent.click(within(evidence).getByRole("button", { name: "Download JSON" }));

    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:connector-evidence-pack");
  });

  it("shows not_verified when no trusted connector proof is available", async () => {
    api.listOutcomeReconciliations.mockResolvedValue({
      total_in_page: 1,
      items: [
        {
          id: "check_ledger_unverified",
          project_id: "proj_1",
          call_id: "call_refund_api",
          trace_id: null,
          runtime_policy_decision_id: null,
          action_type: "refund",
          connector_type: "ledger_refund_api",
          system_ref: "ledger:rf_missing",
          verdict: "not_verified",
          reason: "system_of_record_missing",
          amount_usd: null,
          currency: null,
          claimed: { refund_id: "rf_missing" },
          actual: null,
          comparison: { compared_fields: [], mismatches: [] },
          idempotency_key: null,
          metadata: { connector: { request_url: "https://ledger.example.com/api/refunds/rf_missing" } },
          checked_at: "2026-06-20T09:00:00Z",
          created_at: "2026-06-20T09:00:00Z",
        },
      ],
    });

    render(<IntegrationsSettingsPage />);

    expect(await screen.findByRole("heading", { name: "Ledger refund connector" })).toBeInTheDocument();
    expect(screen.getAllByText("Not verified").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No response yet").length).toBeGreaterThan(0);
    expect(screen.getByText("data.0")).toBeInTheDocument();
    expect((screen.getByRole("button", { name: "View ledger evidence" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getAllByText("Unavailable until this reconciliation is linked to a runtime policy decision.").length).toBeGreaterThan(0);
  });

  it("surfaces degraded connector health from saved status", async () => {
    api.getLedgerRefundConnectorStatus.mockResolvedValue({
      connected: true,
      connector_type: "ledger_refund_api",
      base_url: "https://ledger.example.com/api",
      path_template: "/refunds/{refund_id}",
      record_path: "data.0",
      query: null,
      has_bearer_token: true,
      bearer_token_last4: "oken",
      last_tested_at: "2026-06-20T09:00:00Z",
      health_status: "degraded",
      last_verdict: "not_verified",
      last_error: "ReadTimeout",
      last_error_code: "connector_timeout",
      last_http_status: null,
      last_attempts: 2,
      last_retryable: true,
      last_checked_at: "2026-06-20T09:00:00Z",
      created_at: "2026-06-20T08:00:00Z",
      updated_at: "2026-06-20T08:30:00Z",
    });
    api.listOutcomeReconciliations.mockResolvedValue({ total_in_page: 0, items: [] });

    render(<IntegrationsSettingsPage />);

    const status = await screen.findByLabelText("Ledger refund connector status");
    expect(within(status).getByText("Degraded")).toBeInTheDocument();
    expect(within(status).getByText("Not verified")).toBeInTheDocument();
    expect(within(status).getByText("Connector Timeout / retryable")).toBeInTheDocument();
    expect(within(status).getByText("2")).toBeInTheDocument();
  });

  it("shows missing evidence state when a decision pack has no matched outcome", async () => {
    api.getRuntimePolicyEvidencePack.mockResolvedValue({
      schema_version: "runtime_policy_evidence.v1",
      project_id: "proj_1",
      decision_id: "decision_1",
      verification_status: "not_verified",
      decision: { id: "decision_1" },
      related_decisions: [],
      audit_log: [],
      trace_policy_spans: [],
      outcome_reconciliation: [],
      call: null,
      generated_at: "2026-06-20T09:01:00Z",
      hash_algorithm: "sha256",
      evidence_hash: "def456def456def456def456def456def456def456def456def456def456def0",
      hash_payload_excludes: ["generated_at"],
    });

    render(<IntegrationsSettingsPage />);

    const heading = await screen.findByRole("heading", { name: "Ledger refund connector" });
    const connectorCard = heading.closest("article");
    expect(connectorCard).not.toBeNull();
    fireEvent.click(within(connectorCard as HTMLElement).getByRole("button", { name: "View ledger evidence" }));

    const evidence = await within(connectorCard as HTMLElement).findByLabelText("Ledger evidence pack");
    expect(within(evidence).getByText("Not verified")).toBeInTheDocument();
    expect(within(evidence).getByText("No matched system-of-record outcome is linked yet.")).toBeInTheDocument();
    expect(within(evidence).getByText("def456def456def456def456def456def456def456def456def456def456def0")).toBeInTheDocument();
  });

  it("copies the ledger refund reconciliation payload", async () => {
    const clipboardWrite = vi.spyOn(navigator.clipboard, "writeText");
    render(<IntegrationsSettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Copy saved test payload" }));

    await waitFor(() => expect(clipboardWrite).toHaveBeenCalled());
    const copied = clipboardWrite.mock.calls[0]?.[0] as string;
    expect(copied).toContain("/v1/integrations/system-of-record/ledger-refund/test");
    expect(copied).not.toContain("bearer_token");
    expect(copied).not.toContain("$LEDGER_TOKEN");
    expect(await screen.findByText("Ledger refund saved-connector test payload copied.")).toBeInTheDocument();
  });

  it("saves ledger refund connector config without rendering the token", async () => {
    render(<IntegrationsSettingsPage />);

    fireEvent.change(await screen.findByLabelText("Bearer token"), {
      target: { value: "new-ledger-secret-token" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save connector" }));

    await waitFor(() =>
      expect(api.saveLedgerRefundConnectorConfig).toHaveBeenCalledWith({
        base_url: "https://ledger.example.com/api",
        path_template: "/refunds/{refund_id}",
        record_path: "data.0",
        bearer_token: "new-ledger-secret-token",
      }),
    );
    expect(await screen.findByText("Ledger refund connector saved.")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("new-ledger-secret-token");
  });

  it("runs saved connector reconciliation from the dashboard", async () => {
    render(<IntegrationsSettingsPage />);

    fireEvent.change(await screen.findByLabelText("Refund ID"), {
      target: { value: "RF-1001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run test reconciliation" }));

    await waitFor(() =>
      expect(api.testLedgerRefundConnector).toHaveBeenCalledWith({
        refund_id: "RF-1001",
        claimed: {
          refund_id: "RF-1001",
          amount_usd: 42.5,
          currency: "USD",
          status: "posted",
        },
        amount_usd: 42.5,
        currency: "USD",
        match_fields: ["refund_id", "amount_usd", "currency", "status"],
      }),
    );
    expect(await screen.findByText("Ledger refund test recorded matched.")).toBeInTheDocument();
    expect(screen.getByText("ledger:RF-1001")).toBeInTheDocument();
  });

  it("surfaces customer record connector without leaking secrets", async () => {
    api.listOutcomeReconciliations.mockResolvedValue({
      total_in_page: 1,
      items: [
        {
          id: "check_customer_record",
          project_id: "proj_1",
          call_id: "call_crm_api",
          trace_id: "trace_crm_api",
          runtime_policy_decision_id: "decision_2",
          action_type: "customer_record_update",
          connector_type: "customer_record_api",
          system_ref: "crm:cus_999",
          verdict: "matched",
          reason: "all_compared_fields_matched",
          amount_usd: null,
          currency: null,
          claimed: { customer_id: "cus_999", email: "owner@example.com" },
          actual: { customer_id: "cus_999", email: "owner@example.com" },
          comparison: { compared_fields: [], mismatches: [] },
          idempotency_key: "call_crm_api:cus_999",
          metadata: {
            connector_kind: "customer_record_api",
            connector: {
              request_url: "https://crm.example.com/api/customers/cus_999",
              http_status: 200,
              record_path: "data",
              bearer_token: "crm-secret-token",
            },
          },
          checked_at: "2026-06-20T09:10:00Z",
          created_at: "2026-06-20T09:10:00Z",
        },
      ],
    });

    render(<IntegrationsSettingsPage />);

    const heading = await screen.findByRole("heading", { name: "Customer record connector" });
    expect(heading).toBeInTheDocument();
    expect(heading.closest("article")?.getAttribute("id")).toBe("customer-record-connector");
    expect(screen.getByText("https://crm.***/...")).toBeInTheDocument();
    expect(screen.getByText("crm:cus_999")).toBeInTheDocument();
    expect(screen.getAllByText("Stored token ending oken").length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toContain("crm-secret-token");
  });

  it("copies the customer record reconciliation payload", async () => {
    const clipboardWrite = vi.spyOn(navigator.clipboard, "writeText");
    render(<IntegrationsSettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Copy CRM saved test payload" }));

    await waitFor(() => expect(clipboardWrite).toHaveBeenCalled());
    const copied = clipboardWrite.mock.calls[0]?.[0] as string;
    expect(copied).toContain("/v1/integrations/system-of-record/customer-record/test");
    expect(copied).not.toContain("bearer_token");
    expect(copied).not.toContain("$CRM_TOKEN");
    expect(await screen.findByText("Customer record saved-connector test payload copied.")).toBeInTheDocument();
  });

  it("saves customer record connector config without rendering the token", async () => {
    render(<IntegrationsSettingsPage />);

    fireEvent.change(await screen.findByLabelText("CRM bearer token"), {
      target: { value: "new-crm-secret-token" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save CRM connector" }));

    await waitFor(() =>
      expect(api.saveCustomerRecordConnectorConfig).toHaveBeenCalledWith({
        base_url: "https://crm.example.com/api",
        path_template: "/customers/{customer_id}",
        record_path: "data",
        bearer_token: "new-crm-secret-token",
      }),
    );
    expect(await screen.findByText("Customer record connector saved.")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("new-crm-secret-token");
  });

  it("runs saved customer record reconciliation from the dashboard", async () => {
    render(<IntegrationsSettingsPage />);

    fireEvent.change(await screen.findByLabelText("Customer ID"), {
      target: { value: "CUS-1001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run CRM test reconciliation" }));

    await waitFor(() =>
      expect(api.testCustomerRecordConnector).toHaveBeenCalledWith({
        customer_id: "CUS-1001",
        claimed: {
          customer_id: "CUS-1001",
          email: "owner@example.com",
          status: "active",
          account_id: "acct_1001",
        },
        match_fields: ["customer_id", "email", "status", "account_id"],
      }),
    );
    expect(await screen.findByText("Customer record test recorded matched.")).toBeInTheDocument();
    expect(screen.getByText("crm:CUS-1001")).toBeInTheDocument();
  });
});
