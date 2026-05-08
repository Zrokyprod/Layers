import type {
  AlertChannel,
  AlertChannelTestResponse,
  AlertItemResponse,
  AlertListResponse,
  ActivityFeedResponse,
  AnalyticsSummaryResponse,
  AuthTokenResponse,
  ApiKeyCreateResponse,
  ApiKeyResponse,
  BudgetConfigResponse,
  BudgetStatusResponse,
  CacheSavingsResponse,
  CallTraceTreeResponse,
  CallDetailResponse,
  CallListResponse,
  CostBreakdownResponse,
  CostDailyTrendResponse,
  CostHourlyResponse,
  CostTopCallsResponse,
  DiagnosisFeedbackResponse,
  DiagnosisGeneratePrResponse,
  DiagnosisFixCopiedResponse,
  DiagnosisFixWatchResponse,
  DiagnosisUiStateResponse,
  DiagnosisPrLinkResponse,
  AuthSummaryResponse,
  LoopIncidentsResponse,
  LoopSummaryResponse,
  TraceListResponse,
  DiagnosisResolveResponse,
  DiagnosisShareCreateResponse,
  DiagnosisShareReadResponse,
  ExportResponse,
  FixAnalyticsResponse,
  MeResponse,
  NotificationSettingsResponse,
  OnboardingTriggerResponse,
  PiiDetectorTestResponse,
  PiiPolicyResponse,
  PricingInterviewNote,
  PricingValidationResponse,
  ProjectResponse,
  ProjectMemberListResponse,
  ProjectInviteResponse,
  ProjectMembershipResponse,
  ProviderVerificationListResponse,
  ProviderVerificationTestResponse,
  ReasoningShareResponse,
  RollbackDrillResponse,
  RollbackDrillVerificationResponse,
  RetentionDataErasureResponse,
  RetentionPolicyResponse,
  HealthScoreResponse,
  GithubConnectionStatusResponse,
  CostForecastResponse,
  CostAnomalyRiskResponse,
  ChangePasswordResponse,
  ProjectInvitationItem,
  AcceptInvitationResponse,
  NotificationListResponse,
  MarkReadResponse,
  MarkAllReadResponse,
  PlatformLlmUsageSummaryResponse,
  SubscriptionPlanListResponse,
  TenantSubscription,
  BillingUsageSummary,
  SupportTicketItem,
  SupportTicketListResponse,
  SupportTicketDetailResponse,
  SupportMessageItem,
  FeatureFlagListResponse,
  FeatureFlag,
  TenantFeatureFlagsResponse,
} from "@/lib/types";
import {
  clearAuthSession,
  readAccessTokenFromBrowser,
  readRefreshTokenFromBrowser,
  storeAuthSession,
} from "@/lib/auth";

type Method = "GET" | "POST" | "PUT" | "DELETE" | "PATCH";

type RequestOptions = {
  method?: Method;
  query?: Record<string, string | number | undefined | null>;
  body?: unknown;
  signal?: AbortSignal;
};

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`/api/zroky${path}`, "http://local.zroky");
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value == null || value === "") {
        continue;
      }
      url.searchParams.set(key, String(value));
    }
  }
  return `${url.pathname}${url.search}`;
}

function buildAuthHeader(token: string): string {
  return token.toLowerCase().startsWith("bearer ") ? token : `Bearer ${token}`;
}

