export type JsonMap = Record<string, unknown>;

export interface AuthTokenResponse {
  access_token: string;
  refresh_token: string;
  access_expires_in_seconds: number;
  refresh_expires_in_seconds: number;
  token_type: string;
  user_id: string;
  email: string | null;
  email_verified: boolean;
}

export interface MeResponse {
  user_id: string;
  email: string | null;
  github_login: string | null;
  google_id: string | null;
  has_password: boolean;
  created_at: string;
}

export type HealthStatusBand = "perfect" | "green" | "yellow" | "red";

// ── Judge Health (Layer 3 — verdict + per-dimension drift) ───────────────────

export interface VerdictDriftView {
  judge_model: string;
  sample_count: number;
  disagreement_count: number;
  disagreement_rate: number;
  threshold: number;
  breached: boolean;
}

export interface DimensionDriftView {
  judge_model: string;
  dimension: string;
  sample_count: number;
  older_mean: number;
  recent_mean: number;
  drift: number;
  threshold: number;
  breached: boolean;
}

export interface JudgeHealthResponse {
  project_id: string;
  window_hours: number;
  enabled: boolean;
  primary_model: string | null;
  ensemble_models: string[];
  verdict_drift: VerdictDriftView[];
  dimension_drift: DimensionDriftView[];
  any_breached: boolean;
}

/**
 * Aggregate ROI summary from /v1/analytics/savings.
 *
 * Distinct figures intentionally — the dashboard surfaces them with
 * different framing:
 *   - cumulative_wasted_usd → "still bleeding" (open issues)
 *   - cumulative_resolved_blast_usd → "already saved" (resolved blast)
 *   - projected_averted_usd → "would have lost" (6h forward projection)
 */
export interface SavingsSummaryResponse {
  window_days: number;
  total_caught_count: number;
  total_resolved_count: number;
  cumulative_wasted_usd: number;
  cumulative_resolved_blast_usd: number;
  projected_averted_usd: number;
  affected_calls: number;
  incidents_by_severity: Record<string, number>;
  updated_at: string;
}

export type AlertStatus = "OPEN" | "ACKNOWLEDGED" | "RESOLVED";

export type ProviderVerificationStatus = "verified" | "unverified" | "failed";

export interface CallListItem {
  call_id: string;
  tenant_id: string;
  status: string;
  provider: string | null;
  model: string | null;
  agent_name: string | null;
  user_id: string | null;
  call_type: string | null;
  total_tokens: number;
  cost_usd: number;
  pricing_version: string | null;
  pricing_last_updated_at: string | null;
  pricing_age_days: number | null;
  cost_confidence: string | null;
  latency_ms: number | null;
  error_code: string | null;
  diagnoses: string[];
  has_blast_radius: boolean;
  created_at: string;
  updated_at: string;
}

export interface CallListResponse {
  total: number;
  limit: number;
  offset: number;
  items: CallListItem[];
}

export interface AdjacentCallItem {
  id: string;
  model: string | null;
  status: string;
}

export interface AdjacentCallsResponse {
  prev: AdjacentCallItem | null;
  next: AdjacentCallItem | null;
}

export interface CallFeedbackSummary {
  helpful_count: number;
  not_helpful_count: number;
}

export interface ActivityFeedItemResponse {
  log_id: string;
  tenant_id: string;
  diagnosis_id: string;
  action: string;
  actor_subject: string | null;
  metadata: JsonMap | null;
  created_at: string;
}

export interface ActivityFeedResponse {
  total: number;
  limit: number;
  offset: number;
  items: ActivityFeedItemResponse[];
}

export interface CallDetailResponse {
  call: CallListItem;
  payload: JsonMap;
  cost_audit: JsonMap | null;
  diagnosis_result: JsonMap | null;
  feedback_summary: CallFeedbackSummary;
}

export interface TraceRootFailure {
  category: string | null;
  root_cause: string | null;
}

export interface TraceTreeNode {
  call_id: string;
  parent_call_id: string | null;
  agent_name: string | null;
  provider: string | null;
  model: string | null;
  cost_confidence: string | null;
  status: string;
  wasted_cost_usd: number;
  latency_ms: number | null;
  error_code: string | null;
  created_at: string;
  children: TraceTreeNode[];
}

