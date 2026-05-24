// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

export interface ZrokyConfig {
  projectId?: string;
  apiKey?: string;
  endpoint?: string;
  agentName?: string;
  agentFramework?: string;
  sessionId?: string;
  workflowId?: string;
  workflowName?: string;
  promptVersion?: string;
  traceId?: string;
  parentCallId?: string;
  userId?: string;
  environment?: string;
  stepIndex?: number;
  metadata?: Record<string, unknown>;
  disabled?: boolean;
}

export interface CapturePayload {
  schema_version?: "v2";
  call_id: string;
  event_id?: string;
  request_id?: string;
  provider: string;
  model: string;
  call_type: string;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  /** @deprecated Use completion_tokens. Accepted only for legacy callers. */
  output_tokens?: number;
  total_tokens: number;
  status: "success" | "error";
  error_code?: string;
  error_message?: string;
  prompt_fingerprint?: string;
  agent_name?: string;
  agent_framework?: string;
  session_id?: string;
  workflow_id?: string;
  workflow_name?: string;
  prompt_version?: string;
  trace_id?: string;
  parent_call_id?: string;
  user_id?: string;
  environment?: string;
  step_index?: number;
  output_content?: string;
  finish_reason?: string;
  stop_reason?: string;
  tool_definitions?: Record<string, unknown>[];
  tool_calls?: Record<string, unknown>[];
  /** @deprecated Use tool_calls. Accepted only for legacy callers. */
  tool_calls_made?: Record<string, unknown>[];
  retrieval?: Record<string, unknown>;
  outcome?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}
