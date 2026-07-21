// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { preExecutionGuard, ZrokyRuntimePolicyBlocked } from "../src";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("preExecutionGuard", () => {
  it("creates intent, checks policy, and blocks observe_only", async () => {
    const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ input, init });
      const payload = calls.length === 1
        ? { id: "intent_1" }
        : { id: "decision_1", decision: "observe_only" };
      return Promise.resolve({ ok: true, status: 200, json: async () => payload } as Response);
    }) as typeof fetch;

    await assert.rejects(
      () =>
        preExecutionGuard(
          { intent: { action: "refund" }, idempotencyKey: "intent-key" },
          { endpoint: "https://api.example", apiKey: "zk_test", projectId: "proj_test" },
        ),
      ZrokyRuntimePolicyBlocked,
    );

    assert.equal(calls[0].input, "https://api.example/v1/intents");
    assert.equal(calls[1].input, "https://api.example/v1/policy/check");
    assert.equal((calls[0].init?.headers as Record<string, string>)["Idempotency-Key"], "intent-key");
  });
});
