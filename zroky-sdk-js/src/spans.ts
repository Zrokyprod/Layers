// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import { resolveConfig } from "./config";
import { emit } from "./emitter";
import { promptFingerprint } from "./fingerprint";
import { newCallId, newEventId } from "./ids";
import type { ZrokyConfig } from "./types";
import { versionMetadata } from "./versions";

type CaptureStatus = "success" | "error";

export interface RetrievedDocument {
  id?: string;
  title?: string;
  source?: string;
  score?: number;
  metadata?: Record<string, unknown>;
  contentPreview?: string;
}

export interface RetrievalCaptureOptions {
  query: string;
  indexName?: string;
  retrieverVersion?: string;
  documents?: RetrievedDocument[];
  latencyMs?: number;
  status?: CaptureStatus;
  errorCode?: string;
  errorMessage?: string;
  callId?: string;
  traceId?: string;
  parentCallId?: string;
  sessionId?: string;
  workflowId?: string;
  workflowName?: string;
  promptVersion?: string;
  stepIndex?: number;
  userId?: string;
  environment?: string;
  metadata?: Record<string, unknown>;
}

export interface MemoryCaptureOptions {
  operation: "read" | "write" | "update" | "delete" | "search" | "summarize";
  namespace?: string;
  keys?: string[];
  itemCount?: number;
  bytes?: number;
  valuePreview?: string;
  latencyMs?: number;
  status?: CaptureStatus;
  errorCode?: string;
  errorMessage?: string;
  callId?: string;
  traceId?: string;
  parentCallId?: string;
  sessionId?: string;
  workflowId?: string;
  workflowName?: string;
  promptVersion?: string;
  stepIndex?: number;
  userId?: string;
  environment?: string;
  metadata?: Record<string, unknown>;
}

export interface ToolCaptureOptions {
  name: string;
  arguments?: Record<string, unknown>;
  result?: unknown;
  errorMessage?: string;
  latencyMs?: number;
  callId?: string;
  traceId?: string;
  parentCallId?: string;
  stepIndex?: number;
  userId?: string;
  environment?: string;
  metadata?: Record<string, unknown>;
}

export interface PolicyDecisionCaptureOptions {
  name: string;
  decision: string;
  reason?: string;
  inputs?: Record<string, unknown>;
  evidence?: Record<string, unknown>;
  latencyMs?: number;
  callId?: string;
  traceId?: string;
  parentCallId?: string;
  stepIndex?: number;
  userId?: string;
  environment?: string;
  metadata?: Record<string, unknown>;
}

export interface HandoffCaptureOptions {
  fromAgent: string;
  toAgent: string;
  reason?: string;
  payload?: Record<string, unknown>;
  latencyMs?: number;
  callId?: string;
  traceId?: string;
  parentCallId?: string;
  stepIndex?: number;
  userId?: string;
  environment?: string;
  metadata?: Record<string, unknown>;
}

function compactDocuments(documents: RetrievedDocument[] | undefined): RetrievedDocument[] | undefined {
  if (!documents?.length) return undefined;
  return documents.slice(0, 20).map((doc) => ({
    id: doc.id,
    title: doc.title,
    source: doc.source,
    score: doc.score,
    metadata: doc.metadata,
    contentPreview: doc.contentPreview?.slice(0, 500),
  }));
}

function documentSummary(documents: RetrievedDocument[] | undefined): string | undefined {
  if (!documents?.length) return undefined;
  return documents
    .slice(0, 20)
    .map((doc) => doc.id ?? doc.title ?? doc.source)
    .filter((value): value is string => Boolean(value))
    .join("\n")
    .slice(0, 4000);
}

