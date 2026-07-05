// Owner Dashboard API. The owner token is held in an HttpOnly cookie by the
// Next.js admin BFF; sessionStorage stores only a non-sensitive UI marker.

import type {
  FeatureFlag,
  FeatureFlagListResponse,
  PlatformLlmUsageSummaryResponse,
} from "@/lib/types";

const BASE = "/api/zroky";
const SESSION_MARKER_KEY = "zroky_owner_session";

export function getOwnerToken(): string {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem(SESSION_MARKER_KEY) ? "active" : "";
}

export function setOwnerToken(token: string): void {
  void token;
  if (typeof window !== "undefined") {
    sessionStorage.setItem(SESSION_MARKER_KEY, "active");
  }
}

export function clearOwnerToken(): void {
  if (typeof window !== "undefined") {
    sessionStorage.removeItem(SESSION_MARKER_KEY);
  }
  void fetch("/api/owner/session", {
    method: "DELETE",
    cache: "no-store",
    credentials: "same-origin",
  });
}

async function ownerRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
    credentials: "same-origin",
  });

  if (res.status === 401) {
    clearOwnerToken();
    throw new Error("UNAUTHORIZED");
  }
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export interface OwnerStats {
  total_users: number;
  total_projects: number;
  total_calls: number;
  calls_last_7d: number;
  total_cost_usd: number;
  cost_last_7d_usd: number;
  new_users_last_7d: number;
  active_users_last_7d: number;
}

export interface ServiceStatus {
  name: string;
  status: "ok" | "degraded" | "down" | "unknown";
  detail: string | null;
  latency_ms: number | null;
}

export interface OwnerHealth {
  overall: string;
  services: ServiceStatus[];
  exchange_rate: Record<string, unknown>;
  maintenance_mode: boolean;
  checked_at: string;
}

export interface QueueStats {
  queue_name: string;
  pending: number;
  failed: number;
}

export interface InfraStats {
  queues: QueueStats[];
  worker_count: number;
  worker_names: string[];
  db_table_sizes: Record<string, number>;
}

export interface OwnerReplayQuotaStatus {
  state: string;
  enabled: boolean;
  used: number;
  limit: number;
  resets_at: string;
}

export interface OwnerProviderKeyStatus {
  state: string;
  active_provider_count: number;
}

export interface OwnerLastDeployedSmoke {
  status: string;
  checked_at: string | null;
  project_id: string | null;
  call_id: string | null;
  golden_trace_id: string | null;
  ci_run_id: string | null;
  detail: string | null;
}

export interface OwnerCaptureDurabilityStatus {
  state: string;
  gateway_count: number;
  unhealthy_gateway_count: number;
  spool_backlog: number;
  spool_oldest_age_seconds: number;
  loss_count: number;
  backpressure_rejections: number;
}

export interface OwnerPricingCostStatus {
  state: string;
  pricing_version: string | null;
  pricing_source: string | null;
  pricing_age_days: number | null;
  cost_confidence: string | null;
  detail: string | null;
}

export interface OwnerBillingStatus {
  state: string;
  plan_code: string;
  subscription_status: string | null;
  current_period_end: string | null;
}

export interface OwnerEventMeteringStatus {
  state: string;
  used: number;
  limit?: number | null;
  overage?: number | null;
  failure_count?: number;
  last_failure_at?: string | null;
}

export interface OwnerBillingProviderVerification {
  state: string;
  provider?: string | null;
  mode?: string;
  checked_at?: string | null;
  provider_event_id?: string | null;
  detail?: string | null;
}

export interface OwnerSupportStatus {
  state: string;
  open_count: number;
  urgent_count: number;
}

