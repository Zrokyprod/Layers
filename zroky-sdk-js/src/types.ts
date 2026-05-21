// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

export interface ZrokyConfig {
  projectId?: string;
  apiKey?: string;
  endpoint?: string;
  agentName?: string;
  sessionId?: string;
  workflowId?: string;
  disabled?: boolean;
}

export interface CapturePayload {
  provider: string;
  model: string;
  call_type: string;
  latency_ms: number;
  prompt_tokens: number;
  output_tokens: number;
  total_tokens: number;
  status: "success" | "error";
  status_code: number;
  error_message?: string;
  prompt_fingerprint?: string;
  agent_name?: string;
  session_id?: string;
  workflow_id?: string;
}
