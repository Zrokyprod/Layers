import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  anonymizeOwnerUser,
  clearRateLimitOverrides,
  clearProjectRateLimit,
  confirmOwnerRazorpayPayment,
  deleteOwnerUser,
  fetchOwnerLaunchReadiness,
  fetchAuditLog,
  fetchOwnerBillingSummary,
  fetchOwnerBillingAccounts,
  fetchOwnerBillingRecovery,
  fetchOwnerHealth,
  fetchOwnerInfra,
  fetchOwnerMoneyPathHealth,
  fetchOwnerPricing,
  fetchOwnerPricingPlans,
  fetchOwnerProject,
  fetchOwnerProjects,
  fetchOwnerRetention,
  fetchOwnerStats,
  fetchOwnerSupportTickets,
  fetchOwnerSupportTicket,
  fetchOwnerUser,
  fetchOwnerUsers,
  fetchProjectRateLimit,
  fetchProjectMembers,
  fetchRateLimits,
  fetchUserMemberships,
  replyOwnerSupportTicket,
  runOwnerBillingRecovery,
  setMaintenanceMode,
  setProjectStatus,
  setProjectRateLimit,
  setRateLimitOverrides,
  setUserStatus,
  updateOwnerPricing,
  updateOwnerSupportTicket,
} from "./owner-api";
import type { OwnerBillingPaymentConfirmRequest } from "./owner-api";

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

export function useOwnerMoneyPathHealth() {
  return useQuery({
    queryKey: ["owner", "money-path-health"],
    queryFn: () => fetchOwnerMoneyPathHealth(),
  });
}

export function useOwnerLaunchReadiness() {
  return useQuery({
    queryKey: ["owner", "launch-readiness"],
    queryFn: ({ signal }) => fetchOwnerLaunchReadiness(signal),
  });
}

export function useOwnerUsers(limit = 200, offset = 0) {
  return useQuery({
    queryKey: ["owner", "users", limit, offset],
    queryFn: () => fetchOwnerUsers(limit, offset),
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
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, isActive, reason }: { userId: string; isActive: boolean; reason?: string }) =>
      setUserStatus(userId, isActive, reason),
    onSuccess: (_, { userId }) => {
      queryClient.invalidateQueries({ queryKey: ["owner", "users", userId] });
      queryClient.invalidateQueries({ queryKey: ["owner", "users"] });
    },
  });
}

export function useAnonymizeOwnerUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => anonymizeOwnerUser(userId),
    onSuccess: (_, userId) => {
      queryClient.invalidateQueries({ queryKey: ["owner", "users", userId] });
      queryClient.invalidateQueries({ queryKey: ["owner", "users"] });
    },
  });
}

export function useDeleteOwnerUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => deleteOwnerUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["owner", "users"] });
    },
  });
}

export function useOwnerProjects(limit = 200, offset = 0) {
  return useQuery({
    queryKey: ["owner", "projects", limit, offset],
    queryFn: () => fetchOwnerProjects(limit, offset),
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

export function useProjectRateLimit(projectId: string) {
  return useQuery({
    queryKey: ["owner", "projects", projectId, "rate-limit"],
    queryFn: () => fetchProjectRateLimit(projectId),
    enabled: !!projectId,
  });
}

export function useSetProjectStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, isActive, reason }: { projectId: string; isActive: boolean; reason?: string }) =>
      setProjectStatus(projectId, isActive, reason),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ["owner", "projects", projectId] });
      queryClient.invalidateQueries({ queryKey: ["owner", "projects"] });
    },
  });
}

export function useSetProjectRateLimit(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { ingest_soft_limit_rpm?: number; ingest_burst_limit_rpm?: number; ingest_enforce_rate_limit?: boolean }) =>
      setProjectRateLimit(projectId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["owner", "projects", projectId, "rate-limit"] }),
  });
}

export function useClearProjectRateLimit(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => clearProjectRateLimit(projectId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["owner", "projects", projectId, "rate-limit"] }),
  });
}

export function useRateLimits() {
  return useQuery({
    queryKey: ["owner", "rate-limits"],
    queryFn: () => fetchRateLimits(),
  });
}

