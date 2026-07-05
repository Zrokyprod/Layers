"use client";

import { useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CircleSlash,
  Filter,
  GitBranch,
  KeyRound,
  RefreshCw,
  Search,
  ShieldAlert,
} from "lucide-react";

import { useOwnerMoneyPathHealth } from "@/lib/hooks";
import type { OwnerMoneyPathPlatformSummary, OwnerMoneyPathTenantRow } from "@/lib/owner-api";

type RiskFilter =
  | "all"
  | "no-capture"
  | "no-goldens"
  | "failed-ci"
  | "provider-missing"
  | "stale-worker"
  | "stale-pricing"
  | "quota-risk"
  | "billing-risk"
  | "support"
  | "getting-value";
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

const FILTERS: Array<{ id: RiskFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "no-capture", label: "No actions" },
  { id: "no-goldens", label: "No receipt baseline" },
  { id: "failed-ci", label: "Release blocked" },
  { id: "provider-missing", label: "Connector gap" },
  { id: "stale-worker", label: "Proof worker stale" },
  { id: "stale-pricing", label: "Stale pricing" },
  { id: "quota-risk", label: "Proof quota" },
  { id: "billing-risk", label: "Billing risk" },
  { id: "support", label: "Support" },
  { id: "getting-value", label: "Getting value" },
];

function fmtCount(value: number): string {
  return value.toLocaleString();
}

function fmtDate(value: string | null): string {
  if (!value) return "No recent capture";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Invalid timestamp";
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action.replaceAll("_", " ");
}

function stateTone(state: string): Tone {
  if (["passed", "configured", "ok", "unlimited", "monitor", "getting_value", "none", "free_default"].includes(state)) return "ok";
  if (["failed", "down", "error", "exceeded", "blocked", "missing", "loss_detected", "risk", "urgent", "failure", "unverified"].includes(state)) return "danger";
  if (["partial", "running", "near_limit", "disabled", "not_configured", "degraded", "backpressure", "setup_missing", "at_risk", "stale", "fallback", "missing_paid", "open"].includes(state)) return "warn";
  return "neutral";
}

function actionTone(action: string): Tone {
  if (["review_blocked_ci", "restore_capture", "restore_replay_worker", "fix_billing", "fix_metering"].includes(action)) return "danger";
  if (["connect_provider_key", "review_replay_quota", "review_event_quota", "review_support", "refresh_pricing", "run_replay", "promote_golden", "run_ci_gate"].includes(action)) return "warn";
  if (action === "monitor") return "ok";
  return "neutral";
}

function loopTone(tenant: OwnerMoneyPathTenantRow, step: string): Tone {
  if (step === "capture") {
    const durability = tenant.capture_durability_status?.state;
    if (durability === "loss_detected" || durability === "backpressure") return "danger";
    if (durability === "degraded") return "warn";
    return tenant.captures_24h > 0 ? "ok" : "danger";
  }
  if (step === "issue") return tenant.open_issue_count > 0 ? "danger" : "ok";
  if (step === "replay") {
    if (tenant.verified_replay_count_7d > 0) return "ok";
    if (tenant.replay_run_count_7d > 0) return "warn";
    return tenant.open_issue_count > 0 ? "danger" : "neutral";
  }
  if (step === "golden") {
    if (tenant.golden_trace_count > 0) return "ok";
    return tenant.verified_replay_count_7d > 0 ? "warn" : "neutral";
  }
  if (step === "ci") {
    if (tenant.blocking_ci_failures_7d > 0) return "danger";
    if (tenant.ci_run_count_7d > 0) return "ok";
    return tenant.golden_trace_count > 0 ? "warn" : "neutral";
  }
  return "neutral";
}

function captureDurabilityLabel(tenant: OwnerMoneyPathTenantRow): string {
  const durability = tenant.capture_durability_status;
  if (!durability) return "unknown";
  if (durability.loss_count > 0) return `${durability.loss_count} lost`;
  if (durability.backpressure_rejections > 0) return `${durability.backpressure_rejections} blocked`;
  if (durability.spool_backlog > 0) return `${durability.spool_backlog} queued`;
  return durability.state;
}

