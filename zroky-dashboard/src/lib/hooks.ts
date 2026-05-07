import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryOptions,
  UseMutationOptions,
} from "@tanstack/react-query";
import {
  getActivityFeed,
  listProviderVerifications,
  testProviderConnection,
  changePassword,
  listCalls,
  getCostDailyTrend,
  getCostByModel,
  getCostByUser,
  getCostByAgent,
  getCostHourly,
  getCostTopCalls,
  getReasoningShare,
  getCacheSavings,
  getBudget,
  getBudgetStatus,
  updateBudget,
  getProjectSettings,
  listProjectApiKeys,
  createProjectApiKey,
  revokeProjectApiKey,
  listAlerts,
  acknowledgeAlert,
  resolveAlert,
  reopenAlert,
  getAlertDetail,
  getMe,
  getCallDetail,
  getCallTraceTree,
  getDiagnosisFixWatch,
  listDiagnosisPrLinks,
  submitDiagnosisFeedback,
  markDiagnosisFixCopied,
  createShareLink,
  generateDiagnosisPr,
  resolveDiagnosis,
  getLoopSummary,
  getLoopIncidents,
  getAuthSummary,
  getRecentTraces,
  getTraceById,
  getCostForecast,
  getCostAnomalyRisk,
  listSupportTickets,
  createSupportTicket,
  updateSupportTicket,
  listProjectMembers,
  inviteProjectMember,
} from "./api";
import {
  fetchOwnerHealth,
  fetchOwnerInfra,
  fetchOwnerStats,
  fetchOwnerUsers,
  fetchOwnerUser,
  fetchUserMemberships,
  setUserStatus,
  fetchOwnerProjects,
  fetchOwnerProject,
  fetchProjectMembers,
  setProjectStatus,
  fetchOwnerPricing,
  updateOwnerPricing,
  fetchRateLimits,
  setRateLimitOverrides,
  clearRateLimitOverrides,
  fetchAuditLog,
  setMaintenanceMode,
} from "./owner-api";
import type {
  CostDailyTrendResponse,
  CostBreakdownResponse,
  CostHourlyResponse,
  CostTopCallsResponse,
  BudgetStatusResponse,
  ReasoningShareResponse,
  CacheSavingsResponse,
  BudgetConfigResponse,
  AlertListResponse,
  AlertItemResponse,
  CallListResponse,
  CallDetailResponse,
  CallTraceTreeResponse,
  DiagnosisFixWatchResponse,
  DiagnosisPrLinkResponse,
  LoopSummaryResponse,
  LoopIncidentsResponse,
  AuthSummaryResponse,
  DiagnosisShareCreateResponse,
  DiagnosisGeneratePrResponse,
  DiagnosisResolveResponse,
  DiagnosisFixCopiedResponse,
  ProjectResponse,
  ApiKeyResponse,
  ApiKeyCreateResponse,
  MeResponse,
  TraceListResponse,
  CostForecastResponse,
  CostAnomalyRiskResponse,
  ProjectMemberListResponse,
  ProjectInviteResponse,
  SupportTicketListResponse,
  SupportTicketItem,
} from "./types";

// ─── Activity Feed ──────────────────────────────────────────────────────────

export function useActivityFeed(opts: {
  limit?: number;
  offset?: number;
  action?: string;
}) {
  return useQuery({
    queryKey: ["activity-feed", opts],
    queryFn: () => getActivityFeed(opts),
  });
}

// ─── Analytics / Cost ───────────────────────────────────────────────────────

export function useCostDailyTrend(days = 14) {
  return useQuery<CostDailyTrendResponse>({
    queryKey: ["cost", "daily-trend", days],
    queryFn: () => getCostDailyTrend(days),
  });
}

export function useCostByModel(days = 14) {
  return useQuery<CostBreakdownResponse>({
    queryKey: ["cost", "by-model", days],
    queryFn: () => getCostByModel(days),
  });
}

export function useCostByUser(days = 14) {
  return useQuery<CostBreakdownResponse>({
    queryKey: ["cost", "by-user", days],
    queryFn: () => getCostByUser(days),
  });
}

export function useReasoningShare(days = 14) {
  return useQuery<ReasoningShareResponse>({
    queryKey: ["cost", "reasoning-share", days],
    queryFn: () => getReasoningShare(days),
  });
}