export interface OwnerMoneyPathPlatformSummary {
  captures_24h: number;
  issues_open: number;
  replay_runs_7d: number;
  verified_replay_runs_7d: number;
  golden_traces_active: number;
  ci_runs_7d: number;
  ci_blocks_7d: number;
  replay_jobs_pending?: number;
  replay_jobs_stale?: number;
  gateway_unhealthy_tenants?: number;
  gateway_loss_tenants?: number;
  gateway_backpressure_tenants?: number;
  tenants_missing_provider_key: number;
  tenants_near_replay_quota: number;
  tenants_without_recent_capture: number;
  tenants_without_goldens?: number;
  tenants_with_failed_ci?: number;
  tenants_with_stale_replay_workers?: number;
  tenants_with_stale_pricing?: number;
  tenants_with_quota_risk?: number;
  tenants_with_billing_risk?: number;
  metering_failure_tenants?: number;
  event_counter_failure_count?: number;
  billing_launch_blockers?: string[];
  billing_provider_verification?: OwnerBillingProviderVerification;
  support_tickets_open?: number;
  support_tickets_urgent?: number;
  blocked_regressions_7d?: number;
  verified_fixes_7d?: number;
  pricing_contract_drift?: string[];
  launch_blockers?: string[];
  last_deployed_smoke: OwnerLastDeployedSmoke;
}

export interface OwnerMoneyPathTenantRow {
  project_id: string;
  project_name: string;
  plan_code: string;
  last_capture_at: string | null;
  captures_24h: number;
  open_issue_count: number;
  replay_run_count_7d: number;
  verified_replay_count_7d: number;
  golden_trace_count: number;
  ci_run_count_7d: number;
  blocking_ci_failures_7d: number;
  replay_jobs_pending?: number;
  replay_jobs_stale?: number;
  capture_durability_status?: OwnerCaptureDurabilityStatus;
  provider_key_status: OwnerProviderKeyStatus;
  replay_quota_status: OwnerReplayQuotaStatus;
  event_metering_status?: OwnerEventMeteringStatus;
  pricing_cost_status?: OwnerPricingCostStatus;
  billing_status?: OwnerBillingStatus;
  support_status?: OwnerSupportStatus;
  blocked_regressions_7d?: number;
  verified_fixes_7d?: number;
  value_status?: string;
  money_path_breaks?: string[];
  tenant_priority_score?: number;
  launch_blockers?: string[];
  next_owner_action: string;
}

export interface OwnerMoneyPathHealth {
  generated_at: string;
  windows: Record<string, number>;
  platform: OwnerMoneyPathPlatformSummary;
  tenants: OwnerMoneyPathTenantRow[];
}

export interface OwnerLaunchGateEvidence {
  label: string;
  value: string | number | boolean | null;
  status?: string | null;
  detail?: string | null;
}

export interface OwnerLaunchReadinessGate {
  code: string;
  title: string;
  status: "pass" | "fail" | "not_verified" | string;
  summary: string;
  blockers: string[];
  evidence: OwnerLaunchGateEvidence[];
  verification_commands: string[];
}

export interface OwnerLaunchReadiness {
  generated_at: string;
  product_standard: string;
  overall_status: "pass" | "blocked" | "not_verified" | string;
  paid_launch_allowed: boolean;
  gates: OwnerLaunchReadinessGate[];
  hard_blockers: string[];
  verification_commands: string[];
}

export interface OwnerProductionReadinessCheck {
  code: string;
  label: string;
  status: "pass" | "fail" | "warn" | string;
  required_for_launch: boolean;
  detail: string;
}

export interface OwnerProductionReadiness {
  overall_status: "pass" | "blocked" | string;
  app_env: string;
  production_profile: boolean;
  hard_blockers: string[];
  checks: OwnerProductionReadinessCheck[];
  checked_at: string;
}

export interface OwnerUserItem {
  id: string;
  email: string | null;
  github_login: string | null;
  display_name: string | null;
  is_active: boolean;
  created_at: string;
  project_count: number;
}

export interface OwnerUsersResponse {
  users: OwnerUserItem[];
  total: number;
}

export interface OwnerProjectItem {
  id: string;
  name: string;
  owner_ref: string | null;
  is_active: boolean;
  created_at: string;
  call_count: number;
  total_cost_usd: number;
  member_count: number;
}

export interface OwnerProjectsResponse {
  projects: OwnerProjectItem[];
  total: number;
}

export interface UserMembershipItem {
  project_id: string;
  project_name: string;
  role: string;
  is_active: boolean;
  joined_at: string;
}

export interface ProjectMemberItem {
  membership_id: string;
  user_id: string;
  email: string | null;
  github_login: string | null;
  display_name: string | null;
  role: string;
  is_active: boolean;
  joined_at: string;
}

export interface ProjectRateLimitResponse {
  project_id: string;
  overrides: Record<string, unknown>;
  has_override: boolean;
}

