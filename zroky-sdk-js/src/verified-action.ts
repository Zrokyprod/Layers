// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import { apiUrl, nodeEnv } from "./api";
import { resolveConfig } from "./config";
import type { ZrokyConfig } from "./types";

type JsonObject = Record<string, unknown>;

const TERMINAL_PROOF_STATUSES = new Set(["matched", "mismatched", "not_verified"]);
const TERMINAL_RECEIPT_STATUSES = new Set(["generated", "failed"]);

const FORBIDDEN_EXECUTION_REQUEST_KEYS = new Set([
  "runner_id",
  "runner",
  "credential_ref",
  "credential_reference",
  "protected_credential_ref",
]);
const RAW_SECRET_KEY_MARKERS = [
  "authorization",
  "bearer_token",
  "api_key",
  "apikey",
  "password",
  "secret",
  "token",
];
const RAW_SECRET_VALUE_MARKERS = [
  "bearer ",
  "sk_live_",
  "sk_test_",
  "xoxb-",
  "xoxp-",
  "ghp_",
  "gho_",
  "github_pat_",
  "-----begin private key-----",
];

export interface VerifiedActionOptions {
  agentId?: string;
  contractVersion: string;
  actionType: string;
  operationKind: string;
  environment?: string;
  principal?: JsonObject;
  actorChain?: JsonObject[];
  purpose?: JsonObject;
  resource?: JsonObject;
  parameters?: JsonObject;
  executionRequest?: JsonObject;
  verificationProfile?: string;
  deadline?: string | Date;
  traceContext?: JsonObject;
  idempotencyKey?: string;
  raiseOnApproval?: boolean;
}

export interface VerifiedActionDecision extends JsonObject {
  action_id?: string;
  status?: string;
  allowed?: boolean;
  requires_approval?: boolean;
  runtime_policy_decision_id?: string | null;
}

export interface AwaitActionProofOptions {
  timeoutMs?: number;
  pollIntervalMs?: number;
}

export interface ActionProofResult {
  actionId: string;
  action: JsonObject;
  receipt: JsonObject | null;
  proofStatus: string;
  receiptStatus: string;
  signatureValid: boolean | null;
  evidenceId: string | null;
}

export class ZrokyVerifiedActionError extends Error {
  action: JsonObject;
  decision: JsonObject;

  constructor(message: string, options: { action?: JsonObject; decision?: JsonObject } = {}) {
    super(message);
    this.name = "ZrokyVerifiedActionError";
    this.action = options.action ?? {};
    this.decision = options.decision ?? {};
  }
}

export class ZrokyVerifiedActionBlocked extends ZrokyVerifiedActionError {
  constructor(message: string, options: { action?: JsonObject; decision?: JsonObject } = {}) {
    super(message, options);
    this.name = "ZrokyVerifiedActionBlocked";
  }
}

export class ZrokyVerifiedActionApprovalRequired extends ZrokyVerifiedActionBlocked {
  actionId?: string;
  approvalId?: string;

  constructor(action: JsonObject, decision: JsonObject) {
    super("[ZROKY] verified action requires approval before execution.", { action, decision });
    this.name = "ZrokyVerifiedActionApprovalRequired";
    this.actionId = text(action.action_id ?? decision.action_id);
    this.approvalId = text(
      decision.runtime_policy_decision_id ??
        decision.id ??
        (isRecord(decision.approval_queue_item)
          ? decision.approval_queue_item.id
          : undefined),
    );
  }
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function isRecord(value: unknown): value is JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function withoutUndefined(value: JsonObject): JsonObject {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined));
}

function deadlineValue(value: string | Date | undefined): string | undefined {
  if (value instanceof Date) {
    return value.toISOString();
  }
  return value;
}

function defaultIdempotencyKey(): string {
  const maybeCrypto = globalThis.crypto as { randomUUID?: () => string } | undefined;
  const random = maybeCrypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `zroky-sdk:${random}`;
}