export function useCacheSavings(days = 14) {
  return useQuery<CacheSavingsResponse>({
    queryKey: ["cost", "cache-savings", days],
    queryFn: () => getCacheSavings(days),
  });
}

export function useBudget() {
  return useQuery<BudgetConfigResponse>({
    queryKey: ["budget"],
    queryFn: () => getBudget(),
  });
}

export function useBudgetStatus() {
  return useQuery<BudgetStatusResponse>({
    queryKey: ["budget", "status"],
    queryFn: () => getBudgetStatus(),
    staleTime: 60_000,
  });
}

export function useCostTopCalls(limit = 10, hours = 168) {
  return useQuery<CostTopCallsResponse>({
    queryKey: ["cost", "top-calls", limit, hours],
    queryFn: () => getCostTopCalls(limit, hours),
  });
}

export function useCostByAgent(days = 14) {
  return useQuery<CostBreakdownResponse>({
    queryKey: ["cost", "by-agent", days],
    queryFn: () => getCostByAgent(days),
  });
}

export function useCostHourly(hours = 48) {
  return useQuery<CostHourlyResponse>({
    queryKey: ["cost", "hourly", hours],
    queryFn: () => getCostHourly(hours),
  });
}

export function useLoopSummary(days = 7) {
  return useQuery<LoopSummaryResponse>({
    queryKey: ["loops", "summary", days],
    queryFn: () => getLoopSummary(days),
    staleTime: 60_000,
  });
}

export function useLoopIncidents(opts: { days?: number; limit?: number; offset?: number } = {}) {
  return useQuery<LoopIncidentsResponse>({
    queryKey: ["loops", "incidents", opts],
    queryFn: () => getLoopIncidents(opts),
    staleTime: 60_000,
  });
}

export function useTraceById(traceId: string, days = 30) {
  return useQuery<import("./types").TraceListItem>({
    queryKey: ["traces", "by-id", traceId, days],
    queryFn: () => getTraceById(traceId, days),
    enabled: !!traceId,
  });
}

export function useAuthSummary(hours = 24) {
  return useQuery<AuthSummaryResponse>({
    queryKey: ["auth", "summary", hours],
    queryFn: () => getAuthSummary(hours),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}

export function useListCalls(filters: {
  status?: string;
  model?: string;
  user_id?: string;
  call_type?: string;
  agent_name?: string;
  date_from?: string;
  date_to?: string;
  sort_by?: string;
  sort_order?: string;
  limit?: number;
  offset?: number;
}) {
  const { limit = 50, offset = 0, date_from, date_to, ...rest } = filters;
  return useQuery<CallListResponse>({
    queryKey: ["calls", "list", filters],
    queryFn: () => listCalls({
      ...rest,
      start_time: date_from || undefined,
      end_time: date_to || undefined,
      limit,
      offset,
    }),
  });
}

export function useUpdateBudget() {
  const qc = useQueryClient();
  return useMutation<BudgetConfigResponse, Error, { monthly_limit_usd: number | null; threshold_percentage: number }>({
    mutationFn: (vars) => updateBudget(vars.monthly_limit_usd, vars.threshold_percentage),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["budget"] }),
  });
}

// ─── Alerts ─────────────────────────────────────────────────────────────────

export function useAlerts(filters: {
  status?: string;
  severity?: string;
  category?: string;
  limit?: number;
  offset?: number;
}) {
  return useQuery<AlertListResponse>({
    queryKey: ["alerts", filters],
    queryFn: () => listAlerts(filters),
  });
}

export function useAlertDetail(alertId: string | null) {
  return useQuery<AlertItemResponse>({
    queryKey: ["alert", alertId],
    queryFn: () => {
      if (!alertId) throw new Error("No alertId");
      return getAlertDetail(alertId);
    },
    enabled: !!alertId,
  });
}

