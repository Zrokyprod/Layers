// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import {
  guard,
  init,
  ZrokyRuntimePolicyBlocked,
  ZrokyRuntimePolicyError,
} from "../src";

type FetchCall = {
  input: RequestInfo | URL;
  init?: RequestInit;
};

const originalFetch = globalThis.fetch;

function recordFetches(decision: Record<string, unknown>): FetchCall[] {
  const calls: FetchCall[] = [];
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ input, init });
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => decision,
    } as Response);
  }) as typeof fetch;
  return calls;
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  init({});
});

describe("guard", () => {
  it("posts a masked runtime policy check and returns allowed decisions", async () => {
    const calls = recordFetches({
      id: "decision_guard_allow",
      allowed: true,
      status: "allowed",
      reasons: ["runtime policy checks passed"],
    });

    const decision = await guard(
      {
        actionType: "refund",
        toolName: "refund_payment",
        toolArgs: { order_id: "ord_123", amount: 42.5, currency: "USD" },
        traceId: "trace_guard",
        outputText: "Refund approved for alice@example.com",
        externalAction: true,
        businessImpact: {
          summary: "Issue approved refund",
          customer_email: "alice@example.com",
          estimated_value_usd: 42.5,
        },
      },
      {
        projectId: "proj_123",
        apiKey: "zk_test",
        endpoint: "https://capture.example/api/v1/ingest",
      },
    );

    assert.equal(decision.id, "decision_guard_allow");
    assert.equal(calls.length, 1);
    assert.equal(calls[0].input, "https://capture.example/api/v1/runtime-policy/check");
    const headers = calls[0].init?.headers as Record<string, string>;
    assert.equal(headers["x-api-key"], "zk_test");
    assert.equal(headers["x-project-id"], "proj_123");

    const body = JSON.parse(calls[0].init?.body as string) as Record<string, unknown>;
    assert.equal(body.action_type, "refund");
    assert.equal(body.tool_name, "refund_payment");
    assert.equal((body.tool_args as Record<string, unknown>).order_id, "ord_123");
    assert.equal(body.output_text, "Refund approved for [REDACTED_EMAIL]");
    assert.equal(
      (body.business_impact as Record<string, unknown>).customer_email,
      "[REDACTED_EMAIL]",
    );
    assert.equal(body.pii_detected, true);
  });

  it("raises when the backend holds an action for approval", async () => {
    recordFetches({
      id: "decision_guard_hold",
      allowed: false,
      status: "pending_approval",
      requires_approval: true,
      reasons: ["sensitive action requires human approval"],
    });

    await assert.rejects(
      () =>
        guard(
          {
            actionType: "refund",
            toolName: "refund_payment",
            toolArgs: { order_id: "ord_hold", amount: 9000 },
            businessImpactSummary: "High-value refund",
          },
          { projectId: "proj_123", apiKey: "zk_test" },
        ),
      (error: unknown) => {
        assert.ok(error instanceof ZrokyRuntimePolicyBlocked);
        assert.equal(error.decision.id, "decision_guard_hold");
        assert.equal(error.decision.status, "pending_approval");
        return true;
      },
    );
  });

  it("fails closed on transport errors", async () => {
    globalThis.fetch = (() => Promise.reject(new Error("backend down"))) as typeof fetch;

    await assert.rejects(
      () =>
        guard(
          { actionType: "delete", toolName: "delete_customer" },
          { projectId: "proj_123", apiKey: "zk_test" },
        ),
      ZrokyRuntimePolicyError,
    );
  });

  it("fails closed when credentials are missing", async () => {
    await assert.rejects(
      () => guard({ actionType: "refund", toolName: "refund_payment" }),
      ZrokyRuntimePolicyError,
    );
  });
});
