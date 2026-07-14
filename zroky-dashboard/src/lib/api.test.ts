import { afterEach, describe, expect, it, vi } from "vitest";

import {
  acknowledgeOutcomeMismatchResponse,
  createActionIntent,
  createOutcomeCorrectiveAction,
  decideActionIntent,
  approveRuntimePolicyDecision,
  activateMcpUpstream,
  disableMcpUpstream,
  enforceAgentProfile,
  getActionsLifecycleSummary,
  getBillingMe,
  getActionIntentReceipt,
  getActionIntentTimeline,
  getCustomerRecordConnectorStatus,
  getLedgerRefundConnectorStatus,
  getMcpUpstreamBinding,
  getRuntimePolicyEvidencePack,
  getOutcomeReconciliation,
  getOutcomeMismatchResponse,
  getOutcomeReconciliationSummary,
  getPostgresReadConnectorStatus,
  listActionExecutionAttempts,
  listActionContracts,
  listActionIntents,
  listProjectActionExecutionAttempts,
  listActionRunners,
  listRuntimePolicyApprovals,
  listOutcomeReconciliations,
  listOutcomeMismatchResponses,
  rejectRuntimePolicyDecision,
  preflightMcpUpstream,
  reconcileSavedConnector,
  reconcileSavedCustomerRecord,
  reconcileSavedGenericRest,
  reconcileSavedLedgerRefund,
  reconcileSavedPostgresRead,
  resolveOutcomeMismatchResponse,
  saveCustomerRecordConnectorConfig,
  saveLedgerRefundConnectorConfig,
  saveMcpUpstreamDraft,
  savePostgresReadConnectorConfig,
  setRuntimePolicyKillSwitch,
  testCustomerRecordConnector,
  testLedgerRefundConnector,
  testPostgresReadConnector,
} from "@/lib/api";

vi.mock("@/lib/auth", () => ({
  clearAuthSession: vi.fn(),
  readAccessTokenFromBrowser: vi.fn(() => null),
  readRefreshTokenFromBrowser: vi.fn(() => null),
  storeAuthSession: vi.fn(),
}));

const mcpBindingResponse = {
  endpoint_url: "https://mcp.example.com/mcp",
  protocol_version: "2025-06-18",
  credential_configured: true,
  allowed_tools: ["refund.create"],
  status: "draft",
  test_status: "not_tested",
  tested_at: null,
  last_test_error: null,
  activated_at: null,
  version: 1,
  created_at: "2026-07-11T09:00:00Z",
  updated_at: "2026-07-11T09:00:00Z",
};

function mockFetchResponse(response: Response): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

function expectBillingRequestToRejectWith(message: string): Promise<void> {
  return expect(getBillingMe()).rejects.toThrow(message);
}

describe("shared API error parsing", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("uses JSON detail when present", async () => {
    mockFetchResponse(new Response(JSON.stringify({ detail: "Workspace missing" }), { status: 404 }));

    await expectBillingRequestToRejectWith("Workspace missing");
  });

  it("uses JSON message when detail is absent", async () => {
    mockFetchResponse(new Response(JSON.stringify({ message: "Plan unavailable" }), { status: 503 }));

    await expectBillingRequestToRejectWith("Plan unavailable");
  });

  it("uses JSON error when detail and message are absent", async () => {
    mockFetchResponse(new Response(JSON.stringify({ error: "Backend unavailable" }), { status: 500 }));

    await expectBillingRequestToRejectWith("Backend unavailable");
  });

  it("uses nested JSON detail message when present", async () => {
    const body = JSON.stringify({ detail: { message: "bad request" } });
    mockFetchResponse(new Response(body, { status: 400 }));

    await expectBillingRequestToRejectWith("bad request");
  });

  it("uses plain text error bodies", async () => {
    mockFetchResponse(new Response("plain failure", { status: 500 }));

    await expectBillingRequestToRejectWith("plain failure");
  });

  it("uses the default HTTP error for empty bodies", async () => {
    mockFetchResponse(new Response("", { status: 503 }));

    await expectBillingRequestToRejectWith("GET /v1/billing/me failed (503)");
  });

  it("returns raw text for invalid JSON without surfacing body stream errors", async () => {
    mockFetchResponse(new Response("{broken", { status: 500 }));

    await getBillingMe().then(
      () => {
        throw new Error("expected request to fail");
      },
      (error: unknown) => {
        expect(error).toBeInstanceOf(Error);
        expect((error as Error).message).toBe("{broken");
        expect((error as Error).message).not.toContain("body stream already read");
      },
    );
  });

  it("reads the error body only once and does not call response.json", async () => {
    const text = vi.fn().mockResolvedValue("single read failure");
    const json = vi.fn();
    const response = {
      ok: false,
      status: 500,
      text,
      json,
    } as unknown as Response;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    await expectBillingRequestToRejectWith("single read failure");

    expect(text).toHaveBeenCalledTimes(1);
    expect(json).not.toHaveBeenCalled();
  });
});