export interface ProjectRateLimitUpdate {
  ingest_soft_limit_rpm?: number;
  ingest_burst_limit_rpm?: number;
  ingest_enforce_rate_limit?: boolean;
}

export type PlanGrantPlanCode = "free" | "starter" | "pro";
export type PlanGrantDurationKind = "permanent" | "comp_30d" | "comp_90d";

export interface PlanGrantChallengeRequest {
  org_id: string;
  target_plan_code: PlanGrantPlanCode;
}

export interface PlanGrantChallengeResponse {
  challenge_id: string;
  expires_at: string;
  org_id: string;
  current_plan_code: string | null;
  target_plan_code: PlanGrantPlanCode;
  delivery: "response" | "email" | string;
  dev_code: string | null;
}

export interface PlanGrantCommitRequest {
  challenge_id: string;
  code: string;
  typed_confirmation: string;
  org_id: string;
  target_plan_code: PlanGrantPlanCode;
  reason: string;
  duration_kind: PlanGrantDurationKind;
}

export interface PlanGrantCommitResponse {
  ok: boolean;
  org_id: string;
  previous_plan_code: string | null;
  plan_code: PlanGrantPlanCode;
  duration_kind: PlanGrantDurationKind;
  granted_at: string;
}

export interface PlanGrantAuditItem {
  id: string;
  actor: string | null;
  org_id: string;
  previous_plan_code: string | null;
  plan_code: string | null;
  reason: string | null;
  duration_kind: string | null;
  created_at: string;
}

export interface PlanGrantAuditResponse {
  items: PlanGrantAuditItem[];
}

export interface PricingConfigResponse {
  config: Record<string, unknown>;
  path: string;
  exists: boolean;
}

export interface OwnerPricingPlanPrice {
  label: string;
  monthly_usd: number | null;
  period: string;
}

export interface OwnerPricingPlanPublicLimits {
  calls_per_month: number;
  retention_days: number;
  replay_credits: number;
  golden_traces: number;
  golden_sets: number;
  non_blocking_ci: boolean;
  blocking_ci: boolean;
  provider_key_vault: boolean;
}

export interface OwnerPricingPlan {
  code: string;
  name: string;
  price: OwnerPricingPlanPrice;
  description: string;
  note: string;
  featured: boolean;
  pricing: OwnerPricingPlanPublicLimits;
  enforcement: {
    limits: Record<string, number>;
    entitlements: Record<string, boolean>;
    compatibility: Record<string, unknown>;
  };
}

export interface OwnerPricingPlansResponse {
  schema_version: string;
  source_of_truth: string;
  currency: string;
  unlimited: number;
  canonical_plan_order: string[];
  aliases: Record<string, string>;
  plans: OwnerPricingPlan[];
  drift: string[];
}

export interface RateLimitConfig {
  ingest_soft_limit_rpm: number;
  ingest_burst_limit_rpm: number;
  ingest_rate_limit_window_seconds: number;
  ingest_sustained_breach_threshold: number;
  ingest_backpressure_ttl_seconds: number;
  ingest_enforce_rate_limit: boolean;
  overrides: Record<string, unknown>;
}

export interface AuditLogItem {
  id: string;
  tenant_id: string;
  diagnosis_id: string;
  action: string;
  actor_subject: string | null;
  metadata_json: string;
  created_at: string;
}

export interface AuditLogResponse {
  entries: AuditLogItem[];
  total: number;
}

export interface OwnerBillingPlanBreakdown {
  plan: string;
  slug: string;
  tenant_count: number;
}

export interface OwnerBillingStatusBreakdown {
  status: string;
  count: number;
}

export interface OwnerBillingSummary {
  total_subscriptions: number;
  overdue: number;
  canceled: number;
  by_plan: OwnerBillingPlanBreakdown[];
  by_status: OwnerBillingStatusBreakdown[];
}

