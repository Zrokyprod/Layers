import type {
  GoldenSetView,
  GoldenTraceView,
  RegressionCIRunDetailResponse,
  ReplayRunDetailItem,
  ReplayRunItem,
  ReplayRunTraceItem,
} from "@/lib/api";
import type {
  CallDetailResponse,
  CallListItem,
  IssueItem,
  IssueProofSnapshot,
} from "@/lib/types";

const badOutput =
  "Refunds are usually processed within 5-10 business days. Please check your payment provider or contact support if you still have questions.";
const fixedOutput =
  "Your refund RF-1001 for order ORD-1001 was issued on 2026-01-14 for $42.18. It should arrive by 2026-01-19.";
const brokenPrOutput =
  "Refunds are usually processed within 5-10 business days. Please check your bank for updates.";

export const moneyPathIds = {
  projectId: "demo-refund-money-path",
  callId: "demo-call-refund-missed-tool",
  traceId: "trace-demo-refund-missed-tool",
  diagnosisId: "demo-diagnosis-refund-tool",
  issueId: "demo-issue-refund-tool-not-called",
  replayRunId: "demo-replay-refund-fixed",
  replayTraceId: "demo-replay-trace-refund-fixed",
  goldenSetId: "demo-golden-refund-status",
  goldenTraceId: "demo-golden-trace-refund-status",
  ciRunId: "demo-ci-refund-tool-regression",
  ciTraceId: "demo-ci-trace-refund-tool-regression",
  gitSha: "demo-break-refund-tool",
  prUrl: "https://github.com/acme/refund-agent/pull/43",
} as const;

export const moneyPathNow = "2026-01-15T10:20:00.000Z";

function sourceContext() {
  return {
    kind: "issue",
    id: moneyPathIds.issueId,
    call_id: moneyPathIds.callId,
    issue_id: moneyPathIds.issueId,
    title: "Refund status tool skipped",
    reason: "TOOL_NOT_CALLED: refund status questions require get_refund_status before answering.",
    failure_code: "TOOL_NOT_CALLED",
    severity: "critical",
    affected_agent: "refund-support-agent",
    affected_workflow: "refund-status",
    occurrence_count: 17,
    last_seen_at: moneyPathNow,
    origin: "issue",
    confidence: 0.99,
    discovery_signature: "fp-demo-refund-v1",
  };
}

export function moneyPathIssueProof(
  overrides: Partial<IssueProofSnapshot> = {},
): IssueProofSnapshot {
  return {
    replay: {
      run_id: moneyPathIds.replayRunId,
      status: "pass",
      replay_mode: "mocked-tool",
      verified_fix: true,
      summary_url: `/v1/replay/runs/${moneyPathIds.replayRunId}`,
      created_at: moneyPathNow,
      completed_at: moneyPathNow,
    },
    golden: {
      golden_set_id: moneyPathIds.goldenSetId,
      golden_set_name: "Refund status protected flow",
      golden_trace_id: moneyPathIds.goldenTraceId,
      status: "active",
      blocks_ci: true,
      trace_count: 1,
      created_at: moneyPathNow,
    },
    ci_gate: {
      run_id: moneyPathIds.ciRunId,
      status: "fail",
      git_sha: moneyPathIds.gitSha,
      summary_url: `/v1/regression-ci/runs/${moneyPathIds.ciRunId}`,
      created_at: moneyPathNow,
      completed_at: moneyPathNow,
    },
    ...overrides,
  };
}

