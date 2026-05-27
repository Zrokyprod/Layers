"use client";

import { useState } from "react";

import { useAuditLog } from "@/lib/hooks";
import type { AuditLogItem } from "@/lib/owner-api";

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

function MetaCell({ raw }: { raw: string }) {
  let parsed: Record<string, unknown> | null = null;
  try { parsed = JSON.parse(raw); } catch { /* ignore */ }
  if (!parsed || Object.keys(parsed).length === 0) return <span className="hint">-</span>;
  return (
    <span className="owner-meta-cell">
      {JSON.stringify(parsed, null, 0)}
    </span>
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

  const loading = isLoading;
  const errorMessage = error?.message ?? "";
  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  return (
    <div className="owner-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Audit Log</h2>
          <p className="hint">
            Immutable record of platform events. {data ? `${data.total.toLocaleString()} total entries.` : ""}
          </p>
        </div>
        <button className="btn btn-soft" onClick={() => void refetch()} disabled={loading}>
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
      {loading && <p className="hint">Loading...</p>}

      {data && (
        <div className="owner-table-wrap">
          <table className="owner-table">
            <thead>
              <tr>
                {["Timestamp", "Action", "Actor", "Tenant", "Diagnosis", "Metadata"].map((h) => (
                  <th key={h} className="owner-th">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.entries.length === 0 && (
                <tr>
                  <td colSpan={6} className="owner-td owner-td-empty">No audit log entries found.</td>
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