describe("MCP upstream API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("treats a missing tenant binding as unconfigured", async () => {
    mockFetchResponse(new Response(JSON.stringify({ detail: "Not found" }), { status: 404 }));

    await expect(getMcpUpstreamBinding()).resolves.toBeNull();
  });

  it("uses the owner lifecycle endpoints and sends only a managed credential reference", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(mcpBindingResponse), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        binding: { ...mcpBindingResponse, test_status: "succeeded" },
        discovered_tools: ["refund.create"],
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ...mcpBindingResponse,
        status: "active",
        test_status: "succeeded",
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ...mcpBindingResponse,
        status: "disabled",
      }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await saveMcpUpstreamDraft({
      endpoint_url: "https://mcp.example.com/mcp",
      protocol_version: "2025-06-18",
      bearer_credential_id: "cred_managed_123",
      allowed_tools: ["refund.create"],
    });
    await preflightMcpUpstream();
    await activateMcpUpstream();
    await disableMcpUpstream();

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/zroky/v1/mcp-config/upstream", expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({
        endpoint_url: "https://mcp.example.com/mcp",
        protocol_version: "2025-06-18",
        bearer_credential_id: "cred_managed_123",
        allowed_tools: ["refund.create"],
      }),
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/zroky/v1/mcp-config/upstream/preflight", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/zroky/v1/mcp-config/upstream/activate", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenNthCalledWith(4, "/api/zroky/v1/mcp-config/upstream/disable", expect.objectContaining({ method: "POST" }));
  });
});

describe("runtime policy API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("lists pending approvals by default", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total_in_page: 0 }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(listRuntimePolicyApprovals()).resolves.toEqual({ items: [], total_in_page: 0 });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/runtime-policy/approvals?status=pending_approval&limit=100",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("sends all status when all approvals are requested", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total_in_page: 0 }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await listRuntimePolicyApprovals("all");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/runtime-policy/approvals?status=all&limit=100",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("loads an evidence pack for a runtime policy decision", async () => {
    const pack = {
      schema_version: "runtime_policy_evidence.v1",
      project_id: "proj_1",
      decision_id: "decision_1",
      verification_status: "pass",
      decision: {},
      related_decisions: [],
      audit_log: [],
      trace_policy_spans: [],
      outcome_reconciliation: [],
      call: null,
      generated_at: "2026-06-20T00:00:00Z",
      hash_algorithm: "sha256",
      evidence_hash: "a".repeat(64),
      hash_payload_excludes: ["generated_at"],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(pack), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getRuntimePolicyEvidencePack("decision_1")).resolves.toMatchObject({
      decision_id: "decision_1",
      evidence_hash: "a".repeat(64),
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/runtime-policy/decisions/decision_1/evidence",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("posts approve and reject decisions with reasons", async () => {
    const decision = {
      id: "decision_1",
      project_id: "proj_1",
      trace_id: "trace_1",
      call_id: null,
      agent_name: "refund-agent",
      role: null,
      action_type: "refund",
      tool_name: "refund_payment",
      decision: "allow",
      status: "approved",
      allowed: true,
      requires_approval: false,
      reasons: ["approved"],
      request: {},
      policy_snapshot: {},
      created_at: "2026-06-11T00:00:00Z",
      expires_at: null,
      resolved_at: "2026-06-11T00:01:00Z",
      resolved_by: "user",
      resolution_reason: "valid request",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(decision), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...decision, status: "rejected", decision: "block" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await approveRuntimePolicyDecision("decision_1", "valid request");
    await rejectRuntimePolicyDecision("decision_1", "unsafe request");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/zroky/v1/runtime-policy/approvals/decision_1/approve",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ reason: "valid request" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/zroky/v1/runtime-policy/approvals/decision_1/reject",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ reason: "unsafe request" }),
      }),
    );
  });

  it("toggles the runtime kill switch", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ project_id: "proj_1", enabled: true, policy: { kill_switch: true } }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(setRuntimePolicyKillSwitch(true)).resolves.toMatchObject({ enabled: true });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/runtime-policy/kill-switch",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ enabled: true }),
      }),
    );
  });
});

