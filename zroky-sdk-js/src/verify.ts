// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import { nodeEnv, resolveApiBase } from "./api";
import { resolveConfig } from "./config";
import type { ZrokyJsonValue, ZrokyRiskActionType } from "./contracts";
import type { ZrokyConfig } from "./types";

export type SavedVerificationConnector = "generic_rest" | "ledger_refund" | "crm_record";
export type OutcomeVerificationVerdict = "matched" | "mismatched" | "not_verified";

export interface OutcomeReconciliationView {
  id: string;
  project_id: string;
  call_id: string | null;
  trace_id: string | null;
  runtime_policy_decision_id: string | null;
  action_type: string | null;
  connector_type: string;
  system_ref: string | null;
  verdict: OutcomeVerificationVerdict;
  reason: string | null;
  amount_usd: number | null;
  currency: string | null;
  claimed: Record<string, unknown>;
  actual: Record<string, unknown> | null;
  comparison: Record<string, unknown>;
  idempotency_key: string | null;
  metadata: Record<string, unknown> | null;
  checked_at: string;
  created_at: string;
}

interface VerifyOutcomeBaseOptions {
  connector: SavedVerificationConnector;
  claimed: Record<string, unknown>;
  callId?: string;
  traceId?: string;
  runtimePolicyDecisionId?: string;
  actionType?: ZrokyRiskActionType | (string & {});
  systemRef?: string;
  matchFields?: string[];
  amountUsd?: number;
  currency?: string;
  idempotencyKey?: string;
  metadata?: Record<string, ZrokyJsonValue | unknown>;
}

export interface VerifyGenericRestOutcomeOptions extends VerifyOutcomeBaseOptions {
  connector: "generic_rest";
  recordRef: string;
}

export interface VerifyLedgerRefundOutcomeOptions extends VerifyOutcomeBaseOptions {
  connector: "ledger_refund";
  refundId?: string;
}

export interface VerifyCrmRecordOutcomeOptions extends VerifyOutcomeBaseOptions {
  connector: "crm_record";
  customerId?: string;
}

export type VerifyOutcomeOptions =
  | VerifyGenericRestOutcomeOptions
  | VerifyLedgerRefundOutcomeOptions
  | VerifyCrmRecordOutcomeOptions;

export class ZrokyOutcomeVerificationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ZrokyOutcomeVerificationError";
  }
}

function withoutUndefined(value: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined));
}

function endpointPath(connector: SavedVerificationConnector): string {
  switch (connector) {
    case "generic_rest":
      return "/v1/outcomes/reconciliation/generic-rest/saved";
    case "ledger_refund":
      return "/v1/outcomes/reconciliation/ledger-refund/saved";
    case "crm_record":
      return "/v1/outcomes/reconciliation/customer-record/saved";
  }
}

function connectorSpecificPayload(options: VerifyOutcomeOptions): Record<string, unknown> {
  switch (options.connector) {
    case "generic_rest":
      return { record_ref: options.recordRef };
    case "ledger_refund":
      return { refund_id: options.refundId };
    case "crm_record":
      return { customer_id: options.customerId };
  }
}

function verificationPayload(options: VerifyOutcomeOptions): Record<string, unknown> {
  return withoutUndefined({
    ...connectorSpecificPayload(options),
    call_id: options.callId,
    trace_id: options.traceId,
    runtime_policy_decision_id: options.runtimePolicyDecisionId,
    action_type: options.actionType,
    system_ref: options.systemRef,
    claimed: options.claimed,
    match_fields: options.matchFields,
    amount_usd: options.amountUsd,
    currency: options.currency,
    idempotency_key: options.idempotencyKey,
    metadata: options.metadata,
  });
}

/**
 * Verify an agent's claimed post-action outcome against a saved Zroky connector.
 *
 * This calls Zroky's saved connector runtime. Customer connector credentials stay
 * server-side; the SDK only sends the record reference and claimed outcome.
 */
export async function verifyOutcome(
  options: VerifyOutcomeOptions,
  config: ZrokyConfig = {},
): Promise<OutcomeReconciliationView> {
  const resolved = resolveConfig(config);
  if (resolved.disabled) {
    throw new ZrokyOutcomeVerificationError("[ZROKY] Outcome verification is disabled.");
  }

  const env = nodeEnv();
  const apiKey = resolved.apiKey ?? env?.["ZROKY_API_KEY"];
  const projectId = resolved.projectId ?? env?.["ZROKY_PROJECT_ID"] ?? env?.["ZROKY_PROJECT"];
  if (!apiKey || !projectId) {
    throw new ZrokyOutcomeVerificationError(
      "[ZROKY] Outcome verification requires apiKey and projectId.",
    );
  }

  const endpoint = resolveApiBase(resolved.endpoint ?? env?.["ZROKY_API_URL"] ?? env?.["ZROKY_ENDPOINT"]);
  const url = `${endpoint}${endpointPath(options.connector)}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": apiKey,
        "x-project-id": projectId,
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify(verificationPayload(options)),
    });
  } catch (error) {
    throw new ZrokyOutcomeVerificationError(
      `[ZROKY] Outcome verification unavailable: ${String(
        (error as { message?: unknown })?.message ?? error,
      )}`,
    );
  }

  if (!response.ok) {
    throw new ZrokyOutcomeVerificationError(
      `[ZROKY] Outcome verification failed with HTTP ${response.status}.`,
    );
  }

  try {
    return (await response.json()) as OutcomeReconciliationView;
  } catch (error) {
    throw new ZrokyOutcomeVerificationError(
      `[ZROKY] Outcome verification returned invalid JSON: ${String(
        (error as { message?: unknown })?.message ?? error,
      )}`,
    );
  }
}