export interface CallTraceTreeResponse {
  call_id: string;
  trace_id: string | null;
  root_failure: TraceRootFailure | null;
  total_downstream_calls: number;
  total_wasted_cost_usd: number;
  root_node: TraceTreeNode;
}

export interface TraceListItem {
  trace_id: string;
  root_call_id: string;
  call_count: number;
  agent_count: number;
  agents: string[];
  providers: string[];
  started_at: string;
  last_seen_at: string;
  total_cost_usd: number;
  has_failure: boolean;
  root_failure_category: string | null;
}

export interface TraceListResponse {
  window_days: number;
  total: number;
  multi_agent_count: number;
  failed_count: number;
  items: TraceListItem[];
}

export interface FixAdoptionSummary {
  viewed_diagnoses: number;
  resolved_diagnoses: number;
  adoption_rate_percent: number;
  status_band: "strong" | "warning" | "critical";
}

export interface FeedbackCategoryVisibility {
  category: string;
  feedback_total: number;
  thumbs_down_count: number;
  thumbs_down_rate_percent: number;
}

export interface FeedbackLoopVisibility {
  feedback_total: number;
  thumbs_down_total: number;
  thumbs_down_rate_percent: number;
  by_category: FeedbackCategoryVisibility[];
}

export interface AnalyticsSummaryResponse {
  calls_today: number;
  calls_yesterday: number;
  cost_today_usd: number;
  cost_yesterday_usd: number;
  open_issues: number;
  health_score: number;
  fix_adoption: FixAdoptionSummary;
  feedback_loop: FeedbackLoopVisibility;
  unusual_activity: JsonMap | null;
  updated_at: string;
}

export interface HealthScoreResponse {
  health_score: number;
  status_band: HealthStatusBand;
  success_rate: number;
  latency_score: number;
  cost_anomaly_score: number;
  open_issues_score: number;
  details: JsonMap;
  updated_at: string;
}

export type CaptureHealthStatus = "connected" | "stale" | "no_data";

export interface CaptureValidationWarning {
  code: "tool_spans_missing" | "outcome_missing" | "prompt_version_missing";
  label: string;
  detail: string;
}

export interface CaptureHealthResponse {
  project_id: string;
  status: CaptureHealthStatus;
  stale_after_minutes: number;
  last_call_id: string | null;
  last_seen_at: string | null;
  seconds_since_last_call: number | null;
  last_provider: string | null;
  last_model: string | null;
  last_call_type: string | null;
  last_source: string | null;
  calls_24h: number;
  sdk_events_24h: number;
  gateway_events_24h: number;
  retrieval_spans_24h: number;
  memory_spans_24h: number;
  error_events_24h: number;
  sampled_recent_calls: number;
  validation_warnings: CaptureValidationWarning[];
}

export interface FixHealthTrustSummary {
  adoption_rate: number;
  adoption_rate_delta: number;
  success_rate: number;
  success_rate_delta: number;
  regression_rate: number;
  regression_rate_delta: number;
  median_time_to_resolution_hours: number | null;
  median_time_to_resolution_hours_delta: number | null;
  average_resolution_confidence: number;
  average_resolution_confidence_delta: number;
  major_regressions_count: number;
  major_regressions_count_delta: number;
  severity_indicator: "stable" | "watch" | "critical";
}

export interface FixFunnelStep {
  state: string;
  label: string;
  count: number;
  conversion_rate: number;
}

export interface FixTrendPoint {
  day: string;
  success_rate: number;
  regression_rate: number;
  resolved_count: number;
  regressed_count: number;
}

export interface FixDiagnosisPerformanceItem {
  diagnosis_type: string;
  fix_tags: string[];
  shown_count: number;
  adopted_count: number;
  resolved_count: number;
  regressed_count: number;
  adoption_rate: number;
  success_rate: number;
  regression_rate: number;
  median_resolution_hours: number | null;
}

export interface FixActionQueueItem {
  fix_id: string;
  diagnosis_id: string;
  status_badge: "stable" | "watch" | "critical";
  priority: string;
  diagnosis_type: string;
  fix_title: string;
  current_state: string;
  success_status: "unresolved" | "resolved" | "regressed";
  resolution_confidence: number | null;
  resolution_correlation: string | null;
  attribution_mode: string | null;
  regression_severity: string | null;
  risk_level: string | null;
  blast_radius: string | null;
  time_open_hours: number;
  recommended_next_action: string;
}