export function moneyPathIssue(overrides: Partial<IssueItem> = {}): IssueItem {
  return {
    id: moneyPathIds.issueId,
    project_id: moneyPathIds.projectId,
    failure_code: "TOOL_NOT_CALLED",
    prompt_fingerprint: "fp-demo-refund-v1",
    agent_name: "refund-support-agent",
    status: "open",
    severity: "critical",
    occurrence_count: 17,
    blast_radius_usd: 1260,
    first_seen_at: moneyPathNow,
    last_seen_at: moneyPathNow,
    sample_call_id: moneyPathIds.callId,
    sample_diagnosis_id: moneyPathIds.diagnosisId,
    last_fix_id: null,
    resolved_at: null,
    resolution_source: null,
    assigned_to: "support-platform",
    deploy_pr_url: "https://github.com/acme/refund-agent/pull/42",
    created_at: moneyPathNow,
    updated_at: moneyPathNow,
    title: "Refund status tool skipped",
    affected_agent: "refund-support-agent",
    affected_workflow: "refund-status",
    root_cause: "The agent treated a status lookup as a policy question and skipped get_refund_status.",
    evidence_traces: [
      {
        call_id: moneyPathIds.callId,
        trace_id: moneyPathIds.traceId,
        workflow_name: "refund-status",
        prompt_version: "refund-agent.bad.v1",
        model: "refund-agent-bad-v1",
        provider: "fake-provider",
        status: "failed",
        latency_ms: 384,
        cost_usd: 0.0021,
        created_at: moneyPathNow,
        evidence_summary: "Refund status request got a generic refund policy answer.",
      },
    ],
    cost_impact_usd: 1260,
    user_impact: "Customers asking about refund RF-1001 received generic policy text instead of account-specific status.",
    replay_coverage_status: "verified_fix",
    recommended_next_action: "Keep the Golden active and block PRs that skip get_refund_status.",
    priority_score: 100,
    proof: moneyPathIssueProof(),
    ...overrides,
  };
}

export function moneyPathCall(overrides: Partial<CallListItem> = {}): CallListItem {
  return {
    call_id: moneyPathIds.callId,
    tenant_id: moneyPathIds.projectId,
    status: "failed",
    provider: "fake-provider",
    model: "refund-agent-bad-v1",
    agent_name: "refund-support-agent",
    user_id: "cus_demo_001",
    call_type: "chat",
    total_tokens: 157,
    cost_usd: 0.0021,
    pricing_version: "demo-fixed",
    pricing_last_updated_at: moneyPathNow,
    pricing_age_days: 0,
    cost_confidence: "high",
    latency_ms: 384,
    error_code: "TOOL_NOT_CALLED",
    diagnoses: [moneyPathIds.diagnosisId],
    has_blast_radius: true,
    created_at: moneyPathNow,
    updated_at: moneyPathNow,
    ...overrides,
  };
}

export function moneyPathCallDetail(): CallDetailResponse {
  return {
    call: moneyPathCall(),
    payload: {
      trace_id: moneyPathIds.traceId,
      input: "Where is my refund?",
      output: badOutput,
      failure_reason: "The refund-status tool was required but no tool call was made.",
      tool_calls: [],
      tools_available: ["get_refund_status"],
      expected_tool: "get_refund_status",
      customer_id: "cus_demo_001",
      order_id: "ORD-1001",
    },
    cost_audit: null,
    diagnosis_result: {
      failure_code: "TOOL_NOT_CALLED",
      root_cause: "The agent treated a status lookup as a policy question and skipped get_refund_status.",
      observed_tools: [],
      expected_tool: "get_refund_status",
    },
    feedback_summary: {
      helpful_count: 0,
      not_helpful_count: 0,
    },
  };
}

export function moneyPathGoldenSet(overrides: Partial<GoldenSetView> = {}): GoldenSetView {
  return {
    id: moneyPathIds.goldenSetId,
    project_id: moneyPathIds.projectId,
    name: "Refund status protected flow",
    description: "Protects refund status lookups from generic policy-only answers.",
    judge_config_json: JSON.stringify({
      owner: "support-platform",
      ci_usage: "blocking",
      source_issue_id: moneyPathIds.issueId,
      source_call_id: moneyPathIds.callId,
      source_replay_run_id: moneyPathIds.replayRunId,
      must_call_tools: ["get_refund_status"],
    }),
    is_flaky: false,
    blocks_ci: true,
    trace_count: 1,
    created_at: moneyPathNow,
    updated_at: moneyPathNow,
    ...overrides,
  };
}