function findExecutionRequestViolation(value: unknown, keyPath: string[] = []): string | undefined {
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      const found = findExecutionRequestViolation(value[index], [...keyPath, String(index)]);
      if (found) return found;
    }
    return undefined;
  }
  if (isRecord(value)) {
    for (const [key, nested] of Object.entries(value)) {
      const keyText = key.trim().toLowerCase();
      if (FORBIDDEN_EXECUTION_REQUEST_KEYS.has(keyText)) {
        return [...keyPath, key].join(".");
      }
      if (RAW_SECRET_KEY_MARKERS.some((marker) => keyText.includes(marker))) {
        return [...keyPath, key].join(".");
      }
      const found = findExecutionRequestViolation(nested, [...keyPath, key]);
      if (found) return found;
    }
    return undefined;
  }
  if (typeof value === "string") {
    const lowered = value.trim().toLowerCase();
    if (RAW_SECRET_VALUE_MARKERS.some((marker) => lowered.includes(marker))) {
      return keyPath.join(".") || "execution_request";
    }
  }
  return undefined;
}

function validateExecutionRequest(value: JsonObject | undefined): JsonObject | undefined {
  if (value === undefined) {
    return undefined;
  }
  const { executionPlan, credentialPointer, ...rest } = value;
  const normalized: JsonObject = {
    ...rest,
    execution_plan: value.execution_plan ?? executionPlan,
    credential_pointer: value.credential_pointer ?? credentialPointer,
  };
  if (!isRecord(normalized.execution_plan) || Object.keys(normalized.execution_plan).length === 0) {
    throw new ZrokyVerifiedActionError("[ZROKY] executionRequest.executionPlan must be a non-empty object.");
  }
  if (typeof normalized.credential_pointer === "string" && normalized.credential_pointer.includes("://")) {
    throw new ZrokyVerifiedActionError("[ZROKY] executionRequest.credentialPointer must be a non-secret alias.");
  }
  if (isRecord(normalized.credential) && typeof normalized.credential.pointer === "string" && normalized.credential.pointer.includes("://")) {
    throw new ZrokyVerifiedActionError("[ZROKY] executionRequest.credential.pointer must be a non-secret alias.");
  }
  const violation = findExecutionRequestViolation(normalized);
  if (violation) {
    throw new ZrokyVerifiedActionError(
      `[ZROKY] executionRequest must not include runner pins, protected credential refs, or raw secret material at ${violation}.`,
    );
  }
  return withoutUndefined(normalized);
}

function credentials(config: ZrokyConfig): { apiKey: string; projectId: string; endpoint?: string } {
  const env = nodeEnv();
  const apiKey = config.apiKey ?? env?.["ZROKY_API_KEY"];
  const projectId = config.projectId ?? env?.["ZROKY_PROJECT_ID"];
  if (!apiKey || !projectId) {
    throw new ZrokyVerifiedActionError("[ZROKY] verifiedAction requires apiKey and projectId.");
  }
  return { apiKey, projectId, endpoint: config.endpoint ?? env?.["ZROKY_ENDPOINT"] };
}

