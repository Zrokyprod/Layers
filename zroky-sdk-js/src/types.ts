// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

export interface ZrokyConfig {
  projectId?: string;
  apiKey?: string;
  endpoint?: string;
  agentId?: string;
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
  codeSha?: string;
  deploymentId?: string;
  modelVersion?: string;
  toolSchemaVersion?: string;
  ragVersion?: string;
  maskPii?: boolean;
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
  span_type?: string;
  span_name?: string;
  span_index?: number;
  input?: Record<string, unknown>;
  system_prompt?: string;
  user_input?: string;
  final_answer?: string;
  tool?: Record<string, unknown>;
  memory?: Record<string, unknown>;
  handoff?: Record<string, unknown>;
  policy?: Record<string, unknown>;
  versions?: Record<string, unknown>;
  capture_source?: string;
  masking_version?: string;
  pii_masked?: boolean;
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
