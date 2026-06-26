// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

export const ZROKY_AGENT_TOOL_CONTROL_SCHEMA_VERSION = "zroky.agent_tool_control.v1" as const;

export const PHASE1_RISKY_ACTION_TYPES = [
  "refund",
  "payment_adjustment",
  "invoice_spend_approval",
  "customer_record_update",
  "ticket_close",
  "email_send",
  "deploy_change",
  "internal_api_mutation",
  "database_record_update",
  "custom",
] as const;

export const PHASE1_RUNTIME_PATHS = ["sdk", "http_gateway", "mcp_gateway", "webhook"] as const;

export const PHASE1_VERIFICATION_CONNECTORS = [
  "generic_rest",
  "webhook_callback",
  "database_read",
  "ledger_refund",
  "crm_record",
  "ticket_status",
  "email_delivery",
  "github_ci",
] as const;

export const PHASE1_NATIVE_TOOL_FAMILIES = [
  "stripe_refund",
  "razorpay_refund",
  "hubspot_customer",
  "salesforce_customer",
  "zendesk_ticket",
  "freshdesk_ticket",
  "sendgrid_email",
  "gmail_email",
  "github_pr_ci_deploy",
  "slack_approval_alert",
] as const;

export type ZrokyRiskActionType = (typeof PHASE1_RISKY_ACTION_TYPES)[number];
export type ZrokyRuntimePath = (typeof PHASE1_RUNTIME_PATHS)[number];
export type ZrokyVerificationConnectorType = (typeof PHASE1_VERIFICATION_CONNECTORS)[number];
export type ZrokyNativeToolFamily = (typeof PHASE1_NATIVE_TOOL_FAMILIES)[number];
export type ZrokyPolicyDecisionStatus = "allow" | "block" | "requires_approval";
export type ZrokyVerificationVerdict = "matched" | "mismatched" | "not_verified";
export type ZrokyJsonValue =
  | string
  | number
  | boolean
  | null
  | ZrokyJsonValue[]
  | { [key: string]: ZrokyJsonValue };

export interface ZrokyAgentProfile {
  schema_version?: typeof ZROKY_AGENT_TOOL_CONTROL_SCHEMA_VERSION;
  agent_id?: string;
  display_name: string;
  runtime_path: ZrokyRuntimePath;
  framework?: string;
  environment?: string;
  owner_user_id?: string;
  model_provider?: string;
  model_name?: string;
  tool_names?: string[];
  allowed_action_types?: ZrokyRiskActionType[];
  blocked_action_types?: ZrokyRiskActionType[];
  default_policy_id?: string;
  risk_limits?: Record<string, ZrokyJsonValue>;
  verification_connectors?: ZrokyVerificationConnectorType[];
  metadata?: Record<string, ZrokyJsonValue>;
  created_at?: string;
  updated_at?: string;
}

export interface ZrokyToolActionPassport {
  schema_version?: typeof ZROKY_AGENT_TOOL_CONTROL_SCHEMA_VERSION;
  action_type: ZrokyRiskActionType | (string & {});
  tool_name?: string;
  tool_args?: ZrokyJsonValue;
  trace_id?: string;
  span_id?: string;
  call_id?: string;
  agent_id?: string;
  agent_name?: string;
  role?: string;
  runtime_path?: ZrokyRuntimePath;
  tool_call_count?: number;
  retry_count?: number;
  estimated_cost_usd?: number;
  input_text?: string;
  user_input?: string;
  output_text?: string;
  external_action?: boolean;
  prompt_injection_detected?: boolean;
  pii_detected?: boolean;
  approval_id?: string;
  business_impact?: ZrokyJsonValue;
  business_impact_summary?: string;
  impact_usd?: number;
  customer_id?: string;
  account_id?: string;
  order_id?: string;
  resource_id?: string;
  metadata?: Record<string, ZrokyJsonValue>;
}

export interface ZrokyPolicyDecisionContract {
  schema_version?: typeof ZROKY_AGENT_TOOL_CONTROL_SCHEMA_VERSION;
  decision_id?: string;
  action_type?: ZrokyRiskActionType | (string & {});
  decision: ZrokyPolicyDecisionStatus;
  allowed?: boolean;
  requires_approval?: boolean;
  reasons?: string[];
  policy_id?: string;
  approval_id?: string;
  expires_at?: string;
  created_at?: string;
  metadata?: Record<string, ZrokyJsonValue>;
}

export interface ZrokyVerificationResult {
  schema_version?: typeof ZROKY_AGENT_TOOL_CONTROL_SCHEMA_VERSION;
  verification_id?: string;
  verdict: ZrokyVerificationVerdict;
  connector_type: ZrokyVerificationConnectorType;
  connector_id?: string;
  source_system?: string;
  expected?: ZrokyJsonValue;
  observed?: ZrokyJsonValue;
  evidence_url?: string;
  evidence_hash?: string;
  checked_at?: string;
  error_message?: string;
  metadata?: Record<string, ZrokyJsonValue>;
}

export interface ZrokyConnectorTemplate {
  schema_version?: typeof ZROKY_AGENT_TOOL_CONTROL_SCHEMA_VERSION;
  connector_type: ZrokyVerificationConnectorType;
  native_tool_family?: ZrokyNativeToolFamily | null;
  display_name: string;
  purpose?: "gate" | "verify" | "approve" | "export";
  auth_mode?: "api_key" | "oauth2" | "webhook_secret" | "basic" | "database_url" | "manual";
  supported_action_types?: ZrokyRiskActionType[];
  required_fields?: string[];
  metadata?: Record<string, ZrokyJsonValue>;
}

export interface ZrokyAuditEvent {
  event_type: string;
  occurred_at: string;
  actor_type?: "agent" | "human" | "system";
  actor_id?: string;
  summary?: string;
  metadata?: Record<string, ZrokyJsonValue>;
}

export interface ZrokyEvidencePackContract {
  schema_version?: typeof ZROKY_AGENT_TOOL_CONTROL_SCHEMA_VERSION;
  evidence_pack_id: string;
  action_passport: ZrokyToolActionPassport;
  decision: ZrokyPolicyDecisionContract;
  verification?: ZrokyVerificationResult;
  audit_events?: ZrokyAuditEvent[];
  evidence_hash: string;
  created_at?: string;
  export_urls?: string[];
  metadata?: Record<string, ZrokyJsonValue>;
}
