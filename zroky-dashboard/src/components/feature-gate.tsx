"use client";

import type { ReactNode } from "react";

export function hasPlanEntitlement(
  planTemplate: Record<string, unknown> | null | undefined,
  key: string | null | undefined,
): boolean {
  if (!key) return true;
  return planTemplate?.[key] === true;
}

export function normalizePlanCode(planCode: string | null | undefined): string {
  return typeof planCode === "string" ? planCode.trim().toLowerCase() : "";
}

export function formatPlanLabel(planCode: string | null | undefined): string {
  const code = normalizePlanCode(planCode);
  if (!code) return "Plan unavailable";
  if (code === "free") return "Free Plan";
  if (code === "watch") return "Watch Plan";
  if (code === "pilot") return "Starter Plan";
  if (code === "starter") return "Starter Plan";
  if (code === "pro") return "Pro Plan";
  if (code === "plus") return "Plus Plan";
  if (code === "enterprise") return "Enterprise Plan";
  return `${code.charAt(0).toUpperCase()}${code.slice(1)} Plan`;
}

export function isPaidGoldensPlan(planCode: string | null | undefined): boolean {
  return ["pilot", "starter", "pro", "plus", "enterprise"].includes(normalizePlanCode(planCode));
}

export function hasGoldensAccess(
  planTemplate: Record<string, unknown> | null | undefined,
  planCode: string | null | undefined,
): boolean {
  return hasPlanEntitlement(planTemplate, "pilot.goldens_basic") || isPaidGoldensPlan(planCode);
}

export function hasCiBlockingAccess(
  planTemplate: Record<string, unknown> | null | undefined,
  planCode: string | null | undefined,
): boolean {
  const code = normalizePlanCode(planCode);
  return (
    hasPlanEntitlement(planTemplate, "pro.ci_gate_blocking") ||
    hasPlanEntitlement(planTemplate, "enterprise.private_replay_worker") ||
    code === "pro" ||
    code === "plus" ||
    code === "enterprise"
  );
}

export function hasFeatureAccess(
  planTemplate: Record<string, unknown> | null | undefined,
  planCode: string | null | undefined,
  key: string | null | undefined,
): boolean {
  if (!key) return true;
  if (key === "pilot.goldens_basic") return hasGoldensAccess(planTemplate, planCode);
  if (key === "pro.ci_gate_blocking") return hasCiBlockingAccess(planTemplate, planCode);
  return hasPlanEntitlement(planTemplate, key);
}

export function FeatureGate({
  requiredEntitlement,
  planTemplate,
  planCode,
  loading = false,
  fallback = null,
  children,
}: {
  requiredEntitlement?: string;
  planTemplate: Record<string, unknown> | null | undefined;
  planCode?: string | null;
  loading?: boolean;
  fallback?: ReactNode;
  children: ReactNode;
}) {
  if (loading || hasFeatureAccess(planTemplate, planCode, requiredEntitlement)) {
    return <>{children}</>;
  }

  return <>{fallback}</>;
}
