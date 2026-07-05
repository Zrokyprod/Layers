"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { OwnerPlanGrantModal } from "@/components/owner-plan-grant-modal";
import { useOwnerMoneyPathHealth, useOwnerProjects } from "@/lib/hooks";
import type { OwnerMoneyPathTenantRow, OwnerProjectItem } from "@/lib/owner-api";

type Tone = "ok" | "warn" | "danger" | "neutral";

const ACTION_LABELS: Record<string, string> = {
  review_blocked_ci: "Review release block",
  restore_capture: "Restore capture",
  connect_provider_key: "Connect analysis key",
  review_replay_quota: "Review proof quota",
  review_event_quota: "Review event quota",
  restore_replay_worker: "Restore proof worker",
  fix_metering: "Fix metering",
  refresh_pricing: "Refresh pricing",
  fix_billing: "Fix billing",
  review_support: "Review support",
  run_replay: "Run proof check",
  promote_golden: "Promote receipt baseline",
  run_ci_gate: "Run release check",
  continue_triage: "Continue triage",
  monitor: "Monitor",
};

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action.replaceAll("_", " ");
}

function statusTone(state: string | undefined | null): Tone {
  const value = state ?? "unknown";
  if (["pass", "passed", "ok", "active", "verified", "configured", "monitor", "unlimited", "getting_value", "live"].includes(value)) return "ok";
  if (["blocked", "fail", "failed", "down", "error", "missing", "risk", "urgent", "exceeded", "unverified", "sdk_silent", "suspended"].includes(value)) return "danger";
  if (["not_verified", "warn", "degraded", "near_limit", "open", "stale", "fallback", "missing_paid", "partial", "at_risk", "needs_action", "no_health"].includes(value)) return "warn";
  return "neutral";
}

function StatusBadge({ value, tone }: { value: string; tone?: Tone }) {
  return <span className={`owner-money-badge owner-money-badge-${tone ?? statusTone(value)}`}>{value.replaceAll("_", " ")}</span>;
}

function fmtCount(value: number): string {
  return value.toLocaleString();
}

