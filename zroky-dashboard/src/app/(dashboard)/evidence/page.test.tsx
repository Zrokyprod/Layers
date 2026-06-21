import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EvidencePage from "./page";

const api = vi.hoisted(() => ({
  getRuntimePolicyEvidencePack: vi.fn(),
  listOutcomeReconciliations: vi.fn(),
  listRuntimePolicyApprovals: vi.fn(),
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

function renderEvidencePage() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <EvidencePage />
    </QueryClientProvider>,
  );
}

describe("EvidencePage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:evidence-pack"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    api.listRuntimePolicyApprovals.mockResolvedValue({
      total_in_page: 1,
      items: [
        {
          id: "decision_1",
          project_id: "proj_1",
          trace_id: "trace_1",
          call_id: "call_1",
          agent_name: "Refund agent",
          role: "refund_ops",
          action_type: "refund",
          tool_name: "ledger.refund",
          decision: "requires_approval",
          status: "approved",
          allowed: false,
          requires_approval: true,
          reasons: ["amount_requires_approval"],
          request: {},
          policy_snapshot: {},
          intended_action: {},
          trace_context: {},
          policy_hit: {},
          business_impact: {},
          audit_log: [],
          created_at: "2026-06-20T09:00:00Z",
          expires_at: null,
          resolved_at: "2026-06-20T09:05:00Z",
          resolved_by: "ops@example.com",
          resolution_reason: "approved for pilot",
          consumed_at: null,
          consumed_by_decision_id: null,
        },
      ],
    });
    api.listOutcomeReconciliations.mockResolvedValue({
      total_in_page: 1,
      items: [
        {
          id: "check_1",
          project_id: "proj_1",
          call_id: "call_1",
          trace_id: "trace_1",
          runtime_policy_decision_id: "decision_1",
          action_type: "refund",
          connector_type: "ledger_refund_api",
          system_ref: "ledger:RF-1001",
          verdict: "matched",
          reason: "all_compared_fields_matched",
          amount_usd: 42.5,
          currency: "USD",
          claimed: { refund_id: "RF-1001" },
          actual: { refund_id: "RF-1001" },
          comparison: { compared_fields: [], mismatches: [] },
          idempotency_key: "refund:RF-1001",
          metadata: {},
          checked_at: "2026-06-20T09:06:00Z",
          created_at: "2026-06-20T09:06:00Z",
        },
      ],
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
      outcome_reconciliation: [],
      call: null,
      generated_at: "2026-06-20T09:07:00Z",
      hash_algorithm: "sha256",
      evidence_hash: "abc123",
      hash_payload_excludes: ["generated_at"],
    });
  });

  it("surfaces linked runtime decisions and downloads Evidence Pack JSON", async () => {
    renderEvidencePage();

    expect(await screen.findByRole("heading", { name: "Evidence" })).toBeInTheDocument();
    expect(await screen.findByText("Refund agent")).toBeInTheDocument();
    expect(screen.getByText("matched")).toBeInTheDocument();
    expect(screen.getByText("ledger_refund_api", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open approvals" }).getAttribute("href")).toBe("/approvals");
    expect(screen.getByRole("link", { name: "Open outcomes" }).getAttribute("href")).toBe("/outcomes");

    fireEvent.click(screen.getByRole("button", { name: "Download JSON" }));

    await waitFor(() => expect(api.getRuntimePolicyEvidencePack).toHaveBeenCalledWith("decision_1"));
    const blob = vi.mocked(URL.createObjectURL).mock.calls.at(-1)?.[0] as Blob;
    expect(await blob.text()).toContain('"decision_id": "decision_1"');
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:evidence-pack");
    expect(await screen.findByText("Evidence Pack JSON downloaded.")).toBeInTheDocument();
  });

  it("keeps unlinked outcome rows visible but not exportable", async () => {
    api.listRuntimePolicyApprovals.mockResolvedValue({ total_in_page: 0, items: [] });
    api.listOutcomeReconciliations.mockResolvedValue({
      total_in_page: 1,
      items: [
        {
          id: "check_unlinked",
          project_id: "proj_1",
          call_id: "call_1",
          trace_id: "trace_1",
          runtime_policy_decision_id: null,
          action_type: "customer_record_update",
          connector_type: "customer_record_api",
          system_ref: "crm:CUS-1001",
          verdict: "not_verified",
          reason: "decision_missing",
          amount_usd: null,
          currency: null,
          claimed: { customer_id: "CUS-1001" },
          actual: null,
          comparison: { compared_fields: [], mismatches: [] },
          idempotency_key: null,
          metadata: {},
          checked_at: "2026-06-20T09:06:00Z",
          created_at: "2026-06-20T09:06:00Z",
        },
      ],
    });

    renderEvidencePage();

    const row = (await screen.findByText("crm:CUS-1001")).closest(".list-row");
    expect(row).not.toBeNull();
    expect((within(row as HTMLElement).getByRole("button", { name: "Not linked" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("not verified")).toBeInTheDocument();
  });
});
