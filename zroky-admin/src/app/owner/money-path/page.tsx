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

type RiskFilter = "all" | "blocked-ci" | "open-issues" | "provider-missing" | "quota-risk" | "stale-capture" | "healthy";
type Tone = "ok" | "warn" | "danger" | "neutral";

const ACTION_LABELS: Record<string, string> = {
  review_blocked_ci: "Review blocked CI",
  restore_capture: "Restore capture",
  connect_provider_key: "Connect provider key",
  review_replay_quota: "Review replay quota",
  run_replay: "Run replay",
  promote_golden: "Promote Golden",
  run_ci_gate: "Run CI gate",
  continue_triage: "Continue triage",
  monitor: "Monitor",
};

const FILTERS: Array<{ id: RiskFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "blocked-ci", label: "Blocked CI" },
  { id: "open-issues", label: "Open issues" },
  { id: "provider-missing", label: "Provider missing" },
  { id: "quota-risk", label: "Quota risk" },
  { id: "stale-capture", label: "Stale capture" },
  { id: "healthy", label: "Monitor" },
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
  if (["passed", "configured", "ok", "unlimited", "monitor"].includes(state)) return "ok";
  if (["failed", "down", "error", "exceeded", "blocked", "missing"].includes(state)) return "danger";
  if (["partial", "running", "near_limit", "disabled", "not_configured"].includes(state)) return "warn";
  return "neutral";
}

function actionTone(action: string): Tone {
  if (["review_blocked_ci", "restore_capture"].includes(action)) return "danger";
  if (["connect_provider_key", "review_replay_quota", "run_replay", "promote_golden", "run_ci_gate"].includes(action)) return "warn";
  if (action === "monitor") return "ok";
  return "neutral";
}

