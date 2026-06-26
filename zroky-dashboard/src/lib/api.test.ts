import { afterEach, describe, expect, it, vi } from "vitest";

import {
  approveRuntimePolicyDecision,
  getBillingMe,
  getCustomerRecordConnectorStatus,
  getLedgerRefundConnectorStatus,
  getRuntimePolicyEvidencePack,
  getOutcomeReconciliation,
  getOutcomeReconciliationSummary,
  getPostgresReadConnectorStatus,
  listRuntimePolicyApprovals,
  listOutcomeReconciliations,
  rejectRuntimePolicyDecision,
  reconcileSavedConnector,
  reconcileSavedCustomerRecord,
  reconcileSavedGenericRest,
  reconcileSavedLedgerRefund,
  reconcileSavedPostgresRead,
  saveCustomerRecordConnectorConfig,
  saveLedgerRefundConnectorConfig,
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
