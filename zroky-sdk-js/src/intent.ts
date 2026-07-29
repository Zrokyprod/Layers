// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import { apiUrl, nodeEnv } from "./api";
import { resolveConfig } from "./config";
import {
  ZrokyRuntimePolicyApprovalRequired,
  ZrokyRuntimePolicyBlocked,
  ZrokyRuntimePolicyError,
  type RuntimePolicyDecision,
} from "./guard";
import type { ZrokyConfig } from "./types";

type JsonObject = Record<string, unknown>;

export interface PreExecutionGuardOptions {
  intent: JsonObject;
  environment?: string;
  agentRef?: string;
  idempotencyKey?: string;
}

export interface PreExecutionGuardResult {
  intent: JsonObject;
  policy: RuntimePolicyDecision;
}

function headers(apiKey: string, projectId: string, idempotencyKey?: string): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "x-api-key": apiKey,
    "x-project-id": projectId,
    Authorization: `Bearer ${apiKey}`,
    ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
  };
}

export async function preExecutionGuard(
  options: PreExecutionGuardOptions,
  config: ZrokyConfig = {},
): Promise<PreExecutionGuardResult> {
  const resolved = resolveConfig(config);
  const env = nodeEnv();
  const apiKey = resolved.apiKey ?? env?.["ZROKY_API_KEY"];
  const projectId = resolved.projectId ?? env?.["ZROKY_PROJECT_ID"] ?? env?.["ZROKY_PROJECT"];
  if (!apiKey || !projectId) {
    throw new ZrokyRuntimePolicyError("[ZROKY] Pre-execution guard requires apiKey and projectId.");
  }

  const key = options.idempotencyKey ?? crypto.randomUUID();
  const endpoint = resolved.endpoint ?? env?.["ZROKY_API_URL"] ?? env?.["ZROKY_ENDPOINT"];
  const intentResponse = await fetch(apiUrl(endpoint, "/v1/intents"), {
    method: "POST",
    headers: headers(apiKey, projectId, key),
    body: JSON.stringify({
      environment: options.environment ?? "production",
      agent_ref: options.agentRef,
      intent: options.intent,
    }),
  });
  if (!intentResponse.ok) {
    throw new ZrokyRuntimePolicyError(`[ZROKY] Trusted intent failed with HTTP ${intentResponse.status}.`);
  }
  const createdIntent = (await intentResponse.json()) as JsonObject;

  const policyResponse = await fetch(apiUrl(endpoint, "/v1/policy/check"), {
    method: "POST",
    headers: headers(apiKey, projectId),
    body: JSON.stringify({ intent_id: createdIntent.id }),
  });
  if (!policyResponse.ok) {
    throw new ZrokyRuntimePolicyError(`[ZROKY] Policy check failed with HTTP ${policyResponse.status}.`);
  }
  const policy = (await policyResponse.json()) as RuntimePolicyDecision;
  if (policy.decision === "allow") {
    return { intent: createdIntent, policy };
  }
  if (policy.decision === "approval_required") {
    throw new ZrokyRuntimePolicyApprovalRequired("[ZROKY] Pre-execution guard requires approval.", policy);
  }
  throw new ZrokyRuntimePolicyBlocked("[ZROKY] Pre-execution guard did not allow action.", policy);
}