export interface OwnerSupportTicketItem {
  ticket_id: string;
  tenant_id: string | null;
  user_id: string | null;
  subject: string | null;
  email: string | null;
  title: string;
  description: string | null;
  category: string | null;
  priority: string;
  status: string;
  assigned_to: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface OwnerSupportTicketsResponse {
  items: OwnerSupportTicketItem[];
  total: number;
}

export interface OwnerSupportMessageItem {
  message_id: string;
  sender_type: string;
  sender_subject: string | null;
  body: string;
  is_internal: boolean;
  created_at: string;
}

export interface OwnerSupportTicketDetailResponse {
  ticket: OwnerSupportTicketItem;
  messages: OwnerSupportMessageItem[];
}

export interface OwnerBillingAccountItem {
  org_id: string;
  project_name: string | null;
  plan_code: string;
  status: string;
  sla_tier: string;
  seats: number;
  current_period_end: string | null;
  trial_end: string | null;
  payment_provider: string;
  payment_customer_ref: string | null;
  payment_subscription_ref: string | null;
  payment_request_ref: string | null;
  payment_dashboard_url: string | null;
  updated_at: string;
}

export interface OwnerBillingAccountsResponse {
  items: OwnerBillingAccountItem[];
  total: number;
}

export interface OwnerBillingPaymentConfirmRequest {
  org_id: string;
  plan_code: string;
  payment_ref: string;
  customer_ref?: string | null;
  payment_request_ref?: string | null;
  current_period_end?: string | null;
  seats?: number | null;
}

export interface OwnerBillingPaymentConfirmResponse {
  ok: boolean;
  org_id: string;
  plan_code: string;
  status: string;
  payment_provider: string;
  payment_subscription_ref: string | null;
  current_period_end: string | null;
}

export interface OwnerBillingRecoveryPendingItem {
  org_id: string;
  project_name: string | null;
  plan_code: string;
  subscription_status: string;
  payment_request_ref: string;
  order_id: string | null;
  requested_plan_code: string | null;
  updated_at: string | null;
  age_seconds: number | null;
  stale: boolean;
}

export interface OwnerBillingRecoveryEvent {
  provider_event_id: string;
  event_type: string;
  result: string;
  affected_org_id: string | null;
  processed_at: string | null;
  payment_id: string | null;
  order_id: string | null;
  plan_code: string | null;
}

export interface OwnerBillingRecoverySummary {
  pending_count: number;
  stale_pending_count: number;
  stale_after_seconds: number;
  oldest_pending_age_seconds: number | null;
  pending_items: OwnerBillingRecoveryPendingItem[];
  recent_reconciled: OwnerBillingRecoveryEvent[];
  last_reconciled_at: string | null;
}

export interface OwnerBillingRecoveryRunRecord {
  org_id: string;
  order_id: string | null;
  plan_code: string | null;
  result: string;
  detail: string;
}

export interface OwnerBillingRecoveryRunResponse {
  examined: number;
  activated: number;
  skipped: number;
  failed: number;
  records: OwnerBillingRecoveryRunRecord[];
}

export interface OwnerRetentionConfig {
  call_retention_days: number | null;
  diagnosis_retention_days: number | null;
  audit_log_retention_days: number | null;
  notification_retention_days: number | null;
  note: string;
}

export type AdminVoteStatus = "below_threshold" | "above_threshold" | "no_votes";

export interface AdminVoteSummary {
  feature_key: string;
  name: string;
  description: string;
  total: number;
  interested: number;
  not_interested: number;
  interested_pct: number;
  ships_after_threshold: number;
  status: AdminVoteStatus;
  last_voted_at: string | null;
}

export interface AdminVoteRow {
  vote_id: string;
  feature_key: string;
  vote: "interested" | "not_interested";
  use_case: string | null;
  user_email_masked: string | null;
  user_subject: string;
  project_id: string;
  project_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminAllFeaturesResponse {
  features: AdminVoteSummary[];
  generated_at: string;
}

export interface AdminFeatureDetailResponse {
  summary: AdminVoteSummary;
  recent_votes: AdminVoteRow[];
  next_cursor: string | null;
}

export function fetchOwnerStats(signal?: AbortSignal): Promise<OwnerStats> {
  return ownerRequest<OwnerStats>("/v1/owner/stats", { signal });
}

export function fetchOwnerHealth(signal?: AbortSignal): Promise<OwnerHealth> {
  return ownerRequest<OwnerHealth>("/v1/owner/health", { signal });
}

export function fetchOwnerInfra(signal?: AbortSignal): Promise<InfraStats> {
  return ownerRequest<InfraStats>("/v1/owner/infra", { signal });
}

export function fetchOwnerMoneyPathHealth(signal?: AbortSignal): Promise<OwnerMoneyPathHealth> {
  return ownerRequest<OwnerMoneyPathHealth>("/v1/owner/money-path-health", { signal });
}

export function fetchOwnerLaunchReadiness(signal?: AbortSignal): Promise<OwnerLaunchReadiness> {
  return ownerRequest<OwnerLaunchReadiness>("/v1/owner/launch-readiness", { signal });
}

export function fetchOwnerProductionReadiness(signal?: AbortSignal): Promise<OwnerProductionReadiness> {
  return ownerRequest<OwnerProductionReadiness>("/v1/owner/production-readiness", { signal });
}

export function fetchOwnerUsers(limit = 100, offset = 0): Promise<OwnerUsersResponse> {
  return ownerRequest<OwnerUsersResponse>(`/v1/owner/users?limit=${limit}&offset=${offset}`);
}

export function fetchOwnerProjects(limit = 100, offset = 0): Promise<OwnerProjectsResponse> {
  return ownerRequest<OwnerProjectsResponse>(`/v1/owner/projects?limit=${limit}&offset=${offset}`);
}

export function fetchOwnerUser(userId: string): Promise<OwnerUserItem> {
  return ownerRequest<OwnerUserItem>(`/v1/owner/users/${encodeURIComponent(userId)}`);
}

export function fetchUserMemberships(userId: string): Promise<{ memberships: UserMembershipItem[] }> {
  return ownerRequest<{ memberships: UserMembershipItem[] }>(
    `/v1/owner/users/${encodeURIComponent(userId)}/memberships`,
  );
}

export async function setUserStatus(userId: string, isActive: boolean, reason?: string): Promise<void> {
  await ownerRequest<unknown>(`/v1/owner/users/${encodeURIComponent(userId)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive, reason }),
  });
}

export async function anonymizeOwnerUser(userId: string): Promise<void> {
  await ownerRequest<unknown>(`/v1/owner/users/${encodeURIComponent(userId)}/anonymize`, {
    method: "POST",
  });
}

export async function deleteOwnerUser(userId: string): Promise<void> {
  await ownerRequest<unknown>(`/v1/owner/users/${encodeURIComponent(userId)}?confirm=DELETE_CONFIRMED`, {
    method: "DELETE",
  });
}

export function fetchOwnerProject(projectId: string): Promise<OwnerProjectItem> {
  return ownerRequest<OwnerProjectItem>(`/v1/owner/projects/${encodeURIComponent(projectId)}`);
}

export function fetchProjectMembers(projectId: string): Promise<{ members: ProjectMemberItem[] }> {
  return ownerRequest<{ members: ProjectMemberItem[] }>(
    `/v1/owner/projects/${encodeURIComponent(projectId)}/members`,
  );
}

export async function setProjectStatus(projectId: string, isActive: boolean, reason?: string): Promise<void> {
  await ownerRequest<unknown>(`/v1/owner/projects/${encodeURIComponent(projectId)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive, reason }),
  });
}

