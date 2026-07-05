"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BadgeDollarSign,
  RefreshCw,
  ServerCog,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

import {
  useOwnerBillingSummary,
  useOwnerHealth,
  useOwnerLaunchReadiness,
  useOwnerMoneyPathHealth,
} from "@/lib/hooks";
import type {
  OwnerBillingSummary,
  OwnerHealth,
  OwnerLaunchReadiness,
  OwnerMoneyPathPlatformSummary,
  OwnerMoneyPathTenantRow,
} from "@/lib/owner-api";

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

function fmtCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString();
}

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action.replaceAll("_", " ");
}

function statusTone(value: string | undefined | null): Tone {
  const state = value ?? "unknown";
  if (["live", "pass", "passed", "ok", "active", "verified", "configured", "monitor", "unlimited"].includes(state)) return "ok";
  if (["blocked", "fail", "failed", "down", "error", "missing", "risk", "urgent", "exceeded", "unverified"].includes(state)) return "danger";
  if (["restricted", "checking", "not_verified", "warn", "degraded", "near_limit", "open", "stale", "fallback", "missing_paid", "partial"].includes(state)) return "warn";
  return "neutral";
}

function tenantNeedsAction(tenant: OwnerMoneyPathTenantRow): boolean {
  return (
    tenant.next_owner_action !== "monitor" ||
    tenant.open_issue_count > 0 ||
    tenant.blocking_ci_failures_7d > 0 ||
    tenant.provider_key_status.state === "missing" ||
    ["near_limit", "exceeded"].includes(tenant.replay_quota_status.state) ||
    ["risk", "missing_paid", "unknown"].includes(tenant.billing_status?.state ?? "")
  );
}

