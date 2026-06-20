import { afterEach, describe, expect, it, vi } from "vitest";

import {
  approveRuntimePolicyDecision,
  getBillingMe,
  getRuntimePolicyEvidencePack,
  getOutcomeReconciliation,
  getOutcomeReconciliationSummary,
  listRuntimePolicyApprovals,
  listOutcomeReconciliations,
  rejectRuntimePolicyDecision,
  setRuntimePolicyKillSwitch,
} from "@/lib/api";

vi.mock("@/lib/auth", () => ({
  clearAuthSession: vi.fn(),
  readAccessTokenFromBrowser: vi.fn(() => null),
  readRefreshTokenFromBrowser: vi.fn(() => null),
  storeAuthSession: vi.fn(),
}));

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
      "/api/zroky/v1/runtime-policy/approvals?status=pending_approval",
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
      "/api/zroky/v1/runtime-policy/approvals?status=all",
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

    await listOutcomeReconciliations({ verdict: "mismatched", limit: 25 });
    await listOutcomeReconciliations({ verdict: "all", limit: 50 });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/zroky/v1/outcomes/reconciliation?verdict=mismatched&limit=25",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/zroky/v1/outcomes/reconciliation?limit=50",
      expect.objectContaining({ method: "GET" }),
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
});
