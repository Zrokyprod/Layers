import { fireEvent, render, screen, within } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDashboardStore } from "@/lib/store";

import { operationsRowsCsv } from "./csv";
import OperationsPage from "./page";

const userEvent = {
  setup: () => ({
    click: async (element: Element) => {
      fireEvent.click(element);
    },
    type: async (element: Element, text: string) => {
      const input = element as HTMLInputElement | HTMLTextAreaElement;
      fireEvent.change(input, { target: { value: `${input.value ?? ""}${text}` } });
    },
  }),
};

const api = vi.hoisted(() => ({
  assignFinalIncident: vi.fn(),
  approveFinalApprovalRequirement: vi.fn(),
  compileFinalIncidentRecovery: vi.fn(),
  containFinalIncident: vi.fn(),
  denyFinalApprovalRequirement: vi.fn(),
  executeFinalIncidentRecovery: vi.fn(),
  listFinalApprovalRequirements: vi.fn(),
  listFinalIncidents: vi.fn(),
  listFinalRuns: vi.fn(),
  listMyProjects: vi.fn(),
  resolveFinalIncidentManually: vi.fn(),
  snoozeFinalIncident: vi.fn(),
}));

const queryState = vi.hoisted(() => ({
  overrides: {} as Record<string, { data?: unknown; error?: unknown; isError?: boolean; isLoading?: boolean }>,
}));

const queryClient = vi.hoisted(() => ({
  invalidateQueries: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

vi.mock("@tanstack/react-query", () => ({
  useMutation: vi.fn(({ mutationFn, onError, onSuccess }) => ({
    isPending: false,
    mutate: (variables: unknown) => {
      try {
        const result = mutationFn(variables);
        onSuccess?.(result);
      } catch (error) {
        onError?.(error);
      }
    },
  })),
  useQuery: vi.fn(({ queryKey, queryFn }: { queryKey: unknown[]; queryFn: (input: { signal?: AbortSignal }) => unknown }) => {
    const key = queryKey.join(":");
    const override = queryState.overrides[key];
    if (override) {
      return {
        data: override.data,
        error: override.error,
        isError: Boolean(override.isError),
        isLoading: Boolean(override.isLoading),
      };
    }
    return {
      data: queryFn({}),
      error: null,
      isError: false,
      isLoading: false,
    };
  }),
  useQueryClient: vi.fn(() => queryClient),
}));

function operationViewButton(name: RegExp | string) {
  return within(screen.getByLabelText("Operations views")).getByRole("button", { name });
}

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    return entry.isDirectory() ? sourceFiles(path) : [path];
  });
}