export function useAcknowledgeAlert() {
  const qc = useQueryClient();
  return useMutation<AlertItemResponse, Error, string>({
    mutationFn: acknowledgeAlert,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
}

export function useResolveAlert() {
  const qc = useQueryClient();
  return useMutation<AlertItemResponse, Error, string>({
    mutationFn: resolveAlert,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
}

export function useReopenAlert() {
  const qc = useQueryClient();
  return useMutation<AlertItemResponse, Error, string>({
    mutationFn: reopenAlert,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
}

// ─── Settings / API Keys ────────────────────────────────────────────────────

export function useProjectSettings() {
  return useQuery<ProjectResponse>({
    queryKey: ["project-settings"],
    queryFn: () => getProjectSettings(),
  });
}

export function useListProjectApiKeys(projectId: string) {
  return useQuery<ApiKeyResponse[]>({
    queryKey: ["project-api-keys", projectId],
    queryFn: () => listProjectApiKeys(projectId),
    enabled: !!projectId,
  });
}

export function useCreateProjectApiKey() {
  const qc = useQueryClient();
  return useMutation<ApiKeyCreateResponse, Error, { projectId: string; name: string }>({
    mutationFn: ({ projectId, name }) => createProjectApiKey(projectId, name),
    onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ["project-api-keys", vars.projectId] }),
  });
}

export function useRevokeProjectApiKey() {
  const qc = useQueryClient();
  return useMutation<ApiKeyResponse, Error, { projectId: string; keyId: string }>({
    mutationFn: ({ projectId, keyId }) => revokeProjectApiKey(projectId, keyId),
    onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ["project-api-keys", vars.projectId] }),
  });
}

// ─── Call Detail ────────────────────────────────────────────────────────────

export function useCallDetail(callId: string) {
  return useQuery<CallDetailResponse>({
    queryKey: ["call-detail", callId],
    queryFn: () => getCallDetail(callId),
    enabled: !!callId,
  });
}

export function useCallTraceTree(callId: string) {
  return useQuery<CallTraceTreeResponse>({
    queryKey: ["call-trace", callId],
    queryFn: () => getCallTraceTree(callId),
    enabled: !!callId,
  });
}

export function useRecentTraces(days = 7, limit = 20) {
  return useQuery<TraceListResponse>({
    queryKey: ["traces", "recent", days, limit],
    queryFn: () => getRecentTraces(days, limit),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}

export function useDiagnosisFixWatch(callId: string) {
  return useQuery<DiagnosisFixWatchResponse>({
    queryKey: ["diagnosis-fix-watch", callId],
    queryFn: () => getDiagnosisFixWatch(callId),
    enabled: !!callId,
  });
}

export function useDiagnosisState(diagnosisId: string) {
  return useQuery<import("./types").DiagnosisUiStateResponse>({
    queryKey: ["diagnosis-state", diagnosisId],
    queryFn: () => getDiagnosisState(diagnosisId),
    enabled: !!diagnosisId,
  });
}

export function useSetDiagnosisAssignment() {
  const qc = useQueryClient();
  return useMutation<import("./types").DiagnosisUiStateResponse, Error, { diagnosisId: string; assigned_subject: string | null }>({
    mutationFn: ({ diagnosisId, assigned_subject }) => setDiagnosisAssignment(diagnosisId, assigned_subject),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["diagnosis-state", vars.diagnosisId] });
      qc.invalidateQueries({ queryKey: ["fixes", "action-queue"] });
    },
  });
}

export function useSetDiagnosisSnooze() {
  const qc = useQueryClient();
  return useMutation<import("./types").DiagnosisUiStateResponse, Error, { diagnosisId: string; snoozed_until: string | null }>({
    mutationFn: ({ diagnosisId, snoozed_until }) => setDiagnosisSnooze(diagnosisId, snoozed_until),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["diagnosis-state", vars.diagnosisId] });
      qc.invalidateQueries({ queryKey: ["fixes", "action-queue"] });
    },
  });
}

export function useSetDiagnosisDismissed() {
  const qc = useQueryClient();
  return useMutation<import("./types").DiagnosisUiStateResponse, Error, { diagnosisId: string; dismissed: boolean }>({
    mutationFn: ({ diagnosisId, dismissed }) => setDiagnosisDismissed(diagnosisId, dismissed),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["diagnosis-state", vars.diagnosisId] });
      qc.invalidateQueries({ queryKey: ["fixes", "action-queue"] });
    },
  });
}

export function useDiagnosisPrLinks(callId: string) {
  return useQuery<DiagnosisPrLinkResponse[]>({
    queryKey: ["diagnosis-pr-links", callId],
    queryFn: () => listDiagnosisPrLinks(callId),
    enabled: !!callId,
  });
}