describe("verified action API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("lists action intents with lifecycle filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total_in_page: 0, limit: 25, offset: 10 }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      listActionIntents({
        status: "approval_pending",
        proof_status: "pending",
        receipt_status: "pending",
        agent_id: "agent_profile_inventory",
        limit: 25,
        offset: 10,
      }),
    ).resolves.toEqual({ items: [], total_in_page: 0, limit: 25, offset: 10 });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/action-intents?limit=25&offset=10&status=approval_pending&proof_status=pending&receipt_status=pending&agent_id=agent_profile_inventory",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("omits all filters when listing action intents", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total_in_page: 0, limit: 50, offset: 0 }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await listActionIntents({ status: "all", proof_status: "all", receipt_status: "all", limit: 50 });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/action-intents?limit=50",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("lists contracts and creates an idempotent protected intent", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total_in_page: 0 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ action_id: "action_correction" }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await listActionContracts(100);
    await createActionIntent({
      contract_version: "ticket.reopen/1.0",
      action_type: "ticket.reopen",
      operation_kind: "UPDATE",
      resource: { ticket_id: "KAN-1" },
      parameters: { status: "In Progress" },
    }, "outcome-correction:case_1:attempt_1");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/zroky/v1/action-contracts?limit=100",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/zroky/v1/action-intents",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Idempotency-Key": "outcome-correction:case_1:attempt_1" }),
      }),
    );
  });

  it("loads the aggregate actions lifecycle summary", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          project_id: "proj_1",
          window_days: 30,
          window_start: "2026-06-01T00:00:00Z",
          generated_at: "2026-06-20T09:15:00Z",
          row_limit: 200,
          source_totals: {
            intents: 2,
            approvals: 1,
            outcomes: 2,
            mutations: 1,
            stale_attempts: 0,
          },
          truncated: false,
          truncated_sources: [],
          metrics: {
            controlled_actions: 2,
            held_actions: 1,
            matched_outcomes: 1,
            mismatched_outcomes: 0,
            not_verified_outcomes: 1,
            bypass_risk: 1,
          },
          sources: {
            lifecycle_summary: true,
            intents: true,
            approvals: true,
            outcomes: true,
            outcome_summary: true,
            source_summary: true,
            mutations: true,
            stale_attempts: true,
            billing_usage: true,
          },
          data: {
            intents: [],
            approvals: [],
            outcomes: [],
            outcome_summary: null,
            source_summary: null,
            mutations: [],
            stale_attempts: [],
            billing_usage: null,
          },
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getActionsLifecycleSummary({ days: 30, limit: 200 })).resolves.toMatchObject({
      metrics: { controlled_actions: 2, bypass_risk: 1 },
      source_totals: { intents: 2, approvals: 1 },
      data: { intents: [] },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/actions/lifecycle-summary?days=30&limit=200",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("loads action timeline, receipt, attempts, project attempts, runners, and posts decide", async () => {
    const receipt = {
      receipt_id: "receipt_1",
      project_id: "proj_1",
      action_id: "action_1",
      receipt_digest: "sha256:abc",
      evidence_hash: "sha256:def",
      signature_algorithm: "Ed25519",
      signature: "sig",
      signing_key_id: "key",
      signature_valid: true,
      generated_at: "2026-06-20T00:00:00Z",
      receipt: { final_status: "matched" },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ allowed: true, action_id: "action_1" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(receipt), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await decideActionIntent("action_1", { approval_id: "decision_1" });
    await getActionIntentTimeline("action_1");
    await expect(getActionIntentReceipt("action_1")).resolves.toMatchObject({ signature_valid: true });
    await listActionExecutionAttempts("action_1");
    await listProjectActionExecutionAttempts({ status: ["planned", "running"], stale: true, stale_after_seconds: 600 });
    await listActionRunners();

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/zroky/v1/action-intents/action_1/decide",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ approval_id: "decision_1" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/zroky/v1/action-intents/action_1/timeline",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/zroky/v1/action-intents/action_1/receipt",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/zroky/v1/action-intents/action_1/execution-attempts",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/api/zroky/v1/action-execution-attempts?status=planned%2Crunning&stale=true&stale_after_seconds=600",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      "/api/zroky/v1/action-runners",
      expect.objectContaining({ method: "GET" }),
    );
  });
});