export function fetchProjectRateLimit(projectId: string): Promise<ProjectRateLimitResponse> {
  return ownerRequest<ProjectRateLimitResponse>(`/v1/owner/projects/${encodeURIComponent(projectId)}/rate-limit`);
}

export async function setProjectRateLimit(projectId: string, body: ProjectRateLimitUpdate): Promise<void> {
  await ownerRequest<unknown>(`/v1/owner/projects/${encodeURIComponent(projectId)}/rate-limit`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function clearProjectRateLimit(projectId: string): Promise<void> {
  await ownerRequest<unknown>(`/v1/owner/projects/${encodeURIComponent(projectId)}/rate-limit`, {
    method: "DELETE",
  });
}

export function createOwnerPlanGrantChallenge(
  body: PlanGrantChallengeRequest,
): Promise<PlanGrantChallengeResponse> {
  return ownerRequest<PlanGrantChallengeResponse>("/v1/owner/plan-grants/challenge", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function commitOwnerPlanGrant(body: PlanGrantCommitRequest): Promise<PlanGrantCommitResponse> {
  return ownerRequest<PlanGrantCommitResponse>("/v1/owner/plan-grants", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchOwnerPlanGrantAudit(
  opts: { org_id?: string; limit?: number } = {},
): Promise<PlanGrantAuditResponse> {
  const params = new URLSearchParams();
  if (opts.org_id) params.set("org_id", opts.org_id);
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return ownerRequest<PlanGrantAuditResponse>(`/v1/owner/plan-grants/audit${qs ? `?${qs}` : ""}`);
}

export async function setMaintenanceMode(enabled: boolean, message?: string): Promise<void> {
  await ownerRequest<unknown>("/v1/owner/maintenance", {
    method: "POST",
    body: JSON.stringify({ enabled, message }),
  });
}

export function fetchOwnerPricing(): Promise<PricingConfigResponse> {
  return ownerRequest<PricingConfigResponse>("/v1/owner/pricing");
}

export function fetchOwnerPricingPlans(signal?: AbortSignal): Promise<OwnerPricingPlansResponse> {
  return ownerRequest<OwnerPricingPlansResponse>("/v1/owner/pricing/plans", { signal });
}

export async function updateOwnerPricing(config: Record<string, unknown>): Promise<PricingConfigResponse> {
  return ownerRequest<PricingConfigResponse>("/v1/owner/pricing", {
    method: "PUT",
    body: JSON.stringify({ config }),
  });
}

export function fetchRateLimits(): Promise<RateLimitConfig> {
  return ownerRequest<RateLimitConfig>("/v1/owner/rate-limits");
}

export async function setRateLimitOverrides(overrides: Record<string, unknown>): Promise<void> {
  await ownerRequest<unknown>("/v1/owner/rate-limits/overrides", {
    method: "PUT",
    body: JSON.stringify({ overrides }),
  });
}

export async function clearRateLimitOverrides(): Promise<void> {
  await ownerRequest<unknown>("/v1/owner/rate-limits/overrides", { method: "DELETE" });
}

export function fetchAuditLog(
  opts: { limit?: number; offset?: number; action?: string; tenant_id?: string } = {},
): Promise<AuditLogResponse> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts.offset !== undefined) params.set("offset", String(opts.offset));
  if (opts.action) params.set("action", opts.action);
  if (opts.tenant_id) params.set("tenant_id", opts.tenant_id);
  const qs = params.toString();
  return ownerRequest<AuditLogResponse>(`/v1/owner/audit-log${qs ? `?${qs}` : ""}`);
}

export function fetchOwnerBillingSummary(): Promise<OwnerBillingSummary> {
  return ownerRequest<OwnerBillingSummary>("/v1/owner/billing/summary");
}

export function fetchOwnerSupportTickets(
  opts: { status?: string; priority?: string; tenant_id?: string; assigned_to?: string; limit?: number; offset?: number } = {},
): Promise<OwnerSupportTicketsResponse> {
  const params = new URLSearchParams();
  if (opts.status) params.set("status", opts.status);
  if (opts.priority) params.set("priority", opts.priority);
  if (opts.tenant_id) params.set("tenant_id", opts.tenant_id);
  if (opts.assigned_to) params.set("assigned_to", opts.assigned_to);
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts.offset !== undefined) params.set("offset", String(opts.offset));
  const qs = params.toString();
  return ownerRequest<OwnerSupportTicketsResponse>(`/v1/owner/support/tickets${qs ? `?${qs}` : ""}`);
}

export function fetchOwnerSupportTicket(ticketId: string): Promise<OwnerSupportTicketDetailResponse> {
  return ownerRequest<OwnerSupportTicketDetailResponse>(`/v1/owner/support/tickets/${encodeURIComponent(ticketId)}`);
}

export async function updateOwnerSupportTicket(
  ticketId: string,
  body: { status?: string; priority?: string; assigned_to?: string },
): Promise<void> {
  await ownerRequest<unknown>(`/v1/owner/support/tickets/${encodeURIComponent(ticketId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function replyOwnerSupportTicket(
  ticketId: string,
  body: { body: string; is_internal?: boolean },
): Promise<void> {
  await ownerRequest<unknown>(`/v1/owner/support/tickets/${encodeURIComponent(ticketId)}/reply`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchOwnerRetention(): Promise<OwnerRetentionConfig> {
  return ownerRequest<OwnerRetentionConfig>("/v1/owner/retention");
}

export function fetchOwnerBillingAccounts(
  opts: { status?: string; plan_code?: string; limit?: number; offset?: number } = {},
): Promise<OwnerBillingAccountsResponse> {
  const params = new URLSearchParams();
  if (opts.status) params.set("status", opts.status);
  if (opts.plan_code) params.set("plan_code", opts.plan_code);
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts.offset !== undefined) params.set("offset", String(opts.offset));
  const qs = params.toString();
  return ownerRequest<OwnerBillingAccountsResponse>(`/v1/owner/billing/accounts${qs ? `?${qs}` : ""}`);
}

export function fetchOwnerBillingRecovery(signal?: AbortSignal): Promise<OwnerBillingRecoverySummary> {
  return ownerRequest<OwnerBillingRecoverySummary>("/v1/owner/billing/payment-recovery", { signal });
}

export function runOwnerBillingRecovery(limit = 50): Promise<OwnerBillingRecoveryRunResponse> {
  return ownerRequest<OwnerBillingRecoveryRunResponse>(`/v1/owner/billing/payments/reconcile?limit=${limit}`, {
    method: "POST",
  });
}

export function confirmOwnerRazorpayPayment(
  body: OwnerBillingPaymentConfirmRequest,
): Promise<OwnerBillingPaymentConfirmResponse> {
  return ownerRequest<OwnerBillingPaymentConfirmResponse>("/v1/owner/billing/payments/confirm", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchPlatformLlmUsageSummary(signal?: AbortSignal): Promise<PlatformLlmUsageSummaryResponse> {
  return ownerRequest<PlatformLlmUsageSummaryResponse>("/v1/owner/platform-llm-usage", { signal });
}

export function fetchFeatureFlags(signal?: AbortSignal): Promise<FeatureFlagListResponse> {
  return ownerRequest<FeatureFlagListResponse>("/v1/feature-flags/admin", { signal });
}

export function createOwnerFeatureFlag(body: {
  key: string;
  description?: string;
  enabled_globally?: boolean;
}): Promise<FeatureFlag> {
  return ownerRequest<FeatureFlag>("/v1/feature-flags/admin", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateOwnerFeatureFlag(
  flagId: string,
  body: {
    description?: string;
    enabled_globally?: boolean;
    add_enabled_tenants?: string[];
    remove_enabled_tenants?: string[];
    add_disabled_tenants?: string[];
    remove_disabled_tenants?: string[];
  },
): Promise<FeatureFlag> {
  return ownerRequest<FeatureFlag>(`/v1/feature-flags/admin/${encodeURIComponent(flagId)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function deleteOwnerFeatureFlag(flagId: string): Promise<void> {
  await ownerRequest<void>(`/v1/feature-flags/admin/${encodeURIComponent(flagId)}`, {
    method: "DELETE",
  });
}

export async function verifyOwnerToken(token: string): Promise<boolean> {
  try {
    const res = await fetch("/api/owner/session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token }),
      cache: "no-store",
      credentials: "same-origin",
    });
    if (res.ok) {
      setOwnerToken(token);
      return true;
    }
    clearOwnerToken();
    return false;
  } catch {
    return false;
  }
}

export async function verifyOwnerSession(): Promise<boolean> {
  try {
    const res = await fetch("/api/owner/session", {
      method: "GET",
      cache: "no-store",
      credentials: "same-origin",
    });
    if (res.ok) {
      setOwnerToken("active");
      return true;
    }
    clearOwnerToken();
    return false;
  } catch {
    return false;
  }
}

export function fetchFeatureInterestList(signal?: AbortSignal): Promise<AdminAllFeaturesResponse> {
  return ownerRequest<AdminAllFeaturesResponse>("/v1/admin/feature-interest", { signal });
}

export function fetchFeatureInterestDetail(
  featureKey: string,
  opts: { limit?: number; vote?: "interested" | "not_interested" | "" } = {},
  signal?: AbortSignal,
): Promise<AdminFeatureDetailResponse> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts.vote) params.set("vote", opts.vote);
  const qs = params.toString();
  return ownerRequest<AdminFeatureDetailResponse>(
    `/v1/admin/feature-interest/${encodeURIComponent(featureKey)}${qs ? `?${qs}` : ""}`,
    { signal },
  );
}

export function featureInterestExportUrl(featureKey: string): string {
  return `${BASE}/v1/admin/feature-interest/${encodeURIComponent(featureKey)}/export.csv`;
}
