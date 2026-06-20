// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import { nodeEnv, runtimePolicyUrl } from "./api";
import { resolveConfig } from "./config";
import { maskPayload } from "./pii";
import type { ZrokyConfig } from "./types";

export interface GuardOptions {
  actionType: string;
  toolName?: string;
  toolArgs?: Record<string, unknown> | unknown[] | string;
  traceId?: string;
  spanId?: string;
  callId?: string;
  agentName?: string;
  role?: string;
  toolCallCount?: number;
  retryCount?: number;
  estimatedCostUsd?: number;
  inputText?: string;
  userInput?: string;
  outputText?: string;
  externalAction?: boolean;
  promptInjectionDetected?: boolean;
  piiDetected?: boolean;
  approvalId?: string;
  businessImpact?: Record<string, unknown> | string;
  businessImpactSummary?: string;
  impactUsd?: number;
  customerId?: string;
  accountId?: string;
  orderId?: string;
  resourceId?: string;
  metadata?: Record<string, unknown>;
}

export interface RuntimePolicyDecision {
  id?: string;
  allowed?: boolean;
  status?: string;
  requires_approval?: boolean;
  approval_queue_item?: RuntimePolicyDecision | null;
  expires_at?: string | null;
  reasons?: unknown;
  [key: string]: unknown;
}

export class ZrokyRuntimePolicyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ZrokyRuntimePolicyError";
  }
}

export class ZrokyRuntimePolicyBlocked extends ZrokyRuntimePolicyError {
  decision: RuntimePolicyDecision;

  constructor(message: string, decision: RuntimePolicyDecision) {
    super(message);
    this.name = "ZrokyRuntimePolicyBlocked";
    this.decision = decision;
  }
}

export class ZrokyRuntimePolicyApprovalRequired extends ZrokyRuntimePolicyBlocked {
  approvalId?: string;
  expiresAt?: string;

  constructor(message: string, decision: RuntimePolicyDecision) {
    super(message, decision);
    this.name = "ZrokyRuntimePolicyApprovalRequired";
    this.approvalId = approvalIdFromDecision(decision);
    this.expiresAt = expiresAtFromDecision(decision);
  }
}

function hasPiiChange(before: unknown, after: unknown): boolean {
  return JSON.stringify(before) !== JSON.stringify(after);
}

function withoutUndefined(value: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined));
}

function reasonText(decision: RuntimePolicyDecision): string {
  const reasons = Array.isArray(decision.reasons) ? decision.reasons : [];
  const rendered = reasons.map((item) => String(item)).filter(Boolean).join(", ");
  return rendered || "runtime policy did not allow action";
}

function approvalIdFromDecision(decision: RuntimePolicyDecision): string | undefined {
  const queueItem = decision.approval_queue_item;
  if (queueItem && typeof queueItem.id === "string" && queueItem.id.length > 0) {
    return queueItem.id;
  }
  return typeof decision.id === "string" && decision.id.length > 0 ? decision.id : undefined;
}

function expiresAtFromDecision(decision: RuntimePolicyDecision): string | undefined {
  if (typeof decision.expires_at === "string" && decision.expires_at.length > 0) {
    return decision.expires_at;
  }
  const queueItem = decision.approval_queue_item;
  if (queueItem && typeof queueItem.expires_at === "string" && queueItem.expires_at.length > 0) {
    return queueItem.expires_at;
  }
  return undefined;
}

function requiresApproval(decision: RuntimePolicyDecision): boolean {
  return decision.requires_approval === true || decision.status === "pending_approval";
}

