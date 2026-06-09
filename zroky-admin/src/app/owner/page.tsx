"use client";

import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  GitBranch,
  KeyRound,
  RefreshCw,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";

import { useOwnerHealth, useOwnerMoneyPathHealth, useToggleMaintenance } from "@/lib/hooks";
import type {
  OwnerHealth,
  OwnerLastDeployedSmoke,
  OwnerMoneyPathPlatformSummary,
  OwnerMoneyPathTenantRow,
} from "@/lib/owner-api";

const STATUS_VAR: Record<string, string> = {
  ok: "var(--owner-green)",
  degraded: "var(--owner-amber)",
  down: "var(--owner-red)",
  unknown: "var(--owner-muted)",
};

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

function fmtCount(value: number): string {
  return value.toLocaleString();
}

function fmtDate(value: string | null): string {
  if (!value) return "No capture";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Invalid date";
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

function stateTone(state: string): "ok" | "warn" | "danger" | "neutral" {
  if (["passed", "configured", "ok", "unlimited", "monitor"].includes(state)) return "ok";
  if (["failed", "down", "error", "exceeded", "blocked", "missing"].includes(state)) return "danger";
  if (["partial", "running", "near_limit", "disabled", "not_configured"].includes(state)) return "warn";
  return "neutral";
}

function actionTone(action: string): "ok" | "warn" | "danger" | "neutral" {
  if (["review_blocked_ci", "restore_capture"].includes(action)) return "danger";
  if (["connect_provider_key", "review_replay_quota", "run_replay", "promote_golden", "run_ci_gate"].includes(action)) return "warn";
  if (action === "monitor") return "ok";
  return "neutral";
}

function StatusBadge({ value }: { value: string }) {
  const tone = stateTone(value);
  return <span className={`owner-money-badge owner-money-badge-${tone}`}>{value.replaceAll("_", " ")}</span>;
}

function RiskCard({
  label,
  value,
  detail,
  icon: Icon,
  tone,
}: {
  label: string;
  value: string | number;
  detail: string;
  icon: LucideIcon;
  tone: "ok" | "warn" | "danger" | "neutral";
}) {
  return (
    <div className={`owner-money-risk-card owner-money-risk-${tone}`}>
      <div className="owner-money-risk-icon">
        <Icon size={16} aria-hidden="true" />
      </div>
      <div>
        <span className="owner-stat-label">{label}</span>
        <strong>{value}</strong>
        <p>{detail}</p>
      </div>
    </div>
  );
}

function HealthBar({
  health,
  onToggleMaintenance,
  isPending,
}: {
  health: OwnerHealth;
  onToggleMaintenance: () => void;
  isPending?: boolean;
}) {
  const color = STATUS_VAR[health.overall] ?? STATUS_VAR.unknown;
  return (
    <div className="owner-health-bar owner-money-health-bar">
      <span className="owner-health-overall">
        <span className="owner-health-dot" style={{ background: color }} />
        <span style={{ color }}>{health.overall}</span>
      </span>

      <span className="owner-health-sep">|</span>

      {health.services.slice(0, 5).map((svc) => (
        <span key={svc.name} title={svc.detail ?? svc.name} className="owner-health-svc">
          <span
            className="owner-health-dot owner-health-dot-sm"
            style={{ background: STATUS_VAR[svc.status] ?? STATUS_VAR.unknown }}
          />
          <span className="owner-health-svc-name">{svc.name}</span>
        </span>
      ))}

      <span className="owner-health-sep">|</span>

      <span className="owner-health-maintenance">
        <span className="owner-health-svc-name">Maintenance:</span>
        <button
          onClick={onToggleMaintenance}
          disabled={isPending}
          className={`owner-maint-btn${health.maintenance_mode ? " owner-maint-btn-on" : ""}`}
        >
          {health.maintenance_mode ? "ON" : "OFF"}
        </button>
      </span>

      <Link href="/owner/infrastructure" className="owner-health-details-link">
        Details
      </Link>
    </div>
  );
}

function MoneyPathFunnel({ platform }: { platform: OwnerMoneyPathPlatformSummary }) {
  const steps = [
    { label: "Capture", value: platform.captures_24h, sub: "24h" },
    { label: "Issue", value: platform.issues_open, sub: "open" },
    { label: "Replay", value: platform.replay_runs_7d, sub: "7d" },
    { label: "Verified", value: platform.verified_replay_runs_7d, sub: "7d" },
    { label: "Golden", value: platform.golden_traces_active, sub: "active" },
    { label: "CI Gate", value: platform.ci_runs_7d, sub: "7d" },
    { label: "Blocked", value: platform.ci_blocks_7d, sub: "7d" },
  ];

  return (
    <section className="panel owner-money-funnel">
      <div className="panel-header">
        <h3>Primary Loop</h3>
        <span className="panel-header-note">Capture -&gt; Diagnose -&gt; Issue -&gt; Replay -&gt; Golden -&gt; CI Gate</span>
      </div>
      <div className="owner-money-funnel-row">
        {steps.map((step, index) => (
          <div key={step.label} className="owner-money-funnel-step">
            <span className="owner-stat-label">{step.label}</span>
            <strong>{fmtCount(step.value)}</strong>
            <span>{step.sub}</span>
            {index < steps.length - 1 ? <i aria-hidden="true">-&gt;</i> : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function SmokePanel({ smoke }: { smoke: OwnerLastDeployedSmoke }) {
  return (
    <section className="panel owner-money-proof-panel">
      <div className="panel-header">
        <h3>Deployment Smoke</h3>
        <StatusBadge value={smoke.status} />
      </div>
      <div className="owner-money-proof-body">
        <p className="hint">{smoke.detail ?? "No deployment smoke detail reported."}</p>
        <div className="owner-money-proof-grid">
          <ProofItem label="Project" value={smoke.project_id} />
          <ProofItem label="Call" value={smoke.call_id} />
          <ProofItem label="Golden" value={smoke.golden_trace_id} />
          <ProofItem label="CI run" value={smoke.ci_run_id} />
        </div>
      </div>
    </section>
  );
}

function ProofItem({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="owner-money-proof-item">
      <span>{label}</span>
      <code>{value ?? "missing"}</code>
    </div>
  );
}

function TenantQueue({ tenants }: { tenants: OwnerMoneyPathTenantRow[] }) {
  const rows = tenants.slice(0, 8);
  return (
    <section className="owner-section">
      <div className="owner-money-section-head">
        <div>
          <p className="owner-section-label">Tenant Action Queue</p>
          <p className="hint">Sorted by blocked CI, open issue, provider-key, capture, and quota risk.</p>
        </div>
        <Link href="/owner/projects" className="btn btn-soft">
          View projects
        </Link>
      </div>
      <div className="owner-table-wrap">
        <table className="owner-table">
          <thead>
            <tr>
              {["Project", "Plan", "Capture", "Issues", "Replay / Golden / CI", "Provider", "Quota", "Next"].map((header) => (
                <th key={header} className="owner-th">{header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={8} className="owner-td owner-td-empty">No active tenants were returned by the backend.</td>
              </tr>
            ) : (
              rows.map((tenant) => (
                <tr key={tenant.project_id} className="owner-tr">
                  <td className="owner-td">
                    <Link href={`/owner/projects/${tenant.project_id}`} className="owner-user-name">
                      {tenant.project_name}
                    </Link>
                    <div className="owner-user-id">{tenant.project_id}</div>
                  </td>
                  <td className="owner-td">{tenant.plan_code}</td>
                  <td className="owner-td">
                    <div>{fmtCount(tenant.captures_24h)} in 24h</div>
                    <span className="owner-td-secondary">{fmtDate(tenant.last_capture_at)}</span>
                  </td>
                  <td className="owner-td">
                    <strong>{fmtCount(tenant.open_issue_count)}</strong>
                  </td>
                  <td className="owner-td owner-money-proof-stack">
                    <span>{fmtCount(tenant.replay_run_count_7d)} replay</span>
                    <span>{fmtCount(tenant.golden_trace_count)} Golden</span>
                    <span>{fmtCount(tenant.ci_run_count_7d)} CI</span>
                    {tenant.blocking_ci_failures_7d > 0 ? (
                      <span className="owner-money-table-danger">{fmtCount(tenant.blocking_ci_failures_7d)} blocked</span>
                    ) : null}
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
                    <span className={`owner-money-action owner-money-badge-${actionTone(tenant.next_owner_action)}`}>
                      {actionLabel(tenant.next_owner_action)}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function OwnerOverviewPage() {
  const moneyPathQuery = useOwnerMoneyPathHealth();
  const healthQuery = useOwnerHealth();
  const toggleMutation = useToggleMaintenance();

  const moneyPath = moneyPathQuery.data ?? null;
  const health = healthQuery.data ?? null;
  const platform = moneyPath?.platform ?? null;
  const error = moneyPathQuery.error?.message ?? healthQuery.error?.message ?? "";
  const lastRefresh = moneyPathQuery.dataUpdatedAt ? new Date(moneyPathQuery.dataUpdatedAt) : null;

  const handleRefresh = () => {
    void moneyPathQuery.refetch();
    void healthQuery.refetch();
  };

  const handleToggleMaintenance = async () => {
    if (!health) return;
    await toggleMutation.mutateAsync({ enabled: !health.maintenance_mode });
  };

  return (
    <div className="owner-page owner-money-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Regression Firewall Health</h2>
          <p className="hint">Real owner view of capture, issue, replay, Golden, CI gate, provider-key, and quota state.</p>
        </div>
        <div className="owner-page-header-actions">
          {lastRefresh ? <span className="hint">Updated {lastRefresh.toLocaleTimeString()} - auto-refresh by query cache</span> : null}
          <button className="btn btn-soft" onClick={handleRefresh}>
            <RefreshCw size={15} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </div>

      {health ? (
        <HealthBar health={health} onToggleMaintenance={handleToggleMaintenance} isPending={toggleMutation.isPending} />
      ) : null}

      {error ? <div className="alert-strip alert-strip-error">{error}</div> : null}

      {!moneyPath && !error ? <p className="hint">Loading owner product health...</p> : null}

      {platform ? (
        <>
          <div className="owner-money-risk-grid">
            <RiskCard
              label="Open issues"
              value={fmtCount(platform.issues_open)}
              detail="Needs replay, Golden proof, or resolution."
              icon={ShieldAlert}
              tone={platform.issues_open > 0 ? "danger" : "ok"}
            />
            <RiskCard
              label="Blocked CI"
              value={fmtCount(platform.ci_blocks_7d)}
              detail="GitHub-triggered gates failing in the last 7 days."
              icon={GitBranch}
              tone={platform.ci_blocks_7d > 0 ? "danger" : "ok"}
            />
            <RiskCard
              label="Provider-key gaps"
              value={fmtCount(platform.tenants_missing_provider_key)}
              detail="Tenants that cannot run provider-backed replay."
              icon={KeyRound}
              tone={platform.tenants_missing_provider_key > 0 ? "warn" : "ok"}
            />
            <RiskCard
              label="Replay quota risk"
              value={fmtCount(platform.tenants_near_replay_quota)}
              detail="Tenants near or over replay allocation."
              icon={AlertTriangle}
              tone={platform.tenants_near_replay_quota > 0 ? "warn" : "ok"}
            />
            <RiskCard
              label="Stale capture"
              value={fmtCount(platform.tenants_without_recent_capture)}
              detail="Tenants with no capture in the last 24 hours."
              icon={CircleSlash}
              tone={platform.tenants_without_recent_capture > 0 ? "warn" : "ok"}
            />
            <RiskCard
              label="Verified replay"
              value={fmtCount(platform.verified_replay_runs_7d)}
              detail={`${fmtCount(platform.replay_runs_7d)} total replay runs in 7 days.`}
              icon={CheckCircle2}
              tone={platform.verified_replay_runs_7d > 0 ? "ok" : "neutral"}
            />
          </div>

          <MoneyPathFunnel platform={platform} />

          <div className="owner-money-grid">
            <SmokePanel smoke={platform.last_deployed_smoke} />
            <section className="panel owner-money-proof-panel">
              <div className="panel-header">
                <h3>Release Guardrails</h3>
                <span className="panel-header-note">DB-backed, no placeholder metrics</span>
              </div>
              <div className="owner-money-proof-body owner-money-proof-body-compact">
                <div className="owner-money-proof-grid">
                  <ProofItem label="Active Goldens" value={fmtCount(platform.golden_traces_active)} />
                  <ProofItem label="CI runs 7d" value={fmtCount(platform.ci_runs_7d)} />
                  <ProofItem label="Captures 24h" value={fmtCount(platform.captures_24h)} />
                  <ProofItem label="Open issues" value={fmtCount(platform.issues_open)} />
                </div>
                <div className="actions">
                  <Link href="/owner/projects" className="btn btn-soft">Tenant evidence</Link>
                  <Link href="/owner/pricing" className="btn btn-soft">Entitlements</Link>
                  <Link href="/owner/infrastructure" className="btn btn-soft">Infra proof</Link>
                </div>
              </div>
            </section>
          </div>

          <TenantQueue tenants={moneyPath?.tenants ?? []} />
        </>
      ) : null}
    </div>
  );
}
