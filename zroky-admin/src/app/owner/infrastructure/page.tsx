"use client";

import { useState } from "react";

import { useOwnerHealth, useOwnerInfra, useToggleMaintenance } from "@/lib/hooks";
import type { ServiceStatus } from "@/lib/owner-api";

const STATUS_VAR: Record<string, string> = {
  ok: "var(--status-success)",
  degraded: "var(--status-warning)",
  down: "var(--status-error)",
  unknown: "var(--text-secondary)",
};

function ServiceCard({ svc }: { svc: ServiceStatus }) {
  const color = STATUS_VAR[svc.status] ?? STATUS_VAR.unknown;
  return (
    <div className="owner-svc-card">
      <div className="owner-svc-card-header">
        <span className="owner-svc-card-name">{svc.name}</span>
        <span className="owner-status-badge" style={{ background: `${color}22`, color, border: `1px solid ${color}44` }}>
          {svc.status}
        </span>
      </div>
      {svc.latency_ms !== null && svc.latency_ms !== undefined && (
        <span className="hint">Latency: <strong>{svc.latency_ms} ms</strong></span>
      )}
      {svc.detail && <span className="owner-svc-detail">{svc.detail}</span>}
    </div>
  );
}

function InfraRow({ label, value, warn }: { label: string; value: string | number; warn?: boolean }) {
  return (
    <div className="infra-row">
      <span className="infra-row-label">{label}</span>
      <span className={`infra-row-value${warn ? " infra-row-warn" : ""}`}>{value}</span>
    </div>
  );
}

export default function InfrastructurePage() {
  const [maintMsg, setMaintMsg] = useState("");

  const healthQuery = useOwnerHealth();
  const infraQuery = useOwnerInfra();
  const toggleMutation = useToggleMaintenance();

  const health = healthQuery.data ?? null;
  const infra = infraQuery.data ?? null;
  const error = healthQuery.error?.message ?? infraQuery.error?.message ?? "";
  const lastRefresh = healthQuery.dataUpdatedAt ? new Date(healthQuery.dataUpdatedAt) : null;

  const handleToggleMaintenance = async () => {
    if (!health) return;
    await toggleMutation.mutateAsync({ enabled: !health.maintenance_mode, message: maintMsg || undefined });
  };

  const er = health?.exchange_rate as Record<string, unknown> | undefined;

  return (
    <div className="owner-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Infrastructure Health</h2>
          <p className="hint">Live status of all platform services - auto-refresh every 30s</p>
        </div>
        <div className="owner-page-header-actions">
          {lastRefresh && (
            <span className="hint">Updated {lastRefresh.toLocaleTimeString()}</span>
          )}
          <button className="btn btn-soft" onClick={() => void healthQuery.refetch()}>Refresh</button>
        </div>
      </div>

      {error && <div className="alert-strip alert-strip-error">{error}</div>}

      {health && (
        <div className="owner-section">
          <p className="owner-section-label">Core Services</p>
          <div className="owner-stat-grid">
            {health.services.map((svc) => (
              <ServiceCard key={svc.name} svc={svc} />
            ))}
          </div>
        </div>
      )}

      {/* Exchange Rate */}
      {er && (
        <div className="panel">
          <div className="panel-header">Exchange Rate Cache</div>
          <InfraRow label="Status" value={String(er.cache_status ?? "unknown")} warn={er.cache_status !== "ok"} />
          <InfraRow label="Rate (USD to INR)" value={er.cache_rate != null ? String(er.cache_rate) : "-"} />
          <InfraRow label="Cache Age" value={er.cache_age_seconds != null ? `${er.cache_age_seconds}s` : "-"} warn={(er.cache_age_seconds as number) > 600} />
          <InfraRow label="Is Stale" value={er.cache_is_stale ? "Yes" : "No"} warn={er.cache_is_stale === true} />
          <InfraRow label="Is Usable" value={er.cache_is_usable ? "Yes" : "No"} warn={!er.cache_is_usable} />
        </div>
      )}

      {infra && (
        <div className="panel">
          <div className="panel-header">
            Celery Workers &amp; Queues
            <span className="panel-header-note">
              {infra.worker_count} worker{infra.worker_count !== 1 ? "s" : ""} active
            </span>
          </div>
          {infra.worker_names.length > 0 && (
            <InfraRow
              label="Worker names"
              value={infra.worker_names.join(", ")}
            />
          )}
          {infra.queues.map((q) => (
            <InfraRow
              key={q.queue_name}
              label={q.queue_name}
              value={`${q.pending} pending`}
              warn={q.pending > 50}
            />
          ))}
        </div>
      )}

      {/* DB Table Sizes */}
      {infra && Object.keys(infra.db_table_sizes).length > 0 && (
        <div className="panel">
          <div className="panel-header">Database Table Sizes</div>
          {Object.entries(infra.db_table_sizes).map(([table, count]) => (
            <InfraRow key={table} label={table} value={count.toLocaleString()} warn={count < 0} />
          ))}
        </div>
      )}

      {health && (
        <div className="panel">
          <div className="panel-header">Maintenance Mode</div>
          <p className="hint" style={{ marginBottom: 14 }}>
            When enabled, a maintenance banner is shown to users. The API continues to operate normally - use this for scheduled maintenance windows.
          </p>
          <div className="owner-maint-controls">
            <span className={`owner-maint-status${health.maintenance_mode ? " owner-maint-status-on" : " owner-maint-status-off"}`}>
              {health.maintenance_mode ? "MAINTENANCE ACTIVE" : "Normal operation"}
            </span>
            <input
              className="input"
              placeholder="Optional message to show users"
              value={maintMsg}
              onChange={(e) => setMaintMsg(e.target.value)}
              style={{ flex: 1, minWidth: 200, maxWidth: 360 }}
            />
            <button
              className={health.maintenance_mode ? "btn btn-danger" : "btn btn-primary"}
              onClick={handleToggleMaintenance}
              disabled={toggleMutation.isPending}
            >
              {toggleMutation.isPending ? "Updating..." : health.maintenance_mode ? "Disable Maintenance" : "Enable Maintenance"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
