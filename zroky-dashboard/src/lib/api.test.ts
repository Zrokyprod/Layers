import { afterEach, describe, expect, it, vi } from "vitest";

import {
  approveRuntimePolicyDecision,
  getBillingMe,
  listRuntimePolicyApprovals,
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
