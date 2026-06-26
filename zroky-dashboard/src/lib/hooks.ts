import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryOptions,
  UseMutationOptions,
} from "@tanstack/react-query";
import {
  getCalibrationHistory,
  getCalibrationLatest,
  getCalibrationMode,
  triggerCalibrationRunNow,
  listCalibrationLabels,
  createOrUpdateCalibrationLabel,
  deleteCalibrationLabel,
  getOutcomeSummary,
  getOutcomeReconciliationSummary,
  listOutcomeReconciliations,
  getSourceMutationSummary,
  listUnreceiptedSourceMutations,
  getReplaySavings,
  ingestOutcome,
  listAblationJobs,
  getAblationJob,
  triggerAblation,
  getReliabilityLeaderboard,
  getReliabilitySummary,
  getAgentReliabilityHistory,
  triggerReliabilityCompute,
  type CalibrationModeView,
  type CalibrationRunView,
  type CalibrationRunNowResponse,
  type LabelView,
  type LabelCreate,
  type OutcomeSummaryResponse,
  type OutcomeReconciliationListResponse,
  type OutcomeReconciliationSummaryResponse,
  type OutcomeReconciliationVerdict,
  type SourceMutationListResponse,
  type SourceMutationSummaryResponse,
  type ReplaySavingsResponse,
  type OutcomeIngestPayload,
  type OutcomeView,
  type AblationJobView,
  type TriggerAblationPayload,
  type TriggerAblationResponse,
  type AgentScoreView,
  type ProjectReliabilitySummary,
  type ComputeReliabilityResponse,
  type RecView,
  type RecSummaryView,
  listRecommendations,
  getRecSummary,
  updateRecStatus,
  generateRecommendations,
} from "./api";
import {
  getActivityFeed,
  listProviderKeys,
  listProviderVerifications,
  testProviderConnection,
  changePassword,
  updateMe,
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
  rotateProjectApiKey,
  listAlerts,
  acknowledgeAlert,
  resolveAlert,
  reopenAlert,
  retrySlackAlert,
  getAlertDetail,
  getMe,
  listMyProjects,
  getCallDetail,
  getAdjacentCalls,
  getCallTraceTree,
  getDiagnosisFixWatch,
  getDiagnosisState,
  setDiagnosisAssignment,
  setDiagnosisDismissed,
  setDiagnosisSnooze,
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
  getTraceGraph,
  getTraceById,
  listDriftModels,
  getDriftStatus,
  getDriftHistory,
  listProjectMembers,
  inviteProjectMember,
  getGithubConnectionStatus,
  listReplayRuns,
  getReplayRun,
  getReplayQuota,
  createReplayRunFromCall,
  createReplayRunFromIssue,
  listRuntimePolicyApprovals,
  getRuntimePolicyEvidencePack,
  approveRuntimePolicyDecision,
  rejectRuntimePolicyDecision,
  setRuntimePolicyKillSwitch,
  getJudgeHealth,
  type ReplayRunDetailItem,
  type ReplayRunListResponse,
  type ReplayQuotaResponse,
  type ReplayCreatePayload,
  type ReplayCreateResponse,
  type RuntimePolicyDecisionStatus,
  type RuntimePolicyListResponse,
  type RuntimePolicyDecisionResponse,
  type RuntimePolicyEvidencePackResponse,
  type RuntimePolicyKillSwitchResponse,
  type JudgeHealthResponse,
} from "./api";
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
  CurrentUserProjectResponse,
  MeResponse,
  TraceListResponse,
  TraceGraphResponse,
  DriftModelView,
  StatusResponse,
  ModelHistoryResponse,
  ProjectInviteResponse,
  GithubConnectionStatusResponse,
  ProjectMembershipResponse,
  ProviderKeyListResponse,
} from "./types";
import type { AdjacentCallsResponse } from "./types";
import { PROVIDER_KEY_QUERY_KEY } from "./provider-key-gate";

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
    retry: false,
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

