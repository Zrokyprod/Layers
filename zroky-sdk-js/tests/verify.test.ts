// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { init, verifyOutcome, ZrokyOutcomeVerificationError } from "../src";

type FetchCall = {
  input: RequestInfo | URL;
  init?: RequestInit;
};

const originalFetch = globalThis.fetch;

function recordFetches(responseBody: Record<string, unknown>): FetchCall[] {
  const calls: FetchCall[] = [];
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ input, init });
    return Promise.resolve({
      ok: true,
      status: 201,
      json: async () => responseBody,
    } as Response);
  }) as typeof fetch;
  return calls;
}

function parseRequestBody(call: FetchCall): Record<string, unknown> {
  assert.equal(typeof call.init?.body, "string");
  return JSON.parse(call.init.body) as Record<string, unknown>;
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  init({});
});

describe("verifyOutcome", () => {
  it("posts Generic REST saved reconciliation without connector secrets", async () => {
    const calls = recordFetches({
      id: "check_generic",
      verdict: "matched",
      connector_type: "generic_rest_api",
      system_ref: "generic:ord_123",
    });

    const check = await verifyOutcome(
      {
        connector: "generic_rest",
        recordRef: "ord_123",
        runtimePolicyDecisionId: "decision_123",
        actionType: "internal_api_mutation",
        claimed: {
          record_ref: "ord_123",
          status: "approved",
          total_usd: 118.42,
        },
        metadata: { run_id: "pilot_1" },
      },
      {
        projectId: "proj_123",
        apiKey: "zk_test",
        endpoint: "https://capture.example/api/v1/ingest",
      },
    );

    assert.equal(check.id, "check_generic");
    assert.equal(calls.length, 1);
    assert.equal(
      calls[0].input,
      "https://capture.example/api/v1/outcomes/reconciliation/generic-rest/saved",
    );
    const headers = calls[0].init?.headers as Record<string, string>;
    assert.equal(headers["x-api-key"], "zk_test");
    assert.equal(headers["x-project-id"], "proj_123");

    const body = parseRequestBody(calls[0]);
    assert.equal(body.record_ref, "ord_123");
    assert.equal(body.runtime_policy_decision_id, "decision_123");
    assert.equal(body.action_type, "internal_api_mutation");
    assert.deepEqual(body.claimed, {
      record_ref: "ord_123",
      status: "approved",
      total_usd: 118.42,
    });
    assert.deepEqual(body.metadata, { run_id: "pilot_1" });
    assert.equal(JSON.stringify(body).includes("bearer"), false);
  });

  it("maps ledger and CRM saved connector routes", async () => {
    const calls = recordFetches({ id: "check_saved", verdict: "matched" });

    await verifyOutcome(
      {
        connector: "ledger_refund",
        refundId: "rf_123",
        runtimePolicyDecisionId: "decision_refund",
        claimed: { refund_id: "rf_123", amount_usd: 42.5, currency: "USD" },
      },
      { projectId: "proj_123", apiKey: "zk_test", endpoint: "https://api.example" },
    );
    await verifyOutcome(
      {
        connector: "crm_record",
        customerId: "cus_123",
        runtimePolicyDecisionId: "decision_customer",
        claimed: { customer_id: "cus_123", status: "active" },
      },
      { projectId: "proj_123", apiKey: "zk_test", endpoint: "https://api.example" },
    );

    assert.equal(
      calls[0].input,
      "https://api.example/v1/outcomes/reconciliation/ledger-refund/saved",
    );
    assert.deepEqual(parseRequestBody(calls[0]), {
      refund_id: "rf_123",
      runtime_policy_decision_id: "decision_refund",
      claimed: { refund_id: "rf_123", amount_usd: 42.5, currency: "USD" },
    });
    assert.equal(
      calls[1].input,
      "https://api.example/v1/outcomes/reconciliation/customer-record/saved",
    );
    assert.deepEqual(parseRequestBody(calls[1]), {
      customer_id: "cus_123",
      runtime_policy_decision_id: "decision_customer",
      claimed: { customer_id: "cus_123", status: "active" },
    });
  });

  it("fails closed when SDK credentials are missing", async () => {
    await assert.rejects(
      () =>
        verifyOutcome({
          connector: "generic_rest",
          recordRef: "ord_123",
          claimed: { record_ref: "ord_123", status: "approved" },
        }),
      ZrokyOutcomeVerificationError,
    );
  });
});
