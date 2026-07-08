import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionRunnerResponse,
  AgentProfileListResponse,
  AgentProfileResponse,
  HomeSummaryResponse,
  OutcomeReconciliationSummaryResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  SourceMutationSummaryResponse,
  SourceMutationView,
} from "@/lib/api";
import type { ApiKeyResponse, BillingUsageResponse } from "@/lib/types";

type FirstRunPreviewData = {
  intents: ActionIntentResponse[];
  approvals: RuntimePolicyDecisionResponse[];
  outcomes: OutcomeReconciliationView[];
  outcomeSummary: OutcomeReconciliationSummaryResponse | null;
  sourceSummary: SourceMutationSummaryResponse | null;
  mutations: SourceMutationView[];
  staleAttempts: ActionExecutionAttemptResponse[];
  agentProfiles: AgentProfileResponse[];
  agentProfileMeta: Pick<AgentProfileListResponse, "active_count" | "max_active_agents" | "limit_reached"> | null;
  actionRunners: ActionRunnerResponse[];
  apiKeys: ApiKeyResponse[];
  billingUsage: BillingUsageResponse | null;
  homeSummary: HomeSummaryResponse | null;
};

const PREVIEW_NOW_MS = Date.now();
const PREVIEW_MINUTE_MS = 60_000;
const PREVIEW_DAY_MS = 24 * 60 * PREVIEW_MINUTE_MS;

function previewIso(minutesAgo: number): string {
  return new Date(PREVIEW_NOW_MS - minutesAgo * PREVIEW_MINUTE_MS).toISOString();
}

function previewDate(daysAgo = 0): string {
  return new Date(PREVIEW_NOW_MS - daysAgo * PREVIEW_DAY_MS).toISOString().slice(0, 10);
}

export const PREVIEW_TIME = previewIso(0);

