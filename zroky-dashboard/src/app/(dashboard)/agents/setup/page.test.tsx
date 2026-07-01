import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ActionIntentResponse,
  ActionRunnerResponse,
  AgentProfileResponse,
  GenericRestConnectorStatusResponse,
  ToolRegistryResponse,
} from "@/lib/api";
import AgentControlSetupPage from "./page";

const api = vi.hoisted(() => ({
  createAgentProfile: vi.fn(),
  dryRunRuntimePolicy: vi.fn(),
  enforceAgentProfile: vi.fn(),
  getCustomerRecordConnectorStatus: vi.fn(),
  getGenericRestConnectorStatus: vi.fn(),
  getAgentProfile: vi.fn(),
  getHubSpotCrmConnectorStatus: vi.fn(),
  getLedgerRefundConnectorStatus: vi.fn(),
  getNetSuiteFinanceConnectorStatus: vi.fn(),
  getPostgresReadConnectorStatus: vi.fn(),
  getRazorpayRefundConnectorStatus: vi.fn(),
  getSalesforceCrmConnectorStatus: vi.fn(),
  getZendeskTicketConnectorStatus: vi.fn(),
  getJiraIssueConnectorStatus: vi.fn(),
  getZohoCrmConnectorStatus: vi.fn(),
  getToolRegistry: vi.fn(),
  listActionIntents: vi.fn(),
  listActionRunners: vi.fn(),
  updateAgentProfile: vi.fn(),
}));

const navigation = vi.hoisted(() => ({
  query: "",
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

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(navigation.query),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    createAgentProfile: api.createAgentProfile,
    dryRunRuntimePolicy: api.dryRunRuntimePolicy,
    enforceAgentProfile: api.enforceAgentProfile,
    getCustomerRecordConnectorStatus: api.getCustomerRecordConnectorStatus,
    getGenericRestConnectorStatus: api.getGenericRestConnectorStatus,
    getAgentProfile: api.getAgentProfile,
    getHubSpotCrmConnectorStatus: api.getHubSpotCrmConnectorStatus,
    getLedgerRefundConnectorStatus: api.getLedgerRefundConnectorStatus,
    getNetSuiteFinanceConnectorStatus: api.getNetSuiteFinanceConnectorStatus,
    getPostgresReadConnectorStatus: api.getPostgresReadConnectorStatus,
    getRazorpayRefundConnectorStatus: api.getRazorpayRefundConnectorStatus,
    getSalesforceCrmConnectorStatus: api.getSalesforceCrmConnectorStatus,
    getZendeskTicketConnectorStatus: api.getZendeskTicketConnectorStatus,
    getJiraIssueConnectorStatus: api.getJiraIssueConnectorStatus,
    getZohoCrmConnectorStatus: api.getZohoCrmConnectorStatus,
    getToolRegistry: api.getToolRegistry,
    listActionIntents: api.listActionIntents,
    listActionRunners: api.listActionRunners,
    updateAgentProfile: api.updateAgentProfile,
  };
});

function registry(): ToolRegistryResponse {
  return {
    schema_version: "zroky.agent_tool_control.v1",
    project_id: "proj_1",
    agent_id: null,
    action_type: "refund",
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
        recommended_for_action_types: ["refund"],
        requires_customer_credentials: false,
        dashboard_href: "/settings/keys",
        backend_capability: "runtime_policy.check",
        availability_notes: "Available for launch.",
      },
    ],
    verification_connectors: [
      {
        id: "ledger_refund",
        kind: "verification_connector",
        label: "Ledger / refund verifier",
        description: "Verify refund claims against a saved payment ledger read endpoint.",
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
      action_types: ["refund"],
      runtime_path_ids: ["sdk"],
      verification_connector_ids: ["ledger_refund"],
      native_tool_family_ids: ["slack_approval_alert"],
      next_steps: [
        "Wrap this agent's tool call with the SDK or route it through a gateway.",
        "Choose one verifier that can prove the real system outcome.",
      ],
    },
  };
}

