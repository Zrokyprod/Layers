import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentProfileResponse } from "@/lib/api";
import type { ApiKeyCreateResponse, ApiKeyResponse, ProjectResponse } from "@/lib/types";
import AgentControlSetupPage from "./page";

const api = vi.hoisted(() => ({
  createProjectApiKey: vi.fn(),
  createAgentProfile: vi.fn(),
  enforceAgentProfile: vi.fn(),
  getProjectSettings: vi.fn(),
  installActionPack: vi.fn(),
  listActionIntents: vi.fn(),
  listActionPacks: vi.fn(),
  listAgentProfiles: vi.fn(),
  listProjectApiKeys: vi.fn(),
}));

const navigation = vi.hoisted(() => ({ query: "" }));

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

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(navigation.query),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    createProjectApiKey: api.createProjectApiKey,
    createAgentProfile: api.createAgentProfile,
    enforceAgentProfile: api.enforceAgentProfile,
    getProjectSettings: api.getProjectSettings,
    installActionPack: api.installActionPack,
    listActionIntents: api.listActionIntents,
    listActionPacks: api.listActionPacks,
    listAgentProfiles: api.listAgentProfiles,
    listProjectApiKeys: api.listProjectApiKeys,
  };
});

function profile(overrides: Partial<AgentProfileResponse> = {}): AgentProfileResponse {
  return { id: "agent_1", display_name: "Ops Agent", ...overrides } as AgentProfileResponse;
}

function project(overrides: Partial<ProjectResponse> = {}): ProjectResponse {
  return {
    project_id: "proj_1",
    name: "My Project",
    owner_ref: "acct_1",
    is_active: true,
    created_at: "2026-07-04T00:00:00Z",
    updated_at: "2026-07-04T00:00:00Z",
    ...overrides,
  };
}

function apiKey(overrides: Partial<ApiKeyResponse> = {}): ApiKeyResponse {
  return {
    key_id: "key_1",
    project_id: "proj_1",
    name: "Protected agent runtime key",
    key_prefix: "zk_live_demo",
    scopes: ["project:member"],
    revoked: false,
    expired: false,
    expires_at: null,
    rotated_from_key_id: null,
    last_used_at: null,
    created_at: "2026-07-04T00:00:00Z",
    ...overrides,
  };
}

function createdApiKey(overrides: Partial<ApiKeyCreateResponse> = {}): ApiKeyCreateResponse {
  return {
    ...apiKey(),
    api_key: "zk_live_created_secret",
    ...overrides,
  };
}

function pack(overrides: Record<string, unknown> = {}) {
  return {
    id: "support-ops-v1",
    display_name: "Support operations",
    summary: "Guard customer refunds and CRM updates.",
    primary_runtime_path: "sdk",
    recommended_connectors: [
      "ledger_refund",
      "crm_record",
      "zendesk_ticket",
      "customer_identity",
      "subscription_billing",
      "email_delivery",
      "slack_approval_alert",
    ],
    native_tool_families: ["stripe_refund", "hubspot_customer", "zendesk_ticket", "intercom"],
    quickstart_steps: [],
    dashboard_href: "/agents/setup",
    contract_templates: [
      {
        contract_key: "customer.access.grant",
        version: "1.0",
        contract_version: "customer.access.grant/1.0",
        action_type: "customer.access.grant",
        operation_kind: "UPDATE",
        domain_family: "customer_operations",
        risk_class: "R3",
        connector_family: "customer_identity",
        schema: {},
        verification_profile: {},
      },
      {
        contract_key: "support.ticket.close",
        version: "1.0",
        contract_version: "support.ticket.close/1.0",
        action_type: "support.ticket.close",
        operation_kind: "UPDATE",
        domain_family: "customer_operations",
        risk_class: "R2",
        connector_family: "zendesk_ticket",
        schema: {},
        verification_profile: {},
      },
      {
        contract_key: "customer.message.send",
        version: "1.0",
        contract_version: "customer.message.send/1.0",
        action_type: "customer.message.send",
        operation_kind: "SEND",
        domain_family: "customer_operations",
        risk_class: "R2",
        connector_family: "email_delivery",
        schema: {},
        verification_profile: {},
      },
      {
        contract_key: "customer.data.export",
        version: "1.0",
        contract_version: "customer.data.export/1.0",
        action_type: "customer.data.export",
        operation_kind: "EXPORT",
        domain_family: "customer_operations",
        risk_class: "R4",
        connector_family: "generic_rest",
        schema: {},
        verification_profile: {},
      },
      {
        contract_key: "customer.record.update",
        version: "1.0",
        contract_version: "customer.record.update/1.0",
        action_type: "customer_record_update",
        operation_kind: "UPDATE",
        domain_family: "customer_operations",
        risk_class: "R2",
        connector_family: "crm_record",
        schema: {},
        verification_profile: {},
      },
      {
        contract_key: "customer.refund.transfer",
        version: "1.0",
        contract_version: "customer.refund.transfer/1.0",
        action_type: "refund",
        operation_kind: "TRANSFER",
        domain_family: "customer_operations",
        risk_class: "R3",
        connector_family: "ledger_refund",
        schema: {},
        verification_profile: {},
      },
    ],
    ...overrides,
  };
}