export interface FixMicroInsight {
  message: string;
  severity: "stable" | "watch" | "critical";
  diagnosis_type: string | null;
  priority_hint: string | null;
  action_label: string | null;
}

export interface FixAnalyticsResponse {
  generated_at: string;
  window_days: number;
  health: FixHealthTrustSummary;
  funnel: FixFunnelStep[];
  trend: FixTrendPoint[];
  diagnosis_performance: FixDiagnosisPerformanceItem[];
  action_queue: FixActionQueueItem[];
  micro_insight: FixMicroInsight;
}

export interface CostDailyTrendPoint {
  day: string;
  total_cost_usd: number;
  call_count: number;
  failed_cost_usd: number;
  failed_call_count: number;
}

export interface CostDailyTrendResponse {
  days: number;
  points: CostDailyTrendPoint[];
  pricing_last_updated_at: string | null;
  pricing_source?: string | null;
  pricing_age_days: number | null;
  cost_confidence: string | null;
  confidence_reason?: string | null;
}

export interface CostBreakdownItem {
  key: string;
  total_cost_usd: number;
  call_count: number;
  failed_cost_usd: number;
  failed_call_count: number;
}

export interface CostBreakdownResponse {
  days: number;
  items: CostBreakdownItem[];
}

export interface ReasoningShareResponse {
  days: number;
  total_cost_usd: number;
  reasoning_cost_usd: number;
  reasoning_share_percent: number;
}

export interface CacheSavingsPoint {
  day: string;
  cache_savings_usd: number;
}

export interface CacheSavingsResponse {
  days: number;
  total_cache_savings_usd: number;
  points: CacheSavingsPoint[];
}

export interface BudgetConfigResponse {
  monthly_limit_usd: number | null;
  threshold_percentage: number;
  updated_at: string;
}

export interface BudgetStatusResponse {
  spent_usd: number;
  limit_usd: number | null;
  percent_used: number | null;
  days_remaining_in_period: number;
  forecast_exhaust_in_days: number | null;
  status: "ok" | "warning" | "critical" | "no_limit";
  forecast_risk_level: string;
  forecast_recommendation: string;
}

export interface CostTopCallItem {
  call_id: string;
  model: string | null;
  provider: string | null;
  cost_usd: number;
  status: string;
  agent_name: string | null;
  user_id?: string | null;
  call_type?: string | null;
  error_code: string | null;
  cost_confidence?: string | null;
  confidence_reason?: string | null;
  pricing_source?: string | null;
  pricing_age_days?: number | null;
  created_at: string;
}

export interface CostTopCallsResponse {
  window_hours: number;
  items: CostTopCallItem[];
}

export interface CostHourlyPoint {
  hour: string;
  total_cost_usd: number;
  call_count: number;
  failed_cost_usd: number;
  failed_count: number;
}

export interface CostHourlyResponse {
  hours: number;
  points: CostHourlyPoint[];
  cost_total_usd: number;
  pricing_last_updated_at: string | null;
  pricing_age_days: number | null;
  cost_confidence: string | null;
}

export interface LoopIncidentItem {
  diagnosis_id: string;
  agent_name: string | null;
  created_at: string;
  loop_score: number;
  dominant_pattern: string | null;
  repeat_count: number;
  no_progress: boolean;
  estimated_cost_usd: number;
  retry_suppression_applied: boolean;
}

export interface LoopIncidentsResponse {
  total: number;
  limit: number;
  offset: number;
  window_days: number;
  items: LoopIncidentItem[];
}

export interface LoopDayPoint {
  day: string;
  count: number;
}

export interface LoopSummaryResponse {
  window_days: number;
  total_loop_count: number;
  estimated_waste_usd: number;
  top_looping_agent: string | null;
  most_common_pattern: string | null;
  loop_count_by_day: LoopDayPoint[];
}

export interface AuthTrendPoint {
  hour: string;
  count: number;
}

export interface AuthSummaryResponse {
  window_hours: number;
  total_auth_failures: number;
  open_alert_count: number;
  is_ongoing: boolean;
  affected_providers: string[];
  first_failure_at: string | null;
  last_failure_at: string | null;
  mean_time_to_acknowledge_minutes: number | null;
  trend: AuthTrendPoint[];
}