export function useSubmitDiagnosisFeedback() {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { callId: string; wasHelpful: boolean; note?: string }>({
    mutationFn: ({ callId, wasHelpful, note }) =>
      submitDiagnosisFeedback(callId, { was_helpful: wasHelpful, developer_note: note || undefined }),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["call-detail", vars.callId] });
      qc.invalidateQueries({ queryKey: ["diagnosis-fix-watch", vars.callId] });
    },
  });
}

export function useResolveDiagnosis() {
  const qc = useQueryClient();
  return useMutation<DiagnosisResolveResponse, Error, string>({
    mutationFn: resolveDiagnosis,
    onSuccess: (_, callId) => {
      qc.invalidateQueries({ queryKey: ["call-detail", callId] });
      qc.invalidateQueries({ queryKey: ["diagnosis-fix-watch", callId] });
    },
  });
}

export function useCreateShareLink() {
  return useMutation<DiagnosisShareCreateResponse, Error, string>({
    mutationFn: createShareLink,
  });
}

export function useGenerateDiagnosisPr() {
  const qc = useQueryClient();
  return useMutation<DiagnosisGeneratePrResponse, Error, { callId: string; repoOwner?: string; repoName?: string; baseBranch?: string }>({
    mutationFn: ({ callId, repoOwner, repoName, baseBranch }) =>
      generateDiagnosisPr(callId, {
        repository_owner: repoOwner,
        repository_name: repoName,
        base_branch: baseBranch,
      }),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["diagnosis-pr-links", vars.callId] });
    },
  });
}

export function useMarkDiagnosisFixCopied() {
  return useMutation<DiagnosisFixCopiedResponse, Error, string>({
    mutationFn: markDiagnosisFixCopied,
  });
}

// ─── Auth ───────────────────────────────────────────────────────────────────

export function useMe() {
  return useQuery<MeResponse>({
    queryKey: ["me"],
    queryFn: () => getMe(),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: ({ currentPassword, newPassword }: { currentPassword: string; newPassword: string }) =>
      changePassword(currentPassword, newPassword),
  });
}

// ─── Owner ──────────────────────────────────────────────────────────────────

export function useOwnerHealth() {
  return useQuery({
    queryKey: ["owner", "health"],
    queryFn: () => fetchOwnerHealth(),
  });
}

export function useOwnerInfra() {
  return useQuery({
    queryKey: ["owner", "infra"],
    queryFn: () => fetchOwnerInfra(),
  });
}

export function useOwnerStats() {
  return useQuery({
    queryKey: ["owner", "stats"],
    queryFn: () => fetchOwnerStats(),
  });
}

export function useOwnerUsers(limit = 200, offset = 0) {
  return useQuery({
    queryKey: ["owner", "users", limit, offset],
    queryFn: () => fetchOwnerUsers(limit, offset),
  });
}

export function useOwnerProjects(limit = 200, offset = 0) {
  return useQuery({
    queryKey: ["owner", "projects", limit, offset],
    queryFn: () => fetchOwnerProjects(limit, offset),
  });
}

export function useOwnerUser(userId: string) {
  return useQuery({
    queryKey: ["owner", "users", userId],
    queryFn: () => fetchOwnerUser(userId),
    enabled: !!userId,
  });
}

export function useUserMemberships(userId: string) {
  return useQuery({
    queryKey: ["owner", "users", userId, "memberships"],
    queryFn: () => fetchUserMemberships(userId),
    enabled: !!userId,
  });
}

export function useSetUserStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, isActive, reason }: { userId: string; isActive: boolean; reason?: string }) =>
      setUserStatus(userId, isActive, reason),
    onSuccess: (_, { userId }) => {
      qc.invalidateQueries({ queryKey: ["owner", "users", userId] });
      qc.invalidateQueries({ queryKey: ["owner", "users"] });
    },
  });
}

export function useOwnerProject(projectId: string) {
  return useQuery({
    queryKey: ["owner", "projects", projectId],
    queryFn: () => fetchOwnerProject(projectId),
    enabled: !!projectId,
  });
}

export function useProjectMembers(projectId: string) {
  return useQuery({
    queryKey: ["owner", "projects", projectId, "members"],
    queryFn: () => fetchProjectMembers(projectId),
    enabled: !!projectId,
  });
}

