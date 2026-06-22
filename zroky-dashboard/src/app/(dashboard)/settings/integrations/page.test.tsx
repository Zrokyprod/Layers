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
  reconcileSavedCustomerRecord: vi.fn(),
  reconcileSavedLedgerRefund: vi.fn(),
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

const readyLedgerReadiness = {
  status: "ready",
  contract: {
    schema_version: "system_of_record_connector.v1",
    connector_type: "ledger_refund_api",
    adapter: "https_json_record",
    system_of_record: "ledger_refund",
    required_inputs: [
      "https_base_url",
      "path_template_with_refund_id",
      "read_scoped_bearer_token",
      "safe_existing_refund_id",
    ],
    required_record_fields: ["refund_id", "status"],
    recommended_record_fields: ["amount_usd", "currency"],
  },
  checks: {
    config_saved: true,
    bearer_token_present: true,
    saved_test_matched: true,
    connector_attempted: true,
    http_2xx: true,
    no_connector_error_code: true,
    not_retryable_failure: true,
  },
  blockers: [],
  last_checked_at: "2026-06-20T09:00:00Z",
};

const notReadyCustomerReadiness = {
  status: "not_ready",
  contract: {
    schema_version: "system_of_record_connector.v1",
    connector_type: "customer_record_api",
    adapter: "https_json_record",
    system_of_record: "customer_record",
    required_inputs: [
      "https_base_url",
      "path_template_with_customer_id",
      "read_scoped_bearer_token",
      "safe_existing_customer_id",
    ],
    required_record_fields: ["customer_id", "status"],
    recommended_record_fields: ["email", "account_id"],
  },
  checks: {
    config_saved: true,
    bearer_token_present: true,
    saved_test_matched: false,
    connector_attempted: false,
    http_2xx: false,
    no_connector_error_code: true,
    not_retryable_failure: true,
  },
  blockers: [
    "Latest connector test did not reconcile as matched.",
    "Connector has not attempted a system-of-record read.",
    "Latest connector test did not return a 2xx HTTP response.",
  ],
  last_checked_at: null,
};

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
      readiness: readyLedgerReadiness,
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
      readiness: notReadyCustomerReadiness,
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
    api.reconcileSavedLedgerRefund.mockResolvedValue({
      id: "check_ledger_saved",
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
      metadata: { connector_kind: "ledger_refund_api", source: "dashboard_saved_connector_proof" },
      checked_at: "2026-06-20T09:20:00Z",
      created_at: "2026-06-20T09:20:00Z",
    });
    api.reconcileSavedCustomerRecord.mockResolvedValue({
      id: "check_customer_saved",
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
      metadata: { connector_kind: "customer_record_api", source: "dashboard_saved_connector_proof" },
      checked_at: "2026-06-20T09:25:00Z",
      created_at: "2026-06-20T09:25:00Z",
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
    expect(screen.getAllByText("ledger:rf_999").length).toBeGreaterThan(0);
    const card = heading.closest("article");
    expect(card).not.toBeNull();
    const readiness = within(card as HTMLElement).getByLabelText("Ledger refund readiness contract");
    expect(within(readiness).getAllByText("Ready").length).toBeGreaterThan(0);
    expect(within(readiness).getByText("Ledger Refund")).toBeInTheDocument();
    expect(within(readiness).getByText("Https Json Record")).toBeInTheDocument();
    expect(within(readiness).getByText(/Https Base Url/)).toBeInTheDocument();
    expect(within(readiness).getByText("Refund Id, Status")).toBeInTheDocument();
    expect(within(readiness).getByText("No readiness blockers.")).toBeInTheDocument();
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
      readiness: {
        ...readyLedgerReadiness,
        status: "not_ready",
        checks: { ...readyLedgerReadiness.checks, http_2xx: false, not_retryable_failure: false },
        blockers: [
          "Latest connector test did not return a 2xx HTTP response.",
          "Latest connector test ended in a retryable failure.",
        ],
      },
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
    const readiness = await screen.findByLabelText("Ledger refund readiness blockers");
    expect(within(readiness).getByText("Latest connector test did not return a 2xx HTTP response.")).toBeInTheDocument();
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

  it("surfaces ledger preflight handoff command and downloadable template", async () => {
    const clipboardWrite = vi.spyOn(navigator.clipboard, "writeText");
    render(<IntegrationsSettingsPage />);

    const heading = await screen.findByRole("heading", { name: "Ledger refund connector" });
    const connectorCard = heading.closest("article");
    expect(connectorCard).not.toBeNull();

    fireEvent.change(within(connectorCard as HTMLElement).getByLabelText("Refund ID"), {
      target: { value: "RF-PILOT-1" },
    });

    const command = within(connectorCard as HTMLElement).getByLabelText("Ledger refund preflight command");
    expect(command.textContent).toContain("--scenario refund --preflight-only");
    expect(command.textContent).toContain("--ledger-base-url https://ledger.example.com/api");
    expect(command.textContent).not.toContain("ledger-secret-token");

    const fullProofCommand = within(connectorCard as HTMLElement).getByLabelText("Ledger refund full proof command");
    expect(fullProofCommand.textContent).toContain("--scenario refund --api-base-url https://api.zroky.ai");
    expect(fullProofCommand.textContent).toContain("--write-evidence artifacts/design-partner-refund-live-evidence.json");
    expect(fullProofCommand.textContent).toContain("--refund-id RF-PILOT-1");
    expect(fullProofCommand.textContent).not.toContain("--preflight-only");
    expect(fullProofCommand.textContent).not.toContain("ledger-secret-token");

    fireEvent.click(within(connectorCard as HTMLElement).getByRole("button", { name: "Copy preflight command" }));

    await waitFor(() =>
      expect(clipboardWrite).toHaveBeenCalledWith(
        expect.stringContaining("--refund-id RF-PILOT-1"),
      ),
    );
    expect(await screen.findByText("Ledger refund preflight command copied.")).toBeInTheDocument();

    fireEvent.click(within(connectorCard as HTMLElement).getByRole("button", { name: "Copy full proof command" }));

    await waitFor(() =>
      expect(clipboardWrite).toHaveBeenCalledWith(
        expect.stringContaining("--write-evidence artifacts/design-partner-refund-live-evidence.json"),
      ),
    );
    expect(await screen.findByText("Ledger refund full proof command copied.")).toBeInTheDocument();

    fireEvent.click(within(connectorCard as HTMLElement).getByRole("button", { name: "Download template JSON" }));

    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    const blob = vi.mocked(URL.createObjectURL).mock.calls.at(-1)?.[0] as Blob;
    const template = await blob.text();
    expect(template).toContain('"connector_type": "ledger_refund_api"');
    expect(template).toContain('"readiness_contract"');
    expect(template).toContain('"system_of_record": "ledger_refund"');
    expect(template).toContain('"readiness_status": "ready"');
    expect(template).toContain('"bearer_token": "<ledger_bearer_token>"');
    expect(template).toContain('"refund_id": "RF-PILOT-1"');
    expect(template).not.toContain("ledger-secret-token");
    expect(await screen.findByText("Ledger refund connector template downloaded.")).toBeInTheDocument();
  });

  it("exports a ready ledger preflight summary without connector secrets", async () => {
    render(<IntegrationsSettingsPage />);

    const heading = await screen.findByRole("heading", { name: "Ledger refund connector" });
    const connectorCard = heading.closest("article");
    expect(connectorCard).not.toBeNull();

    const summary = await within(connectorCard as HTMLElement).findByLabelText("Ledger refund preflight summary");
    expect(within(summary).getAllByText("Ready for pilot handoff").length).toBeGreaterThan(0);
    expect(within(summary).getByText("None in latest 25")).toBeInTheDocument();

    fireEvent.click(within(summary).getByRole("button", { name: "Download preflight summary" }));

    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    const blob = vi.mocked(URL.createObjectURL).mock.calls.at(-1)?.[0] as Blob;
    const payload = JSON.parse(await blob.text()) as Record<string, unknown>;
    expect(payload).toMatchObject({
      schema_version: "zroky_connector_preflight_summary.v1",
      connector_kind: "ledger_refund_api",
      ready_for_pilot_handoff: true,
      status: {
        connected: true,
        health_status: "healthy",
        last_verdict: "matched",
        last_http_status: "200",
        last_attempts: "2",
        readiness_status: "ready",
        readiness_blockers: [],
      },
      readiness_contract: {
        system_of_record: "ledger_refund",
        adapter: "https_json_record",
      },
      latest_check: {
        id: "check_ledger_refund",
        verdict: "matched",
        system_ref: "ledger:rf_999",
      },
      failed_attempts: [],
      next_full_proof_command: expect.stringContaining("--write-evidence artifacts/design-partner-refund-live-evidence.json"),
    });
    expect(String(payload.next_full_proof_command)).not.toContain("--preflight-only");
    expect(JSON.stringify(payload)).not.toContain("ledger-secret-token");
    expect(await screen.findByText("Ledger refund preflight summary downloaded.")).toBeInTheDocument();
  });

  it("shows failed ledger preflight attempts with exact retry guidance", async () => {
    api.getLedgerRefundConnectorStatus.mockResolvedValue({
      connected: true,
      connector_type: "ledger_refund_api",
      base_url: "https://ledger.example.com/api",
      path_template: "/refunds/{refund_id}",
      record_path: "data",
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
    api.listOutcomeReconciliations.mockResolvedValue({
      total_in_page: 1,
      items: [
        {
          id: "check_ledger_timeout",
          project_id: "proj_1",
          call_id: "call_refund_api",
          trace_id: "trace_refund_api",
          runtime_policy_decision_id: null,
          action_type: "refund",
          connector_type: "ledger_refund_api",
          system_ref: "ledger:rf_timeout",
          verdict: "not_verified",
          reason: "connector_timeout",
          amount_usd: 42.5,
          currency: "USD",
          claimed: { refund_id: "rf_timeout", amount_usd: 42.5, currency: "USD" },
          actual: null,
          comparison: { compared_fields: [], mismatches: [] },
          idempotency_key: "call_refund_api:rf_timeout",
          metadata: {
            connector_kind: "ledger_refund_api",
            connector: {
              request_url: "https://ledger.example.com/api/refunds/rf_timeout",
              error_code: "connector_timeout",
              error: "ReadTimeout",
              retryable: true,
              attempts: 2,
              bearer_token: "ledger-secret-token",
            },
          },
          checked_at: "2026-06-20T09:00:00Z",
          created_at: "2026-06-20T09:00:00Z",
        },
      ],
    });

    render(<IntegrationsSettingsPage />);

    const heading = await screen.findByRole("heading", { name: "Ledger refund connector" });
    const connectorCard = heading.closest("article");
    expect(connectorCard).not.toBeNull();

    const summary = await within(connectorCard as HTMLElement).findByLabelText("Ledger refund preflight summary");
    expect(within(summary).getAllByText("Not ready for pilot handoff").length).toBeGreaterThan(0);
    expect(within(summary).getByText("1 in latest 25")).toBeInTheDocument();

    const timeline = within(connectorCard as HTMLElement).getByLabelText("Ledger refund failed preflight attempts");
    expect(within(timeline).getByText("Connector Timeout / retryable")).toBeInTheDocument();
    expect(within(timeline).getByText("2 attempts")).toBeInTheDocument();
    expect(within(timeline).getByText("ledger:rf_timeout", { exact: false })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("ledger-secret-token");
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

  it("shows exact fix guidance for auth-failed ledger preflight", async () => {
    api.getLedgerRefundConnectorStatus.mockResolvedValue({
      connected: true,
      connector_type: "ledger_refund_api",
      base_url: "https://ledger.example.com/api",
      path_template: "/refunds/{refund_id}",
      record_path: "data",
      query: null,
      has_bearer_token: true,
      bearer_token_last4: "oken",
      last_tested_at: "2026-06-20T09:00:00Z",
      health_status: "auth_failed",
      last_verdict: "not_verified",
      last_error: "http_error",
      last_error_code: "auth_failed",
      last_http_status: 401,
      last_attempts: 1,
      last_retryable: false,
      last_checked_at: "2026-06-20T09:00:00Z",
      created_at: "2026-06-20T08:00:00Z",
      updated_at: "2026-06-20T08:30:00Z",
    });
    api.listOutcomeReconciliations.mockResolvedValue({ total_in_page: 0, items: [] });

    render(<IntegrationsSettingsPage />);

    const guidance = await screen.findByLabelText("Ledger refund preflight guidance");
    expect(within(guidance).getByText("Action required")).toBeInTheDocument();
    expect(
      within(guidance).getByText(
        "Fix ledger/refund auth: rotate the bearer token, confirm scopes, then rerun preflight.",
      ),
    ).toBeInTheDocument();
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
    expect(screen.getAllByText("ledger:RF-1001").length).toBeGreaterThan(0);
  });

  it("runs ledger saved proof without sending connector secrets", async () => {
    render(<IntegrationsSettingsPage />);

    const heading = await screen.findByRole("heading", { name: "Ledger refund connector" });
    const connectorCard = heading.closest("article");
    expect(connectorCard).not.toBeNull();

    fireEvent.change(within(connectorCard as HTMLElement).getByLabelText("Refund ID"), {
      target: { value: "RF-1001" },
    });
    const proofButton = within(connectorCard as HTMLElement).getByRole("button", { name: "Run saved proof" });

    await waitFor(() => expect((proofButton as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(proofButton);

    await waitFor(() =>
      expect(api.reconcileSavedLedgerRefund).toHaveBeenCalledWith({
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
        metadata: { source: "dashboard_saved_connector_proof" },
      }),
    );
    expect(api.testLedgerRefundConnector).not.toHaveBeenCalled();
    expect(JSON.stringify(api.reconcileSavedLedgerRefund.mock.calls[0]?.[0])).not.toMatch(/bearer|token/i);
    expect(await screen.findByText("Ledger saved proof recorded matched.")).toBeInTheDocument();
    expect(screen.getAllByText("ledger:RF-1001").length).toBeGreaterThan(0);
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
    expect(screen.getAllByText("crm:cus_999").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Stored token ending oken").length).toBeGreaterThan(0);
    const card = heading.closest("article");
    expect(card).not.toBeNull();
    const readiness = within(card as HTMLElement).getByLabelText("Customer record readiness contract");
    expect(within(readiness).getAllByText("Not ready").length).toBeGreaterThan(0);
    expect(within(readiness).getByText("Customer Record")).toBeInTheDocument();
    expect(within(readiness).getByText("Latest connector test did not reconcile as matched.")).toBeInTheDocument();
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

  it("surfaces customer preflight handoff command and downloadable template", async () => {
    const clipboardWrite = vi.spyOn(navigator.clipboard, "writeText");
    render(<IntegrationsSettingsPage />);

    const heading = await screen.findByRole("heading", { name: "Customer record connector" });
    const connectorCard = heading.closest("article");
    expect(connectorCard).not.toBeNull();

    fireEvent.change(within(connectorCard as HTMLElement).getByLabelText("Customer ID"), {
      target: { value: "CUS-PILOT-1" },
    });

    const command = within(connectorCard as HTMLElement).getByLabelText("Customer record preflight command");
    expect(command.textContent).toContain("--scenario customer-record --preflight-only");
    expect(command.textContent).toContain("--crm-base-url https://crm.example.com/api");
    expect(command.textContent).not.toContain("crm-secret-token");

    const fullProofCommand = within(connectorCard as HTMLElement).getByLabelText("Customer record full proof command");
    expect(fullProofCommand.textContent).toContain("--scenario customer-record --api-base-url https://api.zroky.ai");
    expect(fullProofCommand.textContent).toContain("--write-evidence artifacts/design-partner-crm-live-evidence.json");
    expect(fullProofCommand.textContent).toContain("--customer-id CUS-PILOT-1");
    expect(fullProofCommand.textContent).not.toContain("--preflight-only");
    expect(fullProofCommand.textContent).not.toContain("crm-secret-token");

    fireEvent.click(within(connectorCard as HTMLElement).getByRole("button", { name: "Copy preflight command" }));

    await waitFor(() =>
      expect(clipboardWrite).toHaveBeenCalledWith(
        expect.stringContaining("--customer-id CUS-PILOT-1"),
      ),
    );
    expect(await screen.findByText("Customer record preflight command copied.")).toBeInTheDocument();

    fireEvent.click(within(connectorCard as HTMLElement).getByRole("button", { name: "Copy full proof command" }));

    await waitFor(() =>
      expect(clipboardWrite).toHaveBeenCalledWith(
        expect.stringContaining("--write-evidence artifacts/design-partner-crm-live-evidence.json"),
      ),
    );
    expect(await screen.findByText("Customer record full proof command copied.")).toBeInTheDocument();

    fireEvent.click(within(connectorCard as HTMLElement).getByRole("button", { name: "Download template JSON" }));

    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    const blob = vi.mocked(URL.createObjectURL).mock.calls.at(-1)?.[0] as Blob;
    const template = await blob.text();
    expect(template).toContain('"connector_type": "customer_record_api"');
    expect(template).toContain('"readiness_contract"');
    expect(template).toContain('"system_of_record": "customer_record"');
    expect(template).toContain('"readiness_status": "ready"');
    expect(template).toContain('"bearer_token": "<crm_bearer_token>"');
    expect(template).toContain('"customer_id": "CUS-PILOT-1"');
    expect(template).not.toContain("crm-secret-token");
    expect(await screen.findByText("Customer record connector template downloaded.")).toBeInTheDocument();
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
    expect(screen.getAllByText("crm:CUS-1001").length).toBeGreaterThan(0);
  });

  it("runs customer saved proof without sending connector secrets", async () => {
    render(<IntegrationsSettingsPage />);

    const heading = await screen.findByRole("heading", { name: "Customer record connector" });
    const connectorCard = heading.closest("article");
    expect(connectorCard).not.toBeNull();

    fireEvent.change(within(connectorCard as HTMLElement).getByLabelText("Customer ID"), {
      target: { value: "CUS-1001" },
    });
    const proofButton = within(connectorCard as HTMLElement).getByRole("button", { name: "Run saved CRM proof" });

    await waitFor(() => expect((proofButton as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(proofButton);

    await waitFor(() =>
      expect(api.reconcileSavedCustomerRecord).toHaveBeenCalledWith({
        customer_id: "CUS-1001",
        claimed: {
          customer_id: "CUS-1001",
          email: "owner@example.com",
          status: "active",
          account_id: "acct_1001",
        },
        match_fields: ["customer_id", "email", "status", "account_id"],
        metadata: { source: "dashboard_saved_connector_proof" },
      }),
    );
    expect(api.testCustomerRecordConnector).not.toHaveBeenCalled();
    expect(JSON.stringify(api.reconcileSavedCustomerRecord.mock.calls[0]?.[0])).not.toMatch(/bearer|token/i);
    expect(await screen.findByText("Customer saved proof recorded matched.")).toBeInTheDocument();
    expect(screen.getAllByText("crm:CUS-1001").length).toBeGreaterThan(0);
  });
});