export function useSetRateLimitOverrides() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (overrides: Record<string, unknown>) => setRateLimitOverrides(overrides),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["owner", "rate-limits"] }),
  });
}

export function useClearRateLimitOverrides() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => clearRateLimitOverrides(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["owner", "rate-limits"] }),
  });
}

export function useAuditLog(
  opts: { limit?: number; offset?: number; action?: string; tenant_id?: string } = {},
) {
  return useQuery({
    queryKey: ["owner", "audit", opts],
    queryFn: () => fetchAuditLog(opts),
  });
}

export function useOwnerBillingSummary() {
  return useQuery({
    queryKey: ["owner", "billing", "summary"],
    queryFn: () => fetchOwnerBillingSummary(),
  });
}

export function useOwnerSupportTickets(
  opts: {
    status?: string;
    priority?: string;
    tenant_id?: string;
    assigned_to?: string;
    limit?: number;
    offset?: number;
  } = {},
) {
  return useQuery({
    queryKey: ["owner", "support", "tickets", opts],
    queryFn: () => fetchOwnerSupportTickets(opts),
  });
}

export function useOwnerSupportTicket(ticketId: string | null) {
  return useQuery({
    queryKey: ["owner", "support", "tickets", ticketId],
    queryFn: () => fetchOwnerSupportTicket(ticketId as string),
    enabled: !!ticketId,
  });
}

export function useUpdateOwnerSupportTicket() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      ticketId,
      body,
    }: {
      ticketId: string;
      body: { status?: string; priority?: string; assigned_to?: string };
    }) => updateOwnerSupportTicket(ticketId, body),
    onSuccess: (_, { ticketId }) => {
      queryClient.invalidateQueries({ queryKey: ["owner", "support", "tickets"] });
      queryClient.invalidateQueries({ queryKey: ["owner", "support", "tickets", ticketId] });
    },
  });
}

export function useReplyOwnerSupportTicket() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      ticketId,
      body,
    }: {
      ticketId: string;
      body: { body: string; is_internal?: boolean };
    }) => replyOwnerSupportTicket(ticketId, body),
    onSuccess: (_, { ticketId }) => {
      queryClient.invalidateQueries({ queryKey: ["owner", "support", "tickets"] });
      queryClient.invalidateQueries({ queryKey: ["owner", "support", "tickets", ticketId] });
    },
  });
}

export function useToggleMaintenance() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, { enabled: boolean; message?: string }>({
    mutationFn: ({ enabled, message }) => setMaintenanceMode(enabled, message),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["owner", "health"] }),
  });
}

export function useOwnerPricing() {
  return useQuery({
    queryKey: ["owner", "pricing"],
    queryFn: () => fetchOwnerPricing(),
  });
}

export function useOwnerPricingPlans() {
  return useQuery({
    queryKey: ["owner", "pricing", "plans"],
    queryFn: ({ signal }) => fetchOwnerPricingPlans(signal),
  });
}

export function useOwnerRetention() {
  return useQuery({
    queryKey: ["owner", "retention"],
    queryFn: () => fetchOwnerRetention(),
  });
}

export function useOwnerBillingAccounts(opts: { status?: string; plan_code?: string; limit?: number; offset?: number } = {}) {
  return useQuery({
    queryKey: ["owner", "billing", "accounts", opts],
    queryFn: () => fetchOwnerBillingAccounts(opts),
  });
}

export function useOwnerBillingRecovery() {
  return useQuery({
    queryKey: ["owner", "billing", "recovery"],
    queryFn: ({ signal }) => fetchOwnerBillingRecovery(signal),
  });
}

export function useUpdateOwnerPricing() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: Record<string, unknown>) => updateOwnerPricing(config),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["owner", "pricing"] }),
  });
}

export function useConfirmOwnerRazorpayPayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: OwnerBillingPaymentConfirmRequest) => confirmOwnerRazorpayPayment(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["owner", "billing"] });
      queryClient.invalidateQueries({ queryKey: ["owner", "money-path-health"] });
    },
  });
}

export function useRunOwnerBillingRecovery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (limit?: number) => runOwnerBillingRecovery(limit ?? 50),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["owner", "billing"] });
      queryClient.invalidateQueries({ queryKey: ["owner", "money-path-health"] });
    },
  });
}
