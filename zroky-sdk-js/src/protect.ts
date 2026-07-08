// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import type { ZrokyConfig } from "./types";
import {
  awaitActionProof,
  verifiedAction,
  ZrokyVerifiedActionError,
  type ActionProofResult,
  type VerifiedActionDecision,
} from "./verified-action";

type JsonObject = Record<string, unknown>;

export interface ProtectOptions {
  action: string;
  params?: JsonObject;
  operationKind?: string;
  contractVersion?: string;
  verificationProfile?: string;
  executionRequest?: JsonObject;
  agentId?: string;
  environment?: string;
  principal?: JsonObject;
  actorChain?: JsonObject[];
  purpose?: JsonObject;
  resource?: JsonObject;
  traceContext?: JsonObject;
  deadline?: string | Date;
  idempotencyKey?: string;
  raiseOnApproval?: boolean;
  waitForReceipt?: boolean;
  proofTimeoutMs?: number;
  pollIntervalMs?: number;
}

export interface ProtectResult extends JsonObject {
  actionId: string;
  decision: VerifiedActionDecision;
  proof: ActionProofResult;
  receipt: JsonObject | null;
  proofStatus: string;
  receiptStatus: string;
  signatureValid: boolean | null;
  evidenceId: string | null;
}

function defaultContractVersion(action: string): string {
  return `${action}/1.0`;
}

export function protect(
  options: ProtectOptions & { waitForReceipt: true },
  config?: ZrokyConfig,
): Promise<ProtectResult>;
export function protect(
  options: ProtectOptions & { waitForReceipt?: false | undefined },
  config?: ZrokyConfig,
): Promise<VerifiedActionDecision>;
export async function protect(
  options: ProtectOptions,
  config: ZrokyConfig = {},
): Promise<VerifiedActionDecision | ProtectResult> {
  const action = options.action.trim();
  if (!action) {
    throw new ZrokyVerifiedActionError("[ZROKY] protect requires a non-empty action.");
  }

  const operationKind = (options.operationKind ?? "EXECUTE").trim().toUpperCase();
  if (!operationKind) {
    throw new ZrokyVerifiedActionError("[ZROKY] protect requires a non-empty operationKind.");
  }

  const decision = await verifiedAction(
    {
      agentId: options.agentId,
      contractVersion: options.contractVersion ?? defaultContractVersion(action),
      actionType: action,
      operationKind,
      environment: options.environment ?? "production",
      principal: options.principal,
      actorChain: options.actorChain,
      purpose: options.purpose,
      resource: options.resource,
      parameters: options.params,
      executionRequest: options.executionRequest,
      verificationProfile: options.verificationProfile,
      deadline: options.deadline,
      traceContext: options.traceContext,
      idempotencyKey: options.idempotencyKey,
      raiseOnApproval: options.raiseOnApproval,
    },
    config,
  );

  if (!options.waitForReceipt) {
    return decision;
  }

  const actionId = typeof decision.action_id === "string" ? decision.action_id : "";
  if (!actionId) {
    throw new ZrokyVerifiedActionError("[ZROKY] protect could not wait for receipt without action_id.", {
      decision,
    });
  }

  const proof = await awaitActionProof(
    actionId,
    {
      timeoutMs: options.proofTimeoutMs,
      pollIntervalMs: options.pollIntervalMs,
    },
    config,
  );

  return {
    actionId,
    decision,
    proof,
    receipt: proof.receipt,
    proofStatus: proof.proofStatus,
    receiptStatus: proof.receiptStatus,
    signatureValid: proof.signatureValid,
    evidenceId: proof.evidenceId,
  };
}