export async function guard(
  options: GuardOptions,
  config: ZrokyConfig = {},
): Promise<RuntimePolicyDecision> {
  const resolved = resolveConfig(config);
  if (resolved.disabled) {
    throw new ZrokyRuntimePolicyError("[ZROKY] Runtime policy guard is disabled.");
  }

  const env = nodeEnv();
  const apiKey = resolved.apiKey ?? env?.["ZROKY_API_KEY"];
  const projectId = resolved.projectId ?? env?.["ZROKY_PROJECT_ID"];
  if (!apiKey || !projectId) {
    throw new ZrokyRuntimePolicyError(
      "[ZROKY] Runtime policy guard requires apiKey and projectId.",
    );
  }

  const masked = {
    toolArgs: maskPayload(options.toolArgs),
    inputText: maskPayload(options.inputText),
    userInput: maskPayload(options.userInput),
    outputText: maskPayload(options.outputText),
    businessImpact: maskPayload(options.businessImpact),
    businessImpactSummary: maskPayload(options.businessImpactSummary),
    customerId: maskPayload(options.customerId),
    accountId: maskPayload(options.accountId),
    orderId: maskPayload(options.orderId),
    resourceId: maskPayload(options.resourceId),
    metadata: maskPayload(options.metadata),
  };
  const piiDetected =
    options.piiDetected ??
    hasPiiChange(
      [
        options.toolArgs,
        options.inputText,
        options.userInput,
        options.outputText,
        options.businessImpact,
        options.businessImpactSummary,
        options.customerId,
        options.accountId,
        options.orderId,
        options.resourceId,
        options.metadata,
      ],
      [
        masked.toolArgs,
        masked.inputText,
        masked.userInput,
        masked.outputText,
        masked.businessImpact,
        masked.businessImpactSummary,
        masked.customerId,
        masked.accountId,
        masked.orderId,
        masked.resourceId,
        masked.metadata,
      ],
    );

  const payload = withoutUndefined({
    action_type: options.actionType,
    tool_name: options.toolName,
    tool_args: masked.toolArgs,
    trace_id: options.traceId ?? resolved.traceId,
    span_id: options.spanId,
    call_id: options.callId,
    agent_name: options.agentName ?? resolved.agentName,
    role: options.role,
    tool_call_count: options.toolCallCount,
    retry_count: options.retryCount,
    estimated_cost_usd: options.estimatedCostUsd,
    input_text: masked.inputText,
    user_input: masked.userInput,
    output_text: masked.outputText,
    external_action: options.externalAction,
    prompt_injection_detected: options.promptInjectionDetected,
    pii_detected: piiDetected || undefined,
    approval_id: options.approvalId,
    business_impact: masked.businessImpact,
    business_impact_summary: masked.businessImpactSummary,
    impact_usd: options.impactUsd,
    customer_id: masked.customerId,
    account_id: masked.accountId,
    order_id: masked.orderId,
    resource_id: masked.resourceId,
    metadata: masked.metadata,
  });

  let response: Response;
  try {
    response = await fetch(runtimePolicyUrl(resolved.endpoint ?? env?.["ZROKY_ENDPOINT"]), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": apiKey,
        "x-project-id": projectId,
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    throw new ZrokyRuntimePolicyError(
      `[ZROKY] Runtime policy guard unavailable: ${String(
        (error as { message?: unknown })?.message ?? error,
      )}`,
    );
  }

  if (!response.ok) {
    throw new ZrokyRuntimePolicyError(
      `[ZROKY] Runtime policy guard failed with HTTP ${response.status}.`,
    );
  }

  let decision: RuntimePolicyDecision;
  try {
    decision = (await response.json()) as RuntimePolicyDecision;
  } catch (error) {
    throw new ZrokyRuntimePolicyError(
      `[ZROKY] Runtime policy guard returned invalid JSON: ${String(
        (error as { message?: unknown })?.message ?? error,
      )}`,
    );
  }

  if (decision.allowed !== true) {
    if (requiresApproval(decision)) {
      throw new ZrokyRuntimePolicyApprovalRequired(
        `[ZROKY] Runtime policy requires approval: ${reasonText(decision)}`,
        decision,
      );
    }
    throw new ZrokyRuntimePolicyBlocked(
      `[ZROKY] Runtime policy blocked action: ${reasonText(decision)}`,
      decision,
    );
  }

  return decision;
}