export function useTraceGraph(traceId: string) {
  return useQuery<TraceGraphResponse>({
    queryKey: ["traces", "graph", traceId],
    queryFn: () => getTraceGraph(traceId),
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
  min_cost_usd?: number;
  max_cost_usd?: number;
  limit?: number;
  offset?: number;
}) {
  const { limit = 50, offset = 0, date_from, date_to, min_cost_usd, max_cost_usd, ...rest } = filters;
  return useQuery<CallListResponse>({
    queryKey: ["calls", "list", filters],
    queryFn: () => listCalls({
      ...rest,
      start_time: date_from || undefined,
      end_time: date_to || undefined,
      min_cost_usd: min_cost_usd ?? undefined,
      max_cost_usd: max_cost_usd ?? undefined,
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

export function useRetrySlackAlert() {
  const qc = useQueryClient();
  return useMutation<AlertItemResponse, Error, string>({
    mutationFn: retrySlackAlert,
    onSuccess: (alert) => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["alert", alert.alert_id] });
    },
  });
}

// ─── Settings / API Keys ────────────────────────────────────────────────────

export function useProjectSettings(projectId?: string | null) {
  const hasExplicitProject = arguments.length > 0;

  return useQuery<ProjectResponse>({
    queryKey: ["project-settings", hasExplicitProject ? projectId : "current"],
    queryFn: () => getProjectSettings(),
    enabled: hasExplicitProject ? Boolean(projectId) : true,
    retry: false,
  });
}

export function useListProjectApiKeys(projectId: string) {
  return useQuery<ApiKeyResponse[]>({
    queryKey: ["project-api-keys", projectId],
    queryFn: () => listProjectApiKeys(projectId),
    enabled: !!projectId,
    retry: false,
  });
}

export function useCreateProjectApiKey() {
  const qc = useQueryClient();
  return useMutation<ApiKeyCreateResponse, Error, { projectId: string; name: string; expires_in_days?: number | null; scopes?: string[] }>({
    mutationFn: ({ projectId, name, expires_in_days, scopes }) => createProjectApiKey(projectId, { name, expires_in_days, scopes }),
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

export function useRotateProjectApiKey() {
  const qc = useQueryClient();
  return useMutation<ApiKeyCreateResponse, Error, { projectId: string; keyId: string }>({
    mutationFn: ({ projectId, keyId }) => rotateProjectApiKey(projectId, keyId),
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

export function useAdjacentCalls(callId: string) {
  return useQuery<AdjacentCallsResponse>({
    queryKey: ["calls", "adjacent", callId],
    queryFn: ({ signal }) => getAdjacentCalls(callId, signal),
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
    retry: false,
  });
}

export function useMyProjects() {
  return useQuery<CurrentUserProjectResponse[]>({
    queryKey: ["me", "projects"],
    queryFn: ({ signal }) => listMyProjects(signal),
    retry: false,
    staleTime: 60_000,
  });
}

export function useUpdateMe() {
  const qc = useQueryClient();
  return useMutation<MeResponse, Error, { displayName: string | null }>({
    mutationFn: ({ displayName }) => updateMe({ display_name: displayName }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: ({ currentPassword, newPassword }: { currentPassword: string; newPassword: string }) =>
      changePassword(currentPassword, newPassword),
  });
}

// ─── Provider Verifications ────────────────────────────────────────────────

export function useProviderVerifications() {
  return useQuery({
    queryKey: ["provider-verifications"],
    queryFn: () => listProviderVerifications(),
  });
}

export function useActiveProviderKeys() {
  return useQuery<ProviderKeyListResponse>({
    queryKey: PROVIDER_KEY_QUERY_KEY,
    queryFn: ({ signal }) => listProviderKeys({ include_revoked: false }, signal),
    staleTime: 60_000,
  });
}

export function useTestProviderConnection() {
  return useMutation({
    mutationFn: (provider: string) => testProviderConnection(provider),
  });
}

// ─── Cost Forecasting ─────────────────────────────────────────────────────────

export function useTeamMembers(projectId: string) {
  return useQuery<ProjectMembershipResponse[], Error>({
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

export function useCalibrationLatest(judgeModel?: string) {
  return useQuery<CalibrationRunView[], Error>({
    queryKey: ["calibration", "latest", judgeModel ?? "all"],
    queryFn: () => getCalibrationLatest(judgeModel),
    staleTime: 60_000,
  });
}

export function useCalibrationHistory(judgeModel: string, days = 30) {
  return useQuery<CalibrationRunView[], Error>({
    queryKey: ["calibration", "history", judgeModel, days],
    queryFn: () => getCalibrationHistory(judgeModel, days),
    enabled: !!judgeModel,
    staleTime: 60_000,
  });
}

export function useCalibrationMode(judgeModel: string) {
  return useQuery<CalibrationModeView, Error>({
    queryKey: ["calibration", "mode", judgeModel],
    queryFn: () => getCalibrationMode(judgeModel),
    enabled: !!judgeModel,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}

export function useTriggerCalibrationRunNow() {
  const qc = useQueryClient();
  return useMutation<CalibrationRunNowResponse, Error, string | undefined>({
    mutationFn: (judgeModel) => triggerCalibrationRunNow(judgeModel),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["calibration"] });
    },
  });
}

export function useCalibrationLabels(traceId?: string) {
  return useQuery<LabelView[], Error>({
    queryKey: ["calibration", "labels", traceId ?? "all"],
    queryFn: ({ signal }) => listCalibrationLabels(traceId, signal),
    staleTime: 30_000,
  });
}

export function useCreateCalibrationLabel() {
  const qc = useQueryClient();
  return useMutation<LabelView, Error, LabelCreate>({
    mutationFn: (body) => createOrUpdateCalibrationLabel(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["calibration", "labels"] });
    },
  });
}

export function useDeleteCalibrationLabel() {
  const qc = useQueryClient();
  return useMutation<{ message: string; label_id: string }, Error, string>({
    mutationFn: (labelId) => deleteCalibrationLabel(labelId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["calibration", "labels"] });
    },
  });
}

// ── Cost-of-Failure Attribution hooks ────────────────────────────────────────

export function useOutcomeSummary(
  days = 30,
  options?: Partial<UseQueryOptions<OutcomeSummaryResponse, Error>>,
) {
  return useQuery<OutcomeSummaryResponse, Error>({
    queryKey: ["outcomes", "summary", days],
    queryFn: ({ signal }) => getOutcomeSummary(days, signal),
    staleTime: 60_000,
    ...options,
  });
}

export function useOutcomeReconciliationSummary(
  days = 30,
  options?: Partial<UseQueryOptions<OutcomeReconciliationSummaryResponse, Error>>,
) {
  return useQuery<OutcomeReconciliationSummaryResponse, Error>({
    queryKey: ["outcomes", "reconciliation", "summary", days],
    queryFn: ({ signal }) => getOutcomeReconciliationSummary(days, signal),
    staleTime: 30_000,
    refetchInterval: 30_000,
    ...options,
  });
}

export function useOutcomeReconciliations(
  verdict: OutcomeReconciliationVerdict | "all" = "all",
  limit = 50,
  options?: Partial<UseQueryOptions<OutcomeReconciliationListResponse, Error>>,
) {
  return useQuery<OutcomeReconciliationListResponse, Error>({
    queryKey: ["outcomes", "reconciliation", "list", verdict, limit],
    queryFn: ({ signal }) => listOutcomeReconciliations({ verdict, limit }, signal),
    staleTime: 15_000,
    refetchInterval: verdict === "mismatched" || verdict === "not_verified" ? 15_000 : 30_000,
    ...options,
  });
}

export function useSourceMutationSummary(
  options?: Partial<UseQueryOptions<SourceMutationSummaryResponse, Error>>,
) {
  return useQuery<SourceMutationSummaryResponse, Error>({
    queryKey: ["outcomes", "reconciliation", "source-mutations", "summary"],
    queryFn: ({ signal }) => getSourceMutationSummary(signal),
    staleTime: 30_000,
    refetchInterval: 30_000,
    ...options,
  });
}

export function useUnreceiptedSourceMutations(
  limit = 50,
  options?: Partial<UseQueryOptions<SourceMutationListResponse, Error>>,
) {
  return useQuery<SourceMutationListResponse, Error>({
    queryKey: ["outcomes", "reconciliation", "source-mutations", "unreceipted", limit],
    queryFn: ({ signal }) => listUnreceiptedSourceMutations(limit, signal),
    staleTime: 15_000,
    refetchInterval: 15_000,
    ...options,
  });
}

export function useReplaySavings(
  runId: string,
  options?: Partial<UseQueryOptions<ReplaySavingsResponse, Error>>,
) {
  return useQuery<ReplaySavingsResponse, Error>({
    queryKey: ["outcomes", "replay", runId],
    queryFn: ({ signal }) => getReplaySavings(runId, signal),
    enabled: !!runId,
    staleTime: 300_000,
    ...options,
  });
}

export function useIngestOutcome() {
  const qc = useQueryClient();
  return useMutation<OutcomeView, Error, OutcomeIngestPayload>({
    mutationFn: (payload) => ingestOutcome(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["outcomes"] });
    },
  });
}

export function useAblationJobs(
  statusFilter?: string,
  limit = 20,
  options?: Partial<UseQueryOptions<AblationJobView[]>>,
) {
  return useQuery<AblationJobView[]>({
    queryKey: ["ablation", "list", statusFilter, limit],
    queryFn: ({ signal }) => listAblationJobs(statusFilter, limit, signal),
    staleTime: 30_000,
    ...options,
  });
}

export function useAblationJob(
  jobId: string | null | undefined,
  options?: Partial<UseQueryOptions<AblationJobView>>,
) {
  return useQuery<AblationJobView>({
    queryKey: ["ablation", "job", jobId],
    queryFn: ({ signal }) => getAblationJob(jobId!, signal),
    enabled: !!jobId,
    staleTime: 15_000,
    refetchInterval: (q) =>
      q.state.data?.status === "pending" || q.state.data?.status === "running" ? 3_000 : false,
    ...options,
  });
}

export function useTriggerAblation() {
  const qc = useQueryClient();
  return useMutation<TriggerAblationResponse, Error, TriggerAblationPayload>({
    mutationFn: (payload) => triggerAblation(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ablation"] });
    },
  });
}

export function useReliabilityLeaderboard(
  limit = 50,
  options?: Partial<UseQueryOptions<AgentScoreView[]>>,
) {
  return useQuery<AgentScoreView[]>({
    queryKey: ["reliability", "leaderboard", limit],
    queryFn: ({ signal }) => getReliabilityLeaderboard(limit, signal),
    staleTime: 60_000,
    ...options,
  });
}

export function useReliabilitySummary(
  options?: Partial<UseQueryOptions<ProjectReliabilitySummary>>,
) {
  return useQuery<ProjectReliabilitySummary>({
    queryKey: ["reliability", "summary"],
    queryFn: ({ signal }) => getReliabilitySummary(signal),
    staleTime: 60_000,
    ...options,
  });
}

export function useAgentReliabilityHistory(
  agentName: string | null | undefined,
  days = 30,
  options?: Partial<UseQueryOptions<AgentScoreView[]>>,
) {
  return useQuery<AgentScoreView[]>({
    queryKey: ["reliability", "agent", agentName, days],
    queryFn: ({ signal }) => getAgentReliabilityHistory(agentName!, days, signal),
    enabled: !!agentName,
    staleTime: 60_000,
    ...options,
  });
}

export function useTriggerReliabilityCompute() {
  const qc = useQueryClient();
  return useMutation<ComputeReliabilityResponse, Error, void>({
    mutationFn: () => triggerReliabilityCompute(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reliability"] });
    },
  });
}

export function useRecommendations(
  params: { status?: string; priority?: string; agent_name?: string; limit?: number } = {},
  options?: Partial<UseQueryOptions<RecView[]>>,
) {
  return useQuery<RecView[]>({
    queryKey: ["recommendations", params],
    queryFn: ({ signal }) => listRecommendations(params, signal),
    staleTime: 30_000,
    ...options,
  });
}

export function useRecSummary(
  options?: Partial<UseQueryOptions<RecSummaryView>>,
) {
  return useQuery<RecSummaryView>({
    queryKey: ["recommendations", "summary"],
    queryFn: ({ signal }) => getRecSummary(signal),
    staleTime: 30_000,
    ...options,
  });
}

export function useUpdateRecStatus() {
  const qc = useQueryClient();
  return useMutation<
    RecView,
    Error,
    { recId: string; status: string; actioned_by?: string }
  >({
    mutationFn: ({ recId, status, actioned_by }) =>
      updateRecStatus(recId, { status, actioned_by }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}

export function useGenerateRecommendations() {
  const qc = useQueryClient();
  return useMutation<{ generated: number; message: string }, Error, void>({
    mutationFn: () => generateRecommendations(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}

// ── Provider Drift Watch ──────────────────────────────────────────────────────

export function useDriftStatus(
  options?: Partial<UseQueryOptions<StatusResponse>>,
) {
  return useQuery<StatusResponse>({
    queryKey: ["drift", "status"],
    queryFn: ({ signal }) => getDriftStatus(signal),
    staleTime: 60_000,
    ...options,
  });
}

export function useDriftModels(
  options?: Partial<UseQueryOptions<DriftModelView[]>>,
) {
  return useQuery<DriftModelView[]>({
    queryKey: ["drift", "models"],
    queryFn: ({ signal }) => listDriftModels(signal),
    staleTime: 60_000,
    ...options,
  });
}

export function useDriftHistory(
  modelId: string | null,
  options?: Partial<UseQueryOptions<ModelHistoryResponse[]>>,
) {
  return useQuery<ModelHistoryResponse[]>({
    queryKey: ["drift", "history", modelId],
    queryFn: ({ signal }) => getDriftHistory(modelId!, signal),
    enabled: !!modelId,
    staleTime: 60_000,
    ...options,
  });
}

// -- GitHub Connection --------------------------------------------------------

export function useGithubConnectionStatus(
  options?: Partial<UseQueryOptions<GithubConnectionStatusResponse>>,
) {
  return useQuery<GithubConnectionStatusResponse>({
    queryKey: ["github", "connection-status"],
    queryFn: ({ signal }) => getGithubConnectionStatus(signal),
    staleTime: 5 * 60_000,
    ...options,
  });
}
// ── Replay Runs ───────────────────────────────────────────────────────────────

export function useReplayRuns(
  params: { golden_set_id?: string; status?: string; cursor?: string; limit?: number } = {},
  options?: Partial<UseQueryOptions<ReplayRunListResponse>>,
) {
  return useQuery<ReplayRunListResponse>({
    queryKey: ["replay-runs", params],
    queryFn: ({ signal }) => listReplayRuns(params, signal),
    staleTime: 15_000,
    ...options,
  });
}

export function useReplayRunDetail(
  runId: string | null | undefined,
  options?: Partial<UseQueryOptions<ReplayRunDetailItem>>,
) {
  return useQuery<ReplayRunDetailItem>({
    queryKey: ["replay-run", runId],
    queryFn: ({ signal }) => getReplayRun(runId!, signal),
    enabled: !!runId,
    staleTime: 10_000,
    refetchInterval: (q) =>
      q.state.data?.status === "pending" || q.state.data?.status === "running"
        ? 4_000
        : false,
    ...options,
  });
}

export function useReplayQuota(options?: Partial<UseQueryOptions<ReplayQuotaResponse>>) {
  return useQuery<ReplayQuotaResponse>({
    queryKey: ["replay-quota"],
    queryFn: ({ signal }) => getReplayQuota(signal),
    staleTime: 60_000,
    retry: false,
    refetchOnWindowFocus: false,
    ...options,
  });
}

// ── Runtime Policy Gate ─────────────────────────────────────────────────────

export function useRuntimePolicyApprovals(
  status: RuntimePolicyDecisionStatus | "all" = "pending_approval",
  options?: Partial<UseQueryOptions<RuntimePolicyListResponse>>,
) {
  return useQuery<RuntimePolicyListResponse>({
    queryKey: ["runtime-policy", "approvals", status],
    queryFn: ({ signal }) => listRuntimePolicyApprovals(status, signal),
    staleTime: 10_000,
    refetchInterval: status === "pending_approval" ? 15_000 : false,
    ...options,
  });
}

export function useRuntimePolicyEvidencePack(
  decisionId: string | null,
  options?: Partial<UseQueryOptions<RuntimePolicyEvidencePackResponse>>,
) {
  return useQuery<RuntimePolicyEvidencePackResponse>({
    queryKey: ["runtime-policy", "evidence", decisionId],
    queryFn: ({ signal }) => getRuntimePolicyEvidencePack(decisionId ?? "", signal),
    enabled: Boolean(decisionId),
    staleTime: 30_000,
    retry: false,
    ...options,
  });
}

export function useApproveRuntimePolicyDecision() {
  const queryClient = useQueryClient();
  return useMutation<RuntimePolicyDecisionResponse, Error, { decisionId: string; reason: string }>({
    mutationFn: ({ decisionId, reason }) => approveRuntimePolicyDecision(decisionId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runtime-policy", "approvals"] });
    },
  });
}

export function useRejectRuntimePolicyDecision() {
  const queryClient = useQueryClient();
  return useMutation<RuntimePolicyDecisionResponse, Error, { decisionId: string; reason: string }>({
    mutationFn: ({ decisionId, reason }) => rejectRuntimePolicyDecision(decisionId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runtime-policy", "approvals"] });
    },
  });
}

export function useSetRuntimePolicyKillSwitch() {
  const queryClient = useQueryClient();
  return useMutation<RuntimePolicyKillSwitchResponse, Error, boolean>({
    mutationFn: (enabled) => setRuntimePolicyKillSwitch(enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runtime-policy", "approvals"] });
    },
  });
}

// ── Judge Health / Drift ──────────────────────────────────────────────────────


export function useCreateReplayRunFromCall(
  options?: Partial<UseMutationOptions<ReplayCreateResponse, Error, { callId: string; payload: ReplayCreatePayload }>>,
) {
  const queryClient = useQueryClient();
  const { onSuccess, ...rest } = options ?? {};
  return useMutation<ReplayCreateResponse, Error, { callId: string; payload: ReplayCreatePayload }>({
    mutationFn: ({ callId, payload }) => createReplayRunFromCall(callId, payload),
    onSuccess: (data, variables, onMutateResult, context) => {
      queryClient.invalidateQueries({ queryKey: ["replay-runs"] });
      queryClient.invalidateQueries({ queryKey: ["replay-quota"] });
      onSuccess?.(data, variables, onMutateResult, context);
    },
    ...rest,
  });
}

export function useCreateReplayRunFromIssue(
  options?: Partial<UseMutationOptions<ReplayCreateResponse, Error, { issueId: string; payload: ReplayCreatePayload }>>,
) {
  const queryClient = useQueryClient();
  const { onSuccess, ...rest } = options ?? {};
  return useMutation<ReplayCreateResponse, Error, { issueId: string; payload: ReplayCreatePayload }>({
    mutationFn: ({ issueId, payload }) => createReplayRunFromIssue(issueId, payload),
    onSuccess: (data, variables, onMutateResult, context) => {
      queryClient.invalidateQueries({ queryKey: ["replay-runs"] });
      queryClient.invalidateQueries({ queryKey: ["replay-quota"] });
      onSuccess?.(data, variables, onMutateResult, context);
    },
    ...rest,
  });
}

export function useJudgeHealth(
  includeZeroSample = false,
  options?: Partial<UseQueryOptions<JudgeHealthResponse>>,
) {
  return useQuery<JudgeHealthResponse>({
    queryKey: ["judge-health", includeZeroSample],
    queryFn: ({ signal }) => getJudgeHealth({ includeZeroSample, signal }),
    staleTime: 300_000,
    retry: false,
    refetchOnWindowFocus: false,
    ...options,
  });
}