async function requestJson(
  method: string,
  path: string,
  config: ZrokyConfig,
  options: { body?: JsonObject; idempotencyKey?: string } = {},
): Promise<JsonObject> {
  const { apiKey, projectId, endpoint } = credentials(config);
  let response: Response;
  try {
    response = await fetch(apiUrl(endpoint, path), {
      method,
      headers: withoutUndefined({
        "Content-Type": "application/json",
        "x-api-key": apiKey,
        "x-project-id": projectId,
        Authorization: `Bearer ${apiKey}`,
        "Idempotency-Key": options.idempotencyKey,
      }) as Record<string, string>,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch (error) {
    throw new ZrokyVerifiedActionError(
      `[ZROKY] verified action API unavailable: ${String((error as { message?: unknown })?.message ?? error)}`,
    );
  }
  if (!response.ok) {
    throw new ZrokyVerifiedActionError(`[ZROKY] verified action API failed with HTTP ${response.status}.`);
  }
  try {
    const payload = (await response.json()) as unknown;
    if (!isRecord(payload)) {
      throw new Error("non-object response");
    }
    return payload;
  } catch (error) {
    throw new ZrokyVerifiedActionError(
      `[ZROKY] verified action API returned invalid JSON: ${String((error as { message?: unknown })?.message ?? error)}`,
    );
  }
}

function requiresApproval(decision: JsonObject): boolean {
  return decision.requires_approval === true || decision.status === "approval_pending";
}

function blocked(decision: JsonObject): boolean {
  return decision.allowed === false && !requiresApproval(decision);
}

export async function verifiedAction(
  options: VerifiedActionOptions,
  config: ZrokyConfig = {},
): Promise<VerifiedActionDecision> {
  const resolved = resolveConfig(config);
  const executionRequest = validateExecutionRequest(options.executionRequest);
  const action = await requestJson(
    "POST",
    "/v1/action-intents",
    resolved,
    {
      idempotencyKey: options.idempotencyKey ?? defaultIdempotencyKey(),
      body: withoutUndefined({
        agent_id: options.agentId ?? resolved.agentId,
        contract_version: options.contractVersion,
        action_type: options.actionType,
        operation_kind: options.operationKind,
        environment: options.environment ?? "production",
        principal: options.principal ?? {},
        actor_chain: options.actorChain ?? [],
        purpose: options.purpose ?? {},
        resource: options.resource ?? {},
        parameters: options.parameters ?? {},
        execution_request: executionRequest,
        verification_profile: options.verificationProfile,
        deadline: deadlineValue(options.deadline),
        trace_context: options.traceContext,
      }),
    },
  );
  const actionId = text(action.action_id);
  if (!actionId) {
    throw new ZrokyVerifiedActionError("[ZROKY] verified action create response did not include action_id.", { action });
  }

  const decision = await requestJson("POST", `/v1/action-intents/${actionId}/decide`, resolved, { body: {} });
  if (requiresApproval(decision)) {
    if (options.raiseOnApproval === false) {
      return decision as VerifiedActionDecision;
    }
    throw new ZrokyVerifiedActionApprovalRequired(action, decision);
  }
  if (blocked(decision)) {
    throw new ZrokyVerifiedActionBlocked("[ZROKY] verified action was blocked by policy.", { action, decision });
  }
  return decision as VerifiedActionDecision;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    globalThis.setTimeout(resolve, ms);
  });
}

export async function awaitActionProof(
  actionId: string,
  options: AwaitActionProofOptions = {},
  config: ZrokyConfig = {},
): Promise<ActionProofResult> {
  const resolved = resolveConfig(config);
  const timeoutMs = Math.max(100, options.timeoutMs ?? 120_000);
  const pollIntervalMs = Math.max(50, options.pollIntervalMs ?? 2_000);
  const deadline = Date.now() + timeoutMs;
  let lastAction: JsonObject | undefined;

  while (Date.now() < deadline) {
    const action = await requestJson("GET", `/v1/action-intents/${actionId}`, resolved);
    lastAction = action;
    const proofStatus = String(action.proof_status ?? "");
    const receiptStatus = String(action.receipt_status ?? "");
    if (TERMINAL_PROOF_STATUSES.has(proofStatus) && TERMINAL_RECEIPT_STATUSES.has(receiptStatus)) {
      const receipt =
        receiptStatus === "generated"
          ? await requestJson("GET", `/v1/action-intents/${actionId}/receipt`, resolved)
          : null;
      return {
        actionId,
        action,
        receipt,
        proofStatus,
        receiptStatus,
        signatureValid: typeof receipt?.signature_valid === "boolean" ? receipt.signature_valid : null,
        evidenceId: typeof receipt?.receipt_id === "string" ? receipt.receipt_id : null,
      };
    }
    await delay(pollIntervalMs);
  }

  throw new ZrokyVerifiedActionError("[ZROKY] timed out waiting for verified action proof.", {
    action: lastAction,
  });
}