function financePack(overrides: Record<string, unknown> = {}) {
  return pack({
    id: "finance-ops-v1",
    display_name: "Finance operations",
    summary: "Guard invoice approvals, journal entries, and vendor payouts.",
    recommended_connectors: ["erp_finance", "accounting_system", "payments_ledger", "slack_approval_alert"],
    native_tool_families: ["netsuite_finance", "stripe_payment", "quickbooks_ledger", "generic_finance"],
    contract_templates: [
      {
        contract_key: "finance.invoice.approve",
        version: "1.0",
        contract_version: "finance.invoice.approve/1.0",
        action_type: "invoice_approve",
        operation_kind: "UPDATE",
        domain_family: "finance_operations",
        risk_class: "R3",
        connector_family: "erp_finance",
        schema: {},
        verification_profile: {},
      },
      {
        contract_key: "finance.journal.entry",
        version: "1.0",
        contract_version: "finance.journal.entry/1.0",
        action_type: "journal_entry",
        operation_kind: "UPDATE",
        domain_family: "finance_operations",
        risk_class: "R3",
        connector_family: "accounting_system",
        schema: {},
        verification_profile: {},
      },
      {
        contract_key: "finance.vendor.payout",
        version: "1.0",
        contract_version: "finance.vendor.payout/1.0",
        action_type: "vendor_payout",
        operation_kind: "TRANSFER",
        domain_family: "finance_operations",
        risk_class: "R4",
        connector_family: "payments_ledger",
        schema: {},
        verification_profile: {},
      },
    ],
    ...overrides,
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AgentControlSetupPage />
    </QueryClientProvider>,
  );
}

describe("Protected agent setup (minimal)", () => {
  beforeEach(() => {
    navigation.query = "";
    api.createProjectApiKey.mockReset().mockResolvedValue(createdApiKey());
    api.getProjectSettings.mockReset().mockResolvedValue(project());
    api.listProjectApiKeys.mockReset().mockResolvedValue([apiKey()]);
    api.createAgentProfile.mockReset().mockResolvedValue(profile());
    api.enforceAgentProfile.mockReset().mockResolvedValue(profile());
    api.listActionIntents.mockReset().mockResolvedValue({ items: [] });
    api.listActionPacks.mockReset().mockResolvedValue({
      items: [
        pack(),
        financePack(),
        pack({ id: "devops-release-v1", display_name: "DevOps release control", recommended_connectors: ["github_ci"], contract_templates: [] }),
        pack({ id: "ecommerce-ops-v1", display_name: "Ecommerce operations", recommended_connectors: ["order_management"], contract_templates: [] }),
      ],
    });
    api.installActionPack.mockReset().mockResolvedValue({
      pack: pack(),
      installed_contracts: [{ contract: { id: "contract_1", contract_version: "customer.record.update/1.0" }, created: true }],
    });
    api.listAgentProfiles.mockReset().mockResolvedValue({ items: [], total: 0 });
  });

  it("shows the pending capture path and defers advanced next steps", async () => {
    renderPage();

    expect(screen.getByText(/Create a key, define one agent, then send one protected action/i)).toBeInTheDocument();
    expect(await screen.findByText("Runtime key ready")).toBeInTheDocument();
    expect(screen.getByLabelText("Live capture status").textContent).toContain("SDK ready");
    expect(screen.getByLabelText("Live capture status").textContent).toContain("waiting for SDK run");
    expect(screen.getByText("Protected actions")).toBeInTheDocument();
    expect(screen.getByText("Unlocks after your first receipt.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Zroky control loop")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Tune policy" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review action" })).not.toBeInTheDocument();
  });

  it("creates and enforces an agent from a minimal form", async () => {
    renderPage();
    await screen.findByText("Runtime key ready");

    fireEvent.change(screen.getByLabelText("Agent name"), { target: { value: "Refund Agent" } });
    fireEvent.click(screen.getByRole("button", { name: /Create agent profile/i }));

    await waitFor(() => expect(api.createAgentProfile).toHaveBeenCalledTimes(1));
    expect(api.createAgentProfile.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        allowed_action_types: ["internal_api_mutation"],
        display_name: "Refund Agent",
        metadata: {
          runner_verification: {
            credential_ref: "customer-runner-secret://zroky/project-key/zk_live_demo",
            runner_mode: "customer_hosted",
          },
        },
        runtime_path: "sdk",
        tool_names: ["agent.protected_action"],
      }),
    );
    await waitFor(() => expect(api.enforceAgentProfile).toHaveBeenCalledWith("agent_1"));
    expect(await screen.findByText("Ops Agent")).toBeInTheDocument();
    expect(screen.getByText("Choose actions next")).toBeInTheDocument();
    expect(await screen.findByText("Support")).toBeInTheDocument();
    expect(screen.getByText("Support engine")).toBeInTheDocument();
    expect(screen.getByText("What can this agent do?")).toBeInTheDocument();
    expect(screen.getByText("Resolve tickets")).toBeInTheDocument();
    expect(screen.getByText("Issue refunds or credits")).toBeInTheDocument();
    expect(screen.getByText("Update customer records")).toBeInTheDocument();
    expect(screen.getByText("Guardrails Zroky will install")).toBeInTheDocument();
    expect(screen.getByText("CRM record")).toBeInTheDocument();
    expect(screen.getByText("Refund ledger")).toBeInTheDocument();
    expect(screen.queryByText("Direct app connectors")).not.toBeInTheDocument();
    expect(screen.queryByText("Advanced: exact installed actions")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Install protected actions" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Add connectors" })).not.toBeInTheDocument();
    expect(screen.queryByText(/zroky doctor/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Live capture status").textContent).toContain("Policy checked");
  });

  it("installs a protected action pack before showing run commands", async () => {
    api.listAgentProfiles.mockResolvedValue({ items: [profile({ display_name: "Manual QA Agent" })], total: 1 });

    renderPage();

    expect(await screen.findByText("Manual QA Agent")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Install protected actions" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Install protected actions" }));

    await waitFor(() => expect(api.installActionPack).toHaveBeenCalledWith("support-ops-v1"));
    expect(await screen.findByText(/Support operations installed/i)).toBeInTheDocument();
    expect(screen.getByText("Install")).toBeInTheDocument();
    expect(screen.getByText("Run scenario")).toBeInTheDocument();
    expect(screen.getByText(/python agent.py access-grant/i)).toBeInTheDocument();
  });

  it("shows finance as a money-risk workflow instead of connector logos", async () => {
    api.listAgentProfiles.mockResolvedValue({ items: [profile({ display_name: "Finance QA Agent" })], total: 1 });

    renderPage();

    expect(await screen.findByText("Finance QA Agent")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /Finance/i }));

    expect(screen.getByText("Finance system")).toBeInTheDocument();
    expect(screen.getByText("NetSuite")).toBeInTheDocument();
    expect(screen.getByText("Stripe Payments")).toBeInTheDocument();
    expect(screen.getAllByText("Generic Finance API").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Postgres Read").length).toBeGreaterThan(0);
    expect(screen.getByText("QuickBooks template")).toBeInTheDocument();
    expect(screen.getByText("What money risk can this agent touch?")).toBeInTheDocument();
    expect(screen.getByText("Approve invoices")).toBeInTheDocument();
    expect(screen.getByText("Create journal entries")).toBeInTheDocument();
    expect(screen.getByText("Send vendor payouts")).toBeInTheDocument();
    expect(screen.getByText("3 protected actions")).toBeInTheDocument();
    expect(screen.getByText("Payments ledger")).toBeInTheDocument();
    expect(screen.getByText("Stripe payment")).toBeInTheDocument();
    expect(screen.getByText("Slack approval")).toBeInTheDocument();
    expect(screen.queryByText("Direct app connectors")).not.toBeInTheDocument();
    expect(screen.queryByText("Advanced: exact installed actions")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Add connectors" })).not.toBeInTheDocument();
  });

  it("reuses an existing agent profile instead of blocking on duplicate setup", async () => {
    api.listAgentProfiles.mockResolvedValue({ items: [profile({ display_name: "Manual QA Agent" })], total: 1 });

    renderPage();

    expect(await screen.findByText("Manual QA Agent")).toBeInTheDocument();
    expect(screen.getByText("Choose actions next")).toBeInTheDocument();
    expect(screen.getByText("Protected actions")).toBeInTheDocument();
    expect(api.createAgentProfile).not.toHaveBeenCalled();
  });

  it("creates a runtime project key inline when none exists", async () => {
    api.listProjectApiKeys.mockResolvedValue([]);
    renderPage();

    const createKeyButton = await screen.findByRole("button", { name: "Create project key" });
    await waitFor(() => expect((createKeyButton as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(createKeyButton);

    await waitFor(() => expect(api.createProjectApiKey).toHaveBeenCalledWith("proj_1", {
      name: "Protected agent runtime key",
      expires_in_days: 90,
      scopes: ["project:member"],
    }));
    expect(await screen.findByText("zk_live_demo...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Copy key/i })).toBeInTheDocument();
    expect(screen.getByText(".env")).toBeInTheDocument();
    expect(screen.getByText(/ZROKY_API_KEY=zk_live_demo/i)).toBeInTheDocument();
    expect(screen.getByText(/ZROKY_PROJECT_ID=proj_1/i)).toBeInTheDocument();
    expect(screen.queryByText(/pip install zroky/i)).not.toBeInTheDocument();
  });

  it("prefills the agent name from the query param", () => {
    navigation.query = "agentName=Shadow%20Agent";
    renderPage();
    expect((screen.getByLabelText("Agent name") as HTMLInputElement).value).toBe("Shadow Agent");
  });

  it("requires an agent name before creating", async () => {
    renderPage();
    await screen.findByText("Runtime key ready");
    fireEvent.click(screen.getByRole("button", { name: /Create agent profile/i }));
    expect(await screen.findByText(/Give the agent a name/i)).toBeInTheDocument();
    expect(api.createAgentProfile).not.toHaveBeenCalled();
  });
});