export const FIRST_RUN_PREVIEW_DATA: FirstRunPreviewData = {
  intents: [
    {
      action_id: "act_preview_refund",
      project_id: "proj_preview",
      agent_id: "agent_preview_refunds",
      agent_profile: {
        id: "agent_preview_refunds",
        display_name: "Refund Agent",
        slug: "refund-agent",
        runtime_path: "sdk",
        environment: "production",
      },
      contract_version: "refund.issue.v1",
      action_type: "ledger.refund.issue",
      operation_kind: "TRANSFER",
      environment: "production",
      status: "approval_pending",
      proof_status: "pending",
      receipt_status: "pending",
      idempotency_key: "preview_refund_1",
      intent_digest: "sha256:preview-refund-digest",
      canonical_intent: {
        purpose: { summary: "Refund high-value invoice after policy check" },
        principal: { id: "refund-agent" },
        resource: { id: "refund_9182", type: "ledger_refund" },
        trace_context: { agent_name: "refund-agent", trace_id: "trace_preview_refund" },
      },
      created_at: PREVIEW_TIME,
      decided_at: PREVIEW_TIME,
      authorized_at: null,
      runtime_policy_decision_id: "decision_preview_refund",
      deadline: null,
      status_url: "/v1/action-intents/act_preview_refund",
    },
    {
      action_id: "act_preview_customer",
      project_id: "proj_preview",
      agent_id: "agent_preview_success",
      contract_version: "customer.update.v1",
      action_type: "crm.customer.update",
      operation_kind: "UPDATE",
      environment: "production",
      status: "authorized",
      proof_status: "matched",
      receipt_status: "generated",
      idempotency_key: "preview_customer_1",
      intent_digest: "sha256:preview-customer-digest",
      canonical_intent: {
        purpose: { summary: "Update verified customer status" },
        principal: { id: "crm-agent" },
        resource: { id: "customer_42", type: "crm_customer" },
        trace_context: { agent_name: "crm-agent", trace_id: "trace_preview_customer" },
      },
      created_at: previewIso(18),
      decided_at: previewIso(17.95),
      authorized_at: previewIso(17.95),
      runtime_policy_decision_id: "decision_preview_customer",
      deadline: null,
      status_url: "/v1/action-intents/act_preview_customer",
    },
  ],
  approvals: [
    {
      id: "decision_preview_refund",
      project_id: "proj_preview",
      trace_id: "trace_preview_refund",
      call_id: null,
      agent_name: "refund-agent",
      role: "agent",
      action_type: "ledger.refund.issue",
      tool_name: "ledger.refunds.create",
      decision: "requires_approval",
      status: "pending_approval",
      allowed: false,
      requires_approval: true,
      reasons: ["sequence risk: repeated money movement in one run"],
      request: { amount_usd: 1280 },
      policy_snapshot: {},
      intended_action: { summary: "Issue refund for invoice INV-9182", amount_usd: 1280 },
      trace_context: { trace_id: "trace_preview_refund" },
      policy_hit: { sequence_risk: { pattern: "fund_drain" } },
      business_impact: { amount_usd: 1280, risk: "high" },
      audit_log: [],
      created_at: PREVIEW_TIME,
      expires_at: previewIso(-60),
      resolved_at: null,
      resolved_by: null,
      resolution_reason: null,
      consumed_at: null,
      consumed_by_decision_id: null,
      required_approval_count: 1,
      approval_count: 0,
      approver_subjects: [],
    },
  ],
  outcomes: [
    {
      id: "outcome_preview_customer",
      project_id: "proj_preview",
      call_id: null,
      trace_id: "trace_preview_customer",
      runtime_policy_decision_id: "decision_preview_customer",
      action_type: "crm.customer.update",
      connector_type: "generic_rest",
      system_ref: "customer_42",
      verdict: "matched",
      verification_status: "matched",
      reason: "source record matched signed receipt",
      amount_usd: null,
      currency: null,
      claimed: { status: "verified" },
      actual: { status: "verified" },
      comparison: {},
      idempotency_key: "preview_customer_1",
      metadata: {},
      checked_at: previewIso(17.8),
      created_at: previewIso(17.8),
    },
  ],
  outcomeSummary: {
    window_days: 30,
    total: 12,
    matched: 11,
    mismatched: 1,
    not_verified: 0,
  },
  sourceSummary: {
    total: 18,
    matched_receipt: 17,
    authorized_external: 1,
    legacy_path: 0,
    unmanaged_agent_action: 0,
    policy_bypass: 1,
    unknown_actor: 0,
    unreceipted: 1,
  },
  mutations: [
    {
      id: "mutation_preview_bypass",
      project_id: "proj_preview",
      source_system: "crm",
      mutation_id: "crm_mutation_77",
      action_type: "customer.export",
      resource_type: "customer_segment",
      resource_id: "segment_enterprise",
      system_ref: "segment_enterprise",
      actor_type: "agent",
      actor_id: "legacy-export-agent",
      zroky_action_id: null,
      action_receipt_id: null,
      idempotency_key: null,
      classification: "policy_bypass",
      metadata: {},
      occurred_at: previewIso(27),
      created_at: previewIso(27),
    },
  ],
  staleAttempts: [],
  agentProfiles: [
    {
      schema_version: "zroky.agent_tool_control.v1",
      id: "agent_preview_refunds",
      project_id: "proj_preview",
      display_name: "Refund Agent",
      slug: "refund-agent",
      description: "Handles high-risk refund actions with approval gates.",
      runtime_path: "sdk",
      framework: "langgraph",
      environment: "production",
      model_provider: "openai",
      model_name: "gpt-4.1",
      tool_names: ["ledger.refunds.create", "crm.customer.update"],
      allowed_action_types: ["refund", "customer_record_update"],
      blocked_action_types: [],
      default_policy_id: null,
      risk_limits: {},
      verification_connectors: ["ledger_refund", "generic_rest"],
      metadata: { agent_name: "refund-agent" },
      is_active: true,
      created_at: previewIso(50),
      updated_at: PREVIEW_TIME,
    },
  ],
  agentProfileMeta: {
    active_count: 1,
    max_active_agents: 3,
    limit_reached: false,
  },
  actionRunners: [
    {
      runner_id: "runner_preview_primary",
      project_id: "proj_preview",
      name: "Production runner",
      runner_type: "customer_hosted",
      environment: "production",
      status: "online",
      supported_operation_kinds: ["UPDATE", "TRANSFER"],
      credential_scope: {},
      heartbeat_payload: {},
      capability_version: previewDate(),
      last_heartbeat_at: PREVIEW_TIME,
      created_at: previewIso(50),
      updated_at: PREVIEW_TIME,
    },
  ],
  apiKeys: [
    {
      key_id: "key_preview",
      project_id: "proj_preview",
      name: "Production verified-action key",
      key_prefix: "zk_live_preview",
      scopes: ["project:member"],
      revoked: false,
      expired: false,
      expires_at: null,
      rotated_from_key_id: null,
      last_used_at: PREVIEW_TIME,
      created_at: previewIso(60),
    },
  ],
  billingUsage: null,
  homeSummary: {
    project_id: "proj_preview",
    window_days: 30,
    window_start: previewIso(30 * 24 * 60),
    generated_at: PREVIEW_TIME,
    metrics: {
      controlled_actions: 2,
      pending_approvals: 1,
      verified_outcomes: 1,
      outcome_checks: 2,
      receipts_generated: 1,
      bypass_mutations: 1,
      unreceipted_mutations: 1,
      sequence_risks: 1,
    },
  },
};