export async function captureRetrieval(
  options: RetrievalCaptureOptions,
  config: ZrokyConfig = {},
): Promise<string> {
  const resolvedConfig = resolveConfig(config);
  const callId = options.callId ?? newCallId();
  const documents = compactDocuments(options.documents);

  await emit(
    {
      schema_version: "v2",
      call_id: callId,
      event_id: newEventId(callId),
      provider: "retrieval",
      model: options.indexName ?? "unknown",
      call_type: "retrieval",
      latency_ms: options.latencyMs ?? 0,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      status: options.status ?? (options.errorMessage ? "error" : "success"),
      error_code: options.errorCode,
      error_message: options.errorMessage,
      prompt_fingerprint: promptFingerprint(options.query),
      retrieval: {
        query: options.query,
        index_name: options.indexName,
        retriever_version: options.retrieverVersion,
        documents,
        result_count: documents?.length ?? 0,
      },
      agent_name: resolvedConfig.agentName,
      agent_framework: resolvedConfig.agentFramework,
      session_id: options.sessionId ?? resolvedConfig.sessionId,
      workflow_id: options.workflowId ?? resolvedConfig.workflowId,
      workflow_name: options.workflowName ?? resolvedConfig.workflowName,
      prompt_version: options.promptVersion ?? resolvedConfig.promptVersion,
      trace_id: options.traceId ?? resolvedConfig.traceId,
      parent_call_id: options.parentCallId ?? resolvedConfig.parentCallId,
      span_type: "retrieval",
      span_name: options.indexName ?? "retrieval",
      span_index: options.stepIndex ?? resolvedConfig.stepIndex,
      input: { query: options.query },
      versions: versionMetadata(resolvedConfig, options.indexName ?? "unknown"),
      user_id: options.userId ?? resolvedConfig.userId,
      environment: options.environment ?? resolvedConfig.environment,
      step_index: options.stepIndex ?? resolvedConfig.stepIndex,
      output_content: documentSummary(options.documents),
      metadata: {
        ...(resolvedConfig.metadata ?? {}),
        ...(options.metadata ?? {}),
        span_type: "retrieval",
        index_name: options.indexName,
        retriever_version: options.retrieverVersion,
        result_count: documents?.length ?? 0,
        documents,
      },
    },
    resolvedConfig,
  );

  return callId;
}

export async function captureMemory(options: MemoryCaptureOptions, config: ZrokyConfig = {}): Promise<string> {
  const resolvedConfig = resolveConfig(config);
  const callId = options.callId ?? newCallId();
  const keys = options.keys?.slice(0, 50);
  const namespace = options.namespace ?? "memory";

  await emit(
    {
      schema_version: "v2",
      call_id: callId,
      event_id: newEventId(callId),
      provider: "memory",
      model: namespace,
      call_type: "memory",
      latency_ms: options.latencyMs ?? 0,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      status: options.status ?? (options.errorMessage ? "error" : "success"),
      error_code: options.errorCode,
      error_message: options.errorMessage,
      prompt_fingerprint: promptFingerprint(
        [options.operation, namespace, ...(keys ?? []).slice().sort()].join(":"),
      ),
      agent_name: resolvedConfig.agentName,
      agent_framework: resolvedConfig.agentFramework,
      session_id: options.sessionId ?? resolvedConfig.sessionId,
      workflow_id: options.workflowId ?? resolvedConfig.workflowId,
      workflow_name: options.workflowName ?? resolvedConfig.workflowName,
      prompt_version: options.promptVersion ?? resolvedConfig.promptVersion,
      trace_id: options.traceId ?? resolvedConfig.traceId,
      parent_call_id: options.parentCallId ?? resolvedConfig.parentCallId,
      span_type: "memory",
      span_name: `${options.operation}:${namespace}`,
      span_index: options.stepIndex ?? resolvedConfig.stepIndex,
      input: { operation: options.operation, namespace, keys },
      memory: {
        operation: options.operation,
        namespace,
        keys,
        item_count: options.itemCount,
        bytes: options.bytes,
        value_preview: options.valuePreview,
      },
      versions: versionMetadata(resolvedConfig),
      user_id: options.userId ?? resolvedConfig.userId,
      environment: options.environment ?? resolvedConfig.environment,
      step_index: options.stepIndex ?? resolvedConfig.stepIndex,
      output_content: options.valuePreview?.slice(0, 4000),
      metadata: {
        ...(resolvedConfig.metadata ?? {}),
        ...(options.metadata ?? {}),
        span_type: "memory",
        operation: options.operation,
        namespace,
        keys,
        item_count: options.itemCount,
        bytes: options.bytes,
      },
    },
    resolvedConfig,
  );

  return callId;
}

