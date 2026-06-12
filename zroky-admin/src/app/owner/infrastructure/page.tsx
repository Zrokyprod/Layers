"use client";

import { useState, type ReactNode } from "react";

import { useOwnerHealth, useOwnerInfra, useOwnerMoneyPathHealth, useToggleMaintenance } from "@/lib/hooks";
import type { InfraStats, OwnerHealth, OwnerLastDeployedSmoke, OwnerMoneyPathHealth, ServiceStatus } from "@/lib/owner-api";

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

function smokeTone(status: string | null | undefined): "ok" | "warn" | "danger" | "neutral" {
  if (status === "passed" || status === "pass" || status === "ok") return "ok";
  if (status === "failed" || status === "fail" || status === "error") return "danger";
  if (status === "running" || status === "pending") return "warn";
  return "neutral";
}

function OpsBadge({ tone, children }: { tone: "ok" | "warn" | "danger" | "neutral"; children: ReactNode }) {
  return <span className={`owner-ops-badge owner-ops-badge-${tone}`}>{children}</span>;
}

function OpsHealthProof({ health, infra }: { health: OwnerHealth | null; infra: InfraStats | null }) {
  const downServices = health?.services.filter((service) => ["down", "unknown"].includes(service.status)).length ?? null;
  const degradedServices = health?.services.filter((service) => service.status === "degraded").length ?? null;
  const pendingQueues = infra?.queues.reduce((sum, queue) => sum + queue.pending, 0) ?? null;
  const failedQueueSignals = infra?.queues.reduce((sum, queue) => sum + queue.failed, 0) ?? null;
  const tableProbeFailures = infra ? Object.values(infra.db_table_sizes).filter((count) => count < 0).length : null;
  const tone = health?.maintenance_mode ? "warn" : health?.overall === "ok" ? "ok" : health ? "danger" : "neutral";

  return (
    <section className="panel owner-infra-proof-panel">
      <div className="panel-header">
        Ops Health Proof
        <OpsBadge tone={tone}>{health?.maintenance_mode ? "maintenance" : health?.overall ?? "checking"}</OpsBadge>
      </div>
      <div className="owner-infra-proof-grid">
        <div className="owner-infra-proof-card">
          <span className="owner-stat-label">Service failures</span>
          <strong>{downServices ?? "-"}</strong>
          <p>{degradedServices ?? "-"} degraded service(s)</p>
        </div>
        <div className="owner-infra-proof-card">
          <span className="owner-stat-label">Workers</span>
          <strong>{infra?.worker_count ?? "-"}</strong>
          <p>{infra?.worker_names.length ? infra.worker_names.join(", ") : "No worker names reported"}</p>
        </div>
        <div className="owner-infra-proof-card">
          <span className="owner-stat-label">Queue pending</span>
          <strong>{pendingQueues ?? "-"}</strong>
          <p>{failedQueueSignals ?? "-"} failed queue signal(s)</p>
        </div>
        <div className="owner-infra-proof-card">
          <span className="owner-stat-label">DB probes</span>
          <strong>{tableProbeFailures ?? "-"}</strong>
          <p>table count probes failed</p>
        </div>
      </div>
    </section>
  );
}

function DeployedSmokeProof({ smoke, error }: { smoke: OwnerLastDeployedSmoke | null; error: string }) {
  if (error) {
    return (
      <section className="panel owner-infra-proof-panel">
        <div className="panel-header">Deployed Smoke Proof</div>
        <div className="owner-infra-proof-body">
          <div className="alert-strip alert-strip-error">{error}</div>
        </div>
      </section>
    );
  }

  return (
    <section className="panel owner-infra-proof-panel">
      <div className="panel-header">
        Deployed Smoke Proof
        <OpsBadge tone={smokeTone(smoke?.status)}>{smoke?.status ?? "unavailable"}</OpsBadge>
      </div>
      <div className="owner-infra-proof-body">
        <p className="hint">
          {smoke?.detail ?? "No deployed money-path smoke has been reported by backend."}
        </p>
        <div className="owner-ops-proof-grid">
          <div className="owner-ops-proof-item"><span>Checked</span><code>{smoke?.checked_at ? new Date(smoke.checked_at).toLocaleString() : "-"}</code></div>
          <div className="owner-ops-proof-item"><span>Project</span><code>{smoke?.project_id ?? "-"}</code></div>
          <div className="owner-ops-proof-item"><span>Golden Trace</span><code>{smoke?.golden_trace_id ?? "-"}</code></div>
          <div className="owner-ops-proof-item"><span>CI Run</span><code>{smoke?.ci_run_id ?? "-"}</code></div>
        </div>
      </div>
    </section>
  );
}