async function refreshAuthSession(): Promise<boolean> {
  const refreshToken = readRefreshTokenFromBrowser();
  if (!refreshToken) {
    return false;  // no token in storage — don't clear session, just fail silently
  }

  try {
    const response = await fetch(buildUrl("/v1/auth/refresh"), {
      method: "POST",
      cache: "no-store",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      if (response.status === 401) {
        clearAuthSession(); // refresh token genuinely rejected — log out
      }
      return false;
    }

    const payload = (await response.json()) as AuthTokenResponse;
    if (!payload.access_token || !payload.refresh_token) {
      return false;
    }

    void storeAuthSession(payload);
    return true;
  } catch {
    return false;
  }
}

function buildError(method: Method, path: string, status: number, detail: string | null): Error {
  const message = detail && detail.trim() ? detail : `${method} ${path} failed (${status})`;
  return new Error(message);
}

async function parseErrorDetail(response: Response): Promise<string | null> {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
  } catch {
    const text = await response.text();
    if (text.trim()) {
      return text;
    }
  }
  return null;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const url = buildUrl(path, options.query);

  const performRequest = async (): Promise<Response> => {
    const token = readAccessTokenFromBrowser();
    const headers: Record<string, string> = {};
    if (options.body != null) {
      headers["content-type"] = "application/json";
    }
    if (token) {
      headers.authorization = buildAuthHeader(token);
    }

    return fetch(url, {
      method,
      cache: "no-store",
      headers: Object.keys(headers).length > 0 ? headers : undefined,
      body: options.body != null ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  };

  let response = await performRequest();

  const canRefresh = !path.startsWith("/v1/auth/") && response.status === 401;
  if (canRefresh) {
    const refreshed = await refreshAuthSession();
    if (refreshed) {
      response = await performRequest();
    }
    // If refresh failed, let the original 401 bubble up as an error — don't force logout
  }

  if (!response.ok) {
    const detail = await parseErrorDetail(response);
    throw buildError(method, path, response.status, detail);
  }

  return (await response.json()) as T;
}

export function loginWithPassword(email: string, password: string): Promise<AuthTokenResponse> {
  return request<AuthTokenResponse>("/v1/auth/login", {
    method: "POST",
    body: {
      email,
      password,
    },
  });
}

export function registerWithPassword(
  email: string,
  password: string,
  confirmPassword: string,
): Promise<AuthTokenResponse> {
  return request<AuthTokenResponse>("/v1/auth/register", {
    method: "POST",
    body: {
      email,
      password,
      confirm_password: confirmPassword,
    },
  });
}

export function verifyEmail(token: string): Promise<{ detail: string }> {
  return request<{ detail: string }>(`/v1/auth/verify-email?token=${encodeURIComponent(token)}`, {
    method: "GET",
  });
}

export function resendVerification(): Promise<{ detail: string }> {
  return request<{ detail: string }>("/v1/auth/resend-verification", {
    method: "POST",
  });
}

export function forgotPassword(email: string): Promise<{ message: string }> {
  return request<{ message: string }>("/v1/auth/forgot-password", {
    method: "POST",
    body: { email },
  });
}

export function resetPassword(token: string, newPassword: string): Promise<{ message: string }> {
  return request<{ message: string }>("/v1/auth/reset-password", {
    method: "POST",
    body: { token, new_password: newPassword },
  });
}

export function completeGithubLogin(code: string, state: string): Promise<AuthTokenResponse> {
  return request<AuthTokenResponse>("/v1/auth/github/callback", {
    query: {
      code,
      state,
    },
  });
}

export function getAnalyticsSummary(windowDays = 1, signal?: AbortSignal): Promise<AnalyticsSummaryResponse> {
  return request<AnalyticsSummaryResponse>("/v1/analytics/summary", {
    query: { window_days: windowDays },
    signal,
  });
}

export function getHealthScore(signal?: AbortSignal): Promise<HealthScoreResponse> {
  return request<HealthScoreResponse>("/v1/analytics/health-score", { signal });
}

export function getFixAnalytics(days = 30, signal?: AbortSignal): Promise<FixAnalyticsResponse> {
  return request<FixAnalyticsResponse>("/v1/analytics/fixes", {
    query: { days },
    signal,
  });
}

export function getActivityFeed(
  query: {
    action?: string;
    limit?: number;
    offset?: number;
  },
  signal?: AbortSignal,
): Promise<ActivityFeedResponse> {
  return request<ActivityFeedResponse>("/v1/analytics/activity-feed", {
    query,
    signal,
  });
}

export function getCostDailyTrend(days = 14, signal?: AbortSignal): Promise<CostDailyTrendResponse> {
  return request<CostDailyTrendResponse>("/v1/analytics/cost/daily-trend", {
    query: { days },
    signal,
  });
}

export function getCostByModel(days = 14, signal?: AbortSignal): Promise<CostBreakdownResponse> {
  return request<CostBreakdownResponse>("/v1/analytics/cost/by-model", {
    query: { days },
    signal,
  });
}

export function getCostByUser(days = 14, signal?: AbortSignal): Promise<CostBreakdownResponse> {
  return request<CostBreakdownResponse>("/v1/analytics/cost/by-user", {
    query: { days },
    signal,
  });
}

export function getReasoningShare(days = 14, signal?: AbortSignal): Promise<ReasoningShareResponse> {
  return request<ReasoningShareResponse>("/v1/analytics/cost/reasoning-share", {
    query: { days },
    signal,
  });
}

export function getCacheSavings(days = 14, signal?: AbortSignal): Promise<CacheSavingsResponse> {
  return request<CacheSavingsResponse>("/v1/analytics/cost/cache-savings", {
    query: { days },
    signal,
  });
}

export function getBudget(signal?: AbortSignal): Promise<BudgetConfigResponse> {
  return request<BudgetConfigResponse>("/v1/analytics/budget", { signal });
}

export function updateBudget(monthly_limit_usd: number | null, threshold_percentage: number): Promise<BudgetConfigResponse> {
  return request<BudgetConfigResponse>("/v1/analytics/budget", {
    method: "PUT",
    body: {
      monthly_limit_usd,
      threshold_percentage,
    },
  });
}

export function getBudgetStatus(signal?: AbortSignal): Promise<BudgetStatusResponse> {
  return request<BudgetStatusResponse>("/v1/analytics/budget/status", { signal });
}

export function getCostTopCalls(limit = 10, hours = 168, signal?: AbortSignal): Promise<CostTopCallsResponse> {
  return request<CostTopCallsResponse>("/v1/analytics/cost/top-calls", {
    query: { limit, hours },
    signal,
  });
}

export function getCostByAgent(days = 14, signal?: AbortSignal): Promise<CostBreakdownResponse> {
  return request<CostBreakdownResponse>("/v1/analytics/cost/by-agent", {
    query: { days },
    signal,
  });
}

export function getCostHourly(hours = 48, signal?: AbortSignal): Promise<CostHourlyResponse> {
  return request<CostHourlyResponse>("/v1/analytics/cost/hourly", {
    query: { hours },
    signal,
  });
}

export function getLoopSummary(days = 7, signal?: AbortSignal): Promise<LoopSummaryResponse> {
  return request<LoopSummaryResponse>("/v1/analytics/loops/summary", {
    query: { days },
    signal,
  });
}

export function getLoopIncidents(
  opts: { days?: number; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<LoopIncidentsResponse> {
  return request<LoopIncidentsResponse>("/v1/analytics/loops/incidents", {
    query: { days: opts.days ?? 30, limit: opts.limit ?? 50, offset: opts.offset ?? 0 },
    signal,
  });
}

export function getAuthSummary(hours = 24, signal?: AbortSignal): Promise<AuthSummaryResponse> {
  return request<AuthSummaryResponse>("/v1/analytics/auth/summary", {
    query: { hours },
    signal,
  });
}

export function listCalls(
  query: {
    status?: string;
    model?: string;
    user_id?: string;
    user?: string;
    call_type?: string;
    agent_name?: string;
    sort_by?: string;
    sort_order?: string;
    start_time?: string;
    end_time?: string;
    limit?: number;
    offset?: number;
  },
  signal?: AbortSignal,
): Promise<CallListResponse> {
  return request<CallListResponse>("/v1/calls", { query, signal });
}

export function exportCallsCsv(
  query: {
    status?: string;
    model?: string;
    user_id?: string;
    call_type?: string;
    agent_name?: string;
    start_time?: string;
    end_time?: string;
  },
): void {
  const url = buildUrl("/v1/calls/export/csv", query);
  const a = document.createElement("a");
  a.href = url;
  a.download = "calls.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

export async function exportCallsJson(
  query: {
    status?: string;
    model?: string;
    user_id?: string;
    call_type?: string;
    agent_name?: string;
    start_time?: string;
    end_time?: string;
    sort_by?: string;
    sort_order?: string;
  },
): Promise<void> {
  const pageSize = 200;
  const maxRows = 2000;
  let offset = 0;
  let total = 0;
  const items: CallListResponse["items"] = [];

  while (items.length < maxRows) {
    const page = await listCalls({
      ...query,
      limit: Math.min(pageSize, maxRows - items.length),
      offset,
    });
    total = page.total;
    items.push(...page.items);
    offset += page.items.length;
    if (page.items.length === 0 || offset >= total) {
      break;
    }
  }

  const blob = new Blob(
    [JSON.stringify({
      exported_at: new Date().toISOString(),
      row_count: items.length,
      total_available: total,
      truncated: total > items.length,
      filters: query,
      items,
    }, null, 2)],
    { type: "application/json" },
  );

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "calls.json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function getCallDetail(callId: string, signal?: AbortSignal): Promise<CallDetailResponse> {
  return request<CallDetailResponse>(`/v1/calls/${encodeURIComponent(callId)}`, { signal });
}

export function getCallTraceTree(callId: string, signal?: AbortSignal): Promise<CallTraceTreeResponse> {
  return request<CallTraceTreeResponse>(`/v1/calls/${encodeURIComponent(callId)}/trace-tree`, { signal });
}

export function getRecentTraces(days = 7, limit = 20, signal?: AbortSignal): Promise<TraceListResponse> {
  return request<TraceListResponse>(`/v1/analytics/traces/recent?days=${days}&limit=${limit}`, { signal });
}

export function getTraceById(traceId: string, days = 30, signal?: AbortSignal): Promise<TraceListItem> {
  return request<TraceListItem>(`/v1/analytics/traces/${encodeURIComponent(traceId)}?days=${days}`, { signal });
}

export function submitDiagnosisFeedback(
  diagnosisId: string,
  body: {
    was_helpful: boolean;
    developer_note?: string;
  },
): Promise<DiagnosisFeedbackResponse> {
  return request<DiagnosisFeedbackResponse>(`/v1/diagnosis/${encodeURIComponent(diagnosisId)}/feedback`, {
    method: "POST",
    body,
  });
}

export function markDiagnosisFixCopied(diagnosisId: string): Promise<DiagnosisFixCopiedResponse> {
  return request<DiagnosisFixCopiedResponse>(`/v1/diagnosis/${encodeURIComponent(diagnosisId)}/fix-copied`, {
    method: "POST",
  });
}

export function createShareLink(diagnosisId: string): Promise<DiagnosisShareCreateResponse> {
  return request<DiagnosisShareCreateResponse>(`/v1/diagnosis/${encodeURIComponent(diagnosisId)}/share`, {
    method: "POST",
  });
}

export function resolveDiagnosis(diagnosisId: string): Promise<DiagnosisResolveResponse> {
  return request<DiagnosisResolveResponse>(`/v1/diagnosis/${encodeURIComponent(diagnosisId)}/resolve`, {
    method: "POST",
  });
}

export function getDiagnosisFixWatch(diagnosisId: string, signal?: AbortSignal): Promise<DiagnosisFixWatchResponse> {
  return request<DiagnosisFixWatchResponse>(`/v1/diagnosis/${encodeURIComponent(diagnosisId)}/fix-watch`, { signal });
}

export function getDiagnosisState(diagnosisId: string, signal?: AbortSignal): Promise<DiagnosisUiStateResponse> {
  return request<DiagnosisUiStateResponse>(`/v1/diagnosis/${encodeURIComponent(diagnosisId)}/state`, { signal });
}

export function setDiagnosisAssignment(diagnosisId: string, assigned_subject: string | null): Promise<DiagnosisUiStateResponse> {
  return request<DiagnosisUiStateResponse>(`/v1/diagnosis/${encodeURIComponent(diagnosisId)}/assignment`, {
    method: "POST",
    body: { assigned_subject },
  });
}

export function setDiagnosisSnooze(diagnosisId: string, snoozed_until: string | null): Promise<DiagnosisUiStateResponse> {
  return request<DiagnosisUiStateResponse>(`/v1/diagnosis/${encodeURIComponent(diagnosisId)}/snooze`, {
    method: "POST",
    body: { snoozed_until },
  });
}

export function setDiagnosisDismissed(diagnosisId: string, dismissed: boolean): Promise<DiagnosisUiStateResponse> {
  return request<DiagnosisUiStateResponse>(`/v1/diagnosis/${encodeURIComponent(diagnosisId)}/dismiss`, {
    method: "POST",
    body: { dismissed },
  });
}

export function generateDiagnosisPr(
  diagnosisId: string,
  body: {
    repository_owner?: string;
    repository_name?: string;
    base_branch?: string;
  },
): Promise<DiagnosisGeneratePrResponse> {
  return request<DiagnosisGeneratePrResponse>(`/v1/diagnosis/${encodeURIComponent(diagnosisId)}/generate-pr`, {
    method: "POST",
    body,
  });
}

export function listDiagnosisPrLinks(diagnosisId: string, signal?: AbortSignal): Promise<DiagnosisPrLinkResponse[]> {
  return request<DiagnosisPrLinkResponse[]>(`/v1/diagnosis/${encodeURIComponent(diagnosisId)}/prs`, { signal });
}

export function listAlerts(
  query: {
    status?: string;
    severity?: string;
    category?: string;
    limit?: number;
    offset?: number;
  },
  signal?: AbortSignal,
): Promise<AlertListResponse> {
  return request<AlertListResponse>("/v1/alerts", {
    query,
    signal,
  });
}

export function getAlertDetail(alertId: string, signal?: AbortSignal): Promise<AlertItemResponse> {
  return request<AlertItemResponse>(`/v1/alerts/${encodeURIComponent(alertId)}`, { signal });
}

export function acknowledgeAlert(alertId: string): Promise<AlertItemResponse> {
  return request<AlertItemResponse>(`/v1/alerts/${encodeURIComponent(alertId)}/acknowledge`, {
    method: "POST",
  });
}

export function resolveAlert(alertId: string): Promise<AlertItemResponse> {
  return request<AlertItemResponse>(`/v1/alerts/${encodeURIComponent(alertId)}/resolve`, {
    method: "POST",
  });
}

export function reopenAlert(alertId: string): Promise<AlertItemResponse> {
  return request<AlertItemResponse>(`/v1/alerts/${encodeURIComponent(alertId)}/reopen`, {
    method: "POST",
  });
}

export function testAlertChannel(channel: AlertChannel): Promise<AlertChannelTestResponse> {
  return request<AlertChannelTestResponse>("/v1/alerts/channel-test", {
    method: "POST",
    body: { channel },
  });
}

export function triggerOnboardingFailure(
  category: "TOKEN_OVERFLOW" | "RATE_LIMIT" | "AUTH_FAILURE" | "LOOP_DETECTED" | "COST_SPIKE",
): Promise<OnboardingTriggerResponse> {
  return request<OnboardingTriggerResponse>("/v1/onboarding/trigger-test-failure", {
    method: "POST",
    body: { category },
  });
}

export function getProjectSettings(signal?: AbortSignal): Promise<ProjectResponse> {
  return request<ProjectResponse>("/v1/settings/project", { signal });
}

export function getPiiPolicy(signal?: AbortSignal): Promise<PiiPolicyResponse> {
  return request<PiiPolicyResponse>("/v1/settings/pii-policy", { signal });
}

export function updatePiiPolicy(custom_patterns: string[]): Promise<PiiPolicyResponse> {
  return request<PiiPolicyResponse>("/v1/settings/pii-policy", {
    method: "PUT",
    body: { custom_patterns },
  });
}

export function testPiiDetector(pattern: string, sample_text: string): Promise<PiiDetectorTestResponse> {
  return request<PiiDetectorTestResponse>("/v1/settings/pii-policy/test-detector", {
    method: "POST",
    body: { pattern, sample_text },
  });
}

export function getRetention(signal?: AbortSignal): Promise<RetentionPolicyResponse> {
  return request<RetentionPolicyResponse>("/v1/settings/retention", { signal });
}

export function updateRetention(retention_days: number): Promise<RetentionPolicyResponse> {
  return request<RetentionPolicyResponse>("/v1/settings/retention", {
    method: "PUT",
    body: { retention_days },
  });
}

export function eraseRetentionData(query?: {
  dry_run?: boolean;
  batch_size?: number;
}): Promise<RetentionDataErasureResponse> {
  return request<RetentionDataErasureResponse>("/v1/settings/retention/data", {
    method: "DELETE",
    query: {
      dry_run: query?.dry_run == null ? undefined : query.dry_run ? "true" : "false",
      batch_size: query?.batch_size,
    },
  });
}

export function getNotifications(signal?: AbortSignal): Promise<NotificationSettingsResponse> {
  return request<NotificationSettingsResponse>("/v1/settings/notifications", { signal });
}

export function updateNotifications(body: {
  email_enabled: boolean;
  slack_enabled: boolean;
  browser_enabled: boolean;
  terminal_enabled: boolean;
}): Promise<NotificationSettingsResponse> {
  return request<NotificationSettingsResponse>("/v1/settings/notifications", {
    method: "PUT",
    body,
  });
}

export function getGithubConnectionStatus(signal?: AbortSignal): Promise<GithubConnectionStatusResponse> {
  return request<GithubConnectionStatusResponse>("/v1/settings/github/connection", { signal });
}

export function completeGithubRepoConnect(code: string, state: string): Promise<GithubConnectionStatusResponse> {
  return request<GithubConnectionStatusResponse>("/v1/settings/github/connect/callback", {
    method: "POST",
    body: { code, state },
  });
}

export function disconnectGithubRepoConnection(): Promise<GithubConnectionStatusResponse> {
  return request<GithubConnectionStatusResponse>("/v1/settings/github/disconnect", {
    method: "POST",
  });
}

export function getPricingValidation(signal?: AbortSignal): Promise<PricingValidationResponse> {
  return request<PricingValidationResponse>("/v1/settings/pricing-validation", { signal });
}

export function updatePricingValidation(body: {
  selected_launch_model: "tiered" | "usage_based" | "undecided";
  rationale?: string | null;
  migration_path?: string | null;
  interviews: PricingInterviewNote[];
  lock_pricing_decision: boolean;
}): Promise<PricingValidationResponse> {
  return request<PricingValidationResponse>("/v1/settings/pricing-validation", {
    method: "PUT",
    body,
  });
}

export function getRollbackDrill(signal?: AbortSignal): Promise<RollbackDrillResponse> {
  return request<RollbackDrillResponse>("/v1/settings/rollback-drill", { signal });
}

export function updateRollbackDrill(body: {
  deploy_revision?: string | null;
  rollback_revision?: string | null;
  deploy_test_passed: boolean;
  rollback_test_passed: boolean;
  failure_simulation_performed: boolean;
  failure_simulation_category?: "TOKEN_OVERFLOW" | "RATE_LIMIT" | "AUTH_FAILURE" | "LOOP_DETECTED" | "COST_SPIKE" | null;
  failure_simulation_notes?: string | null;
  drill_notes?: string | null;
  status: "not_started" | "in_progress" | "passed" | "failed";
}): Promise<RollbackDrillResponse> {
  return request<RollbackDrillResponse>("/v1/settings/rollback-drill", {
    method: "PUT",
    body,
  });
}

export function verifyRollbackDrill(body: {
  phase: "deploy" | "rollback";
  deploy_revision?: string | null;
  rollback_revision?: string | null;
}): Promise<RollbackDrillVerificationResponse> {
  return request<RollbackDrillVerificationResponse>("/v1/settings/rollback-drill/verify", {
    method: "POST",
    body,
  });
}

export function listProviderVerifications(signal?: AbortSignal): Promise<ProviderVerificationListResponse> {
  return request<ProviderVerificationListResponse>("/v1/settings/provider-verifications", { signal });
}

export function testProviderConnection(provider: string): Promise<ProviderVerificationTestResponse> {
  return request<ProviderVerificationTestResponse>(
    `/v1/settings/provider-verifications/${encodeURIComponent(provider)}/test`,
    {
      method: "POST",
    },
  );
}

export function exportProjectData(query?: {
  limit?: number;
  status?: string;
  alert_status?: string;
  category?: string;
  include_payload?: boolean;
}): Promise<ExportResponse> {
  return request<ExportResponse>("/v1/export", {
    query: {
      limit: query?.limit,
      status: query?.status,
      alert_status: query?.alert_status,
      category: query?.category,
      include_payload: query?.include_payload == null ? undefined : query.include_payload ? "true" : "false",
    },
  });
}

export function listProjectApiKeys(projectId: string, signal?: AbortSignal): Promise<ApiKeyResponse[]> {
  return request<ApiKeyResponse[]>(`/v1/projects/${encodeURIComponent(projectId)}/api-keys`, { signal });
}

export function createProjectApiKey(projectId: string, name: string): Promise<ApiKeyCreateResponse> {
  return request<ApiKeyCreateResponse>(`/v1/projects/${encodeURIComponent(projectId)}/api-keys`, {
    method: "POST",
    body: { name },
  });
}

export function revokeProjectApiKey(projectId: string, keyId: string): Promise<ApiKeyResponse> {
  return request<ApiKeyResponse>(
    `/v1/projects/${encodeURIComponent(projectId)}/api-keys/${encodeURIComponent(keyId)}/revoke`,
    {
      method: "POST",
    },
  );
}

export function getMe(signal?: AbortSignal): Promise<MeResponse> {
  return request<MeResponse>("/v1/auth/me", { signal });
}

export function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<ChangePasswordResponse> {
  return request<ChangePasswordResponse>("/v1/auth/me/password", {
    method: "PATCH",
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

// ── Shared diagnosis (public — no auth required) ─────────────────────────────

export async function getSharedDiagnosis(shareToken: string): Promise<DiagnosisShareReadResponse> {
  const url = buildUrl(`/v1/diagnosis/share/${encodeURIComponent(shareToken)}`);
  const response = await fetch(url, { method: "GET", cache: "no-store" });
  if (!response.ok) {
    let detail: string | null = null;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (typeof payload.detail === "string" && payload.detail.trim()) {
        detail = payload.detail;
      }
    } catch {
      // ignore
    }
    throw new Error(detail ?? `Share link not available (${response.status})`);
  }
  return (await response.json()) as DiagnosisShareReadResponse;
}

// ── Cost Forecasting ──────────────────────────────────────────────────────────

export function getCostForecast(hoursAhead = 4, signal?: AbortSignal): Promise<CostForecastResponse> {
  return request<CostForecastResponse>("/ai/cost/forecast", {
    query: { hours_ahead: hoursAhead },
    signal,
  });
}

export function getCostAnomalyRisk(signal?: AbortSignal): Promise<CostAnomalyRiskResponse> {
  return request<CostAnomalyRiskResponse>("/ai/cost/anomaly-risk", { signal });
}

// ── Team / project memberships ────────────────────────────────────────────────

export function listProjectMembers(projectId: string, signal?: AbortSignal): Promise<ProjectMemberListResponse> {
  return request<ProjectMemberListResponse>(`/v1/projects/${encodeURIComponent(projectId)}/memberships`, { signal });
}

export function upsertProjectMember(
  projectId: string,
  body: { subject?: string; user_subject?: string; email?: string | null; role?: string; is_active?: boolean },
): Promise<ProjectMembershipResponse> {
  // Accept both `subject` and legacy `user_subject` keys for compatibility.
  const payload: { subject?: string; email?: string | null; role?: string; is_active?: boolean } = {
    subject: (body as any).subject ?? (body as any).user_subject,
    email: (body as any).email ?? null,
    role: (body as any).role,
    is_active: (body as any).is_active,
  };
  return request<ProjectMembershipResponse>(`/v1/projects/${encodeURIComponent(projectId)}/memberships`, {
    method: "POST",
    body: payload,
  });
}

export function inviteProjectMember(projectId: string, email: string): Promise<ProjectInviteResponse> {
  return request<ProjectInviteResponse>(`/v1/projects/${encodeURIComponent(projectId)}/invite`, {
    method: "POST",
    body: { email },
  });
}

// ── Invitations (token-based) ───────────────────────────────────────────────

export function listProjectInvitations(projectId: string, signal?: AbortSignal): Promise<ProjectInvitationItem[]> {
  return request<ProjectInvitationItem[]>(`/v1/invitations/projects/${encodeURIComponent(projectId)}/invitations`, { signal });
}

export function createProjectInvitation(projectId: string, body: { email: string; role?: string }): Promise<ProjectInvitationItem> {
  return request<ProjectInvitationItem>(`/v1/invitations/projects/${encodeURIComponent(projectId)}/invitations`, {
    method: "POST",
    body,
  });
}

export function revokeProjectInvitation(projectId: string, invitationId: string): Promise<void> {
  return request<void>(`/v1/invitations/projects/${encodeURIComponent(projectId)}/invitations/${encodeURIComponent(invitationId)}`, {
    method: "DELETE",
  });
}

export function acceptInvitation(token: string): Promise<AcceptInvitationResponse> {
  return request<AcceptInvitationResponse>("/v1/invitations/accept", {
    method: "POST",
    body: { token },
  });
}

// ── Notifications ────────────────────────────────────────────────────────────

export function listNotifications(query?: { unread_only?: boolean; limit?: number; offset?: number }, signal?: AbortSignal): Promise<NotificationListResponse> {
  return request<NotificationListResponse>("/v1/notifications", {
    signal,
    query: {
      unread_only: query?.unread_only == null ? undefined : query.unread_only ? "true" : "false",
      limit: query?.limit,
      offset: query?.offset,
    },
  });
}

export function markNotificationRead(notificationId: string): Promise<MarkReadResponse> {
  return request<MarkReadResponse>(`/v1/notifications/${encodeURIComponent(notificationId)}/read`, {
    method: "PATCH",
  });
}

export function markAllNotificationsRead(): Promise<MarkAllReadResponse> {
  return request<MarkAllReadResponse>("/v1/notifications/mark-all-read", {
    method: "POST",
  });
}

export function deleteNotification(notificationId: string): Promise<void> {
  return request<void>(`/v1/notifications/${encodeURIComponent(notificationId)}`, {
    method: "DELETE",
  });
}

// ── Platform LLM Usage (owner) ───────────────────────────────────────────────

export function getPlatformLlmUsageSummary(signal?: AbortSignal): Promise<PlatformLlmUsageSummaryResponse> {
  return request<PlatformLlmUsageSummaryResponse>("/v1/owner/platform-llm-usage", { signal });
}

// ── Billing / Subscriptions ──────────────────────────────────────────────────

export function listSubscriptionPlans(signal?: AbortSignal): Promise<SubscriptionPlanListResponse> {
  return request<SubscriptionPlanListResponse>("/v1/billing/plans", { signal });
}

export function getTenantSubscription(signal?: AbortSignal): Promise<TenantSubscription> {
  return request<TenantSubscription>("/v1/billing/subscription", { signal });
}

export function updateTenantSubscription(body: {
  plan_id?: string;
  billing_interval?: string;
  status?: string;
  seats?: number;
}): Promise<TenantSubscription> {
  return request<TenantSubscription>("/v1/billing/subscription", {
    method: "PUT",
    body,
  });
}

export function getBillingUsageSummary(signal?: AbortSignal): Promise<BillingUsageSummary> {
  return request<BillingUsageSummary>("/v1/billing/usage", { signal });
}

// ── Support Tickets ──────────────────────────────────────────────────────────

export function listSupportTickets(query?: { status?: string; limit?: number; offset?: number }, signal?: AbortSignal): Promise<SupportTicketListResponse> {
  return request<SupportTicketListResponse>("/v1/support/tickets", {
    signal,
    query: {
      status: query?.status,
      limit: query?.limit,
      offset: query?.offset,
    },
  });
}

export function createSupportTicket(body: { title: string; description?: string; category?: string; priority?: string }): Promise<SupportTicketItem> {
  return request<SupportTicketItem>("/v1/support/tickets", {
    method: "POST",
    body,
  });
}

export function getSupportTicket(ticketId: string, signal?: AbortSignal): Promise<SupportTicketDetailResponse> {
  return request<SupportTicketDetailResponse>(`/v1/support/tickets/${encodeURIComponent(ticketId)}`, { signal });
}

export function updateSupportTicket(ticketId: string, body: { status?: string; priority?: string; assigned_to?: string }): Promise<SupportTicketItem> {
  return request<SupportTicketItem>(`/v1/support/tickets/${encodeURIComponent(ticketId)}`, {
    method: "PATCH",
    body,
  });
}

export function addSupportMessage(ticketId: string, body: { body: string }): Promise<SupportMessageItem> {
  return request<SupportMessageItem>(`/v1/support/tickets/${encodeURIComponent(ticketId)}/messages`, {
    method: "POST",
    body,
  });
}

// ── Feature Flags ────────────────────────────────────────────────────────────

export function listFeatureFlags(signal?: AbortSignal): Promise<FeatureFlagListResponse> {
  return request<FeatureFlagListResponse>("/v1/feature-flags/admin", { signal });
}

export function createFeatureFlag(body: { key: string; description?: string; enabled_globally?: boolean }): Promise<FeatureFlag> {
  return request<FeatureFlag>("/v1/feature-flags/admin", {
    method: "POST",
    body,
  });
}

export function updateFeatureFlag(
  flagId: string,
  body: {
    description?: string;
    enabled_globally?: boolean;
    add_enabled_tenants?: string[];
    remove_enabled_tenants?: string[];
    add_disabled_tenants?: string[];
    remove_disabled_tenants?: string[];
  }
): Promise<FeatureFlag> {
  return request<FeatureFlag>(`/v1/feature-flags/admin/${encodeURIComponent(flagId)}`, {
    method: "PUT",
    body,
  });
}

export function deleteFeatureFlag(flagId: string): Promise<void> {
  return request<void>(`/v1/feature-flags/admin/${encodeURIComponent(flagId)}`, {
    method: "DELETE",
  });
}

export function getTenantFeatureFlags(signal?: AbortSignal): Promise<TenantFeatureFlagsResponse> {
  return request<TenantFeatureFlagsResponse>("/v1/feature-flags/tenant", { signal });
}
