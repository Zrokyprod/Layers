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
  CaptureHealthResponse,
  AdjacentCallsResponse,
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
  TraceListItem,
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
  SavingsSummaryResponse,
  GithubConnectionStatusResponse,
  SlackInstallStartResponse,
  SlackInstallStatusResponse,
  SlackTestMessageResponse,
  TeamsInstallStatusResponse,
  TeamsTestMessageResponse,
  CostForecastResponse,
  CostAnomalyRiskResponse,
  ChangePasswordResponse,
  ProjectInvitationItem,
  AcceptInvitationResponse,
  NotificationListResponse,
  MarkReadResponse,
  MarkAllReadResponse,
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
  IssueItem,
  IssueListResponse,
  DetectorListResponse,
  FeatureVoteRequest,
  FeatureVoteResponse,
  DriftModelView,
  StatusResponse,
  ModelHistoryResponse,
  AskResponse,
  AskContext,
  AskFeedbackRequest,
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

export function getCaptureHealth(signal?: AbortSignal): Promise<CaptureHealthResponse> {
  return request<CaptureHealthResponse>("/v1/capture/health", { signal });
}

export function getJudgeHealth(
  options: { includeZeroSample?: boolean; signal?: AbortSignal } = {},
): Promise<JudgeHealthResponse> {
  return request<JudgeHealthResponse>("/v1/judge/health", {
    query: options.includeZeroSample ? { include_zero_sample: "true" } : undefined,
    signal: options.signal,
  });
}

/**
 * Aggregate "what Zroky saved you" figures over the given window.
 * Used by the top-bar Saved-You badge in `DashboardShell`.
 */