describe("agent profile API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("posts explicit enforcement for an agent profile", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          schema_version: "zroky.agent_tool_control.v1",
          id: "agent_1",
          project_id: "proj_1",
          display_name: "Operations Agent",
          slug: "operations-agent",
          description: null,
          runtime_path: "sdk",
          framework: null,
          environment: "production",
          model_provider: null,
          model_name: null,
          tool_names: ["internal.ops.execute"],
          allowed_action_types: ["internal_api_mutation"],
          blocked_action_types: [],
          default_policy_id: null,
          risk_limits: {},
          verification_connectors: ["generic_rest"],
          metadata: { runtime_policy_mandate_enforced: true },
          is_active: true,
          created_at: "2026-06-20T09:00:00.000Z",
          updated_at: "2026-06-20T09:01:00.000Z",
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await enforceAgentProfile("agent_1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/agents/agent_1/enforce",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("outcome reconciliation API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("reads reconciliation summary for a window", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ window_days: 30, total: 3, matched: 1, mismatched: 1, not_verified: 1 }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getOutcomeReconciliationSummary(30)).resolves.toMatchObject({ total: 3 });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/outcomes/reconciliation/summary?days=30",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("lists reconciliation checks with optional verdict filters", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total_in_page: 0 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total_in_page: 0 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await listOutcomeReconciliations({ verdict: "mismatched", days: 14, limit: 25 });
    await listOutcomeReconciliations({ verdict: "all", limit: 50 });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/zroky/v1/outcomes/reconciliation?verdict=mismatched&days=14&limit=25",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/zroky/v1/outcomes/reconciliation?limit=50",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("lists, acknowledges, and resolves mismatch response cases", async () => {
    const responseCase = {
      id: "case_1",
      project_id: "proj_1",
      reconciliation_check_id: "check_1",
      status: "OPEN",
      remediation: {},
      evidence: {},
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [responseCase], total_in_page: 1 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(responseCase), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...responseCase, status: "ACKNOWLEDGED" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...responseCase, status: "RESOLVED" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await listOutcomeMismatchResponses("OPEN", 25, 14);
    await getOutcomeMismatchResponse("case_1");
    await acknowledgeOutcomeMismatchResponse("case_1");
    await resolveOutcomeMismatchResponse("case_1", {
      resolution_code: "confirmed_mismatch",
      resolution_note: "Confirmed against the ledger.",
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/zroky/v1/outcomes/reconciliation/mismatch-responses?status=OPEN&limit=25&days=14",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/zroky/v1/outcomes/reconciliation/mismatch-responses/case_1",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/zroky/v1/outcomes/reconciliation/mismatch-responses/case_1/acknowledge",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/zroky/v1/outcomes/reconciliation/mismatch-responses/case_1/resolve",
      expect.objectContaining({
        body: JSON.stringify({
          resolution_code: "confirmed_mismatch",
          resolution_note: "Confirmed against the ledger.",
        }),
        method: "POST",
      }),
    );
  });

  it("submits a mismatch correction through its tenant-scoped case endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ action_id: "action_correction", requires_approval: true }), { status: 201 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createOutcomeCorrectiveAction("case_1", {
      contract_version: "ticket.reopen/1.0",
      action_type: "ticket.reopen",
      operation_kind: "UPDATE",
      resource: { ticket_id: "KAN-1" },
      parameters: { status: "In Progress" },
    }, "outcome-correction:case_1:attempt_1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/outcomes/reconciliation/mismatch-responses/case_1/corrective-action",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Idempotency-Key": "outcome-correction:case_1:attempt_1" }),
      }),
    );
  });

  it("reads one reconciliation check by id", async () => {
    const check = {
      id: "check_1",
      project_id: "proj_1",
      call_id: null,
      trace_id: null,
      runtime_policy_decision_id: null,
      action_type: "refund",
      connector_type: "ledger_api",
      system_ref: "ledger:rf_1",
      verdict: "matched",
      reason: "all_compared_fields_matched",
      amount_usd: 42.5,
      currency: "USD",
      claimed: {},
      actual: {},
      comparison: {},
      idempotency_key: null,
      metadata: null,
      checked_at: "2026-06-20T00:00:00Z",
      created_at: "2026-06-20T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(check), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getOutcomeReconciliation("check_1")).resolves.toMatchObject({ id: "check_1" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/outcomes/reconciliation/check_1",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("runs saved ledger refund reconciliation without connector secrets in the request", async () => {
    const check = {
      id: "check_saved_ledger",
      project_id: "proj_1",
      call_id: "call_1",
      trace_id: "trace_1",
      runtime_policy_decision_id: "decision_1",
      action_type: "refund",
      connector_type: "ledger_refund_api",
      system_ref: "ledger:rf_1",
      verdict: "matched",
      reason: "all_compared_fields_matched",
      amount_usd: 42.5,
      currency: "USD",
      claimed: {},
      actual: {},
      comparison: {},
      idempotency_key: "saved_ledger_refund:decision_1:rf_1",
      metadata: { source: "saved_connector_runtime" },
      checked_at: "2026-06-20T00:00:00Z",
      created_at: "2026-06-20T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(check), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      reconcileSavedLedgerRefund({
        runtime_policy_decision_id: "decision_1",
        claimed: { refund_id: "rf_1", amount_usd: 42.5, currency: "USD" },
      }),
    ).resolves.toMatchObject({ id: "check_saved_ledger" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/outcomes/reconciliation/ledger-refund/saved",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          runtime_policy_decision_id: "decision_1",
          claimed: { refund_id: "rf_1", amount_usd: 42.5, currency: "USD" },
        }),
      }),
    );
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).not.toContain("bearer");
  });

  it("runs saved customer record reconciliation without connector secrets in the request", async () => {
    const check = {
      id: "check_saved_customer",
      project_id: "proj_1",
      call_id: "call_1",
      trace_id: "trace_1",
      runtime_policy_decision_id: "decision_1",
      action_type: "customer_record_update",
      connector_type: "customer_record_api",
      system_ref: "crm:cus_1",
      verdict: "matched",
      reason: "all_compared_fields_matched",
      amount_usd: null,
      currency: null,
      claimed: {},
      actual: {},
      comparison: {},
      idempotency_key: "saved_customer_record:decision_1:cus_1",
      metadata: { source: "saved_connector_runtime" },
      checked_at: "2026-06-20T00:00:00Z",
      created_at: "2026-06-20T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(check), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      reconcileSavedCustomerRecord({
        runtime_policy_decision_id: "decision_1",
        customer_id: "cus_1",
        claimed: { customer_id: "cus_1", status: "active" },
      }),
    ).resolves.toMatchObject({ id: "check_saved_customer" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/outcomes/reconciliation/customer-record/saved",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          runtime_policy_decision_id: "decision_1",
          customer_id: "cus_1",
          claimed: { customer_id: "cus_1", status: "active" },
        }),
      }),
    );
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).not.toContain("bearer");
  });

  it("runs saved Generic REST reconciliation without connector secrets in the request", async () => {
    const check = {
      id: "check_saved_generic",
      project_id: "proj_1",
      call_id: "call_1",
      trace_id: "trace_1",
      runtime_policy_decision_id: "decision_1",
      action_type: "internal_api_mutation",
      connector_type: "generic_rest_api",
      system_ref: "generic:ord_1",
      verdict: "matched",
      reason: "all_compared_fields_matched",
      amount_usd: null,
      currency: null,
      claimed: {},
      actual: {},
      comparison: {},
      idempotency_key: "saved_generic_rest:decision_1:ord_1",
      metadata: { source: "saved_connector_runtime" },
      checked_at: "2026-06-20T00:00:00Z",
      created_at: "2026-06-20T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(check), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      reconcileSavedGenericRest({
        runtime_policy_decision_id: "decision_1",
        action_type: "internal_api_mutation",
        record_ref: "ord_1",
        claimed: { record_ref: "ord_1", status: "approved" },
      }),
    ).resolves.toMatchObject({ id: "check_saved_generic" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/outcomes/reconciliation/generic-rest/saved",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          runtime_policy_decision_id: "decision_1",
          action_type: "internal_api_mutation",
          record_ref: "ord_1",
          claimed: { record_ref: "ord_1", status: "approved" },
        }),
      }),
    );
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).not.toContain("bearer");
  });

  it("runs saved PostgreSQL read reconciliation without database credentials in the request", async () => {
    const check = {
      id: "check_saved_postgres",
      project_id: "proj_1",
      call_id: "call_1",
      trace_id: "trace_1",
      runtime_policy_decision_id: "decision_1",
      action_type: "ticket_update",
      connector_type: "postgres_read",
      system_ref: "postgres:tickets:t_1",
      verdict: "matched",
      verification_status: "verified",
      reason: "all_compared_fields_matched",
      amount_usd: null,
      currency: null,
      claimed: {},
      actual: {},
      comparison: {},
      idempotency_key: "saved_postgres_read:decision_1:digest",
      metadata: { source: "saved_connector_runtime" },
      checked_at: "2026-06-20T00:00:00Z",
      created_at: "2026-06-20T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(check), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      reconcileSavedPostgresRead({
        runtime_policy_decision_id: "decision_1",
        action_type: "ticket_update",
        system_ref: "postgres:tickets:t_1",
        claimed: { ticket_id: "t_1", status: "closed" },
        params: { ticket_id: "t_1" },
      }),
    ).resolves.toMatchObject({ id: "check_saved_postgres" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/outcomes/reconciliation/postgres-read/saved",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          runtime_policy_decision_id: "decision_1",
          action_type: "ticket_update",
          system_ref: "postgres:tickets:t_1",
          claimed: { ticket_id: "t_1", status: "closed" },
          params: { ticket_id: "t_1" },
        }),
      }),
    );
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).not.toContain("postgresql://");
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).not.toContain("password");
  });

  it("runs the saved connector bridge without connector secrets in the request", async () => {
    const check = {
      id: "check_saved_bridge",
      project_id: "proj_1",
      call_id: "call_1",
      trace_id: "trace_1",
      runtime_policy_decision_id: "decision_1",
      action_type: "internal_api_mutation",
      connector_type: "generic_rest_api",
      system_ref: "generic:ord_1",
      verdict: "matched",
      reason: "all_compared_fields_matched",
      amount_usd: null,
      currency: null,
      claimed: {},
      actual: {},
      comparison: {},
      idempotency_key: "saved_generic_rest:decision_1:ord_1",
      metadata: { source: "saved_connector_runtime", runtime_path: "webhook_bridge" },
      checked_at: "2026-06-20T00:00:00Z",
      created_at: "2026-06-20T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(check), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      reconcileSavedConnector({
        connector: "generic_rest",
        runtime_policy_decision_id: "decision_1",
        action_type: "internal_api_mutation",
        record_ref: "ord_1",
        claimed: { record_ref: "ord_1", status: "approved" },
      }),
    ).resolves.toMatchObject({ id: "check_saved_bridge" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/outcomes/reconciliation/saved",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          connector: "generic_rest",
          runtime_policy_decision_id: "decision_1",
          action_type: "internal_api_mutation",
          record_ref: "ord_1",
          claimed: { record_ref: "ord_1", status: "approved" },
        }),
      }),
    );
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).not.toContain("bearer");
  });

  it("runs the saved connector bridge for PostgreSQL read checks", async () => {
    const check = {
      id: "check_saved_postgres_bridge",
      project_id: "proj_1",
      call_id: "call_1",
      trace_id: "trace_1",
      runtime_policy_decision_id: "decision_1",
      action_type: "ticket_update",
      connector_type: "postgres_read",
      system_ref: "postgres:source-record",
      verdict: "matched",
      verification_status: "verified",
      reason: "all_compared_fields_matched",
      amount_usd: null,
      currency: null,
      claimed: {},
      actual: {},
      comparison: {},
      idempotency_key: "saved_postgres_read:decision_1:digest",
      metadata: { source: "saved_connector_runtime", runtime_path: "webhook_bridge" },
      checked_at: "2026-06-20T00:00:00Z",
      created_at: "2026-06-20T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(check), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      reconcileSavedConnector({
        connector: "postgres_read",
        runtime_policy_decision_id: "decision_1",
        action_type: "ticket_update",
        claimed: { ticket_id: "t_1", status: "closed" },
        params: { ticket_id: "t_1" },
      }),
    ).resolves.toMatchObject({ id: "check_saved_postgres_bridge" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/outcomes/reconciliation/saved",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          connector: "postgres_read",
          runtime_policy_decision_id: "decision_1",
          action_type: "ticket_update",
          claimed: { ticket_id: "t_1", status: "closed" },
          params: { ticket_id: "t_1" },
        }),
      }),
    );
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).not.toContain("postgresql://");
  });
});