function profile(overrides: Partial<AgentProfileResponse> = {}): AgentProfileResponse {
  return {
    schema_version: "zroky.agent_tool_control.v1",
    id: "agent_1",
    project_id: "proj_1",
    display_name: "Operations Agent",
    slug: "operations-agent",
    description: "Production Agent Workflow - Control one risky action.",
    runtime_path: "sdk",
    framework: "LangGraph",
    environment: "production",
    model_provider: "openai",
    model_name: "gpt-4.1",
    tool_names: ["internal.ops.execute", "crm.customers.update"],
    allowed_action_types: ["internal_api_mutation", "customer_record_update"],
    blocked_action_types: [],
    default_policy_id: null,
    risk_limits: {},
    verification_connectors: ["generic_rest"],
    metadata: {},
    is_active: true,
    created_at: "2026-06-20T09:00:00.000Z",
    updated_at: "2026-06-20T09:00:00.000Z",
    ...overrides,
  };
}

function enforcedProfile(): AgentProfileResponse {
  return {
    ...profile(),
    metadata: {
      protection_state: "enforced",
      runtime_policy_mandate_enforced: true,
      runtime_policy_mandate: {
        runner_id: "runner_1",
        runner_name: "operations-agent-runner",
        runner_type: "managed_sandbox",
        runner_environment: "production",
        runner_supported_operation_kinds: ["UPDATE"],
        runner_credential_ref: "cred_prod_protected_actions",
      },
    },
    updated_at: "2026-06-20T09:01:00.000Z",
  };
}

function actionRunner(overrides: Partial<ActionRunnerResponse> = {}): ActionRunnerResponse {
  return {
    runner_id: "runner_1",
    project_id: "proj_1",
    name: "operations-agent-runner",
    runner_type: "managed_sandbox",
    environment: "production",
    status: "online",
    supported_operation_kinds: ["UPDATE"],
    credential_scope: { credential_ref: "cred_prod_protected_actions" },
    heartbeat_payload: {},
    capability_version: "agent-setup.v1",
    last_heartbeat_at: "2026-06-20T09:01:00.000Z",
    created_at: "2026-06-20T09:00:00.000Z",
    updated_at: "2026-06-20T09:01:00.000Z",
    ...overrides,
  };
}

function actionIntent(overrides: Partial<ActionIntentResponse> = {}): ActionIntentResponse {
  return {
    action_id: "act_first_receipt",
    project_id: "proj_1",
    agent_id: "agent_1",
    agent_profile: {
      id: "agent_1",
      display_name: "Operations Agent",
      slug: "operations-agent",
      runtime_path: "sdk",
      environment: "production",
    },
    contract_version: "internal_api_mutation/1.0",
    action_type: "internal_api_mutation",
    operation_kind: "UPDATE",
    environment: "production",
    status: "authorized",
    proof_status: "matched",
    receipt_status: "generated",
    idempotency_key: "first_receipt",
    intent_digest: "sha256:first-receipt",
    canonical_intent: {},
    created_at: "2026-06-20T09:10:00.000Z",
    decided_at: "2026-06-20T09:10:05.000Z",
    authorized_at: "2026-06-20T09:10:10.000Z",
    runtime_policy_decision_id: "decision_first_receipt",
    deadline: null,
    status_url: "/v1/action-intents/act_first_receipt",
    ...overrides,
  };
}

function genericConnector(
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
    readiness: { status: "not_ready", checks: {}, blockers: ["connector config has not been saved"] },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function renderWizard() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={client}>
      <AgentControlSetupPage />
    </QueryClientProvider>,
  );
}

function clickStep(label: string) {
  const stepper = screen.getByLabelText("Agent setup steps");
  const button = within(stepper).getAllByRole("button").find((item) => item.textContent?.includes(label));
  if (!button) throw new Error(`Missing step button for ${label}`);
  fireEvent.click(button);
}