export function moneyPathGoldenTrace(overrides: Partial<GoldenTraceView> = {}): GoldenTraceView {
  return {
    id: moneyPathIds.goldenTraceId,
    golden_set_id: moneyPathIds.goldenSetId,
    project_id: moneyPathIds.projectId,
    call_id: moneyPathIds.callId,
    status: "active",
    expected_output_text: fixedOutput,
    source_output_text: badOutput,
    source_evidence_json: JSON.stringify({
      summary: "Verified replay called get_refund_status and returned account-specific refund status.",
      source_issue_id: moneyPathIds.issueId,
      source_replay_run_id: moneyPathIds.replayRunId,
      source_call_id: moneyPathIds.callId,
    }),
    expected_tokens: null,
    expected_cost_usd: 0.0034,
    expected_latency_ms: 522,
    criteria_json: JSON.stringify({
      must_call_tools: ["get_refund_status"],
      must_not_contain: ["Refunds are usually processed within 5-10 business days."],
      expected_semantics: [
        "Tell the customer refund id RF-1001.",
        "Say the refund was issued on 2026-01-14.",
        "Say the expected arrival date is 2026-01-19.",
      ],
    }),
    weight: 1,
    created_at: moneyPathNow,
    updated_at: moneyPathNow,
    ...overrides,
  };
}

export function moneyPathReplayRun(overrides: Partial<ReplayRunItem> = {}): ReplayRunItem {
  return {
    id: moneyPathIds.replayRunId,
    project_id: moneyPathIds.projectId,
    golden_set_id: moneyPathIds.goldenSetId,
    trigger: "manual",
    git_sha: "demo-fixed-refund-tool",
    status: "pass",
    started_at: moneyPathNow,
    completed_at: moneyPathNow,
    created_at: moneyPathNow,
    replay_mode: "mocked-tool",
    executor_replay_mode: "mocked-tool",
    replay_mode_warning: null,
    candidate_prompt_override:
      "For refund status questions, call get_refund_status before answering. Use the tool result to give the customer their refund ID, status, issued date, ETA, and amount.",
    candidate_model_override: "refund-agent-fixed-v2",
    prevented_outcome_cost_usd: 1260,
    source_context: sourceContext(),
    summary: {
      trace_count_at_dispatch: 1,
      trace_count_executed: 1,
      pass_count: 1,
      fail_count: 0,
      error_count: 0,
      reproduced_original_failure: true,
      fix_passed: true,
      verified_fix: true,
      verification_status: "verified_fix",
      output_diff: { before: badOutput, after: fixedOutput },
      tool_behavior_diff: {
        expected_tool: "get_refund_status",
        before_tool_calls: [],
        after_tool_calls: ["get_refund_status"],
        required_tool_called: true,
      },
      cost_delta_usd: 0.0013,
      latency_delta_ms: 138,
      replay_cost_usd: 0.0034,
    },
    ...overrides,
  };
}

export function moneyPathReplayTrace(
  overrides: Partial<ReplayRunTraceItem> = {},
): ReplayRunTraceItem {
  return {
    id: moneyPathIds.replayTraceId,
    replay_run_id: moneyPathIds.replayRunId,
    golden_trace_id: moneyPathIds.goldenTraceId,
    project_id: moneyPathIds.projectId,
    call_id_replayed: moneyPathIds.callId,
    judge_scores_json: JSON.stringify({
      tool_behavior: 1,
      reason: "get_refund_status was called before answering.",
    }),
    status: "pass",
    diff_metric: 0,
    output_text: fixedOutput,
    completed_at: moneyPathNow,
    created_at: moneyPathNow,
    output_diff: { before: badOutput, after: fixedOutput },
    tool_behavior_diff: {
      expected_tool: "get_refund_status",
      before_tool_calls: [],
      after_tool_calls: ["get_refund_status"],
      required_tool_called: true,
    },
    cost_delta_usd: 0.0013,
    latency_delta_ms: 138,
    ...overrides,
  };
}

export function moneyPathReplayRunDetail(
  overrides: Partial<ReplayRunDetailItem> = {},
): ReplayRunDetailItem {
  return {
    ...moneyPathReplayRun(),
    traces: [moneyPathReplayTrace()],
    ...overrides,
  };
}