describe("ledger refund connector API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("reads saved connector status", async () => {
    const payload = {
      connected: true,
      connector_type: "ledger_refund_api",
      base_url: "https://ledger.example.com/api",
      path_template: "/refunds/{refund_id}",
      record_path: "data",
      query: null,
      has_bearer_token: true,
      bearer_token_last4: "oken",
      last_tested_at: null,
      readiness: {
        status: "ready",
        contract: { system_of_record: "ledger_refund" },
        checks: { config_saved: true },
        blockers: [],
        last_checked_at: "2026-06-21T00:00:00Z",
      },
      created_at: "2026-06-21T00:00:00Z",
      updated_at: "2026-06-21T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getLedgerRefundConnectorStatus()).resolves.toMatchObject({
      connected: true,
      bearer_token_last4: "oken",
      readiness: expect.objectContaining({
        status: "ready",
        contract: { system_of_record: "ledger_refund" },
      }),
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/integrations/system-of-record/ledger-refund/status",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("saves connector config without transforming the secret", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          connected: true,
          connector_type: "ledger_refund_api",
          base_url: "https://ledger.example.com/api",
          path_template: "/refunds/{refund_id}",
          record_path: "data",
          query: null,
          has_bearer_token: true,
          bearer_token_last4: "oken",
          last_tested_at: null,
          created_at: null,
          updated_at: null,
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await saveLedgerRefundConnectorConfig({
      base_url: "https://ledger.example.com/api",
      path_template: "/refunds/{refund_id}",
      record_path: "data",
      bearer_token: "ledger-secret-token",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/integrations/system-of-record/ledger-refund/config",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          base_url: "https://ledger.example.com/api",
          path_template: "/refunds/{refund_id}",
          record_path: "data",
          bearer_token: "ledger-secret-token",
        }),
      }),
    );
  });

  it("runs a saved connector test", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          check: {
            id: "check_1",
            project_id: "proj_1",
            call_id: null,
            trace_id: null,
            runtime_policy_decision_id: null,
            action_type: "refund",
            connector_type: "ledger_refund_api",
            system_ref: "ledger:rf_1",
            verdict: "matched",
            reason: "all_compared_fields_matched",
            amount_usd: 42.5,
            currency: "USD",
            claimed: {},
            actual: {},
            comparison: {},
            idempotency_key: null,
            metadata: null,
            checked_at: "2026-06-21T00:00:00Z",
            created_at: "2026-06-21T00:00:00Z",
          },
          connector: {
            connected: true,
            connector_type: "ledger_refund_api",
            base_url: "https://ledger.example.com/api",
            path_template: "/refunds/{refund_id}",
            record_path: "data",
            query: null,
            has_bearer_token: true,
            bearer_token_last4: "oken",
            last_tested_at: "2026-06-21T00:00:00Z",
            created_at: null,
            updated_at: null,
          },
        }),
        { status: 201 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await testLedgerRefundConnector({
      refund_id: "rf_1",
      claimed: { refund_id: "rf_1", amount_usd: 42.5 },
      match_fields: ["refund_id", "amount_usd"],
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/integrations/system-of-record/ledger-refund/test",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          refund_id: "rf_1",
          claimed: { refund_id: "rf_1", amount_usd: 42.5 },
          match_fields: ["refund_id", "amount_usd"],
        }),
      }),
    );
  });
});