export function useSetProjectStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, isActive, reason }: { projectId: string; isActive: boolean; reason?: string }) =>
      setProjectStatus(projectId, isActive, reason),
    onSuccess: (_, { projectId }) => {
      qc.invalidateQueries({ queryKey: ["owner", "projects", projectId] });
      qc.invalidateQueries({ queryKey: ["owner", "projects"] });
    },
  });
}

export function useRateLimits() {
  return useQuery({
    queryKey: ["owner", "rate-limits"],
    queryFn: () => fetchRateLimits(),
  });
}

export function useSetRateLimitOverrides() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (overrides: Record<string, unknown>) => setRateLimitOverrides(overrides),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["owner", "rate-limits"] }),
  });
}

export function useClearRateLimitOverrides() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => clearRateLimitOverrides(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["owner", "rate-limits"] }),
  });
}

export function useAuditLog(opts: {
  limit?: number;
  offset?: number;
  action?: string;
  tenant_id?: string;
}) {
  return useQuery({
    queryKey: ["owner", "audit", opts],
    queryFn: () => fetchAuditLog(opts),
  });
}

export function useToggleMaintenance() {
  const qc = useQueryClient();
  return useMutation<void, Error, { enabled: boolean; message?: string }>({
    mutationFn: ({ enabled, message }) => setMaintenanceMode(enabled, message),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["owner", "health"] }),
  });
}

// ─── Owner Pricing ───────────────────────────────────────────────────────────

export function useOwnerPricing() {
  return useQuery({
    queryKey: ["owner", "pricing"],
    queryFn: () => fetchOwnerPricing(),
  });
}

export function useUpdateOwnerPricing() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (config: Record<string, unknown>) => updateOwnerPricing(config),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["owner", "pricing"] }),
  });
}

// ─── Provider Verifications ────────────────────────────────────────────────

export function useProviderVerifications() {
  return useQuery({
    queryKey: ["provider-verifications"],
    queryFn: () => listProviderVerifications(),
  });
}

export function useTestProviderConnection() {
  return useMutation({
    mutationFn: (provider: string) => testProviderConnection(provider),
  });
}

// ─── Cost Forecasting ─────────────────────────────────────────────────────────

export function useCostForecast(hoursAhead = 4) {
  return useQuery<CostForecastResponse, Error>({
    queryKey: ["cost-forecast", hoursAhead],
    queryFn: () => getCostForecast(hoursAhead),
    staleTime: 5 * 60 * 1000,
  });
}

export function useCostAnomalyRisk() {
  return useQuery<CostAnomalyRiskResponse, Error>({
    queryKey: ["cost-anomaly-risk"],
    queryFn: () => getCostAnomalyRisk(),
    staleTime: 5 * 60 * 1000,
  });
}

// ─── Team / Project Members ───────────────────────────────────────────────────

export function useTeamMembers(projectId: string) {
  return useQuery<ProjectMemberListResponse, Error>({
    queryKey: ["project-members", projectId],
    queryFn: () => listProjectMembers(projectId),
    enabled: !!projectId,
  });
}

export function useInviteTeamMember(projectId: string) {
  const qc = useQueryClient();
  return useMutation<ProjectInviteResponse, Error, { email: string }>({
    mutationFn: ({ email }) => inviteProjectMember(projectId, email),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project-members", projectId] }),
  });
}

export function useCreateSupportTicket() {
  const qc = useQueryClient();
  return useMutation<SupportTicketItem, Error, { title: string; description?: string; category?: string; priority?: string }>({
    mutationFn: (body) => createSupportTicket(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["support-tickets"] }),
  });
}

export function useUpdateSupportTicket() {
  const qc = useQueryClient();
  return useMutation<SupportTicketItem, Error, { ticketId: string; body: { status?: string; priority?: string; assigned_to?: string } }>({
    mutationFn: ({ ticketId, body }) => updateSupportTicket(ticketId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["support-tickets"] }),
  });
}

export function useSupportTickets(opts?: { status?: string; limit?: number; offset?: number }) {
  return useQuery<SupportTicketListResponse, Error>({
    queryKey: ["support-tickets", opts ?? {}],
    queryFn: () => listSupportTickets(opts ?? {}),
  });
}