function loopTone(tenant: OwnerMoneyPathTenantRow, step: string): Tone {
  if (step === "capture") return tenant.captures_24h > 0 ? "ok" : "danger";
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

function tenantMatchesFilter(tenant: OwnerMoneyPathTenantRow, filter: RiskFilter): boolean {
  if (filter === "all") return true;
  if (filter === "blocked-ci") return tenant.blocking_ci_failures_7d > 0;
  if (filter === "open-issues") return tenant.open_issue_count > 0;
  if (filter === "provider-missing") return tenant.provider_key_status.state === "missing";
  if (filter === "quota-risk") return ["near_limit", "exceeded"].includes(tenant.replay_quota_status.state);
  if (filter === "stale-capture") return tenant.captures_24h === 0;
  return tenant.next_owner_action === "monitor";
}

function tenantSearchMatch(tenant: OwnerMoneyPathTenantRow, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    tenant.project_name.toLowerCase().includes(q) ||
    tenant.project_id.toLowerCase().includes(q) ||
    tenant.plan_code.toLowerCase().includes(q) ||
    tenant.next_owner_action.toLowerCase().includes(q)
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
    { label: "Capture", value: platform.captures_24h, sub: "calls in 24h" },
    { label: "Issue", value: platform.issues_open, sub: "open groups" },
    { label: "Replay", value: platform.replay_runs_7d, sub: "runs in 7d" },
    { label: "Verified", value: platform.verified_replay_runs_7d, sub: "verified runs" },
    { label: "Golden", value: platform.golden_traces_active, sub: "active traces" },
    { label: "CI Gate", value: platform.ci_runs_7d, sub: "runs in 7d" },
    { label: "Blocked", value: platform.ci_blocks_7d, sub: "failed gates" },
  ];

  return (
    <section className="panel owner-money-path-loop">
      <div className="panel-header">
        <h3>Platform Money Path</h3>
        <span className="panel-header-note">Backend-reported loop state</span>
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
    { id: "capture", label: "Capture", value: `${fmtCount(tenant.captures_24h)} in 24h`, detail: fmtDate(tenant.last_capture_at) },
    { id: "issue", label: "Issue", value: `${fmtCount(tenant.open_issue_count)} open`, detail: tenant.open_issue_count ? "triage required" : "no open issue" },
    { id: "replay", label: "Replay", value: `${fmtCount(tenant.replay_run_count_7d)} runs`, detail: `${fmtCount(tenant.verified_replay_count_7d)} verified` },
    { id: "golden", label: "Golden", value: `${fmtCount(tenant.golden_trace_count)} active`, detail: tenant.golden_trace_count ? "CI eligible" : "no active trace" },
    { id: "ci", label: "CI Gate", value: `${fmtCount(tenant.ci_run_count_7d)} runs`, detail: `${fmtCount(tenant.blocking_ci_failures_7d)} blocked` },
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
          <EvidenceItem label="Provider keys" value={`${tenant.provider_key_status.state} (${tenant.provider_key_status.active_provider_count})`} />
          <EvidenceItem
            label="Replay quota"
            value={
              tenant.replay_quota_status.limit === -1
                ? `${fmtCount(tenant.replay_quota_status.used)} used`
                : `${fmtCount(tenant.replay_quota_status.used)} / ${fmtCount(tenant.replay_quota_status.limit)}`
            }
          />
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
          <p className="hint">Tenant drill-down for Capture -&gt; Issue -&gt; Replay -&gt; Golden -&gt; CI Gate proof.</p>
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
            <RiskMetric label="Open issues" value={platform.issues_open} detail="Grouped failures waiting on proof or resolution." tone={platform.issues_open > 0 ? "danger" : "ok"} />
            <RiskMetric label="Blocked CI" value={platform.ci_blocks_7d} detail="GitHub-triggered gate failures in 7 days." tone={platform.ci_blocks_7d > 0 ? "danger" : "ok"} />
            <RiskMetric label="Provider gaps" value={platform.tenants_missing_provider_key} detail="Tenants unable to run provider-backed replay." tone={platform.tenants_missing_provider_key > 0 ? "warn" : "ok"} />
            <RiskMetric label="Quota risk" value={platform.tenants_near_replay_quota} detail="Tenants near or above replay limits." tone={platform.tenants_near_replay_quota > 0 ? "warn" : "ok"} />
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
                      {["Tenant", "Capture", "Issue", "Replay", "Golden", "CI", "Provider", "Quota", "Next", ""].map((header) => (
                        <th key={header || "action"} className="owner-th">{header}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTenants.length === 0 ? (
                      <tr>
                        <td colSpan={10} className="owner-td owner-td-empty">No tenants match the current money-path filter.</td>
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
                            <strong>{fmtCount(tenant.captures_24h)}</strong>
                            <div className="owner-user-id">{fmtDate(tenant.last_capture_at)}</div>
                          </td>
                          <td className="owner-td">
                            <StatusBadge value={`${fmtCount(tenant.open_issue_count)} open`} tone={tenant.open_issue_count > 0 ? "danger" : "ok"} />
                          </td>
                          <td className="owner-td">
                            <div>{fmtCount(tenant.replay_run_count_7d)} runs</div>
                            <span className="owner-td-secondary">{fmtCount(tenant.verified_replay_count_7d)} verified</span>
                          </td>
                          <td className="owner-td">{fmtCount(tenant.golden_trace_count)}</td>
                          <td className="owner-td">
                            <StatusBadge
                              value={tenant.blocking_ci_failures_7d > 0 ? `${fmtCount(tenant.blocking_ci_failures_7d)} blocked` : `${fmtCount(tenant.ci_run_count_7d)} runs`}
                              tone={tenant.blocking_ci_failures_7d > 0 ? "danger" : tenant.ci_run_count_7d > 0 ? "ok" : "neutral"}
                            />
                          </td>
                          <td className="owner-td">
                            <StatusBadge value={tenant.provider_key_status.state} />
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
              title="Blocked CI Evidence"
              icon={<GitBranch size={16} aria-hidden="true" />}
              empty="No blocking CI failures in the 7-day window."
              tenants={tenants.filter((tenant) => tenant.blocking_ci_failures_7d > 0)}
              getDetail={(tenant) => `${fmtCount(tenant.blocking_ci_failures_7d)} blocked gate(s), ${fmtCount(tenant.golden_trace_count)} active Golden trace(s)`}
            />
            <RiskListPanel
              title="Provider Key Gaps"
              icon={<KeyRound size={16} aria-hidden="true" />}
              empty="Every active tenant has at least one provider key."
              tenants={tenants.filter((tenant) => tenant.provider_key_status.state === "missing")}
              getDetail={(tenant) => `${actionLabel(tenant.next_owner_action)} - ${fmtCount(tenant.open_issue_count)} open issue(s)`}
            />
            <RiskListPanel
              title="Replay Quota Risk"
              icon={<AlertTriangle size={16} aria-hidden="true" />}
              empty="No tenant is near or above replay quota."
              tenants={tenants.filter((tenant) => ["near_limit", "exceeded"].includes(tenant.replay_quota_status.state))}
              getDetail={(tenant) =>
                tenant.replay_quota_status.limit === -1
                  ? `${fmtCount(tenant.replay_quota_status.used)} used, unlimited plan`
                  : `${fmtCount(tenant.replay_quota_status.used)} of ${fmtCount(tenant.replay_quota_status.limit)} used`
              }
            />
            <RiskListPanel
              title="Stale Capture"
              icon={<ShieldAlert size={16} aria-hidden="true" />}
              empty="Every active tenant has capture in the 24-hour window."
              tenants={tenants.filter((tenant) => tenant.captures_24h === 0)}
              getDetail={(tenant) => `Last capture: ${fmtDate(tenant.last_capture_at)}`}
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