describe("customer record connector API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("reads saved connector status", async () => {
    const payload = {
      connected: true,
      connector_type: "customer_record_api",
      base_url: "https://crm.example.com/api",
      path_template: "/customers/{customer_id}",
      record_path: "data",
      query: null,
      has_bearer_token: true,
      bearer_token_last4: "oken",
      last_tested_at: null,
      readiness: {
        status: "not_ready",
        contract: { system_of_record: "customer_record" },
        checks: { saved_test_matched: false },
        blockers: ["Latest connector test did not reconcile as matched."],
        last_checked_at: null,
      },
      created_at: "2026-06-21T00:00:00Z",
      updated_at: "2026-06-21T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getCustomerRecordConnectorStatus()).resolves.toMatchObject({
      connected: true,
      connector_type: "customer_record_api",
      bearer_token_last4: "oken",
      readiness: expect.objectContaining({
        status: "not_ready",
        blockers: ["Latest connector test did not reconcile as matched."],
      }),
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/integrations/system-of-record/customer-record/status",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("saves connector config without transforming the secret", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          connected: true,
          connector_type: "customer_record_api",
          base_url: "https://crm.example.com/api",
          path_template: "/customers/{customer_id}",
          record_path: "data",
          query: null,
          has_bearer_token: true,
          bearer_token_last4: "oken",
          last_tested_at: null,
          created_at: null,
          updated_at: null,
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await saveCustomerRecordConnectorConfig({
      base_url: "https://crm.example.com/api",
      path_template: "/customers/{customer_id}",
      record_path: "data",
      bearer_token: "crm-secret-token",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/integrations/system-of-record/customer-record/config",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          base_url: "https://crm.example.com/api",
          path_template: "/customers/{customer_id}",
          record_path: "data",
          bearer_token: "crm-secret-token",
        }),
      }),
    );
  });

  it("runs a saved connector test", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          check: {
            id: "check_crm_1",
            project_id: "proj_1",
            call_id: null,
            trace_id: null,
            runtime_policy_decision_id: null,
            action_type: "customer_record_update",
            connector_type: "customer_record_api",
            system_ref: "crm:cus_1",
            verdict: "matched",
            reason: "all_compared_fields_matched",
            amount_usd: null,
            currency: null,
            claimed: {},
            actual: {},
            comparison: {},
            idempotency_key: null,
            metadata: null,
            checked_at: "2026-06-21T00:00:00Z",
            created_at: "2026-06-21T00:00:00Z",
          },
          connector: {
            connected: true,
            connector_type: "customer_record_api",
            base_url: "https://crm.example.com/api",
            path_template: "/customers/{customer_id}",
            record_path: "data",
            query: null,
            has_bearer_token: true,
            bearer_token_last4: "oken",
            last_tested_at: "2026-06-21T00:00:00Z",
            created_at: null,
            updated_at: null,
          },
        }),
        { status: 201 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await testCustomerRecordConnector({
      customer_id: "cus_1",
      claimed: { customer_id: "cus_1", email: "owner@example.com" },
      match_fields: ["customer_id", "email"],
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/integrations/system-of-record/customer-record/test",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          customer_id: "cus_1",
          claimed: { customer_id: "cus_1", email: "owner@example.com" },
          match_fields: ["customer_id", "email"],
        }),
      }),
    );
  });
});