function fmtDate(value: string | null | undefined): string {
  if (!value) return "No captures";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Unknown";
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function quotaText(tenant: OwnerMoneyPathTenantRow | undefined): string {
  if (!tenant) return "No health row";
  if (tenant.replay_quota_status.limit === -1) return `${fmtCount(tenant.replay_quota_status.used)} used`;
  return `${fmtCount(tenant.replay_quota_status.used)} / ${fmtCount(tenant.replay_quota_status.limit)}`;
}

function proofSignal(tenant: OwnerMoneyPathTenantRow | undefined): { value: string; detail: string; tone: Tone } {
  if (!tenant) return { value: "No health row", detail: "Backend has no proof row", tone: "warn" };
  if (tenant.verified_replay_count_7d > 0 && tenant.golden_trace_count > 0) {
    return {
      value: "Verified",
      detail: `${fmtCount(tenant.verified_replay_count_7d)} verified, ${fmtCount(tenant.golden_trace_count)} receipt baseline`,
      tone: "ok",
    };
  }
  if (tenant.blocking_ci_failures_7d > 0) {
    return { value: "Release risk", detail: `${fmtCount(tenant.blocking_ci_failures_7d)} blocked release check`, tone: "danger" };
  }
  return { value: "Proof missing", detail: `${fmtCount(tenant.replay_run_count_7d)} proof checks`, tone: tenant.open_issue_count > 0 ? "warn" : "neutral" };
}

function sdkSignal(tenant: OwnerMoneyPathTenantRow | undefined): { value: string; detail: string; tone: Tone } {
  if (!tenant) return { value: "No health", detail: "No action row", tone: "warn" };
  if (!tenant.last_capture_at || tenant.captures_24h === 0) {
    return { value: "No actions", detail: fmtDate(tenant.last_capture_at), tone: "danger" };
  }
  return { value: "Active", detail: `${fmtCount(tenant.captures_24h)} protected actions in 24h`, tone: "ok" };
}

function connectorSignal(tenant: OwnerMoneyPathTenantRow | undefined): { value: string; detail: string; tone: Tone } {
  if (!tenant) return { value: "No health", detail: "No connector row", tone: "warn" };
  const state = tenant.provider_key_status.state;
  return {
    value: state,
    detail: `${fmtCount(tenant.provider_key_status.active_provider_count)} active key(s)`,
    tone: statusTone(state),
  };
}

function tenantIssueSignal(project: OwnerProjectItem, tenant: OwnerMoneyPathTenantRow | undefined): { value: string; detail: string; tone: Tone } {
  if (!project.is_active) return { value: "Suspended", detail: "Tenant is disabled", tone: "danger" };
  if (!tenant) return { value: "No health row", detail: "Backend has not reported tenant health", tone: "warn" };
  if (!tenant.last_capture_at || tenant.captures_24h === 0) return { value: "Needs action", detail: "No protected actions", tone: "danger" };
  if (tenant.provider_key_status.state === "missing") return { value: "Needs action", detail: "Connector key missing", tone: "danger" };
  if (["risk", "missing_paid", "unknown"].includes(tenant.billing_status?.state ?? "")) return { value: "Needs action", detail: "Billing risk", tone: "danger" };
  if (["near_limit", "exceeded"].includes(tenant.replay_quota_status.state)) return { value: "Needs action", detail: "Proof quota risk", tone: "warn" };
  if (tenant.blocking_ci_failures_7d > 0 || tenant.open_issue_count > 0) return { value: "Needs action", detail: actionLabel(tenant.next_owner_action), tone: "warn" };
  if (tenant.next_owner_action !== "monitor") return { value: "Review", detail: actionLabel(tenant.next_owner_action), tone: "warn" };
  return { value: "Live", detail: "No owner action queued", tone: "ok" };
}

function tenantNeedsAction(project: OwnerProjectItem, tenant: OwnerMoneyPathTenantRow | undefined): boolean {
  return tenantIssueSignal(project, tenant).tone !== "ok";
}

function SummaryCard({ label, value, detail, tone }: { label: string; value: string; detail: string; tone: Tone }) {
  return (
    <div className={`owner-tenant-summary-card owner-tenant-summary-card-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

export default function OwnerProjectsPage() {
  const { data, isLoading, error } = useOwnerProjects(200, 0);
  const moneyPathQuery = useOwnerMoneyPathHealth();
  const [search, setSearch] = useState("");
  const [grantTarget, setGrantTarget] = useState<OwnerProjectItem | null>(null);

  const projects = useMemo(() => data?.projects ?? [], [data?.projects]);
  const tenantsById = useMemo(() => {
    const map = new Map<string, OwnerMoneyPathTenantRow>();
    for (const tenant of moneyPathQuery.data?.tenants ?? []) {
      map.set(tenant.project_id, tenant);
    }
    return map;
  }, [moneyPathQuery.data?.tenants]);
  const total = data?.total ?? 0;
  const loading = isLoading || moneyPathQuery.isLoading;
  const errorMessage = error?.message ?? moneyPathQuery.error?.message ?? "";

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return projects.filter((p) => {
      const tenant = tenantsById.get(p.id);
      const issue = tenantIssueSignal(p, tenant);
      return (
        !q ||
        p.name.toLowerCase().includes(q) ||
        (p.owner_ref ?? "").toLowerCase().includes(q) ||
        p.id.toLowerCase().includes(q) ||
        (tenant?.plan_code ?? "").toLowerCase().includes(q) ||
        issue.value.toLowerCase().includes(q) ||
        issue.detail.toLowerCase().includes(q) ||
        (tenant?.next_owner_action ?? "").toLowerCase().includes(q)
      );
    });
  }, [projects, search, tenantsById]);

  const needsAction = projects.filter((project) => tenantNeedsAction(project, tenantsById.get(project.id))).length;
  const sdkSilent = projects.filter((project) => sdkSignal(tenantsById.get(project.id)).value === "No actions").length;
  const connectorMissing = projects.filter((project) => connectorSignal(tenantsById.get(project.id)).value === "missing").length;
  const quotaRisk = projects.filter((project) => ["near_limit", "exceeded"].includes(tenantsById.get(project.id)?.replay_quota_status.state ?? "")).length;

  return (
    <div className="owner-page owner-tenant-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Tenants</h2>
          <p className="hint">{total} customers with plan, protected actions, connectors, proof quota, proof, and next owner action.</p>
        </div>
        <input
          className="input"
          placeholder="Search tenant, plan, issue..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 280 }}
        />
      </div>

      {errorMessage && <div className="alert-strip alert-strip-error">{errorMessage}</div>}

      <div className="owner-tenant-summary-grid">
        <SummaryCard label="Need action" value={fmtCount(needsAction)} detail="Customers not clean/live" tone={needsAction > 0 ? "warn" : "ok"} />
        <SummaryCard label="No actions" value={fmtCount(sdkSilent)} detail="No recent protected actions" tone={sdkSilent > 0 ? "danger" : "ok"} />
        <SummaryCard label="Connector gaps" value={fmtCount(connectorMissing)} detail="Connector readiness missing" tone={connectorMissing > 0 ? "danger" : "ok"} />
        <SummaryCard label="Proof quota" value={fmtCount(quotaRisk)} detail="Near or over proof-check quota" tone={quotaRisk > 0 ? "warn" : "ok"} />
      </div>

      {loading && !errorMessage && <p className="hint">Loading tenants...</p>}

      {!loading && !errorMessage && (
        <div className="owner-table-wrap">
          <table className="owner-table owner-tenant-table">
            <thead>
              <tr>
                {["Customer", "Status", "Plan", "Actions", "Connector", "Proof quota", "Proof", "Next Action", ""].map((h) => (
                  <th key={h} className="owner-th">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={9} className="owner-td owner-td-empty">No tenants found</td>
                </tr>
              )}
              {filtered.map((p, i) => {
                const tenant = tenantsById.get(p.id);
                const issue = tenantIssueSignal(p, tenant);
                const sdk = sdkSignal(tenant);
                const connector = connectorSignal(tenant);
                const proof = proofSignal(tenant);
                return (
                  <tr key={p.id} className={`owner-tr${i < filtered.length - 1 ? "" : " owner-tr-last"}`}>
                    <td className="owner-td">
                      <Link href={`/owner/projects/${p.id}`} className="owner-row-link">{p.name}</Link>
                      <div className="owner-user-id">{p.id}</div>
                      <div className="owner-user-id">Owner: {p.owner_ref ?? "-"}</div>
                    </td>
                    <td className="owner-td">
                      <StatusBadge value={issue.value} tone={issue.tone} />
                      <div className="owner-user-id">{issue.detail}</div>
                    </td>
                    <td className="owner-td">
                      <span className="pill">{tenant?.plan_code ?? "unknown"}</span>
                      <div className="owner-user-id">{tenant?.billing_status?.subscription_status ?? tenant?.billing_status?.state ?? "-"}</div>
                    </td>
                    <td className="owner-td">
                      <StatusBadge value={sdk.value} tone={sdk.tone} />
                      <div className="owner-user-id">{sdk.detail}</div>
                    </td>
                    <td className="owner-td">
                      <StatusBadge value={connector.value} tone={connector.tone} />
                      <div className="owner-user-id">{connector.detail}</div>
                    </td>
                    <td className="owner-td">
                      <StatusBadge value={tenant?.replay_quota_status.state ?? "unknown"} />
                      <div className="owner-user-id">{quotaText(tenant)}</div>
                    </td>
                    <td className="owner-td">
                      <StatusBadge value={proof.value} tone={proof.tone} />
                      <div className="owner-user-id">{proof.detail}</div>
                    </td>
                    <td className="owner-td">
                      <StatusBadge value={tenant ? actionLabel(tenant.next_owner_action) : "Inspect"} tone={tenant ? undefined : "neutral"} />
                    </td>
                    <td className="owner-td owner-tenant-actions">
                      <button className="btn btn-soft" type="button" onClick={() => setGrantTarget(p)}>
                        Change plan
                      </button>
                      <Link href={`/owner/projects/${p.id}`} className="owner-row-link">Open</Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {grantTarget && (
        <OwnerPlanGrantModal
          orgId={grantTarget.id}
          orgLabel={grantTarget.name}
          onClose={() => setGrantTarget(null)}
          onGranted={() => setGrantTarget(null)}
        />
      )}
    </div>
  );
}