function ReplayWorkerFreshness({ moneyPath }: { moneyPath: OwnerMoneyPathHealth | null }) {
  const staleTenants = (moneyPath?.tenants ?? []).filter((tenant) => (tenant.replay_jobs_stale ?? 0) > 0);
  const pendingJobs = moneyPath?.platform.replay_jobs_pending ?? 0;
  const staleJobs = moneyPath?.platform.replay_jobs_stale ?? 0;
  const tone = staleJobs > 0 ? "danger" : pendingJobs > 0 ? "warn" : "ok";

  return (
    <section className="panel owner-infra-proof-panel">
      <div className="panel-header">
        Replay Worker Freshness
        <OpsBadge tone={tone}>{staleJobs > 0 ? "stale leases" : pendingJobs > 0 ? "backlog" : "ok"}</OpsBadge>
      </div>
      <div className="owner-infra-proof-body">
        <div className="owner-ops-proof-grid">
          <div className="owner-ops-proof-item"><span>Pending replay jobs</span><code>{pendingJobs.toLocaleString()}</code></div>
          <div className="owner-ops-proof-item"><span>Stale replay jobs</span><code>{staleJobs.toLocaleString()}</code></div>
          <div className="owner-ops-proof-item"><span>Tenants affected</span><code>{(moneyPath?.platform.tenants_with_stale_replay_workers ?? staleTenants.length).toLocaleString()}</code></div>
          <div className="owner-ops-proof-item"><span>Generated</span><code>{moneyPath?.generated_at ? new Date(moneyPath.generated_at).toLocaleTimeString() : "-"}</code></div>
        </div>
        {staleTenants.length ? (
          <div className="owner-ops-list">
            {staleTenants.slice(0, 5).map((tenant) => (
              <div key={tenant.project_id} className="owner-billing-breakdown-row">
                <span>{tenant.project_name}</span>
                <strong>{tenant.replay_jobs_stale ?? 0} stale</strong>
              </div>
            ))}
          </div>
        ) : (
          <p className="hint">No stale replay worker leases reported by owner money-path health.</p>
        )}
      </div>
    </section>
  );
}

export default function InfrastructurePage() {
  const [maintMsg, setMaintMsg] = useState("");

  const healthQuery = useOwnerHealth();
  const infraQuery = useOwnerInfra();
  const moneyPathQuery = useOwnerMoneyPathHealth();
  const toggleMutation = useToggleMaintenance();

  const health = healthQuery.data ?? null;
  const infra = infraQuery.data ?? null;
  const moneyPath = moneyPathQuery.data ?? null;
  const error = healthQuery.error?.message ?? infraQuery.error?.message ?? "";
  const moneyPathError = moneyPathQuery.error?.message ?? "";
  const lastRefreshAt = Math.max(healthQuery.dataUpdatedAt || 0, infraQuery.dataUpdatedAt || 0, moneyPathQuery.dataUpdatedAt || 0);
  const lastRefresh = lastRefreshAt ? new Date(lastRefreshAt) : null;

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
          <button
            className="btn btn-soft"
            onClick={() => {
              void healthQuery.refetch();
              void infraQuery.refetch();
              void moneyPathQuery.refetch();
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      {error && <div className="alert-strip alert-strip-error">{error}</div>}

      <div className="owner-infra-proof-layout">
        <OpsHealthProof health={health} infra={infra} />
        <DeployedSmokeProof smoke={moneyPath?.platform.last_deployed_smoke ?? null} error={moneyPathError} />
        <ReplayWorkerFreshness moneyPath={moneyPath} />
      </div>

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