describe("PostgreSQL read connector API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("reads saved connector status without returning the DSN", async () => {
    const payload = {
      connected: true,
      connector_type: "postgres_read",
      base_url: "postgresql://db.example.com/app",
      path_template: "/",
      record_path: null,
      query: null,
      has_database_url: true,
      database_url_last4: "/app",
      has_read_query: true,
      read_query_digest: "abc123",
      has_bearer_token: false,
      bearer_token_last4: null,
      last_tested_at: null,
      readiness: {
        status: "ready",
        contract: { adapter: "postgresql_readonly" },
        checks: { database_url_present: true, read_query_present: true },
        blockers: [],
        last_checked_at: "2026-06-21T00:00:00Z",
      },
      created_at: "2026-06-21T00:00:00Z",
      updated_at: "2026-06-21T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getPostgresReadConnectorStatus()).resolves.toMatchObject({
      connected: true,
      connector_type: "postgres_read",
      has_database_url: true,
      read_query_digest: "abc123",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/integrations/system-of-record/postgres-read/status",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("saves encrypted connector config without transforming the DSN", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          connected: true,
          connector_type: "postgres_read",
          base_url: "postgresql://db.example.com/app",
          path_template: "/",
          record_path: null,
          query: null,
          has_database_url: true,
          database_url_last4: "/app",
          has_read_query: true,
          read_query_digest: "abc123",
          has_bearer_token: false,
          bearer_token_last4: null,
          last_tested_at: null,
          created_at: null,
          updated_at: null,
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await savePostgresReadConnectorConfig({
      database_url: "postgresql://readonly:pg-secret@db.example.com/app",
      read_query: "SELECT ticket_id, status FROM tickets WHERE ticket_id = :ticket_id",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/integrations/system-of-record/postgres-read/config",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          database_url: "postgresql://readonly:pg-secret@db.example.com/app",
          read_query: "SELECT ticket_id, status FROM tickets WHERE ticket_id = :ticket_id",
        }),
      }),
    );
  });

  it("runs a saved connector test with params", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          check: {
            id: "check_pg_1",
            project_id: "proj_1",
            call_id: null,
            trace_id: null,
            runtime_policy_decision_id: null,
            action_type: "ticket_update",
            connector_type: "postgres_read",
            system_ref: "postgres:tickets:t_1",
            verdict: "matched",
            verification_status: "verified",
            reason: "all_compared_fields_matched",
            amount_usd: null,
            currency: null,
            claimed: {},
            actual: {},
            comparison: {},
            idempotency_key: null,
            metadata: null,
            checked_at: "2026-06-21T00:00:00Z",
            created_at: "2026-06-21T00:00:00Z",
          },
          connector: {
            connected: true,
            connector_type: "postgres_read",
            base_url: "postgresql://db.example.com/app",
            path_template: "/",
            record_path: null,
            query: null,
            has_database_url: true,
            database_url_last4: "/app",
            has_read_query: true,
            read_query_digest: "abc123",
            has_bearer_token: false,
            bearer_token_last4: null,
            last_tested_at: "2026-06-21T00:00:00Z",
            created_at: null,
            updated_at: null,
          },
        }),
        { status: 201 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await testPostgresReadConnector({
      claimed: { ticket_id: "t_1", status: "closed" },
      params: { ticket_id: "t_1" },
      match_fields: ["ticket_id", "status"],
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/zroky/v1/integrations/system-of-record/postgres-read/test",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          claimed: { ticket_id: "t_1", status: "closed" },
          params: { ticket_id: "t_1" },
          match_fields: ["ticket_id", "status"],
        }),
      }),
    );
  });
});