function tenantMatchesFilter(tenant: OwnerMoneyPathTenantRow, filter: RiskFilter): boolean {
  if (filter === "all") return true;
  if (filter === "no-capture") return tenant.captures_24h === 0;
  if (filter === "no-goldens") return tenant.golden_trace_count === 0;
  if (filter === "failed-ci") return tenant.blocking_ci_failures_7d > 0;
  if (filter === "provider-missing") return tenant.provider_key_status.state === "missing";
  if (filter === "stale-worker") return (tenant.replay_jobs_stale ?? 0) > 0;
  if (filter === "stale-pricing") return ["drift", "missing", "fallback", "stale", "degraded"].includes(tenant.pricing_cost_status?.state ?? "");
  if (filter === "quota-risk") return ["near_limit", "exceeded"].includes(tenant.replay_quota_status.state);
  if (filter === "billing-risk") return ["risk", "missing_paid", "unknown"].includes(tenant.billing_status?.state ?? "");
  if (filter === "support") return ["urgent", "open"].includes(tenant.support_status?.state ?? "");
  return tenant.value_status === "getting_value";
}

function tenantSearchMatch(tenant: OwnerMoneyPathTenantRow, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    tenant.project_name.toLowerCase().includes(q) ||
    tenant.project_id.toLowerCase().includes(q) ||
    tenant.plan_code.toLowerCase().includes(q) ||
    tenant.next_owner_action.toLowerCase().includes(q)
    || (tenant.value_status ?? "").toLowerCase().includes(q)
    || (tenant.money_path_breaks ?? []).some((code) => code.toLowerCase().includes(q))
  );
}

function StatusBadge({ value, tone }: { value: string; tone?: Tone }) {
  const resolved = tone ?? stateTone(value);
  return <span className={`owner-money-badge owner-money-badge-${resolved}`}>{value.replaceAll("_", " ")}</span>;
}

function RiskMetric({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: number;
  detail: string;
  tone: Tone;
}) {
  return (
    <div className={`owner-money-path-metric owner-money-risk-${tone}`}>
      <span className="owner-stat-label">{label}</span>
      <strong>{fmtCount(value)}</strong>
      <p>{detail}</p>
    </div>
  );
}