function fmtRelative(value: string | null | undefined, now: number): string {
  if (!value) return "No captures";
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return "Unknown";
  const seconds = Math.max(0, Math.floor((now - parsed) / 1000));
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function activeSubscriptions(billing: OwnerBillingSummary | null): number | null {
  if (!billing) return null;
  return billing.by_status.find((row) => row.status === "active")?.count ?? billing.total_subscriptions - billing.overdue - billing.canceled;
}

function paidTrafficStatus({
  readiness,
  health,
  platform,
  badServices,
}: {
  readiness: OwnerLaunchReadiness | null;
  health: OwnerHealth | null;
  platform: OwnerMoneyPathPlatformSummary | null;
  badServices: number;
}): { value: string; detail: string; tone: Tone } {
  if (!readiness || !health) {
    return {
      value: "Checking",
      detail: "Waiting for launch, money, and infra checks.",
      tone: "warn",
    };
  }

  const criticalBreaks =
    readiness.hard_blockers.length +
    (platform?.gateway_loss_tenants ?? 0) +
    (platform?.replay_jobs_stale ?? 0) +
    (platform?.metering_failure_tenants ?? 0) +
    (platform?.billing_launch_blockers?.length ?? 0);
  const failingGates = readiness.gates.filter((gate) => gate.status !== "pass").length;
  const blockerCount = Math.max(criticalBreaks, readiness.hard_blockers.length, failingGates);

  if (!readiness.paid_launch_allowed || criticalBreaks > 0) {
    return {
      value: "Blocked",
      detail: `${blockerCount} critical issue${blockerCount === 1 ? "" : "s"} before paid traffic.`,
      tone: "danger",
    };
  }

  if (health.overall !== "ok" || badServices > 0 || (platform?.issues_open ?? 0) > 0) {
    return {
      value: "Restricted",
      detail: "Paid traffic can run, but owner attention is needed.",
      tone: "warn",
    };
  }

  return {
    value: "Live",
    detail: "Payments, quota, proof, capture, and infra checks are clean.",
    tone: "ok",
  };
}

function issueForTenant(tenant: OwnerMoneyPathTenantRow): { issue: string; severity: string; tone: Tone } {
  if (!tenant.last_capture_at || tenant.captures_24h === 0) return { issue: "No recent protected actions", severity: "High", tone: "danger" };
  if (tenant.provider_key_status.state === "missing") return { issue: "Connector key missing", severity: "Medium", tone: "warn" };
  if (tenant.capture_durability_status?.state && tenant.capture_durability_status.state !== "ok") return { issue: "Capture risk", severity: "High", tone: "danger" };
  if ((tenant.replay_jobs_stale ?? 0) > 0) return { issue: "Proof worker stale", severity: "High", tone: "danger" };
  if (["risk", "missing_paid", "unknown"].includes(tenant.billing_status?.state ?? "")) return { issue: "Billing risk", severity: "High", tone: "danger" };
  if (["near_limit", "exceeded"].includes(tenant.replay_quota_status.state)) return { issue: "Proof quota risk", severity: "Medium", tone: "warn" };
  if (tenant.blocking_ci_failures_7d > 0) return { issue: "Release check blocked", severity: "Medium", tone: "warn" };
  if (tenant.open_issue_count > 0) return { issue: "Open support/product issue", severity: "Medium", tone: "warn" };
  return { issue: actionLabel(tenant.next_owner_action), severity: "Low", tone: "neutral" };
}

function issuePriority(tone: Tone): number {
  if (tone === "danger") return 0;
  if (tone === "warn") return 1;
  return 2;
}

function StatusBadge({ value, tone }: { value: string; tone?: Tone }) {
  return <span className={`owner-money-badge owner-money-badge-${tone ?? statusTone(value.toLowerCase())}`}>{value.replaceAll("_", " ")}</span>;
}

function CommandCard({
  label,
  value,
  detail,
  href,
  tone,
  icon: Icon,
}: {
  label: string;
  value: string;
  detail: string;
  href: string;
  tone: Tone;
  icon: LucideIcon;
}) {
  return (
    <Link href={href} className={`owner-command-card owner-command-card-${tone}`}>
      <span className="owner-command-icon" aria-hidden="true">
        <Icon size={18} />
      </span>
      <span className="owner-stat-label">{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </Link>
  );
}

function MiniBarChart({
  title,
  note,
  items,
}: {
  title: string;
  note: string;
  items: Array<{ label: string; value: number; detail: string; tone?: Tone }>;
}) {
  const max = Math.max(1, ...items.map((item) => item.value));
  const criticalCount = items.filter((item) => item.tone === "danger" && item.value > 0).length;
  const warningCount = items.filter((item) => item.tone === "warn" && item.value > 0).length;
  const panelTone: Tone = criticalCount > 0 ? "danger" : warningCount > 0 ? "warn" : "ok";
  const panelStatus = criticalCount > 0 ? "Needs owner action" : warningCount > 0 ? "Watch" : "Clean";

  return (
    <section className={`panel owner-live-chart owner-snapshot-card owner-snapshot-card-${panelTone}`}>
      <div className="panel-header">
        <div>
          <h3>{title}</h3>
          <span className="panel-header-note">{note}</span>
        </div>
        <StatusBadge value={panelStatus} tone={panelTone} />
      </div>
      <div className="owner-snapshot-list" role="img" aria-label={`${title} chart`}>
        {items.map((item) => (
          <div key={item.label} className={`owner-snapshot-row owner-snapshot-row-${item.tone ?? "neutral"}`}>
            <div className="owner-snapshot-row-main">
              <span className="owner-snapshot-value">{fmtCount(item.value)}</span>
              <div>
                <strong>{item.label}</strong>
                <p>{item.detail}</p>
              </div>
            </div>
            <div className="owner-snapshot-track" aria-hidden="true">
              <span className={`owner-snapshot-bar owner-snapshot-bar-${item.tone ?? "neutral"}`} style={{ width: `${Math.round((item.value / max) * 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function OwnerOverviewPage() {
  const [now, setNow] = useState(() => Date.now());
  const moneyPathQuery = useOwnerMoneyPathHealth();
  const readinessQuery = useOwnerLaunchReadiness();
  const healthQuery = useOwnerHealth();
  const billingQuery = useOwnerBillingSummary();

  const moneyPath = moneyPathQuery.data ?? null;
  const platform = moneyPath?.platform ?? null;
  const readiness = readinessQuery.data ?? null;
  const health = healthQuery.data ?? null;
  const billing = billingQuery.data ?? null;
  const tenants = moneyPath?.tenants ?? [];
  const issueRows = tenants
    .filter(tenantNeedsAction)
    .map((tenant) => ({ tenant, ...issueForTenant(tenant) }))
    .sort((a, b) => issuePriority(a.tone) - issuePriority(b.tone));
  const tenantRiskCount = issueRows.length;
  const badServices = health?.services.filter((service) => !["ok", "unknown"].includes(service.status)) ?? [];
  const firstTenantAction = tenants.find(tenantNeedsAction);
  const paidTraffic = paidTrafficStatus({ readiness, health, platform, badServices: badServices.length });
  const activeSubCount = activeSubscriptions(billing);
  const quotaRisk = tenants.filter((tenant) => ["near_limit", "exceeded"].includes(tenant.replay_quota_status.state)).length;
  const error =
    moneyPathQuery.error?.message ??
    readinessQuery.error?.message ??
    healthQuery.error?.message ??
    billingQuery.error?.message ??
    "";
  const lastRefresh = Math.max(
    moneyPathQuery.dataUpdatedAt || 0,
    readinessQuery.dataUpdatedAt || 0,
    healthQuery.dataUpdatedAt || 0,
    billingQuery.dataUpdatedAt || 0,
  );
  const isStale = lastRefresh > 0 && now - lastRefresh > 60_000;

  const refreshAll = useCallback(() => {
    setNow(Date.now());
    void moneyPathQuery.refetch();
    void readinessQuery.refetch();
    void healthQuery.refetch();
    void billingQuery.refetch();
  }, [billingQuery.refetch, healthQuery.refetch, moneyPathQuery.refetch, readinessQuery.refetch]);

  useEffect(() => {
    const interval = window.setInterval(refreshAll, 15_000);
    return () => window.clearInterval(interval);
  }, [refreshAll]);

  return (
    <div className="owner-page owner-command-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Owner 360 Home</h2>
          <p className="hint">Simple live view for paid traffic, customer actions, money, and infrastructure.</p>
        </div>
        <div className="owner-page-header-actions">
          {lastRefresh ? (
            <span className={`hint ${isStale ? "owner-live-stale" : ""}`}>
              Live check every 15s - updated {new Date(lastRefresh).toLocaleTimeString()}
              {isStale ? " - stale data" : ""}
            </span>
          ) : null}
          <button className="btn btn-soft" type="button" onClick={refreshAll}>
            <RefreshCw size={15} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="alert-strip alert-strip-error">{error}</div> : null}
      {!moneyPath && !error ? <p className="hint">Loading owner command center...</p> : null}

      <div className="owner-command-grid">
        <CommandCard
          label="Paid Traffic"
          value={paidTraffic.value}
          detail={paidTraffic.detail}
          href="/owner/money-path"
          tone={paidTraffic.tone}
          icon={ShieldCheck}
        />
        <CommandCard
          label="Customers Needing Action"
          value={fmtCount(tenantRiskCount)}
          detail={firstTenantAction ? `${firstTenantAction.project_name}: ${actionLabel(firstTenantAction.next_owner_action)}` : "No tenant action queued"}
          href="/owner/projects"
          tone={tenantRiskCount > 0 ? "warn" : moneyPath ? "ok" : "neutral"}
          icon={Activity}
        />
        <CommandCard
          label="Money"
          value={fmtCount(billing?.total_subscriptions)}
          detail={`${fmtCount(activeSubCount)} active, ${fmtCount(billing?.overdue)} overdue, ${fmtCount(billing?.canceled)} canceled`}
          href="/owner/pricing"
          tone={(billing?.overdue ?? 0) > 0 || (billing?.canceled ?? 0) > 0 ? "danger" : billing ? "ok" : "warn"}
          icon={BadgeDollarSign}
        />
        <CommandCard
          label="Infrastructure"
          value={health?.overall ?? "unknown"}
          detail={badServices.length ? `${badServices.length} degraded/down service(s)` : "Core services healthy"}
          href="/owner/infrastructure"
          tone={statusTone(health?.overall)}
          icon={ServerCog}
        />
      </div>

      <div className="owner-live-charts">
        <MiniBarChart
          title="Control Plane Health"
          note="Protected-action volume and proof quality"
          items={[
            { label: "Protected actions", value: platform?.captures_24h ?? 0, detail: "Action intents captured in the last 24h.", tone: (platform?.captures_24h ?? 0) > 0 ? "ok" : "neutral" },
            { label: "Proof checks", value: platform?.replay_runs_7d ?? 0, detail: "Outcome/proof checks requested in 7 days.", tone: "neutral" },
            { label: "Verified outcomes", value: platform?.verified_replay_runs_7d ?? 0, detail: "Checks that matched the source of record.", tone: (platform?.verified_replay_runs_7d ?? 0) > 0 ? "ok" : "neutral" },
            { label: "Receipt baselines", value: platform?.golden_traces_active ?? 0, detail: "Signed evidence artifacts ready for review.", tone: "neutral" },
          ]}
        />
        <MiniBarChart
          title="Customer Risk"
          note="Tenants that need owner attention"
          items={[
            { label: "Need action", value: tenantRiskCount, detail: "Customers with an owner action queued.", tone: tenantRiskCount > 0 ? "warn" : "ok" },
            { label: "No recent actions", value: platform?.tenants_without_recent_capture ?? 0, detail: "Tenants with silent protected-action flow.", tone: (platform?.tenants_without_recent_capture ?? 0) > 0 ? "danger" : "ok" },
            { label: "Connector gaps", value: platform?.tenants_missing_provider_key ?? 0, detail: "Customers missing connector or analysis readiness.", tone: (platform?.tenants_missing_provider_key ?? 0) > 0 ? "warn" : "ok" },
            { label: "Proof quota", value: quotaRisk, detail: "Tenants near or above proof-check limits.", tone: quotaRisk > 0 ? "warn" : "ok" },
          ]}
        />
        <MiniBarChart
          title="Money & Infra"
          note="Revenue health and platform blockers"
          items={[
            { label: "Subscriptions", value: billing?.total_subscriptions ?? 0, detail: "Total billing accounts visible to owner.", tone: (billing?.total_subscriptions ?? 0) > 0 ? "ok" : "neutral" },
            { label: "Overdue", value: billing?.overdue ?? 0, detail: "Accounts needing billing recovery.", tone: (billing?.overdue ?? 0) > 0 ? "danger" : "ok" },
            { label: "Open issues", value: platform?.issues_open ?? 0, detail: "Open product/support issues from customer signals.", tone: (platform?.issues_open ?? 0) > 0 ? "warn" : "ok" },
            { label: "Bad services", value: badServices.length, detail: "Services currently degraded or down.", tone: badServices.length > 0 ? "danger" : "ok" },
          ]}
        />
      </div>

      <section className="panel owner-live-issues">
        <div className="panel-header">
          <h3>Customer Action Queue</h3>
          <span className="panel-header-note">Customers that need owner attention across action intake, connectors, proof, billing, or support.</span>
        </div>
        {issueRows.length ? (
          <div className="owner-live-issue-list">
            {issueRows.slice(0, 5).map(({ tenant, issue, severity, tone }) => (
              <Link key={tenant.project_id} href={`/owner/projects/${tenant.project_id}`} className="owner-live-issue-row">
                <span className={`owner-live-issue-icon owner-live-issue-icon-${tone}`} aria-hidden="true">
                  <AlertTriangle size={15} />
                </span>
                <span>
                  <strong>{tenant.project_name}</strong>
                  <small>{issue}</small>
                </span>
                <StatusBadge value={severity} tone={tone} />
                <span className="owner-live-issue-meta">{fmtRelative(tenant.last_capture_at, now)}</span>
                <span className="owner-live-issue-meta">{actionLabel(tenant.next_owner_action)}</span>
              </Link>
            ))}
          </div>
        ) : (
          <p className="hint">No customer action signals reported.</p>
        )}
      </section>
    </div>
  );
}
