// Owner Dashboard API — uses PROVISIONING_TOKEN stored in sessionStorage
// Sends it as x-zroky-admin-token header (forwarded by the Next.js proxy)

const BASE = "/api/zroky";
const TOKEN_KEY = "zroky_owner_token";

export function getOwnerToken(): string {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem(TOKEN_KEY) ?? "";
}

export function setOwnerToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearOwnerToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

async function ownerRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getOwnerToken();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      "x-zroky-admin-token": token,
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (res.status === 401) {
    clearOwnerToken();
    throw new Error("UNAUTHORIZED");
  }
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ─── Types ───────────────────────────────────────────────────────────────────

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

// ─── API functions ────────────────────────────────────────────────────────────

export function fetchOwnerStats(signal?: AbortSignal): Promise<OwnerStats> {
  return ownerRequest<OwnerStats>("/v1/owner/stats", { signal });
}

export function fetchOwnerHealth(signal?: AbortSignal): Promise<OwnerHealth> {
  return ownerRequest<OwnerHealth>("/v1/owner/health", { signal });
}

export function fetchOwnerInfra(signal?: AbortSignal): Promise<InfraStats> {
  return ownerRequest<InfraStats>("/v1/owner/infra", { signal });
}

export function fetchOwnerUsers(limit = 100, offset = 0): Promise<OwnerUsersResponse> {
  return ownerRequest<OwnerUsersResponse>(`/v1/owner/users?limit=${limit}&offset=${offset}`);
}

export function fetchOwnerProjects(limit = 100, offset = 0): Promise<OwnerProjectsResponse> {
  return ownerRequest<OwnerProjectsResponse>(`/v1/owner/projects?limit=${limit}&offset=${offset}`);
}

export function fetchOwnerUser(userId: string): Promise<OwnerUserItem> {
  return ownerRequest<OwnerUserItem>(`/v1/owner/users/${userId}`);
}

export function fetchUserMemberships(userId: string): Promise<{ memberships: UserMembershipItem[] }> {
  return ownerRequest<{ memberships: UserMembershipItem[] }>(`/v1/owner/users/${userId}/memberships`);
}

export async function setUserStatus(userId: string, isActive: boolean, reason?: string): Promise<void> {
  await ownerRequest<unknown>(`/v1/owner/users/${userId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive, reason }),
  });
}

export function fetchOwnerProject(projectId: string): Promise<OwnerProjectItem> {
  return ownerRequest<OwnerProjectItem>(`/v1/owner/projects/${projectId}`);
}

export function fetchProjectMembers(projectId: string): Promise<{ members: ProjectMemberItem[] }> {
  return ownerRequest<{ members: ProjectMemberItem[] }>(`/v1/owner/projects/${projectId}/members`);
}

export async function setProjectStatus(projectId: string, isActive: boolean, reason?: string): Promise<void> {
  await ownerRequest<unknown>(`/v1/owner/projects/${projectId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive, reason }),
  });
}

export async function setMaintenanceMode(enabled: boolean, message?: string): Promise<void> {
  await ownerRequest<unknown>("/v1/owner/maintenance", {
    method: "POST",
    body: JSON.stringify({ enabled, message }),
  });
}

export interface PricingConfigResponse {
  config: Record<string, unknown>;
  path: string;
  exists: boolean;
}

export function fetchOwnerPricing(): Promise<PricingConfigResponse> {
  return ownerRequest<PricingConfigResponse>("/v1/owner/pricing");
}

export async function updateOwnerPricing(config: Record<string, unknown>): Promise<PricingConfigResponse> {
  return ownerRequest<PricingConfigResponse>("/v1/owner/pricing", {
    method: "PUT",
    body: JSON.stringify({ config }),
  });
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
  title: string;
  category: string | null;
  priority: string;
  status: string;
  assigned_to: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface OwnerSupportTicketsResponse {
  items: OwnerSupportTicketItem[];
  total: number;
}

export function fetchAuditLog(
  opts: { limit?: number; offset?: number; action?: string; tenant_id?: string } = {}
): Promise<AuditLogResponse> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts.offset !== undefined) params.set("offset", String(opts.offset));
  if (opts.action) params.set("action", opts.action);
  if (opts.tenant_id) params.set("tenant_id", opts.tenant_id);
  const qs = params.toString();
  return ownerRequest<AuditLogResponse>(`/v1/owner/audit-log${qs ? "?" + qs : ""}`);
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
  return ownerRequest<OwnerSupportTicketsResponse>(`/v1/owner/support/tickets${qs ? "?" + qs : ""}`);
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

/** Ping /v1/owner/stats with the given token to verify it works */
export async function verifyOwnerToken(token: string): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/v1/owner/stats`, {
      headers: { "x-zroky-admin-token": token },
      cache: "no-store",
    });
    return res.ok;
  } catch {
    return false;
  }
}

// ─── Feature-interest voting (Module 9 smoke-test) ──────────────────────────

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

export function fetchFeatureInterestList(
  signal?: AbortSignal,
): Promise<AdminAllFeaturesResponse> {
  return ownerRequest<AdminAllFeaturesResponse>(
    "/v1/admin/feature-interest",
    { signal },
  );
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
    `/v1/admin/feature-interest/${encodeURIComponent(featureKey)}${qs ? "?" + qs : ""}`,
    { signal },
  );
}

/** URL to the CSV export endpoint (browser navigates to download). */
export function featureInterestExportUrl(featureKey: string): string {
  return `${BASE}/v1/admin/feature-interest/${encodeURIComponent(featureKey)}/export.csv`;
}