function PlatformLoop({ platform }: { platform: OwnerMoneyPathPlatformSummary }) {
  const steps = [
    { label: "Protected actions", value: platform.captures_24h, sub: "captured in 24h" },
    { label: "Issue", value: platform.issues_open, sub: "open groups" },
    { label: "Proof checks", value: platform.replay_runs_7d, sub: "checks in 7d" },
    { label: "Verified outcomes", value: platform.verified_replay_runs_7d, sub: "source matched" },
    { label: "Receipt baseline", value: platform.golden_traces_active, sub: "active receipts" },
    { label: "Release checks", value: platform.ci_runs_7d, sub: "checks in 7d" },
    { label: "Release blocks", value: platform.ci_blocks_7d, sub: "blocked changes" },
  ];

  return (
    <section className="panel owner-money-path-loop">
      <div className="panel-header">
        <h3>Platform Control Path</h3>
        <span className="panel-header-note">Backend-reported action control state</span>
      </div>
      <div className="owner-money-path-loop-grid">
        {steps.map((step, index) => (
          <div key={step.label} className="owner-money-path-step">
            <span className="owner-stat-label">{step.label}</span>
            <strong>{fmtCount(step.value)}</strong>
            <small>{step.sub}</small>
            {index < steps.length - 1 ? <i aria-hidden="true">-&gt;</i> : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function TenantLoopEvidence({ tenant }: { tenant: OwnerMoneyPathTenantRow }) {
  const steps = [
    { id: "capture", label: "Protected actions", value: `${fmtCount(tenant.captures_24h)} in 24h`, detail: fmtDate(tenant.last_capture_at) },
    { id: "issue", label: "Issue", value: `${fmtCount(tenant.open_issue_count)} open`, detail: tenant.open_issue_count ? "triage required" : "no open issue" },
    { id: "replay", label: "Proof checks", value: `${fmtCount(tenant.replay_run_count_7d)} checks`, detail: `${fmtCount(tenant.verified_replay_count_7d)} verified` },
    { id: "golden", label: "Receipt baseline", value: `${fmtCount(tenant.golden_trace_count)} active`, detail: tenant.golden_trace_count ? "release-ready proof" : "no active receipt" },
    { id: "ci", label: "Release check", value: `${fmtCount(tenant.ci_run_count_7d)} checks`, detail: `${fmtCount(tenant.blocking_ci_failures_7d)} blocked` },
  ];

  return (
    <div className="owner-money-tenant-loop">
      {steps.map((step) => (
        <div key={step.id} className={`owner-money-tenant-step owner-money-badge-${loopTone(tenant, step.id)}`}>
          <span>{step.label}</span>
          <strong>{step.value}</strong>
          <small>{step.detail}</small>
        </div>
      ))}
    </div>
  );
}

function TenantEvidencePanel({ tenant }: { tenant: OwnerMoneyPathTenantRow | null }) {
  if (!tenant) {
    return (
      <aside className="panel owner-money-tenant-panel" aria-label="Selected tenant money-path evidence">
        <div className="owner-money-empty-panel">
          <CircleSlash size={20} aria-hidden="true" />
          <p>No tenant selected.</p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="panel owner-money-tenant-panel" aria-label="Selected tenant money-path evidence">
      <div className="panel-header">
        <h3>{tenant.project_name}</h3>
        <StatusBadge value={actionLabel(tenant.next_owner_action)} tone={actionTone(tenant.next_owner_action)} />
      </div>
      <div className="owner-money-tenant-body">
        <div className="owner-money-proof-grid">
          <EvidenceItem label="Project" value={tenant.project_id} />
          <EvidenceItem label="Plan" value={tenant.plan_code} />
          <EvidenceItem label="Capture durability" value={captureDurabilityLabel(tenant)} />
          <EvidenceItem label="Connector keys" value={`${tenant.provider_key_status.state} (${tenant.provider_key_status.active_provider_count})`} />
          <EvidenceItem label="Value status" value={(tenant.value_status ?? "unknown").replaceAll("_", " ")} />
          <EvidenceItem
            label="Event metering"
            value={
              tenant.event_metering_status?.limit == null
                ? `${tenant.event_metering_status?.state ?? "unknown"} / ${fmtCount(tenant.event_metering_status?.used ?? 0)} used`
                : `${tenant.event_metering_status?.state ?? "unknown"} / ${fmtCount(tenant.event_metering_status?.used ?? 0)} of ${fmtCount(tenant.event_metering_status.limit)}`
            }
          />
          <EvidenceItem label="Proof worker" value={`${tenant.replay_jobs_pending ?? 0} pending, ${tenant.replay_jobs_stale ?? 0} stale`} />
          <EvidenceItem label="Pricing" value={`${tenant.pricing_cost_status?.state ?? "unknown"} (${tenant.pricing_cost_status?.pricing_age_days ?? "-"}d)`} />
          <EvidenceItem label="Billing" value={`${tenant.billing_status?.state ?? "unknown"} / ${tenant.billing_status?.subscription_status ?? tenant.billing_status?.plan_code ?? tenant.plan_code}`} />
          <EvidenceItem label="Support" value={`${tenant.support_status?.state ?? "none"} (${tenant.support_status?.open_count ?? 0} open)`} />
          <EvidenceItem
            label="Proof quota"
            value={
              tenant.replay_quota_status.limit === -1
                ? `${fmtCount(tenant.replay_quota_status.used)} used`
                : `${fmtCount(tenant.replay_quota_status.used)} / ${fmtCount(tenant.replay_quota_status.limit)}`
            }
          />
        </div>
        <div className="owner-money-proof-grid">
          <EvidenceItem
            label="Broken steps"
            value={(tenant.money_path_breaks ?? tenant.launch_blockers ?? []).length ? (tenant.money_path_breaks ?? tenant.launch_blockers ?? []).join(", ") : "none"}
          />
          <EvidenceItem label="Priority score" value={String(tenant.tenant_priority_score ?? 0)} />
        </div>
        <TenantLoopEvidence tenant={tenant} />
        <div className="owner-money-tenant-actions">
          <Link href={`/owner/projects/${tenant.project_id}`} className="btn btn-soft">Project detail</Link>
          <Link href="/owner/pricing" className="btn btn-soft">Entitlements</Link>
          <Link href="/owner/infrastructure" className="btn btn-soft">Ops proof</Link>
        </div>
      </div>
    </aside>
  );
}

function EvidenceItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="owner-money-proof-item">
      <span>{label}</span>
      <code>{value}</code>
    </div>
  );
}

export default function OwnerMoneyPathPage() {
  const moneyPathQuery = useOwnerMoneyPathHealth();
  const moneyPath = moneyPathQuery.data ?? null;
  const platform = moneyPath?.platform ?? null;
  const tenants = useMemo(() => moneyPath?.tenants ?? [], [moneyPath?.tenants]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<RiskFilter>("all");
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  const filteredTenants = useMemo(() => {
    return tenants.filter((tenant) => tenantMatchesFilter(tenant, filter) && tenantSearchMatch(tenant, query));
  }, [filter, query, tenants]);

  const selectedTenant = useMemo(() => {
    if (!filteredTenants.length) return null;
    if (!selectedProjectId) return filteredTenants[0];
    return filteredTenants.find((tenant) => tenant.project_id === selectedProjectId) ?? filteredTenants[0];
  }, [filteredTenants, selectedProjectId]);

  return (
    <div className="owner-page owner-money-path-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Money Path</h2>
          <p className="hint">Tenant drill-down for protected actions, issues, proof checks, receipt baselines, and release checks.</p>
        </div>
        <div className="owner-page-header-actions">
          {moneyPath ? <span className="hint">Generated {new Date(moneyPath.generated_at).toLocaleTimeString()}</span> : null}
          <button className="btn btn-soft" onClick={() => void moneyPathQuery.refetch()}>
            <RefreshCw size={15} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </div>

      {moneyPathQuery.error ? <div className="alert-strip alert-strip-error">{moneyPathQuery.error.message}</div> : null}
      {!moneyPath && !moneyPathQuery.error ? <p className="hint">Loading money-path health...</p> : null}

      {platform ? (
        <>
          <div className="owner-money-path-summary">
            <RiskMetric label="No actions" value={platform.tenants_without_recent_capture} detail="Tenants without protected actions in 24h." tone={platform.tenants_without_recent_capture > 0 ? "danger" : "ok"} />
            <RiskMetric label="No receipt baseline" value={platform.tenants_without_goldens ?? 0} detail="Tenants missing active receipt baselines." tone={(platform.tenants_without_goldens ?? 0) > 0 ? "warn" : "ok"} />
            <RiskMetric label="Release blocked" value={platform.tenants_with_failed_ci ?? platform.ci_blocks_7d} detail="Tenants with blocked release checks." tone={platform.ci_blocks_7d > 0 ? "danger" : "ok"} />
            <RiskMetric label="Capture durability" value={platform.gateway_unhealthy_tenants ?? 0} detail="Tenants with unhealthy gateway capture guarantees." tone={(platform.gateway_loss_tenants ?? 0) > 0 ? "danger" : (platform.gateway_unhealthy_tenants ?? 0) > 0 ? "warn" : "ok"} />
            <RiskMetric label="Connector gaps" value={platform.tenants_missing_provider_key} detail="Tenants missing connector or analysis readiness." tone={platform.tenants_missing_provider_key > 0 ? "warn" : "ok"} />
            <RiskMetric label="Proof workers" value={platform.tenants_with_stale_replay_workers ?? 0} detail="Tenants with stale proof worker leases." tone={(platform.tenants_with_stale_replay_workers ?? 0) > 0 ? "danger" : "ok"} />
            <RiskMetric label="Stale pricing" value={platform.tenants_with_stale_pricing ?? 0} detail="Tenants with weak cost evidence." tone={(platform.tenants_with_stale_pricing ?? 0) > 0 ? "warn" : "ok"} />
            <RiskMetric label="Proof quota" value={platform.tenants_with_quota_risk ?? platform.tenants_near_replay_quota} detail="Tenants near or above proof-check limits." tone={(platform.tenants_with_quota_risk ?? platform.tenants_near_replay_quota) > 0 ? "warn" : "ok"} />
            <RiskMetric label="Billing risk" value={platform.tenants_with_billing_risk ?? 0} detail="Tenants with broken subscription state." tone={(platform.tenants_with_billing_risk ?? 0) > 0 ? "danger" : "ok"} />
            <RiskMetric label="Metering failures" value={platform.metering_failure_tenants ?? 0} detail={`${fmtCount(platform.event_counter_failure_count ?? 0)} event counter failure(s).`} tone={(platform.metering_failure_tenants ?? 0) > 0 ? "danger" : "ok"} />
            <RiskMetric label="Support" value={platform.support_tickets_open ?? 0} detail={`${fmtCount(platform.support_tickets_urgent ?? 0)} urgent ticket(s).`} tone={(platform.support_tickets_urgent ?? 0) > 0 ? "danger" : (platform.support_tickets_open ?? 0) > 0 ? "warn" : "ok"} />
          </div>

          <PlatformLoop platform={platform} />

          <div className="owner-money-path-layout">
            <section className="owner-money-path-main">
              <div className="panel owner-money-path-controls">
                <div className="owner-money-search">
                  <Search size={16} aria-hidden="true" />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search tenant, project id, plan, action"
                    aria-label="Search tenants"
                  />
                </div>
                <div className="owner-money-filter-row" aria-label="Risk filters">
                  <Filter size={15} aria-hidden="true" />
                  {FILTERS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={`owner-money-filter-btn${filter === item.id ? " owner-money-filter-btn-active" : ""}`}
                      onClick={() => setFilter(item.id)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="owner-table-wrap">
                <table className="owner-table">
                  <thead>
                    <tr>
                      {["Tenant", "Value", "Breaks", "Protected actions", "Proof checks", "Receipt baseline", "Release check", "Connector", "Worker", "Metering", "Pricing", "Billing", "Support", "Proof quota", "Next", ""].map((header) => (
                        <th key={header || "action"} className="owner-th">{header}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTenants.length === 0 ? (
                      <tr>
                        <td colSpan={16} className="owner-td owner-td-empty">No tenants match the current money-path filter.</td>
                      </tr>
                    ) : (
                      filteredTenants.map((tenant) => (
                        <tr
                          key={tenant.project_id}
                          className={`owner-tr${selectedTenant?.project_id === tenant.project_id ? " owner-tr-selected" : ""}`}
                        >
                          <td className="owner-td">
                            <Link href={`/owner/projects/${tenant.project_id}`} className="owner-user-name">
                              {tenant.project_name}
                            </Link>
                            <div className="owner-user-id">{tenant.project_id} - {tenant.plan_code}</div>
                          </td>
                          <td className="owner-td">
                            <StatusBadge value={tenant.value_status ?? "unknown"} />
                            <div className="owner-user-id">score {tenant.tenant_priority_score ?? 0}</div>
                          </td>
                          <td className="owner-td owner-money-proof-stack">
                            {(tenant.money_path_breaks ?? tenant.launch_blockers ?? []).slice(0, 2).map((code) => (
                              <span key={code} className="owner-td-secondary">{code.replaceAll("_", " ")}</span>
                            ))}
                            {(tenant.money_path_breaks ?? tenant.launch_blockers ?? []).length === 0 ? <span className="owner-td-secondary">No breaks</span> : null}
                          </td>
                          <td className="owner-td">
                            <strong>{fmtCount(tenant.captures_24h)}</strong>
                            <div className="owner-user-id">{fmtDate(tenant.last_capture_at)}</div>
                          </td>
                          <td className="owner-td">
                            <div>{fmtCount(tenant.replay_run_count_7d)} checks</div>
                            <span className="owner-td-secondary">{fmtCount(tenant.verified_replay_count_7d)} verified</span>
                          </td>
                          <td className="owner-td">{fmtCount(tenant.golden_trace_count)}</td>
                          <td className="owner-td">
                            <StatusBadge
                              value={tenant.blocking_ci_failures_7d > 0 ? `${fmtCount(tenant.blocking_ci_failures_7d)} blocked` : `${fmtCount(tenant.ci_run_count_7d)} checks`}
                              tone={tenant.blocking_ci_failures_7d > 0 ? "danger" : tenant.ci_run_count_7d > 0 ? "ok" : "neutral"}
                            />
                          </td>
                          <td className="owner-td">
                            <StatusBadge value={tenant.provider_key_status.state} />
                          </td>
                          <td className="owner-td">
                            <StatusBadge value={(tenant.replay_jobs_stale ?? 0) > 0 ? "stale" : (tenant.replay_jobs_pending ?? 0) > 0 ? "running" : "ok"} />
                            <div className="owner-user-id">{tenant.replay_jobs_pending ?? 0} pending</div>
                          </td>
                          <td className="owner-td">
                            <StatusBadge value={tenant.event_metering_status?.state ?? "unknown"} />
                            <div className="owner-user-id">
                              {tenant.event_metering_status?.limit == null
                                ? `${fmtCount(tenant.event_metering_status?.used ?? 0)} used`
                                : `${fmtCount(tenant.event_metering_status?.used ?? 0)} / ${fmtCount(tenant.event_metering_status.limit)}`}
                            </div>
                          </td>
                          <td className="owner-td">
                            <StatusBadge value={tenant.pricing_cost_status?.state ?? "unknown"} />
                            <div className="owner-user-id">{tenant.pricing_cost_status?.pricing_age_days ?? "-"}d age</div>
                          </td>
                          <td className="owner-td">
                            <StatusBadge value={tenant.billing_status?.state ?? "unknown"} />
                            <div className="owner-user-id">{tenant.billing_status?.subscription_status ?? tenant.billing_status?.plan_code ?? tenant.plan_code}</div>
                          </td>
                          <td className="owner-td">
                            <StatusBadge value={tenant.support_status?.state ?? "none"} />
                            <div className="owner-user-id">{fmtCount(tenant.support_status?.open_count ?? 0)} open</div>
                          </td>
                          <td className="owner-td">
                            <StatusBadge value={tenant.replay_quota_status.state} />
                            <div className="owner-user-id">
                              {tenant.replay_quota_status.limit === -1
                                ? `${fmtCount(tenant.replay_quota_status.used)} used`
                                : `${fmtCount(tenant.replay_quota_status.used)} / ${fmtCount(tenant.replay_quota_status.limit)}`}
                            </div>
                          </td>
                          <td className="owner-td">
                            <StatusBadge value={actionLabel(tenant.next_owner_action)} tone={actionTone(tenant.next_owner_action)} />
                          </td>
                          <td className="owner-td">
                            <button
                              type="button"
                              className="owner-row-link owner-money-inspect-btn"
                              onClick={() => setSelectedProjectId(tenant.project_id)}
                            >
                              Inspect
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <TenantEvidencePanel tenant={selectedTenant} />
          </div>

          <section className="owner-money-path-risk-panels">
            <RiskListPanel
              title="Release Block Evidence"
              icon={<GitBranch size={16} aria-hidden="true" />}
              empty="No blocked release checks in the 7-day window."
              tenants={tenants.filter((tenant) => tenant.blocking_ci_failures_7d > 0)}
              getDetail={(tenant) => `${fmtCount(tenant.blocking_ci_failures_7d)} blocked check(s), ${fmtCount(tenant.golden_trace_count)} receipt baseline(s)`}
            />
            <RiskListPanel
              title="Connector Gaps"
              icon={<KeyRound size={16} aria-hidden="true" />}
              empty="Every active tenant has connector readiness."
              tenants={tenants.filter((tenant) => tenant.provider_key_status.state === "missing")}
              getDetail={(tenant) => `${actionLabel(tenant.next_owner_action)} - ${fmtCount(tenant.open_issue_count)} open issue(s)`}
            />
            <RiskListPanel
              title="Proof Quota Risk"
              icon={<AlertTriangle size={16} aria-hidden="true" />}
              empty="No tenant is near or above proof quota."
              tenants={tenants.filter((tenant) => ["near_limit", "exceeded"].includes(tenant.replay_quota_status.state))}
              getDetail={(tenant) =>
                tenant.replay_quota_status.limit === -1
                  ? `${fmtCount(tenant.replay_quota_status.used)} used, unlimited plan`
                  : `${fmtCount(tenant.replay_quota_status.used)} of ${fmtCount(tenant.replay_quota_status.limit)} used`
              }
            />
            <RiskListPanel
              title="Stale Protected Actions"
              icon={<ShieldAlert size={16} aria-hidden="true" />}
              empty="Every active tenant has protected actions in the 24-hour window."
              tenants={tenants.filter((tenant) => tenant.captures_24h === 0)}
              getDetail={(tenant) => `Last capture: ${fmtDate(tenant.last_capture_at)}`}
            />
            <RiskListPanel
              title="Capture Durability"
              icon={<ShieldAlert size={16} aria-hidden="true" />}
              empty="Every gateway reports protected capture."
              tenants={tenants.filter((tenant) => {
                const durability = tenant.capture_durability_status;
                return Boolean(durability && durability.state !== "ok" && durability.state !== "unknown");
              })}
              getDetail={(tenant) => captureDurabilityLabel(tenant)}
            />
          </section>
        </>
      ) : null}
    </div>
  );
}

function RiskListPanel({
  title,
  icon,
  tenants,
  empty,
  getDetail,
}: {
  title: string;
  icon: ReactNode;
  tenants: OwnerMoneyPathTenantRow[];
  empty: string;
  getDetail: (tenant: OwnerMoneyPathTenantRow) => string;
}) {
  return (
    <section className="panel owner-money-risk-list-panel">
      <div className="panel-header">
        <h3>{title}</h3>
        {icon}
      </div>
      <div className="owner-money-risk-list">
        {tenants.length === 0 ? (
          <p className="hint">{empty}</p>
        ) : (
          tenants.slice(0, 5).map((tenant) => (
            <Link key={tenant.project_id} href={`/owner/projects/${tenant.project_id}`} className="owner-money-risk-row">
              <span>
                <strong>{tenant.project_name}</strong>
                <small>{tenant.project_id}</small>
              </span>
              <em>{getDetail(tenant)}</em>
            </Link>
          ))
        )}
      </div>
    </section>
  );
}
