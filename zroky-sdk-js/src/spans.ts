// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import { resolveConfig } from "./config";
import { emit } from "./emitter";
import { promptFingerprint } from "./fingerprint";
import { newCallId, newEventId } from "./ids";
import type { ZrokyConfig } from "./types";

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
