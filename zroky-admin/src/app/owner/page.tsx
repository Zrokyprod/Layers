"use client";

import Link from "next/link";

import { useOwnerHealth, useOwnerStats, useToggleMaintenance } from "@/lib/hooks";
import type { OwnerHealth } from "@/lib/owner-api";

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className={`owner-stat-card${accent ? " owner-stat-card-accent" : ""}`}>
      <span className="owner-stat-label">{label}</span>
      <span className={`owner-stat-value${accent ? " owner-stat-value-accent" : ""}`}>{value}</span>
      {sub && <span className="owner-stat-sub">{sub}</span>}
    </div>
  );
}

const STATUS_VAR: Record<string, string> = {
  ok: "var(--status-success)",
  degraded: "var(--status-warning)",
  down: "var(--status-error)",
  unknown: "var(--text-secondary)",
};

function HealthBar({ health, onToggleMaintenance, isPending }: { health: OwnerHealth; onToggleMaintenance: () => void; isPending?: boolean }) {
  const overall = health.overall;
  const color = STATUS_VAR[overall] ?? STATUS_VAR.unknown;
  return (
    <div className="owner-health-bar">
      <span className="owner-health-overall">
        <span className="owner-health-dot" style={{ background: color }} />
        <span style={{ color }}>{overall}</span>
      </span>

      <span className="owner-health-sep">|</span>

      {health.services.map((svc) => (
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

export default function OwnerOverviewPage() {
  const statsQuery = useOwnerStats();
  const healthQuery = useOwnerHealth();
  const toggleMutation = useToggleMaintenance();

  const stats = statsQuery.data ?? null;
  const health = healthQuery.data ?? null;
  const statsError = statsQuery.error?.message ?? "";
  const lastRefresh = statsQuery.dataUpdatedAt ? new Date(statsQuery.dataUpdatedAt) : null;

  const handleToggleMaintenance = async () => {
    if (!health) return;
    await toggleMutation.mutateAsync({ enabled: !health.maintenance_mode });
  };

  const fmt = (n: number) => n.toLocaleString();
  const usd = (n: number) =>
    new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);

  return (
    <div className="owner-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Command Center</h2>
          <p className="hint">Live snapshot of all platform activity</p>
        </div>
        <div className="owner-page-header-actions">
          {lastRefresh && (
            <span className="hint">
              Updated {lastRefresh.toLocaleTimeString()} - auto-refresh 60s
            </span>
          )}
          <button className="btn btn-soft" onClick={() => void statsQuery.refetch()}>
            Refresh
          </button>
        </div>
      </div>

      {/* Health bar */}
      {health && (
        <HealthBar health={health} onToggleMaintenance={handleToggleMaintenance} isPending={toggleMutation.isPending} />
      )}

      {statsError && <div className="alert-strip alert-strip-error">{statsError}</div>}
      {!stats && !statsError && (
        <p className="hint">Loading...</p>
      )}

      {stats && (
        <>
          <div className="owner-section">
            <p className="owner-section-label">Users &amp; Projects</p>
            <div className="owner-stat-grid">
              <StatCard label="Total Users" value={fmt(stats.total_users)} accent />
              <StatCard label="New Users (7d)" value={fmt(stats.new_users_last_7d)} sub={`of ${fmt(stats.total_users)} total`} />
              <StatCard label="Active Users (7d)" value={fmt(stats.active_users_last_7d)} />
              <StatCard label="Total Projects" value={fmt(stats.total_projects)} />
            </div>
          </div>

          <div className="owner-section">
            <p className="owner-section-label">API Activity</p>
            <div className="owner-stat-grid">
              <StatCard label="Total Calls" value={fmt(stats.total_calls)} />
              <StatCard label="Calls (last 7d)" value={fmt(stats.calls_last_7d)} sub={`of ${fmt(stats.total_calls)} all time`} accent />
              <StatCard label="Total Cost (all time)" value={usd(stats.total_cost_usd)} />
              <StatCard label="Cost (last 7d)" value={usd(stats.cost_last_7d_usd)} sub="USD billed to projects" />
            </div>
          </div>

          <div className="owner-section">
            <p className="owner-section-label">Quick Actions</p>
            <div className="actions">
              <Link href="/owner/users" className="btn btn-soft">Manage Users</Link>
              <Link href="/owner/projects" className="btn btn-soft">Manage Projects</Link>
              <Link href="/owner/infrastructure" className="btn btn-soft">Infrastructure Health</Link>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