export interface AlertItemResponse {
  alert_id: string;
  diagnosis_id: string;
  category: string;
  severity: string;
  status: AlertStatus;
  source: string;
  title: string;
  evidence: JsonMap | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

export interface AlertListResponse {
  total: number;
  limit: number;
  offset: number;
  items: AlertItemResponse[];
}

export type AlertChannel = "email" | "slack" | "browser" | "terminal";

export interface AlertChannelTestResponse {
  channel: string;
  status: "queued" | "sent";
  message: string;
}

export interface OnboardingTriggerResponse {
  diagnosis_id: string;
  status: string;
  synthetic: boolean;
  message: string;
}

export interface PiiPolicyResponse {
  custom_patterns: string[];
  updated_at: string;
}

export interface PiiDetectorTestResponse {
  valid: boolean;
  match_count: number;
  matches: string[];
  error: string | null;
}

export interface RetentionPolicyResponse {
  retention_days: number;
  updated_at: string;
}

export interface RetentionDataErasureResponse {
  tenant_id: string;
  dry_run: boolean;
  batch_size: number;
  deleted_by_table: Record<string, number>;
  total_deleted: number;
  erased_at: string;
}

export interface NotificationSettingsResponse {
  email_enabled: boolean;
  slack_enabled: boolean;
  teams_enabled: boolean;
  browser_enabled: boolean;
  terminal_enabled: boolean;
  updated_at: string;
}

export interface GithubConnectionStatusResponse {
  connected: boolean;
  github_id: string | null;
  github_login: string | null;
  scopes: string[];
  connected_at: string | null;
  updated_at: string | null;
}

export interface SlackInstallStatusResponse {
  connected: boolean;
  team_id: string | null;
  team_name: string | null;
  channel_id: string | null;
  channel_name: string | null;
  bot_user_id: string | null;
  scopes: string[];
  installed_by_user: string | null;
  installed_at: string | null;
  updated_at: string | null;
}

export interface SlackInstallStartResponse {
  authorization_url: string;
}

export interface SlackTestMessageResponse {
  ok: boolean;
  message: string;
}

export interface TeamsInstallStatusResponse {
  connected: boolean;
  channel_name: string | null;
  connector_type: string | null;
  installed_by_user: string | null;
  installed_at: string | null;
  updated_at: string | null;
}

export interface TeamsTestMessageResponse {
  ok: boolean;
  message: string;
}

export type PricingModelDecision = "tiered" | "usage_based" | "undecided";

export interface PricingInterviewNote {
  developer_ref: string;
  preferred_model: PricingModelDecision;
  fairness_score: number;
  call_volume_context: string | null;
  notes: string | null;
  interviewed_at: string;
}

export interface PricingValidationResponse {
  selected_launch_model: PricingModelDecision;
  rationale: string | null;
  migration_path: string | null;
  interviews: PricingInterviewNote[];
  interview_count: number;
  unique_developer_count: number;
  required_interviews: number;
  missing_interviews: number;
  minimum_interviews_met: boolean;
  pricing_locked: boolean;
  launch_gate_passed: boolean;
  blockers: string[];
  locked_at: string | null;
  updated_at: string;
}

export type RollbackDrillStatus = "not_started" | "in_progress" | "passed" | "failed";
export type FailureSimulationCategory =
  | "TOKEN_OVERFLOW"
  | "RATE_LIMIT"
  | "AUTH_FAILURE"
  | "LOOP_DETECTED"
  | "COST_SPIKE";

export interface RollbackDrillResponse {
  deploy_revision: string | null;
  rollback_revision: string | null;
  deploy_test_passed: boolean;
  rollback_test_passed: boolean;
  failure_simulation_performed: boolean;
  failure_simulation_category: FailureSimulationCategory | null;
  failure_simulation_notes: string | null;
  drill_notes: string | null;
  status: RollbackDrillStatus;
  completed_at: string | null;
  updated_at: string;
}

export type RollbackVerificationPhase = "deploy" | "rollback";
export type RollbackVerificationCheckStatus = "ok" | "failed" | "skipped";

export interface RollbackDrillVerificationCheck {
  name: "database" | "redis";
  status: RollbackVerificationCheckStatus;
  detail: string;
}

export interface RollbackDrillVerificationResponse {
  phase: RollbackVerificationPhase;
  passed: boolean;
  checks: RollbackDrillVerificationCheck[];
  verified_at: string;
  rollback_drill: RollbackDrillResponse;
}

export interface ProviderVerificationItem {
  provider: string;
  status: ProviderVerificationStatus;
  tracked_call_count: number;
  last_checked_at: string | null;
  last_error: string | null;
}

export interface ProviderVerificationListResponse {
  items: ProviderVerificationItem[];
}

export interface ProviderVerificationTestResponse {
  provider: string;
  status: "verified" | "failed";
  message: string;
  checked_at: string;
}

export interface ProjectResponse {
  project_id: string;
  name: string;
  owner_ref: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ApiKeyResponse {
  key_id: string;
  project_id: string;
  name: string;
  key_prefix: string;
  revoked: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyCreateResponse {
  key_id: string;
  project_id: string;
  name: string;
  key_prefix: string;
  api_key: string;
  created_at: string;
}

export interface DiagnosisFeedbackResponse {
  feedback_id: string;
  tenant_id: string;
  diagnosis_id: string;
  was_helpful: boolean;
  developer_note: string | null;
  created_by_subject: string | null;
  created_at: string;
}

export interface DiagnosisFixCopiedResponse {
  tenant_id: string;
  diagnosis_id: string;
  action: string;
  created_at: string;
}

export interface DiagnosisShareCreateResponse {
  share_id: string;
  diagnosis_id: string;
  token: string;
  token_prefix: string;
  expires_at: string;
  created_at: string;
}

export interface DiagnosisShareReadResponse {
  share_id: string;
  diagnosis_id: string;
  tenant_id: string;
  status: string;
  result_json: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string;
  read_only: boolean;
}

export interface DiagnosisResolveResponse {
  tenant_id: string;
  diagnosis_id: string;
  status: string;
  resolved_at: string;
  watch_expires_at: string;
  target_categories: string[];
  message: string;
}

export interface DiagnosisFixWatchResponse {
  tenant_id: string;
  diagnosis_id: string;
  status: string;
  resolved_at: string | null;
  watch_expires_at: string | null;
  target_categories: string[];
  recurrence_count: number;
  last_recurrence_at: string | null;
  message: string;
}

export interface DiagnosisUiStateResponse {
  tenant_id: string;
  diagnosis_id: string;
  assigned_subject: string | null;
  snoozed_until: string | null;
  dismissed: boolean;
  updated_at: string;
}

export interface DiagnosisGeneratePrResponse {
  tenant_id: string;
  diagnosis_id: string;
  fix_id: string;
  auth_source: string;
  repository_owner: string;
  repository_name: string;
  base_branch: string;
  branch_name: string;
  pull_request_number: number;
  pull_request_url: string;
  pull_request_title: string;
  file_path: string;
  commit_sha: string | null;
  merge_commit_sha: string | null;
  merged_at: string | null;
  last_ci_state: string | null;
  last_ci_conclusion: string | null;
  last_ci_completed_at: string | null;
  generated_patch: string;
  created_at: string;
}

export interface DiagnosisPrLinkResponse {
  pr_link_id: string;
  tenant_id: string;
  diagnosis_id: string;
  fix_id: string | null;
  repository_owner: string;
  repository_name: string;
  base_branch: string;
  branch_name: string;
  pull_request_number: number;
  pull_request_url: string;
  pull_request_title: string;
  file_path: string;
  commit_sha: string | null;
  merge_commit_sha: string | null;
  merged_at: string | null;
  last_ci_state: string | null;
  last_ci_conclusion: string | null;
  last_ci_completed_at: string | null;
  created_at: string;
}

export interface ExportDiagnosisItem {
  tenant_id: string;
  diagnosis_id: string;
  status: string;
  categories: string[];
  result_json: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExportCallItem {
  call: CallListItem;
  payload: JsonMap;
  diagnosis_result: JsonMap | null;
  feedback_summary: CallFeedbackSummary;
}

export interface ExportResponse {
  tenant_id: string;
  generated_at: string;
  call_count: number;
  diagnosis_count: number;
  alert_count: number;
  calls: ExportCallItem[];
  diagnoses: ExportDiagnosisItem[];
  alerts: AlertItemResponse[];
}

// ── Cost Forecast ────────────────────────────────────────────────────────────

export interface CostForecastPoint {
  hour: string;
  predicted_cost_usd: number;
  lower_bound_usd: number;
  upper_bound_usd: number;
}

export interface CostForecastResponse {
  status: "ok" | "insufficient_data" | "error";
  hours_ahead: number;
  points: CostForecastPoint[];
  trend: "stable" | "rising" | "falling";
  confidence: number;
  generated_at: string;
}

export interface CostAnomalyRiskResponse {
  status: "ok" | "elevated" | "high" | "error";
  risk_score: number;
  risk_label: string;
  contributing_factors: string[];
  recommended_action: string | null;
  generated_at: string;
}

// ── Team management ──────────────────────────────────────────────────────────

export interface ProjectMembershipResponse {
  membership_id: string;
  project_id: string;
  user_id: string;
  subject: string;
  email: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectMemberListResponse {
  project_id: string;
  items: ProjectMembershipResponse[];
}

export interface ProjectInviteResponse {
  invited: boolean;
  message: string;
  email: string;
}

// ── User profile ─────────────────────────────────────────────────────────────

export interface ChangePasswordResponse {
  detail: string;
}

// ── Invitations ──────────────────────────────────────────────────────────────

export interface ProjectInvitationItem {
  invitation_id: string;
  project_id: string;
  email: string;
  role: string;
  invited_by_subject: string | null;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface AcceptInvitationResponse {
  success: boolean;
  message: string;
  project_id: string | null;
  membership_id: string | null;
}

// ── Notifications ──────────────────────────────────────────────────────────────

export interface NotificationItem {
  notification_id: string;
  user_id: string;
  project_id: string | null;
  title: string;
  body: string | null;
  category: string;
  is_read: boolean;
  read_at: string | null;
  action_url: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  total: number;
  unread_count: number;
  items: NotificationItem[];
}

export interface MarkReadResponse {
  notification_id: string;
  is_read: boolean;
  read_at: string;
}

export interface MarkAllReadResponse {
  marked_count: number;
}

// ── Platform LLM Usage (owner) ───────────────────────────────────────────────

export interface PlatformLlmUsageItem {
  id: string;
  purpose: string;
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number;
  tenant_id: string | null;
  diagnosis_id: string | null;
  created_at: string;
}

export interface PlatformLlmUsageSummaryResponse {
  total_calls: number;
  total_cost_usd: number;
  total_tokens: number;
  avg_latency_ms: number;
  by_purpose: Record<string, { calls: number; cost_usd: number; tokens: number }>;
  by_model: Record<string, { calls: number; cost_usd: number; tokens: number }>;
  recent: PlatformLlmUsageItem[];
}

// ── Billing / Subscriptions ──────────────────────────────────────────────────

export interface SubscriptionPlan {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  monthly_cost_usd: number;
  annual_cost_usd: number;
  max_projects: number;
  max_members_per_project: number;
  max_calls_per_month: number | null;
  max_tokens_per_month: number | null;
  features: string[];
  is_active: boolean;
  sort_order: number;
  created_at: string;
}

export interface SubscriptionPlanListResponse {
  plans: SubscriptionPlan[];
}

export interface TenantSubscription {
  id: string;
  tenant_id: string;
  plan: SubscriptionPlan;
  billing_interval: string;
  status: string;
  trial_ends_at: string | null;
  current_period_start: string;
  current_period_end: string;
  canceled_at: string | null;
  seats: number;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface BillingUsageSummary {
  tenant_id: string;
  period_start: string;
  period_end: string;
  total_calls: number;
  total_tokens: number;
  total_cost_usd: number;
  plan_limit_calls: number | null;
  plan_limit_tokens: number | null;
  overage_calls: number | null;
  overage_tokens: number | null;
}

// ── Support Tickets ──────────────────────────────────────────────────────────

export interface SupportMessageItem {
  message_id: string;
  sender_type: string;
  sender_subject: string | null;
  body: string;
  is_internal: boolean;
  created_at: string;
}

export interface SupportTicketItem {
  ticket_id: string;
  tenant_id: string | null;
  user_id: string | null;
  subject: string | null;
  email: string | null;
  title: string;
  description: string | null;
  category: string;
  priority: string;
  status: string;
  assigned_to: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface SupportTicketDetailResponse {
  ticket: SupportTicketItem;
  messages: SupportMessageItem[];
}

export interface SupportTicketListResponse {
  items: SupportTicketItem[];
  total: number;
}

// ── Feature Flags ────────────────────────────────────────────────────────────

export interface FeatureFlag {
  id: string;
  key: string;
  description: string | null;
  enabled_globally: boolean;
  enabled_tenants: string[];
  disabled_tenants: string[];
  created_at: string;
  updated_at: string;
}

export interface FeatureFlagListResponse {
  items: FeatureFlag[];
}

export interface TenantFeatureFlagsResponse {
  flags: Record<string, boolean>;
}

// ── Issues ────────────────────────────────────────────────────────────────────

export type IssueStatus = "open" | "resolved" | "ignored";

export interface IssueEvidenceTrace {
  call_id: string | null;
  trace_id: string | null;
  workflow_name: string | null;
  prompt_version: string | null;
  model: string | null;
  provider: string | null;
  status: string | null;
  latency_ms: number | null;
  cost_usd: number;
  created_at: string | null;
  evidence_summary: string | null;
}

export interface IssueItem {
  id: string;
  project_id: string;
  failure_code: string;
  prompt_fingerprint: string | null;
  agent_name: string | null;
  status: IssueStatus;
  severity: string;
  occurrence_count: number;
  blast_radius_usd: number;
  first_seen_at: string;
  last_seen_at: string;
  sample_call_id: string | null;
  sample_diagnosis_id: string | null;
  last_fix_id: string | null;
  resolved_at: string | null;
  resolution_source: string | null;
  created_at: string;
  updated_at: string;
  title: string;
  affected_agent: string | null;
  affected_workflow: string | null;
  root_cause: string;
  evidence_traces: IssueEvidenceTrace[];
  cost_impact_usd: number;
  user_impact: string;
  replay_coverage_status: string;
  recommended_next_action: string;
  priority_score: number;
}

export interface IssueListResponse {
  items: IssueItem[];
  next_cursor: string | null;
  total_in_page: number;
}

// ── Detectors ─────────────────────────────────────────────────────────────────

export interface DetectorInfo {
  name: string;
  failure_code: string;
  label: string;
  speed_class: string;
  confidence_threshold: number;
  description: string;
  loaded: boolean;
}

export interface DetectorListResponse {
  count: number;
  items: DetectorInfo[];
}

// ── Feature-interest voting (Module 9 smoke-test) ──────────────────────────

export type FeatureVoteValue = "interested" | "not_interested";

export interface FeatureVoteResponse {
  feature_key: string;
  vote: FeatureVoteValue;
  use_case: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeatureVoteRequest {
  feature_key: string;
  vote: FeatureVoteValue;
  use_case?: string | null;
}

// ── Provider Drift Watch ──────────────────────────────────────────────────────

export interface DriftModelView {
  id: string;
  provider: string;
  model_id: string;
  display_name: string;
  family: string | null;
  active: boolean;
}

export interface AlertView {
  id: string;
  model_id: string;
  category: string;
  severity: "info" | "warn" | "critical";
  headline: string;
  evidence: Record<string, unknown>;
  created_at: string;
}

export interface StatusResponse {
  date: string;
  models: DriftModelView[];
  alerts: AlertView[];
  total_alerts: number;
  critical_count: number;
  warn_count: number;
  info_count: number;
}

export interface MetricPoint {
  run_date: string;
  judge_pass_rate: number | null;
  embedding_mean_cosine: number | null;
  probe_count: number;
  ok_count: number;
}

export interface ModelHistoryResponse {
  model_id: string;
  display_name: string;
  category: string;
  points: MetricPoint[];
}


// -- Ask Zroky -----------------------------------------------------------------

export interface AskEvidence {
  kind: string;
  id: string;
  label: string;
  href: string;
}

export interface AskResponse {
  answer: string;
  suggested_actions: string[];
  confidence: number;
  intent: string;
  evidence: AskEvidence[];
  used_llm: boolean;
  fallback_reason: string | null;
}

export interface AskContext {
  call_id?: string;
  anomaly_id?: string;
  issue_id?: string;
  trace_id?: string;
}

export interface AskFeedbackRequest {
  question: string;
  answer: string;
  helpful: boolean;
  intent: string;
  confidence: number;
}