describe("AgentControlSetupPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.query = "";
    window.localStorage.clear();
    api.getToolRegistry.mockResolvedValue(registry());
    api.getAgentProfile.mockResolvedValue(profile());
    api.getLedgerRefundConnectorStatus.mockResolvedValue(genericConnector({ connector_type: "ledger_refund_api" }));
    api.getCustomerRecordConnectorStatus.mockResolvedValue(genericConnector({ connector_type: "customer_record_api" }));
    api.getGenericRestConnectorStatus.mockResolvedValue(genericConnector());
    api.getHubSpotCrmConnectorStatus.mockResolvedValue(genericConnector({ connector_type: "hubspot_crm" }));
    api.getNetSuiteFinanceConnectorStatus.mockResolvedValue(genericConnector({ connector_type: "netsuite_finance" }));
    api.getRazorpayRefundConnectorStatus.mockResolvedValue(genericConnector({ connector_type: "razorpay_refund" }));
    api.getPostgresReadConnectorStatus.mockResolvedValue(genericConnector({ connector_type: "postgres_read" }));
    api.getSalesforceCrmConnectorStatus.mockResolvedValue(genericConnector({ connector_type: "salesforce_crm" }));
    api.getZendeskTicketConnectorStatus.mockResolvedValue(genericConnector({ connector_type: "zendesk_ticket" }));
    api.getJiraIssueConnectorStatus.mockResolvedValue(genericConnector({ connector_type: "jira_issue" }));
    api.getZohoCrmConnectorStatus.mockResolvedValue(genericConnector({ connector_type: "zoho_crm" }));
    api.listActionIntents.mockResolvedValue({ items: [], total_in_page: 0, limit: 1, offset: 0 });
    api.listActionRunners.mockResolvedValue({ items: [] });
    api.createAgentProfile.mockResolvedValue(profile());
    api.updateAgentProfile.mockResolvedValue(profile());
    api.enforceAgentProfile.mockResolvedValue(enforcedProfile());
    api.dryRunRuntimePolicy.mockResolvedValue({
      recorded: false,
      decision: "requires_approval",
      status: "pending_approval",
      allowed: false,
      requires_approval: true,
      reasons: ["amount requires approval"],
      request: {},
      policy_hit: {},
      business_impact: {},
      intended_action: {},
      required_approval_count: 1,
    });
  });

  it("renders the full control setup workflow and protection plan preview", async () => {
    renderWizard();

    expect(await screen.findByText("Agent Control Setup")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Enable protection for this agent/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Agent setup readiness")).toBeInTheDocument();

    const stepper = screen.getByLabelText("Agent setup steps");
    expect(within(stepper).getByRole("button", { name: /Agent IdentityWho we protect/i })).toBeInTheDocument();
    expect(within(stepper).getByRole("button", { name: /Protected ActionFirst risky path/i })).toBeInTheDocument();
    expect(within(stepper).getByRole("button", { name: /Control PathPolicy and runner/i })).toBeInTheDocument();
    expect(within(stepper).getByRole("button", { name: /Proof & ReadinessDry-run and handoff/i })).toBeInTheDocument();
    expect(within(stepper).getByRole("button", { name: /Go LiveFirst matched receipt/i })).toBeInTheDocument();

    const preview = screen.getByLabelText("Protection plan");
    expect(within(preview).getByText("Control Plan")).toBeInTheDocument();
    expect(within(preview).getAllByText("Internal API change").length).toBeGreaterThan(0);
    expect(within(preview).getAllByText("Primary business system API").length).toBeGreaterThan(0);
    expect(within(screen.getByLabelText("Agent setup readiness")).getByText("Ready")).toBeInTheDocument();
    expect(within(preview).getByText("Advanced technical preview")).toBeInTheDocument();
  });

  it("prefills create mode from an observed telemetry agent name", async () => {
    navigation.query = "agentName=shadow-agent";
    window.localStorage.setItem("zroky.agentControlSetupWizard.v1", JSON.stringify({ agentName: "Stale draft" }));

    renderWizard();

    expect(await screen.findByDisplayValue("shadow-agent")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Stale draft")).toBeNull();
  });

  it("discovers risky actions from pasted tool names", async () => {
    renderWizard();

    clickStep("Protected Action");
    await screen.findByRole("heading", { name: "Protected Action" });
    fireEvent.change(screen.getByLabelText("Agent tools or function names"), {
      target: {
        value: "stripe.refunds.create, zendesk.tickets.update, sendgrid.messages.send",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: /Detect risky actions/i }));

    const detected = screen.getByLabelText("Detected risky actions");
    expect(within(detected).getByText("Refund customer payment").closest("button")?.className).toContain("is-selected");
    expect(within(detected).getByText("Update or close support ticket").closest("button")?.className).toContain("is-selected");
    expect(within(detected).getByText("Send customer-visible message").closest("button")?.className).toContain("is-selected");
  });

  it("allows essentials-only enable without optional business context or simulation", async () => {
    renderWizard();

    fireEvent.change(await screen.findByLabelText("Primary business goal"), {
      target: { value: "" },
    });
    clickStep("Proof & Readiness");
    fireEvent.click(screen.getByRole("button", { name: /Enable project policy/i }));

    await waitFor(() => expect(api.createAgentProfile).toHaveBeenCalledTimes(1));
    expect(api.enforceAgentProfile).toHaveBeenCalledWith("agent_1");
    const payload = api.createAgentProfile.mock.calls[0]?.[0];
    expect(payload.metadata.product_context.business_goal).toBe("");
    expect(payload.metadata.readiness_preview_completed).toBeUndefined();
  });

  it("blocks enable when essential policy thresholds are invalid", async () => {
    renderWizard();

    clickStep("Control Path");
    fireEvent.change(await screen.findByLabelText("Deny above"), {
      target: { value: "100" },
    });
    clickStep("Proof & Readiness");
    fireEvent.click(screen.getByRole("button", { name: /Enable project policy/i }));

    expect(api.createAgentProfile).not.toHaveBeenCalled();
    expect(api.enforceAgentProfile).not.toHaveBeenCalled();
    expect(screen.getByText(/Complete the essential readiness checklist/i)).toBeInTheDocument();
  });

  it("enables the project runtime policy through the backend without fake readiness flags", async () => {
    renderWizard();

    clickStep("Proof & Readiness");
    expect(await screen.findByText("Policy dry-run · not recorded")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Enable project policy/i }));

    await waitFor(() => {
      expect(api.createAgentProfile).toHaveBeenCalledTimes(1);
    });

    const payload = api.createAgentProfile.mock.calls[0]?.[0];
    expect(payload.display_name).toBe("Operations Agent");
    expect(payload.runtime_path).toBe("sdk");
    expect(payload.allowed_action_types).toEqual(["internal_api_mutation", "customer_record_update"]);
    expect(payload.verification_connectors).toEqual(["generic_rest"]);
    expect(payload.metadata.setup_source).toBe("agent_control_setup_wizard");
    expect(payload.metadata.protection_state).toBe("plan_saved");
    expect(payload.metadata.readiness).toBeUndefined();
    expect(payload.metadata.runtime_policy_mandate_enforced).toBe(false);
    expect(payload.metadata.product_context.product_name).toBe("Production Agent Workflow");
    expect(payload.metadata.workflow_manifest.workflow_id).toBe("protected_action_workflow");
    expect(payload.metadata.action_contracts[0]).toMatchObject({
      id: "protected_action_workflow.internal_api_mutation",
      verb: "UPDATE",
      risk_class: "R3",
      runner_required: true,
      verifier: "generic_rest",
      proof_assertion: "Action result exists in the source of record and matches the requested intent.",
    });
    expect(payload.metadata.readiness_preview_completed).toBeUndefined();
    expect(payload.metadata.local_readiness_test_ran).toBeUndefined();
    expect(payload.metadata.receipt_preview_generated).toBeUndefined();
    expect(payload.metadata.proof.proof_assertion).toBe("Action result exists in the source of record and matches the requested intent.");
    expect(payload.metadata.control_binding.readiness).toBeUndefined();
    expect(api.enforceAgentProfile).toHaveBeenCalledWith("agent_1");
    expect(await screen.findByText("Project policy enabled for Operations Agent.")).toBeInTheDocument();
    expect(screen.getByText(/Project runtime policy enforced/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Agent profile" }).getAttribute("href")).toBe("/agents/agent_1");
  });

  it("runs a real policy dry-run after enforcement without recording it", async () => {
    renderWizard();

    clickStep("Proof & Readiness");
    fireEvent.click(screen.getByRole("button", { name: /Enable project policy/i }));

    expect(await screen.findByText("Project policy enabled for Operations Agent.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Test amount USD"), { target: { value: "750" } });
    fireEvent.click(screen.getByRole("button", { name: /Run policy dry-run/i }));

    await waitFor(() => expect(api.dryRunRuntimePolicy).toHaveBeenCalledTimes(1));
    expect(api.dryRunRuntimePolicy.mock.calls[0]?.[0]).toMatchObject({
      action_type: "internal_api_mutation",
      operation_kind: "UPDATE",
      impact_usd: 750,
      metadata: { recorded: false, source: "agent_setup_policy_dry_run" },
    });
    await waitFor(() => expect(screen.getAllByText("pending approval").length).toBeGreaterThan(0));
    expect(screen.getAllByText(/not recorded/i).length).toBeGreaterThan(0);
  });

  it("go-live step waits for the first real protected action with an agent_id SDK snippet", async () => {
    navigation.query = "agentId=agent_existing";
    api.getAgentProfile.mockResolvedValue(enforcedProfile());
    api.listActionRunners.mockResolvedValue({ items: [actionRunner()] });
    api.getGenericRestConnectorStatus.mockResolvedValue(genericConnector({
      connected: true,
      health_status: "healthy",
      last_verdict: "matched",
      last_tested_at: "2026-06-20T09:05:00.000Z",
      readiness: { status: "ready", checks: {}, blockers: [] },
    }));
    api.listActionIntents.mockResolvedValue({ items: [], total_in_page: 0, limit: 5, offset: 0 });

    renderWizard();

    expect(await screen.findByRole("heading", { name: /Run the first protected action/i })).toBeInTheDocument();
    clickStep("Go Live");

    expect(await screen.findByRole("heading", { name: "Go Live" })).toBeInTheDocument();
    expect(screen.getByText("Waiting for first protected action")).toBeInTheDocument();
    expect(screen.getByText(/zroky.verified_action/)).toBeInTheDocument();
    expect(screen.getByText(/agent_id=\"agent_1\"/)).toBeInTheDocument();
  });

  it("marks the wizard live only after a matched generated receipt exists", async () => {
    navigation.query = "agentId=agent_existing";
    api.getAgentProfile.mockResolvedValue(enforcedProfile());
    api.listActionRunners.mockResolvedValue({ items: [actionRunner()] });
    api.getGenericRestConnectorStatus.mockResolvedValue(genericConnector({
      connected: true,
      health_status: "healthy",
      last_verdict: "matched",
      last_tested_at: "2026-06-20T09:05:00.000Z",
      readiness: { status: "ready", checks: {}, blockers: [] },
    }));
    api.listActionIntents.mockResolvedValue({
      items: [actionIntent()],
      total_in_page: 1,
      limit: 5,
      offset: 0,
    });

    renderWizard();

    expect(await screen.findByRole("heading", { name: /Operations Agent is live and verified/i })).toBeInTheDocument();
    clickStep("Go Live");

    expect(await screen.findByText("First matched receipt generated")).toBeInTheDocument();
    expect(screen.getByText("matched receipt generated")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open Evidence" }).some((link) => (
      link.getAttribute("href") === "/evidence?action_id=act_first_receipt"
    ))).toBe(true);
  });

  it("loads edit mode from agentId and saves with update instead of create", async () => {
    navigation.query = "agentId=agent_existing";
    api.getAgentProfile.mockResolvedValue(profile({
      id: "agent_existing",
      display_name: "Existing Agent",
      slug: "existing-agent",
      tool_names: ["stripe.refunds.create"],
      allowed_action_types: ["refund"],
      verification_connectors: ["ledger_refund"],
      risk_limits: {
        approval_required_above_usd: 250,
        deny_above_usd: 2500,
        approval_ttl_minutes: 20,
      },
    }));
    api.updateAgentProfile.mockResolvedValue(profile({
      id: "agent_existing",
      display_name: "Existing Agent",
      slug: "existing-agent",
    }));

    renderWizard();

    expect(await screen.findByDisplayValue("Existing Agent")).toBeInTheDocument();
    clickStep("Proof & Readiness");
    fireEvent.click(screen.getByRole("button", { name: /Save changes/i }));

    await waitFor(() => expect(api.updateAgentProfile).toHaveBeenCalledTimes(1));
    expect(api.updateAgentProfile.mock.calls[0]?.[0]).toBe("agent_existing");
    expect(api.createAgentProfile).not.toHaveBeenCalled();
    expect(api.enforceAgentProfile).not.toHaveBeenCalled();
  });

  it("edit mode enables policy by updating the profile before enforcing", async () => {
    navigation.query = "agentId=agent_existing";
    api.getAgentProfile.mockResolvedValue(profile({
      id: "agent_existing",
      display_name: "Existing Agent",
      slug: "existing-agent",
    }));
    api.updateAgentProfile.mockResolvedValue(profile({
      id: "agent_existing",
      display_name: "Existing Agent",
      slug: "existing-agent",
    }));
    api.enforceAgentProfile.mockResolvedValue(enforcedProfile());

    renderWizard();

    expect(await screen.findByDisplayValue("Existing Agent")).toBeInTheDocument();
    clickStep("Proof & Readiness");
    fireEvent.click(screen.getByRole("button", { name: /Enable project policy/i }));

    await waitFor(() => expect(api.updateAgentProfile).toHaveBeenCalledTimes(1));
    expect(api.createAgentProfile).not.toHaveBeenCalled();
    expect(api.enforceAgentProfile).toHaveBeenCalledWith("agent_existing");
  });

  it("derives runner readiness from a managed online ActionRunner row", async () => {
    navigation.query = "agentId=agent_existing";
    api.getAgentProfile.mockResolvedValue(enforcedProfile());
    api.listActionRunners.mockResolvedValue({ items: [actionRunner()] });

    renderWizard();

    expect(await screen.findByDisplayValue("Operations Agent")).toBeInTheDocument();
    clickStep("Control Path");

    const runnerStatus = await screen.findByLabelText("Runner readiness");
    expect(within(runnerStatus).getByText("Runner ready")).toBeInTheDocument();
    expect(within(runnerStatus).getByText(/is online and supports UPDATE/i)).toBeInTheDocument();
  });

  it("keeps customer-hosted runner readiness offline until heartbeat", async () => {
    navigation.query = "agentId=agent_existing";
    api.getAgentProfile.mockResolvedValue(enforcedProfile());
    api.listActionRunners.mockResolvedValue({
      items: [
        actionRunner({
          runner_type: "customer_hosted",
          status: "registered",
          last_heartbeat_at: null,
        }),
      ],
    });

    renderWizard();

    expect(await screen.findByDisplayValue("Operations Agent")).toBeInTheDocument();
    clickStep("Control Path");

    const runnerStatus = await screen.findByLabelText("Runner readiness");
    expect(within(runnerStatus).getByText("Registered, not online")).toBeInTheDocument();
    expect(within(runnerStatus).getByText(/Start the customer-hosted runner heartbeat/i)).toBeInTheDocument();
  });

  it("marks setup live only after a matched generated receipt for the bound agent_id", async () => {
    navigation.query = "agentId=agent_1";
    api.getAgentProfile.mockResolvedValue(enforcedProfile());
    api.listActionRunners.mockResolvedValue({ items: [actionRunner()] });
    api.getGenericRestConnectorStatus.mockResolvedValue(genericConnector({
      connected: true,
      base_url: "https://records.example.test",
      has_bearer_token: true,
      bearer_token_last4: "1234",
      last_tested_at: "2026-06-20T09:02:00.000Z",
      health_status: "healthy",
      last_verdict: "matched",
      last_attempts: 1,
      last_http_status: 200,
      readiness: { status: "ready", checks: { saved_test_matched: true }, blockers: [] },
    }));
    api.listActionIntents.mockResolvedValue({
      items: [actionIntent()],
      total_in_page: 1,
      limit: 1,
      offset: 0,
    });

    renderWizard();

    expect(await screen.findByDisplayValue("Operations Agent")).toBeInTheDocument();
    await waitFor(() => expect(api.listActionIntents).toHaveBeenCalledWith(
      {
        agent_id: "agent_1",
        proof_status: "matched",
        receipt_status: "generated",
        limit: 1,
      },
      expect.any(AbortSignal),
    ));
    clickStep("Proof & Readiness");

    const receipt = await screen.findByLabelText("First Action Receipt");
    await waitFor(() => expect(within(receipt).getByText("Matched receipt seen")).toBeInTheDocument());
    expect(within(receipt).getByText("live")).toBeInTheDocument();
    expect(within(receipt).getByText("generated from real receipt")).toBeInTheDocument();
  });

  it("derives verifier readiness from a healthy matching connector", async () => {
    api.getGenericRestConnectorStatus.mockResolvedValue(genericConnector({
      connected: true,
      base_url: "https://records.example.test",
      has_bearer_token: true,
      bearer_token_last4: "1234",
      last_tested_at: "2026-06-20T09:02:00.000Z",
      health_status: "healthy",
      last_verdict: "matched",
      last_attempts: 1,
      last_http_status: 200,
      readiness: { status: "ready", checks: { saved_test_matched: true }, blockers: [] },
    }));

    renderWizard();

    clickStep("Proof & Readiness");
    const verifierStatus = await screen.findByLabelText("Verifier readiness");
    await waitFor(() => expect(within(verifierStatus).getByText("Verifier ready")).toBeInTheDocument());
    expect(within(verifierStatus).getByText(/latest saved test matched/i)).toBeInTheDocument();
    expect(within(verifierStatus).queryByRole("link", { name: /Connect in Integrations/i })).not.toBeInTheDocument();
  });

  it("shows missing connector CTA instead of fake verifier readiness", async () => {
    renderWizard();

    clickStep("Proof & Readiness");
    const verifierStatus = await screen.findByLabelText("Verifier readiness");
    expect(within(verifierStatus).getByText("Connector missing")).toBeInTheDocument();
    expect(within(verifierStatus).getByRole("link", { name: /Connect in Integrations/i }).getAttribute("href")).toBe(
      "/integrations#generic-rest-connector",
    );
  });

  it("shows failing connector when saved test did not match", async () => {
    api.getGenericRestConnectorStatus.mockResolvedValue(genericConnector({
      connected: true,
      base_url: "https://records.example.test",
      has_bearer_token: true,
      bearer_token_last4: "1234",
      last_tested_at: "2026-06-20T09:02:00.000Z",
      health_status: "failing",
      last_verdict: "mismatched",
      last_attempts: 1,
      last_http_status: 200,
      readiness: { status: "not_ready", checks: { saved_test_matched: false }, blockers: ["latest connector test did not reconcile as matched"] },
    }));

    renderWizard();

    clickStep("Proof & Readiness");
    const verifierStatus = await screen.findByLabelText("Verifier readiness");
    await waitFor(() => expect(within(verifierStatus).getByText("Connector failing")).toBeInTheDocument());
    expect(within(verifierStatus).getByText(/has not produced a matched saved test/i)).toBeInTheDocument();
  });

  it("does not mark an incompatible connector type verifier-ready", async () => {
    api.getGenericRestConnectorStatus.mockResolvedValue(genericConnector({
      connected: true,
      base_url: "https://records.example.test",
      has_bearer_token: true,
      bearer_token_last4: "1234",
      last_tested_at: "2026-06-20T09:02:00.000Z",
      health_status: "healthy",
      last_verdict: "matched",
      last_attempts: 1,
      last_http_status: 200,
      readiness: { status: "ready", checks: { saved_test_matched: true }, blockers: [] },
    }));

    renderWizard();

    clickStep("Proof & Readiness");
    fireEvent.change(await screen.findByLabelText("Verifier"), {
      target: { value: "crm_record" },
    });

    const verifierStatus = await screen.findByLabelText("Verifier readiness");
    expect(within(verifierStatus).getByText("Verifier mismatch")).toBeInTheDocument();
    expect(within(verifierStatus).getByText(/expects Generic REST verifier/i)).toBeInTheDocument();
  });
});