describe("OperationsPage", () => {
  beforeEach(() => {
    window.history.pushState(null, "", "/operations");
    useDashboardStore.setState({ realTimeEnabled: true, selectedProject: null });
    api.listFinalRuns.mockReset();
    api.listFinalIncidents.mockReset();
    api.listFinalApprovalRequirements.mockReset();
    api.listMyProjects.mockReset();
    api.assignFinalIncident.mockReset();
    api.approveFinalApprovalRequirement.mockReset();
    api.compileFinalIncidentRecovery.mockReset();
    api.containFinalIncident.mockReset();
    api.denyFinalApprovalRequirement.mockReset();
    api.executeFinalIncidentRecovery.mockReset();
    api.resolveFinalIncidentManually.mockReset();
    api.snoozeFinalIncident.mockReset();
    queryClient.invalidateQueries.mockReset();
    api.assignFinalIncident.mockReturnValue({ id: "incident_1", status: "open" });
    api.approveFinalApprovalRequirement.mockReturnValue({ id: "approval_1", status: "approved" });
    api.compileFinalIncidentRecovery.mockResolvedValue({
      incident_id: "incident_1",
      playbook_id: "refund-workflow:1.0.0:reissue_refund",
      plan_digest: "sha256:compiled",
      plan: { steps: [{ step_key: "reissue_refund", target: { charge: "ch_1" } }] },
      included_effects: ["refund_posted"],
      skipped_effects: [],
    });
    api.containFinalIncident.mockReturnValue({ id: "incident_1", status: "unresolved" });
    api.denyFinalApprovalRequirement.mockReturnValue({ id: "approval_1", status: "denied" });
    api.executeFinalIncidentRecovery.mockReturnValue({ incident: { id: "incident_1" }, execution_status: "dispatched" });
    api.resolveFinalIncidentManually.mockReturnValue({ id: "incident_1", status: "resolved" });
    api.snoozeFinalIncident.mockReturnValue({ id: "incident_1", status: "unresolved" });
    queryState.overrides = {};
    api.listMyProjects.mockReturnValue([
      {
        membership_id: "membership_1",
        project_id: "project_1",
        project_name: "Acme",
        role: "owner",
        is_active: true,
        created_at: "2026-07-21T10:00:00Z",
        updated_at: "2026-07-21T10:00:00Z",
      },
    ]);
    api.listFinalRuns.mockReturnValue({
      items: [
        {
          id: "run_1",
          project_id: "project_1",
          environment: "production",
          idempotency_key: "idem_1",
          external_run_id: "stripe_refund_1",
          intent_id: "intent_1",
          workflow_key: "refund-workflow",
          agent_ref: "stripe-agent",
          status: "verified",
          run_digest: "run_digest_abcdef1234567890",
          run: { action_id: "action_1" },
          started_at: "2026-07-21T09:59:00Z",
          finished_at: "2026-07-21T10:00:00Z",
          created_at: "2026-07-21T10:00:00Z",
        },
      ],
    });
    api.listFinalIncidents.mockReturnValue([
      {
        id: "incident_1",
        project_id: "project_1",
        environment: "production",
        outcome_graph_id: "run_incident_1",
        status: "open",
        severity: "high",
        created_at: "2026-07-21T10:01:00Z",
        resolved_at: null,
        incident: {
          deviation_type: "Mismatch in payroll export",
          intent_id: "intent_incident_1",
          reason: "Source-of-truth file did not contain the claimed payroll export.",
          source_system: "Workday Payroll",
          agent_ref: "Payroll Export WF",
          expected: "Payroll export should exist in Workday.",
          impact: "Payroll automation needs operator containment.",
        },
      },
    ]);
    api.listFinalApprovalRequirements.mockReturnValue({
      items: [
        {
          id: "approval_1",
          project_id: "project_1",
          environment: "production",
          intent_id: "intent_approval_1",
          policy_decision_id: "policy_1",
          required_role: "admin",
          binding_digest: "binding_digest_abcdef1234567890",
          status: "pending",
          created_at: "2026-07-21T10:02:00Z",
          resolved_at: null,
        },
      ],
    });
  });

  it("renders the Operations workbench from final APIs", () => {
    render(<OperationsPage />);

    expect(screen.getByRole("heading", { name: "Operator action required" })).toBeInTheDocument();
    const metrics = screen.getByLabelText("Operations metrics");
    expect(metrics).toBeInTheDocument();
    expect(within(metrics).getByText("Needs attention")).toBeInTheDocument();
    expect(within(metrics).getByText("Recovery rail")).toBeInTheDocument();
    const views = screen.getByLabelText("Operations views");
    expect(within(views).getByRole("button", { name: /Operator queue/i })).toBeInTheDocument();
    expect(within(views).getByRole("button", { name: /Runs/i })).toBeInTheDocument();
    expect(within(views).getByRole("button", { name: /Incidents/i })).toBeInTheDocument();
    expect(within(views).getByRole("button", { name: /Approvals/i })).toBeInTheDocument();
    expect(within(views).getByRole("button", { name: /Unverifiable/i })).toBeInTheDocument();
    expect(within(views).getByRole("button", { name: /Recovery/i })).toBeInTheDocument();
    const table = screen.getByLabelText("Operator queue table");
    expect(within(table).getByText("Mismatch in payroll export")).toBeInTheDocument();
    expect(within(table).getByText("Approval required: admin")).toBeInTheDocument();
    expect(screen.getByText("Expected vs actual")).toBeInTheDocument();
  });

  it("keeps Runs as the run ledger instead of duplicating all attention items", async () => {
    const user = userEvent.setup();
    render(<OperationsPage />);

    await user.click(operationViewButton(/Runs/i));

    const table = screen.getByLabelText("Runs table");
    expect(within(table).getByText("refund-workflow")).toBeInTheDocument();
    expect(within(table).queryByText("Mismatch in payroll export")).not.toBeInTheDocument();
    expect(within(table).queryByText("Approval required: admin")).not.toBeInTheDocument();
  });

  it("summarizes and filters runs by agent", async () => {
    api.listFinalRuns.mockReturnValue({
      items: [
        {
          id: "run_agent_1",
          project_id: "project_1",
          environment: "production",
          idempotency_key: "idem_agent_1",
          external_run_id: "refund_1",
          intent_id: "intent_refund_1",
          workflow_key: "refund-workflow",
          agent_ref: "stripe-agent",
          status: "verified",
          run_digest: "digest_agent_1",
          run: {},
          started_at: "2026-07-21T09:59:00Z",
          finished_at: "2026-07-21T10:00:00Z",
          created_at: "2026-07-21T10:00:00Z",
        },
        {
          id: "run_agent_2",
          project_id: "project_1",
          environment: "production",
          idempotency_key: "idem_agent_2",
          external_run_id: "db_1",
          intent_id: "intent_db_1",
          workflow_key: "db-workflow",
          agent_ref: "db-agent",
          status: "recovery_failed",
          run_digest: "digest_agent_2",
          run: {},
          started_at: "2026-07-21T09:58:00Z",
          finished_at: null,
          created_at: "2026-07-21T09:59:00Z",
        },
      ],
    });
    const user = userEvent.setup();
    render(<OperationsPage />);

    await user.click(operationViewButton(/Runs/i));
    await user.click(within(screen.getByLabelText("Agent summary")).getByRole("button", { name: /stripe-agent/i }));

    const table = screen.getByLabelText("Runs table");
    expect(within(table).getByText("refund-workflow")).toBeInTheDocument();
    expect(within(table).queryByText("db-workflow")).not.toBeInTheDocument();
  });

  it("renders unverifiable reason codes with reason-specific actions", async () => {
    api.listFinalRuns.mockReturnValue({
      items: [
        {
          id: "run_unverifiable_1",
          project_id: "project_1",
          environment: "production",
          idempotency_key: "idem_unverifiable_1",
          external_run_id: "quote_1",
          intent_id: "intent_quote_1",
          workflow_key: "quote-workflow",
          agent_ref: "salesforce-agent",
          status: "unverifiable",
          run_digest: "run_digest_unverifiable",
          run: { reason_code: "missing_correlation" },
          started_at: "2026-07-21T09:59:00Z",
          finished_at: null,
          created_at: "2026-07-21T10:00:00Z",
        },
      ],
    });
    const user = userEvent.setup();
    render(<OperationsPage />);

    await user.click(within(screen.getByLabelText("Operations views")).getByRole("button", { name: /Unverifiable/i }));

    const table = screen.getByLabelText("Unverifiable table");
    expect(within(table).getByText("missing_correlation")).toBeInTheDocument();
    expect(within(table).getByText("Fix correlation")).toBeInTheDocument();
    expect(screen.getByText("ZROKY could not map the agent claim to a source-of-truth object.")).toBeInTheDocument();
  });

  it("approves exact payload approvals with the stored binding digest", async () => {
    const user = userEvent.setup();
    render(<OperationsPage />);

    await user.click(screen.getByText("Approval required: admin"));
    expect(screen.getByText("Binding digest")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve exact payload" }).hasAttribute("disabled")).toBe(true);
    await user.type(screen.getByLabelText("Approval decision reason"), "Payload matches approved budget exception.");
    await user.click(screen.getByRole("button", { name: "Approve exact payload" }));

    expect(api.approveFinalApprovalRequirement).toHaveBeenCalledWith(
      "approval_1",
      "binding_digest_abcdef1234567890",
      "Payload matches approved budget exception.",
    );
  });

  it("denies approvals with a mandatory operator reason", async () => {
    const user = userEvent.setup();
    render(<OperationsPage />);

    await user.click(screen.getByText("Approval required: admin"));
    await user.type(screen.getByLabelText("Approval decision reason"), "Payload exceeds allowed vendor threshold.");
    await user.click(screen.getByRole("button", { name: "Deny" }));

    expect(api.denyFinalApprovalRequirement).toHaveBeenCalledWith(
      "approval_1",
      "binding_digest_abcdef1234567890",
      "Payload exceeds allowed vendor threshold.",
    );
  });

  it("assigns incident owners through the final incident endpoint", async () => {
    const user = userEvent.setup();
    render(<OperationsPage />);

    await user.type(screen.getByLabelText("Incident owner"), "ops@example.com");
    await user.click(screen.getByRole("button", { name: "Assign owner" }));

    expect(api.assignFinalIncident).toHaveBeenCalledWith("incident_1", "ops@example.com");
  });

  it("executes recovery only with a customer executor reference", async () => {
    const user = userEvent.setup();
    render(<OperationsPage />);

    await user.type(screen.getByLabelText("Recovery executor ref"), "customer-recovery-executor://primary");
    await user.click(screen.getByRole("button", { name: "Execute recovery" }));

    await vi.waitFor(() => {
      expect(api.compileFinalIncidentRecovery).toHaveBeenCalledWith("incident_1");
      expect(api.executeFinalIncidentRecovery).toHaveBeenCalledWith(
        "incident_1",
        "customer-recovery-executor://primary",
        expect.any(String),
        { steps: [{ step_key: "reissue_refund", target: { charge: "ch_1" } }] },
      );
    });
  });

  it("manual incident resolution requires an explicit verified graph id", async () => {
    const user = userEvent.setup();
    render(<OperationsPage />);

    await user.type(screen.getByLabelText("Verified outcome graph ID"), "graph_verified_1");
    await user.type(screen.getByLabelText("Resolution note"), "Verified by second source read.");
    await user.click(screen.getByRole("button", { name: "Resolve manually" }));

    expect(api.resolveFinalIncidentManually).toHaveBeenCalledWith(
      "incident_1",
      "graph_verified_1",
      "Verified by second source read.",
    );
  });

  it("keeps contained and snoozed incidents separate from resolved", async () => {
    const user = userEvent.setup();
    render(<OperationsPage />);

    expect(screen.getByLabelText("Incident lifecycle")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark contained" }).hasAttribute("disabled")).toBe(true);
    await user.type(screen.getByLabelText("Containment note"), "Payroll export disabled until proof is restored.");
    await user.click(screen.getByRole("button", { name: "Mark contained" }));
    expect(api.containFinalIncident).toHaveBeenCalledWith("incident_1", "Payroll export disabled until proof is restored.");

    expect(screen.getByRole("button", { name: "Snooze" }).hasAttribute("disabled")).toBe(true);
    await user.type(screen.getByLabelText("Snooze reason"), "Accepted while payroll team re-runs source read.");
    fireEvent.change(screen.getByLabelText("Snooze until"), { target: { value: "2026-07-22T10:00" } });
    await user.click(screen.getByRole("button", { name: "Snooze" }));
    expect(api.snoozeFinalIncident).toHaveBeenCalledWith(
      "incident_1",
      "Accepted while payroll team re-runs source read.",
      "2026-07-22T10:00",
    );
  });

  it("disables operator mutations for read-only members", async () => {
    api.listMyProjects.mockReturnValue([
      {
        membership_id: "membership_1",
        project_id: "project_1",
        project_name: "Acme",
        role: "viewer",
        is_active: true,
        created_at: "2026-07-21T10:00:00Z",
        updated_at: "2026-07-21T10:00:00Z",
      },
    ]);
    const user = userEvent.setup();
    render(<OperationsPage />);

    expect(screen.getByText("Read-only role: actions are disabled.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Assign owner" }).hasAttribute("disabled")).toBe(true);
    await user.click(screen.getByText("Approval required: admin"));
    expect(screen.getByRole("button", { name: "Approve exact payload" }).hasAttribute("disabled")).toBe(true);
  });

  it("opens permalinked operation rows from URL parameters", async () => {
    window.history.pushState(null, "", "/operations?approval_id=approval_1");

    render(<OperationsPage />);

    expect(await screen.findByLabelText("Approvals table")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Approval required: admin" })).toBeInTheDocument();
  });

  it("opens the incidents view from a Home metric deep-link", async () => {
    window.history.pushState(null, "", "/operations?view=incidents");

    render(<OperationsPage />);

    expect(await screen.findByLabelText("Incidents table")).toBeInTheDocument();
  });

  it.each([
    ["intent_id=intent_incident_1", "Incidents table", "Mismatch in payroll export"],
    ["intent_id=intent_1", "Runs table", "refund-workflow"],
    ["decision_id=policy_1", "Approvals table", "Approval required: admin"],
    ["action_id=action_1", "Runs table", "refund-workflow"],
  ])("resolves Operations deep-link %s to its exact row", async (query, tableLabel, heading) => {
    window.history.pushState(null, "", `/operations?${query}`);

    render(<OperationsPage />);

    expect(await screen.findByLabelText(tableLabel)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
  });

  it("prefers the visible run when an intent also has a resolved incident", async () => {
    api.listFinalIncidents.mockReturnValue([
      {
        id: "incident_resolved_1",
        project_id: "project_1",
        environment: "production",
        outcome_graph_id: "run_1",
        status: "resolved",
        severity: "high",
        created_at: "2026-07-21T10:01:00Z",
        resolved_at: "2026-07-21T10:05:00Z",
        incident: { intent_id: "intent_1", deviation_type: "Recovered refund" },
      },
    ]);
    window.history.pushState(null, "", "/operations?intent_id=intent_1");

    render(<OperationsPage />);

    expect(await screen.findByLabelText("Runs table")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "refund-workflow" })).toBeInTheDocument();
  });

  it("prefers an actionable incident when the intent also has a run", async () => {
    api.listFinalIncidents.mockReturnValue([
      {
        id: "incident_open_1",
        project_id: "project_1",
        environment: "production",
        outcome_graph_id: "run_1",
        status: "open",
        severity: "high",
        created_at: "2026-07-21T10:01:00Z",
        resolved_at: null,
        incident: { intent_id: "intent_1", deviation_type: "Missing refund" },
      },
    ]);
    window.history.pushState(null, "", "/operations?intent_id=intent_1");

    render(<OperationsPage />);

    expect(await screen.findByLabelText("Incidents table")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Missing refund" })).toBeInTheDocument();
  });

  it("applies agent_name as a Runs facet", async () => {
    window.history.pushState(null, "", "/operations?agent_name=stripe-agent");

    render(<OperationsPage />);

    expect(await screen.findByLabelText("Runs table")).toBeInTheDocument();
    const agent = within(screen.getByLabelText("Agent summary")).getByRole("button", { name: /stripe-agent/i });
    expect(agent.getAttribute("data-active")).toBe("true");
  });

  it("handles every Operations query parameter emitted by production source", () => {
    const srcRoot = resolve(process.cwd(), "src");
    const params = new Set<string>();
    for (const file of sourceFiles(srcRoot).filter((path) => /\.(ts|tsx)$/.test(path) && !path.includes(".test."))) {
      const source = readFileSync(file, "utf8");
      for (const link of source.matchAll(/\/operations\?([^"'`\s]*)/g)) {
        for (const query of link[1].matchAll(/(?:^|&)([a-z_]+)=/g)) params.add(query[1]);
      }
    }

    const operationsSource = readFileSync(resolve(srcRoot, "app", "(dashboard)", "operations", "page.tsx"), "utf8");
    expect([...params].sort()).toEqual([
      "action_id", "agent_name", "approval_id", "decision_id", "incident_id", "intent_id", "run_id", "view",
    ]);
    for (const param of params) expect(operationsSource).toContain(`params.get("${param}")`);
  });

  it("applies cross-cutting filters without duplicating tab navigation", async () => {
    const user = userEvent.setup();
    render(<OperationsPage />);

    await user.click(screen.getByRole("button", { name: "My items" }));

    const table = screen.getByLabelText("Operator queue table");
    expect(within(table).getByText("Approval required: admin")).toBeInTheDocument();
    expect(within(table).queryByText("Mismatch in payroll export")).not.toBeInTheDocument();

    await user.click(operationViewButton(/Runs/i));
    expect(screen.getByLabelText("Runs table")).toBeInTheDocument();
  });

  it("filters operation rows with local search", async () => {
    const user = userEvent.setup();
    render(<OperationsPage />);

    await user.type(screen.getByLabelText("Search operations"), "Workday");

    const table = screen.getByLabelText("Operator queue table");
    expect(within(table).getByText("Mismatch in payroll export")).toBeInTheDocument();
    expect(within(table).queryByText("Approval required: admin")).not.toBeInTheDocument();
  });

  it("refreshes all live operation rails", async () => {
    const user = userEvent.setup();
    render(<OperationsPage />);

    await user.click(screen.getByRole("button", { name: /Refresh/i }));

    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["final-runs"] });
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["final-incidents"] });
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["final-approval-requirements"] });
  });

  it("keeps live polling out of the header toolbar", () => {
    render(<OperationsPage />);

    expect(screen.queryByRole("button", { name: /Live/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Paused/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh operations" })).toBeInTheDocument();
  });

  it("exports visible operations rows as escaped CSV", () => {
    expect(
      operationsRowsCsv([
        {
          runId: "run_1",
          type: "Mismatch",
          severity: "P1",
          item: 'Payroll "export"',
          source: "Workday",
          agent: "Payroll WF",
          state: "open",
          age: "12m",
          owner: "Ops",
        },
      ]),
    ).toContain('"Payroll ""export"""');
  });

  it("supports keyboard search focus and row navigation", () => {
    render(<OperationsPage />);

    fireEvent.keyDown(window, { key: "/" });
    expect(document.activeElement).toBe(screen.getByLabelText("Search operations"));

    screen.getByLabelText("Search operations").blur();
    fireEvent.keyDown(window, { key: "j" });
    expect(screen.getByRole("heading", { name: "Approval required: admin" })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "k" });
    expect(screen.getByRole("heading", { name: "Mismatch in payroll export" })).toBeInTheDocument();
  });

  it("renders empty states without demo data", () => {
    api.listFinalRuns.mockReturnValue({ items: [] });
    api.listFinalIncidents.mockReturnValue([]);
    api.listFinalApprovalRequirements.mockReturnValue({ items: [] });

    render(<OperationsPage />);

    expect(screen.getByRole("heading", { name: "Operations are clear" })).toBeInTheDocument();
    expect(screen.getByText("No items in this view.")).toBeInTheDocument();
    expect(screen.getByText("Select an operation")).toBeInTheDocument();
  });

  it("renders loading state without pretending queues are empty", () => {
    queryState.overrides = {
      "final-runs": { isLoading: true },
      "final-incidents": { isLoading: true },
      "final-approval-requirements": { isLoading: true },
    };

    render(<OperationsPage />);

    expect(screen.getByRole("heading", { name: "Loading operations" })).toBeInTheDocument();
    expect(screen.getByText("Loading operations...")).toBeInTheDocument();
    expect(screen.queryByText("No items in this view.")).not.toBeInTheDocument();
  });

  it("renders permission errors without demo fallback", () => {
    queryState.overrides = {
      "final-runs": { isError: true, error: new Error("403 forbidden") },
      "final-incidents": { isError: true, error: new Error("403 forbidden") },
      "final-approval-requirements": { isError: true, error: new Error("403 forbidden") },
    };

    render(<OperationsPage />);

    expect(screen.getByRole("heading", { name: "Operations access unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Permission required")).toBeInTheDocument();
    expect(screen.getByText("You do not have access to the live operations rail.")).toBeInTheDocument();
    expect(screen.queryByText("No items in this view.")).not.toBeInTheDocument();
  });
});