export async function captureToolCall(options: ToolCaptureOptions, config: ZrokyConfig = {}): Promise<string> {
  const resolvedConfig = resolveConfig(config);
  const callId = options.callId ?? newCallId();
  await emit(
    {
      schema_version: "v2",
      call_id: callId,
      event_id: newEventId(callId),
      provider: "tool",
      model: options.name,
      call_type: "tool_call",
      latency_ms: options.latencyMs ?? 0,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      status: options.errorMessage ? "error" : "success",
      error_code: options.errorMessage ? "TOOL_ERROR" : undefined,
      error_message: options.errorMessage,
      agent_name: resolvedConfig.agentName,
      agent_framework: resolvedConfig.agentFramework,
      prompt_version: resolvedConfig.promptVersion,
      trace_id: options.traceId ?? resolvedConfig.traceId,
      parent_call_id: options.parentCallId ?? resolvedConfig.parentCallId,
      span_type: "tool_call",
      span_name: options.name,
      span_index: options.stepIndex ?? resolvedConfig.stepIndex,
      input: { arguments: options.arguments },
      tool: { name: options.name, arguments: options.arguments, result: options.result, error: options.errorMessage },
      versions: versionMetadata(resolvedConfig),
      user_id: options.userId ?? resolvedConfig.userId,
      environment: options.environment ?? resolvedConfig.environment,
      step_index: options.stepIndex ?? resolvedConfig.stepIndex,
      metadata: { ...(resolvedConfig.metadata ?? {}), ...(options.metadata ?? {}) },
    },
    resolvedConfig,
  );
  return callId;
}

export async function capturePolicyDecision(
  options: PolicyDecisionCaptureOptions,
  config: ZrokyConfig = {},
): Promise<string> {
  const resolvedConfig = resolveConfig(config);
  const callId = options.callId ?? newCallId();
  await emit(
    {
      schema_version: "v2",
      call_id: callId,
      event_id: newEventId(callId),
      provider: "policy",
      model: options.name,
      call_type: "policy_decision",
      latency_ms: options.latencyMs ?? 0,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      status: "success",
      agent_name: resolvedConfig.agentName,
      agent_framework: resolvedConfig.agentFramework,
      prompt_version: resolvedConfig.promptVersion,
      trace_id: options.traceId ?? resolvedConfig.traceId,
      parent_call_id: options.parentCallId ?? resolvedConfig.parentCallId,
      span_type: "policy",
      span_name: options.name,
      span_index: options.stepIndex ?? resolvedConfig.stepIndex,
      input: { inputs: options.inputs },
      policy: {
        name: options.name,
        decision: options.decision,
        reason: options.reason,
        inputs: options.inputs,
        evidence: options.evidence,
      },
      versions: versionMetadata(resolvedConfig),
      user_id: options.userId ?? resolvedConfig.userId,
      environment: options.environment ?? resolvedConfig.environment,
      step_index: options.stepIndex ?? resolvedConfig.stepIndex,
      metadata: { ...(resolvedConfig.metadata ?? {}), ...(options.metadata ?? {}) },
    },
    resolvedConfig,
  );
  return callId;
}

export async function captureHandoff(options: HandoffCaptureOptions, config: ZrokyConfig = {}): Promise<string> {
  const resolvedConfig = resolveConfig(config);
  const callId = options.callId ?? newCallId();
  await emit(
    {
      schema_version: "v2",
      call_id: callId,
      event_id: newEventId(callId),
      provider: "handoff",
      model: `${options.fromAgent}->${options.toAgent}`,
      call_type: "handoff",
      latency_ms: options.latencyMs ?? 0,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      status: "success",
      agent_name: options.fromAgent,
      agent_framework: resolvedConfig.agentFramework,
      prompt_version: resolvedConfig.promptVersion,
      trace_id: options.traceId ?? resolvedConfig.traceId,
      parent_call_id: options.parentCallId ?? resolvedConfig.parentCallId,
      span_type: "handoff",
      span_name: `${options.fromAgent} to ${options.toAgent}`,
      span_index: options.stepIndex ?? resolvedConfig.stepIndex,
      input: { payload: options.payload },
      handoff: {
        from_agent: options.fromAgent,
        to_agent: options.toAgent,
        reason: options.reason,
        payload: options.payload,
      },
      versions: versionMetadata(resolvedConfig),
      user_id: options.userId ?? resolvedConfig.userId,
      environment: options.environment ?? resolvedConfig.environment,
      step_index: options.stepIndex ?? resolvedConfig.stepIndex,
      metadata: { ...(resolvedConfig.metadata ?? {}), ...(options.metadata ?? {}) },
    },
    resolvedConfig,
  );
  return callId;
}
