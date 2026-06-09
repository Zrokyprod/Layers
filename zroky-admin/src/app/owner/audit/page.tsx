"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { useAuditLog, useOwnerMoneyPathHealth } from "@/lib/hooks";
import type { AuditLogItem, OwnerMoneyPathTenantRow } from "@/lib/owner-api";

const PAGE_SIZE = 50;

const KNOWN_ACTIONS = [
  "onboarding.completed",
  "diagnosis.created",
  "diagnosis.retry",
  "user.suspended",
  "user.activated",
  "project.suspended",
  "project.activated",
];

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

function parseMeta(raw: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null;
  } catch {
    return null;
  }
}

function MetaCell({ raw }: { raw: string }) {
  const parsed = parseMeta(raw);
  if (!parsed || Object.keys(parsed).length === 0) return <span className="hint">-</span>;
  return (
    <span className="owner-meta-cell">
      {JSON.stringify(parsed, null, 0)}
    </span>
  );
}

function fmtCount(value: number): string {
  return value.toLocaleString();
}

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action.replaceAll("_", " ");
}

function evidenceTone(tenant: OwnerMoneyPathTenantRow): "ok" | "warn" | "danger" | "neutral" {
  if (tenant.blocking_ci_failures_7d > 0 || tenant.provider_key_status.state === "missing") return "danger";
  if (tenant.open_issue_count > 0 || ["near_limit", "exceeded"].includes(tenant.replay_quota_status.state)) return "warn";
  if (tenant.next_owner_action === "monitor") return "ok";
  return "neutral";
}

function resolveEvidenceTenantId(entry: AuditLogItem): string | null {
  if (entry.tenant_id && entry.tenant_id !== "PLATFORM") return entry.tenant_id;
  const meta = parseMeta(entry.metadata_json);
  const target = meta?.target_id;
  return typeof target === "string" && target && target !== "all" ? target : null;
}

function AuditProductEvidence({
  entry,
  tenant,
  error,
}: {
  entry: AuditLogItem;
  tenant: OwnerMoneyPathTenantRow | null;
  error: string;
}) {
  if (error) {
    return <span className="owner-ops-badge owner-ops-badge-danger">Evidence unavailable</span>;
  }
  const tenantId = resolveEvidenceTenantId(entry);
  if (!tenantId) {
    return <span className="owner-ops-badge owner-ops-badge-neutral">Platform event</span>;
  }
  if (!tenant) {
    return (
      <div className="owner-audit-evidence">
        <span className="owner-ops-badge owner-ops-badge-neutral">No tenant proof</span>
        <small>{tenantId}</small>
      </div>
    );
  }
  return (
    <div className="owner-audit-evidence">
      <span className={`owner-ops-badge owner-ops-badge-${evidenceTone(tenant)}`}>
        {actionLabel(tenant.next_owner_action)}
      </span>
      <small>{fmtCount(tenant.open_issue_count)} issue(s), {fmtCount(tenant.blocking_ci_failures_7d)} CI block(s)</small>
      <Link href={`/owner/projects/${tenant.project_id}`} className="owner-row-link">Project</Link>
    </div>
  );
}

export default function AuditLogPage() {
  const [page, setPage] = useState(0);
  const [action, setAction] = useState("");
  const [tenantId, setTenantId] = useState("");

  const { data, isLoading, error, refetch } = useAuditLog({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    action: action || undefined,
    tenant_id: tenantId || undefined,
  });
  const moneyPathQuery = useOwnerMoneyPathHealth();
  const tenantsByProjectId = useMemo(() => {
    const map = new Map<string, OwnerMoneyPathTenantRow>();
    for (const tenant of moneyPathQuery.data?.tenants ?? []) {
      map.set(tenant.project_id, tenant);
    }
    return map;
  }, [moneyPathQuery.data?.tenants]);

  const loading = isLoading;
  const errorMessage = error?.message ?? "";
  const moneyPathError = moneyPathQuery.error?.message ?? "";
  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  return (
    <div className="owner-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Audit Log</h2>
          <p className="hint">
            Immutable owner action trail with current tenant product evidence. {data ? `${data.total.toLocaleString()} total entries.` : ""}
          </p>
        </div>
        <button
          className="btn btn-soft"
          onClick={() => {
            void refetch();
            void moneyPathQuery.refetch();
          }}
          disabled={loading || moneyPathQuery.isFetching}
        >
          Refresh
        </button>
      </div>

      <div className="panel owner-panel-filter">
        <div className="owner-filter-row">
          <div className="owner-filter-group">
            <label className="owner-filter-label">ACTION</label>
            <select
              className="owner-select"
              value={action}
              onChange={(e) => { setAction(e.target.value); setPage(0); }}
            >
              <option value="">All actions</option>
              {KNOWN_ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div className="owner-filter-group">
            <label className="owner-filter-label">TENANT ID</label>
            <input
              className="input"
              placeholder="Filter by tenant..."
              value={tenantId}
              onChange={(e) => { setTenantId(e.target.value); setPage(0); }}
            />
          </div>
          {(action || tenantId) && (
            <button className="btn" onClick={() => { setAction(""); setTenantId(""); setPage(0); }}>
              Clear Filters
            </button>
          )}
        </div>
      </div>

      {errorMessage && <div className="alert-strip alert-strip-error">{errorMessage}</div>}
      {moneyPathError && <div className="alert-strip alert-strip-error">{moneyPathError}</div>}
      {loading && <p className="hint">Loading...</p>}

      {data && (
        <div className="owner-table-wrap">
          <table className="owner-table">
            <thead>
              <tr>
                {["Timestamp", "Action", "Actor", "Tenant", "Product Evidence", "Diagnosis", "Metadata"].map((h) => (
                  <th key={h} className="owner-th">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.entries.length === 0 && (
                <tr>
                  <td colSpan={7} className="owner-td owner-td-empty">No audit log entries found.</td>
                </tr>
              )}
              {data.entries.map((e: AuditLogItem) => (
                <tr key={e.id} className="owner-tr">
                  <td className="owner-td owner-td-ts">{new Date(e.created_at).toLocaleString()}</td>
                  <td className="owner-td">
                    <code className="owner-action-code">{e.action}</code>
                  </td>
                  <td className="owner-td owner-td-truncate">
                    {e.actor_subject || <span className="hint">-</span>}
                  </td>
                  <td className="owner-td-mono">{e.tenant_id}</td>
                  <td className="owner-td">
                    <AuditProductEvidence
                      entry={e}
                      tenant={(resolveEvidenceTenantId(e) && tenantsByProjectId.get(resolveEvidenceTenantId(e) as string)) || null}
                      error={moneyPathError}
                    />
                  </td>
                  <td className="owner-td-mono">{e.diagnosis_id}</td>
                  <td className="owner-td">
                    <MetaCell raw={e.metadata_json} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="owner-pagination">
          <button className="btn btn-soft" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0 || loading}>
            Prev
          </button>
          <span className="owner-pagination-info">Page {page + 1} of {totalPages}</span>
          <button className="btn btn-soft" onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1 || loading}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}
