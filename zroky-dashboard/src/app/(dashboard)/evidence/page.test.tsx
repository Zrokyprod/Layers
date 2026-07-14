import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EvidencePage from "./page";
import type {
  ActionIntentResponse,
  ActionReceiptResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  RuntimePolicyEvidencePackResponse,
} from "@/lib/api";
import { buildEvidenceLedger, evidenceLedgerCounts } from "@/lib/evidence-ledger";

const api = vi.hoisted(() => ({
  getActionIntentReceipt: vi.fn(),
  getEvidenceLedger: vi.fn(),
  getEvidenceManifest: vi.fn(),
  getRuntimePolicyEvidencePack: vi.fn(),
  listActionIntents: vi.fn(),
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

function actionIntent(overrides: Partial<ActionIntentResponse> = {}): ActionIntentResponse {
  return {
    action_id: "act_1",
    project_id: "proj_1",
    contract_version: "v1",
    action_type: "ticket.close",
    operation_kind: "business_mutation",
    environment: "test",
    status: "authorized",
    proof_status: "matched",
    receipt_status: "generated",
    idempotency_key: "idem_act_1",
    intent_digest: "sha256:intent_1",
    canonical_intent: {
      principal: { id: "support-agent" },
      purpose: { summary: "Close ticket T-1001" },
      resource: { id: "T-1001" },
      trace_context: { agent_name: "Support agent", trace_id: "trace_1", call_id: "call_1" },
    },
    created_at: "2026-06-20T09:00:00Z",
    decided_at: "2026-06-20T09:01:00Z",
    authorized_at: "2026-06-20T09:02:00Z",
    runtime_policy_decision_id: "decision_1",
    deadline: null,
    status_url: "/v1/action-intents/act_1",
    ...overrides,
  };
}

function runtimeDecision(overrides: Partial<RuntimePolicyDecisionResponse> = {}): RuntimePolicyDecisionResponse {
  return {
    id: "decision_1",
    project_id: "proj_1",
    trace_id: "trace_1",
    call_id: "call_1",
    agent_name: "Support agent",
    role: "agent",
    action_type: "ticket.close",
    tool_name: "ticket.close",
    decision: "allow",
    status: "approved",
    allowed: true,
    requires_approval: false,
    reasons: ["policy checks passed"],
    request: {},
    policy_snapshot: { mandate: "support-control" },
    intended_action: { summary: "Close ticket T-1001" },
    trace_context: {},
    policy_hit: {},
    business_impact: {},
    audit_log: [],
    created_at: "2026-06-20T09:00:00Z",
    expires_at: null,
    resolved_at: "2026-06-20T09:01:00Z",
    resolved_by: "ops@example.com",
    resolution_reason: "approved",
    consumed_at: null,
    consumed_by_decision_id: null,
    ...overrides,
  };
}

function outcome(overrides: Partial<OutcomeReconciliationView> = {}): OutcomeReconciliationView {
  return {
    id: "check_1",
    project_id: "proj_1",
    call_id: "call_1",
    trace_id: "trace_1",
    runtime_policy_decision_id: "decision_1",
    action_type: "ticket.close",
    connector_type: "generic_rest_api",
    system_ref: "ticket:T-1001",
    verdict: "matched",
    reason: "matched",
    amount_usd: null,
    currency: null,
    claimed: { status: "closed" },
    actual: { status: "closed" },
    comparison: { status: true },
    idempotency_key: "idem_act_1",
    metadata: {},
    checked_at: "2026-06-20T09:03:00Z",
    created_at: "2026-06-20T09:03:00Z",
    ...overrides,
  };
}

function receipt(overrides: Partial<ActionReceiptResponse> = {}): ActionReceiptResponse {
  return {
    receipt_id: "receipt_1",
    project_id: "proj_1",
    action_id: "act_1",
    receipt_digest: "sha256:receipt_1",
    evidence_hash: "sha256:evidence_1",
    signature_algorithm: "Ed25519",
    signature: "sig",
    signing_key_id: "receipt-key-1",
    signature_valid: true,
    generated_at: "2026-06-20T09:04:00Z",
    receipt: {
      schema_version: "zroky.action_receipt.v1",
      project_id: "proj_1",
      action_id: "act_1",
      environment: "test",
      final_status: "matched",
      generated_at: "2026-06-20T09:04:00Z",
      action_contract: {
        id: "contract_1",
        contract_version: "ticket.close/v1",
        action_type: "ticket.close",
        operation_kind: "business_mutation",
        risk_class: "medium",
      },
      intent: {
        contract_version: "ticket.close/v1",
        action_type: "ticket.close",
        operation_kind: "business_mutation",
        idempotency_key: "idem_act_1",
        intent_digest: "sha256:intent_1",
        canonical_intent: {
          principal: { id: "support-agent" },
          purpose: { summary: "Close ticket T-1001" },
          resource: { id: "T-1001" },
          trace_context: { agent_name: "Support agent", trace_id: "trace_1", call_id: "call_1" },
        },
        principal: { id: "support-agent" },
        actor_chain: [{ actor: "agent" }],
        purpose: { summary: "Close ticket T-1001" },
        resource: { id: "T-1001" },
        parameters: { status: "closed" },
        verification_profile: "generic_rest",
        created_at: "2026-06-20T09:00:00Z",
        decided_at: "2026-06-20T09:01:00Z",
        authorized_at: "2026-06-20T09:02:00Z",
      },
      policy_decision: {
        id: "decision_1",
        decision: "allow",
        status: "approved",
        reasons: ["policy checks passed"],
        approval_scope_hash: "scope_1",
        approval_id: null,
        resolved_by: "ops@example.com",
        resolved_at: "2026-06-20T09:01:00Z",
        consumed_at: "2026-06-20T09:02:00Z",
        required_approval_count: 1,
        approval_count: 1,
        approver_subjects: ["ops@example.com"],
      },
      runner_execution: {
        id: "attempt_1",
        runner_id: "runner_1",
        attempt_number: 1,
        status: "succeeded",
        idempotency_key: "idem_act_1",
        credential_ref: "support-crm",
        plan_digest: "sha256:plan_1",
        plan: { method: "PATCH", path: "/tickets/T-1001" },
        protected_credential_returned: false,
        started_at: "2026-06-20T09:02:10Z",
        finished_at: "2026-06-20T09:02:20Z",
      },
      verification: {
        status: "matched",
        outcomes: [
          {
            id: "check_1",
            verdict: "matched",
            verification_status: "verified",
            reason: "matched",
            connector_type: "generic_rest_api",
            system_ref: "ticket:T-1001",
            idempotency_key: "idem_act_1",
            checked_at: "2026-06-20T09:03:00Z",
          },
        ],
      },
      evidence: {
        hash_algorithm: "sha256",
        evidence_hash: "sha256:evidence_1",
      },
      timeline: [
        {
          id: "event_1",
          event_type: "receipt_generated",
          event_digest: "sha256:event_1",
          actor: "system",
          created_at: "2026-06-20T09:04:00Z",
        },
      ],
    },
    ...overrides,
  };
}

function evidencePack(overrides: Partial<RuntimePolicyEvidencePackResponse> = {}): RuntimePolicyEvidencePackResponse {
  return {
    schema_version: "zroky.evidence_pack.v1",
    project_id: "proj_1",
    decision_id: "decision_1",
    verification_status: "pass",
    decision: {
      ...runtimeDecision(),
      approval_scope_hash: "scope_1",
    },
    related_decisions: [],
    audit_log: [
      {
        id: "audit_1",
        decision_id: "decision_1",
        event_type: "approved",
        actor: "ops@example.com",
        reason: "approved for support close",
        before: null,
        after: { status: "approved" },
        created_at: "2026-06-20T09:01:00Z",
      },
    ],
    trace_policy_spans: [],
    outcome_reconciliation: [outcome()],
    call: null,
    generated_at: "2026-06-20T09:04:00Z",
    hash_algorithm: "sha256",
    evidence_hash: "sha256:evidence_pack_1",
    hash_payload_excludes: ["generated_at"],
    ...overrides,
  };
}

function ledgerResponse({
  decisions = [runtimeDecision()],
  intents = [actionIntent()],
  outcomes = [outcome()],
}: {
  decisions?: RuntimePolicyDecisionResponse[];
  intents?: ActionIntentResponse[];
  outcomes?: OutcomeReconciliationView[];
} = {}) {
  const rows = buildEvidenceLedger({ decisions, intents, outcomes });
  const counts = evidenceLedgerCounts(rows);
  return {
    counts: {
      exceptions: counts.exceptions,
      export_ready: counts.exportReady,
      needs_verification: counts.needsVerification,
      total: counts.total,
    },
    has_more: false,
    items: rows.map((row) => ({
      action_id: row.actionId,
      action_type: row.actionType,
      agent_name: row.agentName,
      call_id: row.callId,
      checked_at: row.checkedAt,
      decision_id: row.decisionId,
      detail: row.detail,
      digest: row.digest,
      export_kind: row.exportKind,
      exportable: row.exportable,
      href: row.href,
      id: row.id,
      kind: row.kind,
      outcome_id: row.outcomeId,
      source_label: row.sourceLabel,
      status: row.status,
      system_ref: row.systemRef,
      title: row.title,
      trace_id: row.traceId,
    })),
    limit: 100,
    offset: 0,
    total_in_scope: rows.length,
    total_matching: rows.length,
    window_days: 7,
  };
}

function renderEvidencePage() {
  const client = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
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
    window.history.pushState({}, "", "/evidence");
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:evidence"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(window, "print", {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    api.getEvidenceLedger.mockResolvedValue(ledgerResponse());
    api.getActionIntentReceipt.mockResolvedValue(receipt());
    api.getEvidenceManifest.mockResolvedValue({
      artifact: "zroky.evidence_manifest",
      schema_version: "zroky.evidence_manifest.v1",
      generated_at: "2026-06-20T09:05:00Z",
      project_id: "proj_1",
      scope: {
        filter: "all",
        search: "sha256:intent_1",
        start_date: "2026-06-20",
        end_date: "2026-06-20",
        total_records: 1,
        exportable_records: 1,
        non_exportable_records: 0,
      },
      verification: {
        public_key_url: "https://api.zroky.com/.well-known/zroky/action-receipt-signing-key",
        instructions: ["Verify receipts with the published Ed25519 public key."],
      },
      records: [
        {
          action_id: "act_1",
          checked_at: "2026-06-20T09:03:00Z",
          decision_id: "decision_1",
          digest: "sha256:intent_1",
          export_kind: "receipt",
          exportable: true,
          href: "http://localhost:3000/evidence?action_id=act_1",
          id: "action:act_1",
          kind: "action_receipt",
          source_label: "Action Receipt",
          status: "matched",
          system_ref: "ticket:T-1001",
          title: "Close ticket T-1001",
          trace_id: "trace_1",
        },
      ],
    });
    api.getRuntimePolicyEvidencePack.mockResolvedValue(evidencePack());
  });

  it("renders the receipt-first ledger and loads only the selected Action Receipt", async () => {
    renderEvidencePage();

    expect(await screen.findByRole("heading", { name: "Evidence ready" }, { timeout: 5_000 })).toBeInTheDocument();
    const summary = screen.getByLabelText("Evidence proof summary");
    const exportReadyCard = within(summary).getByText("Export-ready").closest(".dashboard-metric-card") as HTMLElement;
    expect(within(exportReadyCard).getByText("1")).toBeInTheDocument();
    expect(screen.getByText("Total proof records")).toBeInTheDocument();

    const ledger = screen.getByLabelText("Evidence ledger");
    const row = (await within(ledger).findByText("Close ticket T-1001")).closest(".ev-ledger-row") as HTMLElement;
    expect(row).not.toBeNull();
    expect(within(row).getByText("Action receipt")).toBeInTheDocument();
    expect(within(row).getByText("Digest")).toBeInTheDocument();
    expect(within(row).getByText("sha256:intent_1")).toBeInTheDocument();
    expect(within(row).getByText("ticket:T-1001")).toBeInTheDocument();
    expect(within(row).getByText("Matched")).toBeInTheDocument();

    const panel = await screen.findByLabelText("Focused proof panel");
    expect(within(panel).getByText("Action Receipt / Ticket.close")).toBeInTheDocument();
    expect(await screen.findByText("Evidence + Signature")).toBeInTheDocument();
    expect(within(ledger).getByRole("button", { name: "Export manifest" })).toBeInTheDocument();
    expect(within(ledger).getByLabelText("Manifest scope").textContent).toContain("1exportable in view");
    expect(screen.getByRole("region", { name: "Independent verification material" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open public key" }).getAttribute("href")).toBe(
      "https://api.zroky.com/.well-known/zroky/action-receipt-signing-key",
    );
    expect(
      screen.getByText("Signature validity is server-attested here and independently checkable with the published Ed25519 public key."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("sha256:receipt_1").length).toBeGreaterThan(0);
    expect(api.getActionIntentReceipt).toHaveBeenCalledTimes(1);
    expect(api.getActionIntentReceipt.mock.calls[0]?.[0]).toBe("act_1");
    expect(api.getRuntimePolicyEvidencePack).not.toHaveBeenCalled();
  });

  it("loads additional server pages without changing the evidence scope", async () => {
    const first = ledgerResponse({
      decisions: [],
      outcomes: [],
      intents: [actionIntent({ action_id: "act_page_1", intent_digest: "sha256:page-1", runtime_policy_decision_id: null })],
    });
    const second = ledgerResponse({
      decisions: [],
      outcomes: [],
      intents: [actionIntent({ action_id: "act_page_2", intent_digest: "sha256:page-2", runtime_policy_decision_id: null })],
    });
    first.has_more = true;
    first.total_in_scope = 2;
    first.total_matching = 2;
    first.counts.total = 2;
    first.counts.export_ready = 2;
    second.offset = 1;
    second.total_in_scope = 2;
    second.total_matching = 2;
    second.counts.total = 2;
    second.counts.export_ready = 2;
    api.getEvidenceLedger.mockImplementation(({ offset }: { offset?: number }) => Promise.resolve(offset ? second : first));

    renderEvidencePage();

    expect(await screen.findByText("sha256:page-1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load more proof records" }));
    expect(await screen.findByText("sha256:page-2")).toBeInTheDocument();
    expect(api.getEvidenceLedger).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ days: 7, offset: 1 }),
      expect.any(AbortSignal),
    );
  });

  it("shows guard-only runtime decisions as secondary full Evidence Packs", async () => {
    api.getEvidenceLedger.mockResolvedValue(ledgerResponse({ intents: [] }));

    renderEvidencePage();

    const row = (await screen.findByText("Close ticket T-1001")).closest(".ev-ledger-row") as HTMLElement;
    expect(within(row).getByText("Guard-only evidence")).toBeInTheDocument();
    expect(await screen.findByText("Mandate snapshot")).toBeInTheDocument();
    expect(screen.getAllByText(/support-control/).length).toBeGreaterThan(0);
    expect(screen.getByText("Approval audit")).toBeInTheDocument();
    expect(screen.getAllByText(/ops@example.com/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Hash algorithm").length).toBeGreaterThan(0);
    expect(screen.getAllByText("trace_1").length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: "trace_1" })).not.toBeInTheDocument();
    expect(api.getRuntimePolicyEvidencePack).toHaveBeenCalledTimes(1);
    expect(api.getRuntimePolicyEvidencePack.mock.calls[0]?.[0]).toBe("decision_1");
    expect(api.getActionIntentReceipt).not.toHaveBeenCalled();
  });

  it("searches the ledger and exports a scoped audit manifest", async () => {
    renderEvidencePage();

    const ledger = await screen.findByLabelText("Evidence ledger");
    await within(ledger).findByText("Close ticket T-1001");

    fireEvent.change(screen.getByPlaceholderText("Search proof records..."), {
      target: { value: "sha256:intent_1" },
    });
    expect(within(ledger).getByText("Close ticket T-1001")).toBeInTheDocument();

    fireEvent.click(within(ledger).getByRole("button", { name: "Export manifest" }));

    await waitFor(() => expect(api.getEvidenceManifest).toHaveBeenCalledWith(
      {
        dashboard_origin: "http://localhost:3000",
        days: 7,
        end_date: "",
        filter: "all",
        search: "sha256:intent_1",
        start_date: "",
      },
    ));
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
    const blob = vi.mocked(URL.createObjectURL).mock.calls.at(-1)?.[0] as Blob;
    const exported = await blob.text();
    expect(exported).toContain('"artifact": "zroky.evidence_manifest"');
    expect(exported).toContain('"search": "sha256:intent_1"');
    expect(exported).toContain('"digest": "sha256:intent_1"');
    expect(exported).toContain('"public_key_url": "https://api.zroky.com/.well-known/zroky/action-receipt-signing-key"');
    expect(await screen.findByText("Audit manifest exported for 1 proof record.")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Search proof records..."), {
      target: { value: "missing-digest" },
    });
    expect(await screen.findByText("No records match this filter or search.")).toBeInTheDocument();
  });

  it("filters exception rows and keeps unlinked outcomes visible but non-exportable", async () => {
    api.getEvidenceLedger.mockResolvedValue(ledgerResponse({
      intents: [actionIntent({ action_id: "act_bad", proof_status: "mismatched", intent_digest: "sha256:mismatch" })],
      outcomes: [
        outcome({ id: "check_bad", verdict: "mismatched", reason: "status mismatch", idempotency_key: "idem_act_1" }),
        outcome({
          id: "check_unlinked",
          call_id: "call_unlinked",
          trace_id: "trace_unlinked",
          runtime_policy_decision_id: null,
          idempotency_key: null,
          system_ref: "crm:CUS-1001",
          verdict: "not_verified",
        }),
      ],
    }));

    renderEvidencePage();

    expect(await screen.findByRole("heading", { name: "Exception needs review" }, { timeout: 5_000 })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Exceptions" }));
    expect(screen.getAllByText("sha256:mismatch").length).toBeGreaterThan(0);
    expect(screen.queryByText("crm:CUS-1001")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Needs verification" }));
    const unlinkedRow = (await screen.findAllByText("crm:CUS-1001"))[0]?.closest(".ev-ledger-row") as HTMLElement;
    expect(within(unlinkedRow).getByText("Unlinked outcome")).toBeInTheDocument();
    expect(within(unlinkedRow).getByText("not linked / not exportable")).toBeInTheDocument();
    fireEvent.click(within(unlinkedRow).getByRole("button", { name: "Not exportable" }));
    expect(await screen.findByText("Not linked / not exportable")).toBeInTheDocument();
  });

  it("explains that denied actions do not require receipt proof", async () => {
    api.getEvidenceLedger.mockResolvedValue(ledgerResponse({
      intents: [actionIntent({ status: "denied", proof_status: "not_started", receipt_status: "missing" })],
      decisions: [runtimeDecision({ status: "blocked", decision: "block", allowed: false })],
      outcomes: [],
    }));

    renderEvidencePage();

    expect(await screen.findByText("Receipt not expected")).toBeInTheDocument();
    expect(screen.getByText("Policy stopped execution; receipt and outcome proof are not expected.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review 1 pending" })).not.toBeInTheDocument();
  });

  it("resolves action deep links to the matching ledger row", async () => {
    window.history.pushState({}, "", "/evidence?action_id=act_1");

    renderEvidencePage();

    const ledger = await screen.findByLabelText("Evidence ledger");
    await within(ledger).findByText("Close ticket T-1001");
    const row = within(ledger).getByText("Close ticket T-1001").closest(".ev-ledger-row") as HTMLElement;
    await waitFor(() => expect(row.getAttribute("data-focused")).toBe("true"));
    expect(await screen.findByText("Evidence + Signature")).toBeInTheDocument();
    expect(api.getActionIntentReceipt.mock.calls[0]?.[0]).toBe("act_1");
    expect(api.getRuntimePolicyEvidencePack).not.toHaveBeenCalled();
  });

  it("exports selected receipt JSON and prints the focused proof", async () => {
    renderEvidencePage();

    await screen.findByText("Evidence + Signature");
    expect(screen.getByLabelText("Printable evidence report")).toBeInTheDocument();
    expect(screen.getByAltText("Zroky").getAttribute("src")).toBe("/zroky-brand.png");
    expect(screen.getByText("Verified Action Control Plane")).toBeInTheDocument();
    expect(screen.getByText("Zroky Evidence Report")).toBeInTheDocument();
    expect(screen.getAllByText("Proof seal").length).toBeGreaterThan(0);
    expect(screen.getByText("Confidential evidence artifact")).toBeInTheDocument();
    expect(screen.getAllByText("Tamper-evident").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Server-attested signature valid/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("SERVER-ATTESTED VALID").length).toBeGreaterThan(0);
    const panel = screen.getByLabelText("Focused proof panel");
    fireEvent.click(within(panel).getByRole("button", { name: "Print" }));
    expect(window.print).toHaveBeenCalled();

    fireEvent.click(within(panel).getByRole("button", { name: "Export receipt JSON" }));

    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
    const blob = vi.mocked(URL.createObjectURL).mock.calls.at(-1)?.[0] as Blob;
    const exported = await blob.text();
    expect(exported).toContain('"artifact": "zroky.action_receipt"');
    expect(exported).toContain('"receipt_id": "receipt_1"');
    expect(exported).toContain('"receipt_digest": "sha256:receipt_1"');
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:evidence");
    expect(await screen.findByText("Action Receipt JSON exported.")).toBeInTheDocument();
    expect(api.getActionIntentReceipt).toHaveBeenCalledTimes(1);
  });
});
