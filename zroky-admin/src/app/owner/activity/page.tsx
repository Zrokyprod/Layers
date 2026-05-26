"use client";

import { useState } from "react";

import { useActivityFeed } from "@/lib/hooks";
import { formatDateTime } from "@/lib/format";

const PAGE_SIZE = 50;

const KNOWN_ACTIONS = [
  "call.created",
  "call.updated",
  "diagnosis.completed",
  "alert.created",
  "alert.resolved",
  "project.created",
  "user.joined",
  "settings.updated",
];

export default function OwnerActivityPage() {
  const [page, setPage] = useState(0);
  const [actionFilter, setActionFilter] = useState("");

  const { data, isLoading, error, refetch } = useActivityFeed({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    action: actionFilter || undefined,
  });

  const loading = isLoading;
  const errorMessage = error?.message ?? "";
  const totalPages = data ? Math.ceil((data.total ?? 0) / PAGE_SIZE) : 0;

  return (
    <div className="owner-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Platform Activity</h2>
          <p className="hint">Real-time feed of platform events and user actions.</p>
        </div>
        <button className="btn btn-soft" onClick={() => void refetch()} disabled={loading}>
          Refresh
        </button>
      </div>

      <div className="panel owner-panel-filter">
        <div className="owner-filter-row">
          <div className="owner-filter-group">
            <label className="owner-filter-label">ACTION FILTER</label>
            <select
              className="owner-select"
              value={actionFilter}
              onChange={(e) => { setActionFilter(e.target.value); setPage(0); }}
            >
              <option value="">All actions</option>
              {KNOWN_ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          {actionFilter && (
            <button className="btn" onClick={() => { setActionFilter(""); setPage(0); }}>Clear</button>
          )}
        </div>
      </div>

      {errorMessage && <div className="alert-strip alert-strip-error">{errorMessage}</div>}
      {loading && <p className="hint">Loading…</p>}

      {data && (
        <div className="owner-table-wrap">
          <table className="owner-table">
            <thead>
              <tr>
                {["Timestamp", "Action", "Actor Subject", "Tenant", "Details"].map((h) => (
                  <th key={h} className="owner-th">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data.items ?? []).length === 0 && (
                <tr>
                  <td colSpan={5} className="owner-td owner-td-empty">No activity found.</td>
                </tr>
              )}
              {(data.items ?? []).map((item) => (
                <tr key={item.log_id} className="owner-tr">
                  <td className="owner-td owner-td-ts">{formatDateTime(item.created_at)}</td>
                  <td className="owner-td">
                    <code className="owner-action-code">{item.action}</code>
                  </td>
                  <td className="owner-td owner-td-truncate">{item.actor_subject ?? "—"}</td>
                  <td className="owner-td-mono">{item.tenant_id}</td>
                  <td className="owner-td">
                    <span className="owner-meta-cell">
                      {JSON.stringify(item.metadata ?? {}, null, 0).slice(0, 200)}
                    </span>
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
            ← Prev
          </button>
          <span className="owner-pagination-info">Page {page + 1} of {totalPages}</span>
          <button className="btn btn-soft" onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1 || loading}>
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
