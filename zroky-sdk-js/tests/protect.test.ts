// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { init, protect } from "../src";

type FetchCall = {
  input: RequestInfo | URL;
  init?: RequestInit;
};

const originalFetch = globalThis.fetch;

function recordFetchSequence(payloads: Record<string, unknown>[]): FetchCall[] {
  const calls: FetchCall[] = [];
  let index = 0;
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ input, init });
    const payload = payloads[index] ?? payloads[payloads.length - 1];
    index += 1;
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => payload,
    } as Response);
  }) as typeof fetch;
  return calls;
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  init({});
});

describe("protect", () => {
  it("maps friendly protected action options to the verified action API", async () => {
    const calls = recordFetchSequence([
      { action_id: "act_access", status: "validated" },
      { action_id: "act_access", status: "authorized", allowed: true },
    ]);

    const decision = await protect(
      {
        action: "customer.access.grant",
        operationKind: "update",
        params: { customer_id: "cus_123", role: "viewer" },
        resource: { type: "customer_access", id: "cus_123" },
        purpose: { summary: "Grant read-only access after support approval." },
        verificationProfile: "identity-access-match",
        idempotencyKey: "access_cus_123_viewer",
      },
      { apiKey: "zk_test", projectId: "proj_test", endpoint: "https://api.zroky.test" },
    );

    assert.equal(decision.status, "authorized");
    assert.equal(calls.length, 2);
    assert.equal(calls[0].input, "https://api.zroky.test/v1/action-intents");
    assert.equal(calls[1].input, "https://api.zroky.test/v1/action-intents/act_access/decide");
    const headers = calls[0].init?.headers as Record<string, string>;
    assert.equal(headers["Idempotency-Key"], "access_cus_123_viewer");

    const body = JSON.parse(calls[0].init?.body as string) as Record<string, unknown>;
    assert.equal(body.contract_version, "customer.access.grant/1.0");
    assert.equal(body.action_type, "customer.access.grant");
    assert.equal(body.operation_kind, "UPDATE");
    assert.deepEqual(body.parameters, { customer_id: "cus_123", role: "viewer" });
    assert.equal(body.verification_profile, "identity-access-match");
  });

  it("can wait for proof and return the receipt envelope", async () => {
    const calls = recordFetchSequence([
      { action_id: "act_done", status: "validated" },
      { action_id: "act_done", status: "authorized", allowed: true },
      { action_id: "act_done", proof_status: "matched", receipt_status: "generated" },
      { receipt_id: "receipt_done", signature_valid: true },
    ]);

    const result = await protect(
      {
        action: "customer.access.grant",
        params: { customer_id: "cus_123" },
        waitForReceipt: true,
        pollIntervalMs: 50,
      },
      { apiKey: "zk_test", projectId: "proj_test", endpoint: "https://api.zroky.test" },
    );

    assert.equal(result.actionId, "act_done");
    assert.equal(result.proofStatus, "matched");
    assert.equal(result.receiptStatus, "generated");
    assert.equal(result.signatureValid, true);
    assert.equal(result.evidenceId, "receipt_done");
    assert.equal(calls[2].input, "https://api.zroky.test/v1/action-intents/act_done");
    assert.equal(calls[3].input, "https://api.zroky.test/v1/action-intents/act_done/receipt");
  });
});