export function moneyPathCiRun(overrides: Partial<ReplayRunItem> = {}): ReplayRunItem {
  return {
    ...moneyPathReplayRun({
      id: moneyPathIds.ciRunId,
      trigger: "github",
      git_sha: moneyPathIds.gitSha,
      status: "fail",
      prevented_outcome_cost_usd: null,
      source_context: {
        ...sourceContext(),
        kind: "issue_ci_gate",
        origin: "ci_gate",
      },
      summary: {
        ...moneyPathReplayRun().summary,
        pass_count: 0,
        fail_count: 1,
        verified_fix: false,
        fix_passed: false,
        verification_status: "regression_failed",
        output_diff: { before: fixedOutput, after: brokenPrOutput },
        tool_behavior_diff: {
          expected_tool: "get_refund_status",
          before_tool_calls: ["get_refund_status"],
          after_tool_calls: [],
          required_tool_called: false,
        },
        replay_cost_usd: 0.0023,
      },
    }),
    ...overrides,
  };
}

export function moneyPathCiRunDetail(
  overrides: Partial<ReplayRunDetailItem> = {},
): ReplayRunDetailItem {
  return {
    ...moneyPathCiRun(),
    traces: [
      moneyPathReplayTrace({
        id: moneyPathIds.ciTraceId,
        replay_run_id: moneyPathIds.ciRunId,
        status: "fail",
        judge_scores_json: JSON.stringify({
          tool_behavior: 0,
          reason: "The PR skipped get_refund_status again.",
          blocks_ci: true,
        }),
        diff_metric: 1,
        output_text: brokenPrOutput,
        output_diff: { before: fixedOutput, after: brokenPrOutput },
        tool_behavior_diff: {
          expected_tool: "get_refund_status",
          before_tool_calls: ["get_refund_status"],
          after_tool_calls: [],
          required_tool_called: false,
        },
      }),
    ],
    ...overrides,
  };
}

export function moneyPathCiDetail(
  overrides: Partial<RegressionCIRunDetailResponse> = {},
): RegressionCIRunDetailResponse {
  return {
    run_id: moneyPathIds.ciRunId,
    project_id: moneyPathIds.projectId,
    git_sha: moneyPathIds.gitSha,
    status: "fail",
    created_at: moneyPathNow,
    started_at: moneyPathNow,
    completed_at: moneyPathNow,
    report: {
      verdict: "fail",
      regression_rate: 1,
      regression_threshold: 0.02,
      regressed_count: 1,
      trace_count: 1,
      protected_flows: 1,
      replay_mode: "mocked-tool",
      golden_set_id: moneyPathIds.goldenSetId,
      pr_number: 43,
      pr_title: "Refund tool guard regression",
      branch: "break/refund-tool-call",
      pr_url: moneyPathIds.prUrl,
      clusters: [
        {
          label: "Refund tool call requirement",
          size: 1,
          reason: "The PR skipped get_refund_status again.",
        },
      ],
      blast_radius: {
        category: "tool_not_called_regression",
        target: "refund-status",
        source: "golden_trace",
      },
      sample_spec: {
        target_total: 1,
      },
      judge_used_count: 1,
      cost_usd: 0.0023,
      duration_seconds: 4,
      outcome_attribution: {
        estimated_monthly_risk_usd: 1260,
      },
      notes: "Blocking Golden failed for PR #43.",
    },
    pr_comment_markdown: [
      "Replay CI: Failed",
      "",
      "PR #43 is blocked because the refund status tool call regressed.",
      `Golden: ${moneyPathIds.goldenSetId}`,
      `Trace: ${moneyPathIds.goldenTraceId}`,
    ].join("\n"),
    ...overrides,
  };
}

export const moneyPathBilling = {
  org_id: moneyPathIds.projectId,
  plan_code: "pro",
  status: "active",
  seats: 1,
  payment_provider: "skydo",
  payment_customer_ref: null,
  payment_subscription_ref: null,
  payment_request_ref: null,
  stripe_customer_id: null,
  stripe_sub_id: null,
  current_period_end: null,
  trial_end: null,
  sla_tier: "standard",
  plan_template: {
    "pilot.root_cause_diagnosis": true,
    "pilot.replay_stub": true,
    "pilot.goldens_basic": true,
    "pro.ci_gate_nonblocking": true,
    "pro.ci_gate_blocking": true,
  },
};