export function getSavingsSummary(
  days = 30,
  signal?: AbortSignal,
): Promise<SavingsSummaryResponse> {
  return request<SavingsSummaryResponse>("/v1/analytics/savings", {
    query: { days },
    signal,
  });
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
    date_from?: string;
    date_to?: string;
    min_cost_usd?: number;
    max_cost_usd?: number;
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

export function getAdjacentCalls(callId: string, signal?: AbortSignal): Promise<AdjacentCallsResponse> {
  return request<AdjacentCallsResponse>(`/v1/calls/${encodeURIComponent(callId)}/adjacent`, { signal });
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
  teams_enabled: boolean;
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

export function getSlackInstallStatus(signal?: AbortSignal): Promise<SlackInstallStatusResponse> {
  return request<SlackInstallStatusResponse>("/v1/integrations/slack/status", { signal });
}

export function startSlackInstall(): Promise<SlackInstallStartResponse> {
  return request<SlackInstallStartResponse>("/v1/integrations/slack/install", {
    method: "POST",
  });
}

export function disconnectSlackInstall(): Promise<SlackInstallStatusResponse> {
  return request<SlackInstallStatusResponse>("/v1/integrations/slack/install", {
    method: "DELETE",
  });
}

export function sendSlackTestMessage(text?: string): Promise<SlackTestMessageResponse> {
  return request<SlackTestMessageResponse>("/v1/integrations/slack/test", {
    method: "POST",
    body: { text },
  });
}

export function getTeamsInstallStatus(signal?: AbortSignal): Promise<TeamsInstallStatusResponse> {
  return request<TeamsInstallStatusResponse>("/v1/integrations/teams/status", { signal });
}

export function upsertTeamsInstall(body: {
  webhook_url: string;
  channel_name?: string | null;
}): Promise<TeamsInstallStatusResponse> {
  return request<TeamsInstallStatusResponse>("/v1/integrations/teams/install", {
    method: "PUT",
    body,
  });
}

export function disconnectTeamsInstall(): Promise<TeamsInstallStatusResponse> {
  return request<TeamsInstallStatusResponse>("/v1/integrations/teams/install", {
    method: "DELETE",
  });
}

export function sendTeamsTestMessage(text?: string): Promise<TeamsTestMessageResponse> {
  return request<TeamsTestMessageResponse>("/v1/integrations/teams/test", {
    method: "POST",
    body: { text },
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

export function deleteAccount(confirmEmail: string): Promise<{ detail: string }> {
  return request<{ detail: string }>("/v1/auth/me", {
    method: "DELETE",
    body: { confirm_email: confirmEmail },
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
    subject: body.subject ?? body.user_subject,
    email: body.email ?? null,
    role: body.role,
    is_active: body.is_active,
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

// ── Issues ────────────────────────────────────────────────────────────────────

export function listIssues(
  params: {
    status?: "open" | "resolved" | "ignored" | "all";
    failure_code?: string;
    agent_name?: string;
    severity?: string;
    has_fix?: boolean;
    cursor?: string;
    limit?: number;
  },
  signal?: AbortSignal,
): Promise<IssueListResponse> {
  const { has_fix, ...rest } = params;
  return request<IssueListResponse>("/v1/issues", {
    query: { ...rest, ...(has_fix !== undefined ? { has_fix: String(has_fix) } : {}) },
    signal,
  });
}

export function getIssue(issueId: string, signal?: AbortSignal): Promise<IssueItem> {
  return request<IssueItem>(`/v1/issues/${encodeURIComponent(issueId)}`, { signal });
}

export function resolveIssue(
  issueId: string,
  body: { fix_id?: string; resolution_source?: string },
): Promise<IssueItem> {
  return request<IssueItem>(`/v1/issues/${encodeURIComponent(issueId)}/resolve`, {
    method: "POST",
    body,
  });
}

export function ignoreIssue(issueId: string): Promise<IssueItem> {
  return request<IssueItem>(`/v1/issues/${encodeURIComponent(issueId)}/ignore`, {
    method: "POST",
  });
}

export function updateIssueTriage(
  issueId: string,
  body: { assigned_to?: string | null; deploy_pr_url?: string | null },
): Promise<IssueItem> {
  return request<IssueItem>(`/v1/issues/${encodeURIComponent(issueId)}/triage`, {
    method: "PATCH",
    body,
  });
}

// ── Replay ────────────────────────────────────────────────────────────────────

export interface ReplayJobResponse {
  id: string;
  tenant_id: string;
  call_id: string | null;
  pr_id: string | null;
  status: "pending" | "running" | "pass" | "fail" | "error";
  diff_metric: number | null;
  error_message: string | null;
  stdout_tail: string | null;
  created_at: string;
  completed_at: string | null;
}

export function createReplayJob(
  body: { call_id: string; pr_id?: string; candidate_fix_diff?: string; timeout_seconds?: number },
): Promise<ReplayJobResponse> {
  return request<ReplayJobResponse>("/v1/replay/jobs", { method: "POST", body });
}

export function getReplayJob(replayId: string, signal?: AbortSignal): Promise<ReplayJobResponse> {
  return request<ReplayJobResponse>(`/v1/replay/jobs/${encodeURIComponent(replayId)}`, { signal });
}

// ── Detectors ─────────────────────────────────────────────────────────────────

export function listDetectors(signal?: AbortSignal): Promise<DetectorListResponse> {
  return request<DetectorListResponse>("/v1/detectors", { signal });
}

// ── Feature-interest voting (Module 9 smoke-test) ─────────────────────────────

export function submitFeatureVote(
  body: FeatureVoteRequest,
): Promise<FeatureVoteResponse> {
  return request<FeatureVoteResponse>("/v1/feature-interest", {
    method: "POST",
    body,
  });
}

export function getMyFeatureVote(
  featureKey: string,
  signal?: AbortSignal,
): Promise<FeatureVoteResponse> {
  return request<FeatureVoteResponse>("/v1/feature-interest/me", {
    query: { feature_key: featureKey },
    signal,
  });
}

// ── Provider Drift Watch ──────────────────────────────────────────────────────

export function listDriftModels(signal?: AbortSignal): Promise<DriftModelView[]> {
  return request<DriftModelView[]>("/v1/drift/models", { signal });
}

export function getDriftStatus(signal?: AbortSignal): Promise<StatusResponse> {
  return request<StatusResponse>("/v1/drift/status", { signal });
}

export function getDriftHistory(
  modelId: string,
  signal?: AbortSignal,
): Promise<ModelHistoryResponse[]> {
  return request<ModelHistoryResponse[]>(`/v1/drift/history/${encodeURIComponent(modelId)}`, { signal });
}

// ── Judge Calibration ────────────────────────────────────────────────────────

export interface CalibrationPerClassMetric {
  label: string;
  precision: number;
  recall: number;
  f1: number;
  support: number;
}

export interface CalibrationRunView {
  id: string;
  project_id: string;
  judge_model: string;
  run_date: string;
  status: string;
  sample_count: number;
  agreement_count: number;
  accuracy: number;
  kappa: number;
  low_confidence_pct: number;
  per_class_metrics: CalibrationPerClassMetric[];
  confusion_matrix: Record<string, Record<string, number>>;
  cost_usd: number;
  completed_at: string | null;
}

export interface CalibrationModeView {
  project_id: string;
  judge_model: string;
  mode: string;
  reason: string | null;
  accuracy: number | null;
  sample_count: number | null;
  last_run_date: string | null;
}

export interface CalibrationRunNowResponse {
  run_id: string;
  status: string;
  message: string;
}

export function getCalibrationLatest(
  judgeModel?: string,
  signal?: AbortSignal,
): Promise<CalibrationRunView[]> {
  return request<CalibrationRunView[]>("/v1/judge/calibration/latest", {
    query: judgeModel ? { judge_model: judgeModel } : undefined,
    signal,
  });
}

export function getCalibrationHistory(
  judgeModel: string,
  days = 30,
  signal?: AbortSignal,
): Promise<CalibrationRunView[]> {
  return request<CalibrationRunView[]>("/v1/judge/calibration/history", {
    query: { judge_model: judgeModel, days },
    signal,
  });
}

export function getCalibrationMode(
  judgeModel: string,
  signal?: AbortSignal,
): Promise<CalibrationModeView> {
  return request<CalibrationModeView>(
    `/v1/judge/calibration/mode/${encodeURIComponent(judgeModel)}`,
    { signal },
  );
}

export function triggerCalibrationRunNow(
  judgeModel?: string,
  signal?: AbortSignal,
): Promise<CalibrationRunNowResponse> {
  return request<CalibrationRunNowResponse>("/v1/judge/calibration/run-now", {
    method: "POST",
    query: judgeModel ? { judge_model: judgeModel } : undefined,
    signal,
  });
}

export interface LabelView {
  id: string;
  golden_trace_id: string;
  labeler_user_id: string | null;
  verdict: string;
  rationale: string | null;
  version: number;
  active: boolean;
  created_at: string;
}

export interface LabelCreate {
  golden_trace_id: string;
  verdict: "pass" | "fail" | "inconclusive";
  rationale?: string;
}

export function listCalibrationLabels(
  traceId?: string,
  signal?: AbortSignal,
): Promise<LabelView[]> {
  return request<LabelView[]>("/v1/judge/calibration/labels", {
    query: traceId ? { trace_id: traceId } : undefined,
    signal,
  });
}

export function createOrUpdateCalibrationLabel(
  body: LabelCreate,
  signal?: AbortSignal,
): Promise<LabelView> {
  return request<LabelView>("/v1/judge/calibration/labels", {
    method: "POST",
    body,
    signal,
  });
}

export function deleteCalibrationLabel(
  labelId: string,
  signal?: AbortSignal,
): Promise<{ message: string; label_id: string }> {
  return request<{ message: string; label_id: string }>(
    `/v1/judge/calibration/labels/${encodeURIComponent(labelId)}`,
    { method: "DELETE", signal },
  );
}

// ── Cost-of-Failure Attribution ───────────────────────────────────────────────

export interface OutcomeTypeRow {
  outcome_type: string;
  total_usd: number;
  count: number;
  avg_usd: number;
}

export interface AttributionClusterRow {
  agent_name: string | null;
  detector: string | null;
  outcome_cost_usd: number;
  outcome_count: number;
  failure_count: number;
  estimated_monthly_savings_usd: number;
  top_outcome_type: string | null;
}

export interface OutcomeSummaryResponse {
  window_days: number;
  total_outcome_usd: number;
  linked_outcome_count: number;
  unlinked_outcome_count: number;
  avg_cost_per_linked: number;
  by_type: OutcomeTypeRow[];
  by_cluster: AttributionClusterRow[];
}

export interface ReplaySavingsResponse {
  run_id: string;
  prevented_outcome_cost_usd: number;
  message: string;
}

export interface OutcomeIngestPayload {
  call_id?: string;
  outcome_type: string;
  amount_usd: number;
  occurred_at?: string;
  external_ref?: string;
  idempotency_key?: string;
  metadata?: Record<string, unknown>;
}

export interface OutcomeView {
  id: string;
  project_id: string;
  call_id: string | null;
  outcome_type: string;
  amount_usd: number;
  source: string;
  occurred_at: string;
  external_ref: string | null;
  created_at: string;
}

export function getOutcomeSummary(
  days = 30,
  signal?: AbortSignal,
): Promise<OutcomeSummaryResponse> {
  return request<OutcomeSummaryResponse>("/v1/outcomes/summary", {
    query: { days: String(days) },
    signal,
  });
}

export function getReplaySavings(
  runId: string,
  signal?: AbortSignal,
): Promise<ReplaySavingsResponse> {
  return request<ReplaySavingsResponse>(`/v1/outcomes/replay/${encodeURIComponent(runId)}`, {
    signal,
  });
}

export function ingestOutcome(
  payload: OutcomeIngestPayload,
  signal?: AbortSignal,
): Promise<OutcomeView> {
  return request<OutcomeView>("/v1/outcomes", {
    method: "POST",
    body: payload,
    signal,
  });
}

// ── Ablation Root-Cause Attribution ──────────────────────────────────────────

export interface AblationAxisView {
  id: string;
  axis_type: string;
  axis_label: string;
  failing_value: string | null;
  confidence: number;
  evidence: Record<string, unknown> | null;
}

export interface AblationJobView {
  id: string;
  project_id: string;
  call_id: string;
  diagnosis_job_id: string | null;
  status: string;
  determinism_class: string | null;
  control_group_size: number;
  root_cause_narrative: string | null;
  fix_suggestion: string | null;
  fix_difficulty: string | null;
  synthesis_confidence: number | null;
  error_message: string | null;
  axes: AblationAxisView[];
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface TriggerAblationPayload {
  call_id: string;
  diagnosis_job_id?: string;
}

export interface TriggerAblationResponse {
  job_id: string;
  status: string;
  message: string;
}

export function triggerAblation(
  payload: TriggerAblationPayload,
  signal?: AbortSignal,
): Promise<TriggerAblationResponse> {
  return request<TriggerAblationResponse>("/v1/ablation", {
    method: "POST",
    body: payload,
    signal,
  });
}

export function getAblationJob(
  jobId: string,
  signal?: AbortSignal,
): Promise<AblationJobView> {
  return request<AblationJobView>(`/v1/ablation/${encodeURIComponent(jobId)}`, { signal });
}

export function getAblationJobsForCall(
  callId: string,
  signal?: AbortSignal,
): Promise<AblationJobView[]> {
  return request<AblationJobView[]>(`/v1/ablation/by-call/${encodeURIComponent(callId)}`, { signal });
}

export function listAblationJobs(
  statusFilter?: string,
  limit = 20,
  signal?: AbortSignal,
): Promise<AblationJobView[]> {
  return request<AblationJobView[]>("/v1/ablation", {
    query: {
      ...(statusFilter ? { status: statusFilter } : {}),
      limit: String(limit),
    },
    signal,
  });
}

// ── Agent Reliability Scorecard ───────────────────────────────────────────────

export interface AgentScoreView {
  agent_name: string;
  score_date: string;
  health_score: number;
  fail_rate: number;
  fail_rate_score: number;
  cost_efficiency_score: number;
  determinism_score: number;
  regression_trend_score: number;
  call_count: number;
  avg_cost_usd: number;
  p95_latency_ms: number | null;
  prev_week_fail_rate: number | null;
  determinism_breakdown: {
    deterministic: number;
    stochastic: number;
    environmental: number;
    unknown: number;
  } | null;
  top_failure_axis: string | null;
  computed_at: string;
}

export interface ProjectReliabilitySummary {
  project_id: string;
  agent_count: number;
  avg_health_score: number;
  worst_agent: string | null;
  best_agent: string | null;
  total_deterministic_failures: number;
  total_stochastic_failures: number;
  score_date: string;
}

export interface ComputeReliabilityResponse {
  agents_computed: number;
  score_date: string;
  message: string;
}

export function getReliabilityLeaderboard(
  limit = 50,
  signal?: AbortSignal,
): Promise<AgentScoreView[]> {
  return request<AgentScoreView[]>("/v1/reliability/leaderboard", {
    query: { limit: String(limit) },
    signal,
  });
}

export function getReliabilitySummary(
  signal?: AbortSignal,
): Promise<ProjectReliabilitySummary> {
  return request<ProjectReliabilitySummary>("/v1/reliability/summary", { signal });
}

export function getAgentReliabilityHistory(
  agentName: string,
  days = 30,
  signal?: AbortSignal,
): Promise<AgentScoreView[]> {
  return request<AgentScoreView[]>(
    `/v1/reliability/agent/${encodeURIComponent(agentName)}`,
    { query: { days: String(days) }, signal },
  );
}

export function triggerReliabilityCompute(
  signal?: AbortSignal,
): Promise<ComputeReliabilityResponse> {
  return request<ComputeReliabilityResponse>("/v1/reliability/compute", {
    method: "POST",
    signal,
  });
}

// ── Reliability Intelligence Queue ────────────────────────────────────────────

export interface RecView {
  id: string;
  agent_name: string;
  recommendation_type: string;
  priority: "critical" | "high" | "medium" | "low";
  title: string;
  detail: string | null;
  fix_suggestion: string | null;
  fix_difficulty: "easy" | "medium" | "hard" | null;
  top_axis: string | null;
  axis_confidence: number | null;
  estimated_monthly_impact_usd: number | null;
  impact_score: number;
  health_score_at_generation: number | null;
  fail_rate_at_generation: number | null;
  call_count_window: number | null;
  ablation_job_id: string | null;
  status: "open" | "acknowledged" | "resolved" | "dismissed" | "snoozed";
  actioned_by: string | null;
  actioned_at: string | null;
  snoozed_until: string | null;
  generated_date: string;
  created_at: string;
}

export interface RecSummaryView {
  project_id: string;
  total_open: number;
  critical_count: number;
  high_count: number;
  total_estimated_saving_usd: number;
  top_agents: string[];
}

export function listRecommendations(
  params: {
    status?: string;
    priority?: string;
    agent_name?: string;
    limit?: number;
  } = {},
  signal?: AbortSignal,
): Promise<RecView[]> {
  return request<RecView[]>("/v1/recommendations", {
    query: {
      ...(params.status ? { status: params.status } : {}),
      ...(params.priority ? { priority: params.priority } : {}),
      ...(params.agent_name ? { agent_name: params.agent_name } : {}),
      limit: String(params.limit ?? 50),
    },
    signal,
  });
}

export function getRecSummary(signal?: AbortSignal): Promise<RecSummaryView> {
  return request<RecSummaryView>("/v1/recommendations/summary", { signal });
}

export function updateRecStatus(
  recId: string,
  body: { status: string; actioned_by?: string; snoozed_until?: string },
  signal?: AbortSignal,
): Promise<RecView> {
  return request<RecView>(`/v1/recommendations/${recId}/status`, {
    method: "PATCH",
    body,
    signal,
  });
}

export function generateRecommendations(
  signal?: AbortSignal,
): Promise<{ generated: number; message: string }> {
  return request("/v1/recommendations/generate", { method: "POST", signal });
}

// ── Golden Sets (Pilot) ──────────────────────────────────────────────────────

export interface GoldenSetView {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  judge_config_json: string | null;
  trace_count: number;
  created_at: string;
  updated_at: string;
}

export interface GoldenSetListResponse {
  items: GoldenSetView[];
  next_cursor: string | null;
  total_in_page: number;
}

export interface GoldenTraceView {
  id: string;
  golden_set_id: string;
  project_id: string;
  call_id: string | null;
  expected_output_text: string | null;
  expected_tokens: number | null;
  expected_cost_usd: number | null;
  expected_latency_ms: number | null;
  criteria_json: string | null;
  weight: number;
  created_at: string;
  updated_at: string;
}

export interface GoldenTraceListResponse {
  items: GoldenTraceView[];
  total_in_page: number;
}

export function listGoldenSets(
  params: { limit?: number; cursor?: string } = {},
  signal?: AbortSignal,
): Promise<GoldenSetListResponse> {
  return request<GoldenSetListResponse>("/v1/goldens", {
    query: {
      limit: String(params.limit ?? 20),
      ...(params.cursor ? { cursor: params.cursor } : {}),
    },
    signal,
  });
}

export function createGoldenSet(
  body: { name: string; description?: string },
  signal?: AbortSignal,
): Promise<GoldenSetView> {
  return request<GoldenSetView>("/v1/goldens", {
    method: "POST",
    body,
    signal,
  });
}

export function getGoldenSet(
  id: string,
  signal?: AbortSignal,
): Promise<GoldenSetView> {
  return request<GoldenSetView>(`/v1/goldens/${encodeURIComponent(id)}`, { signal });
}

export function listGoldenTraces(
  goldenSetId: string,
  params: { limit?: number } = {},
  signal?: AbortSignal,
): Promise<GoldenTraceListResponse> {
  return request<GoldenTraceListResponse>(
    `/v1/goldens/${encodeURIComponent(goldenSetId)}/traces`,
    { query: { limit: String(params.limit ?? 50) }, signal },
  );
}

export function addGoldenTrace(
  goldenSetId: string,
  body: {
    call_id?: string;
    expected_output_text?: string;
    expected_tokens?: number;
    expected_cost_usd?: number;
    expected_latency_ms?: number;
    criteria_json?: string;
    weight?: number;
  },
  signal?: AbortSignal,
): Promise<GoldenTraceView> {
  return request<GoldenTraceView>(
    `/v1/goldens/${encodeURIComponent(goldenSetId)}/traces`,
    { method: "POST", body, signal },
  );
}

export function deleteGoldenTrace(
  goldenSetId: string,
  traceId: string,
  signal?: AbortSignal,
): Promise<{ message: string }> {
  return request<{ message: string }>(
    `/v1/goldens/${encodeURIComponent(goldenSetId)}/traces/${encodeURIComponent(traceId)}`,
    { method: "DELETE", signal },
  );
}

export interface GoldenRunDispatchResponse {
  id: string;
  project_id: string;
  golden_set_id: string;
  trigger: string;
  git_sha: string | null;
  status: string;
  created_at: string;
  summary_url: string;
  idempotent: boolean;
}

export function runGoldenSet(
  goldenSetId: string,
  body: {
    trigger?: string;
    git_sha?: string;
    branch_name?: string;
    pr_number?: number;
    commit_message?: string;
    replay_mode?: ReplayMode;
    candidate_prompt_override?: string;
    candidate_model_override?: string;
  } = {},
  signal?: AbortSignal,
): Promise<GoldenRunDispatchResponse> {
  return request<GoldenRunDispatchResponse>(
    `/v1/goldens/${encodeURIComponent(goldenSetId)}/run`,
    { method: "POST", body, signal },
  );
}


// -- Ask Zroky -----------------------------------------------------------------

export function askZroky(
  body: { question: string; context?: AskContext },
  signal?: AbortSignal,
): Promise<AskResponse> {
  return request<AskResponse>("/v1/ask", { method: "POST", body, signal });
}

export function submitAskFeedback(
  body: AskFeedbackRequest,
  signal?: AbortSignal,
): Promise<{ accepted: boolean }> {
  return request<{ accepted: boolean }>("/v1/ask/feedback", { method: "POST", body, signal });
}

// ── Replay Runs (Pilot) ───────────────────────────────────────────────────────

export interface ReplayRunSummary {
  trace_count_at_dispatch: number;
  trace_count_executed: number;
  pass_count: number;
  fail_count: number;
  error_count: number;
  reproduced_original_failure: boolean | null;
  fix_passed: boolean | null;
  verified_fix: boolean;
  verification_status: string;
  output_diff: Record<string, unknown> | null;
  tool_behavior_diff: Record<string, unknown> | null;
  cost_delta_usd: number | null;
  latency_delta_ms: number | null;
  replay_cost_usd: number | null;
}

export interface ReplayRunItem {
  id: string;
  project_id: string;
  golden_set_id: string;
  trigger: string;
  git_sha: string | null;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  summary: ReplayRunSummary;
  created_at: string;
  replay_mode: string;
  executor_replay_mode: string;
  replay_mode_warning: string | null;
  candidate_prompt_override: string | null;
  candidate_model_override: string | null;
  prevented_outcome_cost_usd: number | null;
}

export interface ReplayRunTraceItem {
  id: string;
  replay_run_id: string;
  golden_trace_id: string | null;
  project_id: string;
  call_id_replayed: string | null;
  judge_scores_json: string | null;
  status: string;
  diff_metric: number | null;
  output_text: string | null;
  completed_at: string | null;
  created_at: string;
  output_diff: Record<string, unknown> | null;
  tool_behavior_diff: Record<string, unknown> | null;
  cost_delta_usd: number | null;
  latency_delta_ms: number | null;
}

export interface ReplayRunDetailItem extends ReplayRunItem {
  traces: ReplayRunTraceItem[];
}

export interface ReplayRunListResponse {
  items: ReplayRunItem[];
  next_cursor: string | null;
  total_in_page: number;
}

export type ReplayMode = "stub" | "real_llm" | "mocked-tool" | "live-sandbox" | "shadow";

export interface ReplayCreatePayload {
  replay_mode: ReplayMode;
  candidate_prompt_override?: string;
  candidate_model_override?: string;
}

export interface ReplayCreateResponse {
  id: string;
  project_id: string;
  golden_set_id: string;
  trigger: string;
  status: string;
  created_at: string;
  summary_url: string;
  replay_mode: string;
}

export function listReplayRuns(
  params: { golden_set_id?: string; status?: string; cursor?: string; limit?: number } = {},
  signal?: AbortSignal,
): Promise<ReplayRunListResponse> {
  const q: Record<string, string> = {};
  if (params.golden_set_id) q.golden_set_id = params.golden_set_id;
  if (params.status) q.status = params.status;
  if (params.cursor) q.cursor = params.cursor;
  if (params.limit != null) q.limit = String(params.limit);
  return request<ReplayRunListResponse>("/v1/replay/runs", { query: q, signal });
}

export function getReplayRun(runId: string, signal?: AbortSignal): Promise<ReplayRunDetailItem> {
  return request<ReplayRunDetailItem>(`/v1/replay/runs/${encodeURIComponent(runId)}`, { signal });
}

export function createReplayRunFromCall(
  callId: string,
  body: ReplayCreatePayload,
  signal?: AbortSignal,
): Promise<ReplayCreateResponse> {
  return request<ReplayCreateResponse>(`/v1/replay/runs/from-call/${encodeURIComponent(callId)}`, {
    method: "POST",
    body,
    signal,
  });
}

export function createReplayRunFromIssue(
  issueId: string,
  body: ReplayCreatePayload,
  signal?: AbortSignal,
): Promise<ReplayCreateResponse> {
  return request<ReplayCreateResponse>(`/v1/replay/runs/from-issue/${encodeURIComponent(issueId)}`, {
    method: "POST",
    body,
    signal,
  });
}
export interface ReplayQuotaResponse {
  enabled: boolean;
  /** -1 = unlimited (Enterprise) */
  limit: number;
  used: number;
  resets_at: string;
  plan_code: string;
}

export function getReplayQuota(signal?: AbortSignal): Promise<ReplayQuotaResponse> {
  return request<ReplayQuotaResponse>("/v1/replay/quota", { signal });
}

// ── Judge Health / Drift ──────────────────────────────────────────────────────

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
