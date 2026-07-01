// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import {
  awaitActionProof,
  init,
  verifiedAction,
  ZrokyVerifiedActionApprovalRequired,
  ZrokyVerifiedActionError,
} from "../src";

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

describe("verifiedAction", () => {
  it("creates an action intent and decides without runner or credential pins", async () => {
    const calls = recordFetchSequence([
      {
        action_id: "act_123",
        status: "validated",
        proof_status: "not_started",
        receipt_status: "missing",
      },
      {
        action_id: "act_123",
        status: "authorized",
        allowed: true,
        requires_approval: false,
      },
    ]);

    const decision = await verifiedAction(
      {
        contractVersion: "inventory.item.update/1.0",
        actionType: "inventory.item.update",
        operationKind: "UPDATE",
        principal: { type: "agent", id: "inventory-agent" },
        resource: { type: "inventory_item", id: "item_123" },
        parameters: { fields: { status: "active" } },
        executionRequest: {
          credentialPointer: "ops-default",
          capability: { adapter: "generic_rest", operation: "rest.patch" },
          executionPlan: {
            adapter: "generic_rest",
            operation: "rest.patch",
            target: { resource_ref: "item_123" },
            arguments: { fields: { status: "active" } },
          },
        },
        idempotencyKey: "inventory_item_123_update",
      },
      {
        projectId: "proj_actions",
        apiKey: "zk_test",
        endpoint: "https://capture.example/api/v1/ingest",
        agentId: "agent_profile_inventory",
      },
    );

    assert.equal(decision.status, "authorized");
    assert.equal(calls[0].input, "https://capture.example/api/v1/action-intents");
    assert.equal(calls[1].input, "https://capture.example/api/v1/action-intents/act_123/decide");
    const headers = calls[0].init?.headers as Record<string, string>;
    assert.equal(headers["Idempotency-Key"], "inventory_item_123_update");
    assert.equal(headers["x-project-id"], "proj_actions");

    const body = JSON.parse(calls[0].init?.body as string) as Record<string, unknown>;
    assert.equal(body.agent_id, "agent_profile_inventory");
    const executionRequest = body.execution_request as Record<string, unknown>;
    assert.equal(executionRequest.credential_pointer, "ops-default");
    assert.deepEqual(executionRequest.execution_plan, {
      adapter: "generic_rest",
      operation: "rest.patch",
      target: { resource_ref: "item_123" },
      arguments: { fields: { status: "active" } },
    });
    assert.equal(executionRequest.runner_id, undefined);
    assert.equal(executionRequest.credential_ref, undefined);
  });

  it("allows per-call agent id override", async () => {
    const calls = recordFetchSequence([
      { action_id: "act_123", status: "validated" },
      { action_id: "act_123", status: "authorized", allowed: true, requires_approval: false },
    ]);

    await verifiedAction(
      {
        agentId: "agent_profile_override",
        contractVersion: "inventory.item.update/1.0",
        actionType: "inventory.item.update",
        operationKind: "UPDATE",
        executionRequest: {
          credentialPointer: "ops-default",
          executionPlan: {
            adapter: "generic_rest",
            operation: "rest.patch",
          },
        },
        idempotencyKey: "inventory_override",
      },
      { projectId: "proj_actions", apiKey: "zk_test", agentId: "agent_profile_default" },
    );

    const body = JSON.parse(calls[0].init?.body as string) as Record<string, unknown>;
    assert.equal(body.agent_id, "agent_profile_override");
  });

  it("raises with action and approval ids when approval is required", async () => {
    recordFetchSequence([
      { action_id: "act_pending", status: "validated" },
      {
        action_id: "act_pending",
        status: "approval_pending",
        allowed: false,
        requires_approval: true,
        runtime_policy_decision_id: "decision_pending",
      },
    ]);

    await assert.rejects(
      () =>
        verifiedAction(
          {
            contractVersion: "inventory.item.delete/1.0",
            actionType: "inventory.item.delete",
            operationKind: "UPDATE",
            executionRequest: {
              credentialPointer: "ops-default",
              executionPlan: {
                adapter: "generic_rest",
                operation: "rest.patch",
                target: { resource_ref: "item_123" },
              },
            },
            idempotencyKey: "inventory_item_123_delete",
          },
          { projectId: "proj_actions", apiKey: "zk_test" },
        ),
      (error: unknown) => {
        assert.ok(error instanceof ZrokyVerifiedActionApprovalRequired);
        assert.equal(error.actionId, "act_pending");
        assert.equal(error.approvalId, "decision_pending");
        assert.equal(error.decision.status, "approval_pending");
        return true;
      },
    );
  });

  it("rejects runner and protected credential pins before API calls", async () => {
    let called = false;
    globalThis.fetch = (() => {
      called = true;
      return Promise.reject(new Error("should not call fetch"));
    }) as typeof fetch;

    await assert.rejects(
      () =>
        verifiedAction(
          {
            contractVersion: "inventory.item.update/1.0",
            actionType: "inventory.item.update",
            operationKind: "UPDATE",
            executionRequest: {
              credentialPointer: "customer-runner-secret://ops/default",
              executionPlan: {
                adapter: "generic_rest",
                operation: "rest.patch",
                target: { resource_ref: "item_123" },
              },
            },
          },
          { projectId: "proj_actions", apiKey: "zk_test" },
        ),
      ZrokyVerifiedActionError,
    );
    assert.equal(called, false);
  });

  it("polls until terminal proof and fetches the receipt", async () => {
    const calls = recordFetchSequence([
      { action_id: "act_done", proof_status: "pending", receipt_status: "pending" },
      { action_id: "act_done", proof_status: "matched", receipt_status: "generated" },
      { receipt_id: "receipt_123", signature_valid: true, receipt: { final_status: "matched" } },
    ]);

    const proof = await awaitActionProof(
      "act_done",
      { timeoutMs: 500, pollIntervalMs: 50 },
      { projectId: "proj_actions", apiKey: "zk_test" },
    );

    assert.equal(proof.proofStatus, "matched");
    assert.equal(proof.receiptStatus, "generated");
    assert.equal(proof.signatureValid, true);
    assert.equal(proof.evidenceId, "receipt_123");
    assert.equal(calls.at(-1)?.input, "https://api.zroky.com/v1/action-intents/act_done/receipt");
  });
});
