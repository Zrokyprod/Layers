"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { testAlertChannel } from "@/lib/api";
import { formatDateTime, safeString } from "@/lib/format";
import type { AlertChannel, AlertItemResponse } from "@/lib/types";
import {
  useAlerts,
  useAlertDetail,
  useAcknowledgeAlert,
  useResolveAlert,
  useReopenAlert,
} from "@/lib/hooks";
import { StatusPill } from "@/components/status-pill";
import {
  QUICK_FILTER_CATEGORIES,
  allDetectorCategories,
  detectorBadgeClass,
  detectorLabel,
  getDetectorMeta,
} from "@/lib/detector-meta";

type Filters = { status: string; severity: string; category: string };

const channelOptions: AlertChannel[] = ["email", "slack", "browser", "terminal"];

const SEVERITY_STRIPE: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#f59e0b",
  low: "#22c55e",
};
function severityStripe(s: string): string {
  return SEVERITY_STRIPE[s.toLowerCase()] ?? "#94a3b8";
}

function EvidenceDisplay({ evidence }: { evidence: AlertItemResponse["evidence"] }) {
  if (!evidence || Object.keys(evidence).length === 0) {
    return <div className="empty">No evidence payload attached to this alert.</div>;
  }
  return (
    <dl className="struct-list">
      {Object.entries(evidence).map(([k, v]) => (
        <div key={k} className="struct-row">
          <dt className="struct-key">{k}</dt>
          <dd className="struct-val">
            {typeof v === "object" && v !== null ? (
              <pre className="struct-pre">{JSON.stringify(v, null, 2)}</pre>
            ) : (
              String(v ?? "—")
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

// Quick-filter chips above the full category dropdown. Sourced from the
// central detector vocab so a single edit there propagates to every page.
const QUICK_CATEGORIES = QUICK_FILTER_CATEGORIES;

export default function AlertsPage() {
  const [filters, setFilters] = useState<Filters>({ status: "", severity: "", category: "" });
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [channelResult, setChannelResult] = useState<{ text: string; ok: boolean } | null>(null);

  // Pre-fill category from ?category= query param (e.g. from home page banner)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const cat = params.get("category") ?? "";
    if (cat) setFilters((prev) => ({ ...prev, category: cat }));
  }, []);

  const alertsQuery = useAlerts({ status: filters.status, severity: filters.severity, category: filters.category, limit: 100, offset: 0 });
  const alertDetail = useAlertDetail(selectedAlertId);

  const ackMutation = useAcknowledgeAlert();
  const resolveMutation = useResolveAlert();
  const reopenMutation = useReopenAlert();
  const isMutating = ackMutation.isPending || resolveMutation.isPending || reopenMutation.isPending;

  const selectedAlert = selectedAlertId
    ? (alertDetail.data ?? alertsQuery.data?.items.find((i) => i.alert_id === selectedAlertId) ?? null)
    : null;

  const loading = alertsQuery.isLoading;
  const error = alertsQuery.error?.message ?? alertDetail.error?.message ?? null;

  // KPI counts
  const kpis = useMemo(() => {
    const items = alertsQuery.data?.items ?? [];
    return {
      total: alertsQuery.data?.total ?? items.length,
      open: items.filter((i) => i.status === "OPEN").length,
      acked: items.filter((i) => i.status === "ACKNOWLEDGED").length,
      resolved: items.filter((i) => i.status === "RESOLVED").length,
      critical: items.filter((i) => i.severity.toLowerCase() === "critical").length,
    };
  }, [alertsQuery.data]);

  // Escape closes drawer
  useEffect(() => {
    if (!selectedAlertId) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setSelectedAlertId(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedAlertId]);

  function applyAction(action: "ack" | "resolve" | "reopen", alertId: string) {
    if (action === "ack") ackMutation.mutate(alertId);
    if (action === "resolve") resolveMutation.mutate(alertId);
    if (action === "reopen") reopenMutation.mutate(alertId);
  }

  async function runChannelTest(channel: AlertChannel) {
    setChannelResult(null);
    try {
      const payload = await testAlertChannel(channel);
      setChannelResult({ text: `${payload.channel}: ${payload.message}`, ok: payload.status === "sent" || payload.status === "queued" });
    } catch (err) {
      setChannelResult({ text: err instanceof Error ? err.message : "Channel test failed.", ok: false });
    }
  }

  return (
    <>
      {/* ── KPI strip ── */}
      <div className="kpi-grid alert-kpi-grid">
        <article className="kpi-card">
          <span className="kpi-label">Total</span>
          <strong className="kpi-value">{kpis.total}</strong>
        </article>
        <article className={`kpi-card${kpis.open > 0 ? " alert-kpi-open" : ""}`}>
          <span className="kpi-label">Open</span>
          <strong className={`kpi-value${kpis.open > 0 ? " kpi-value-danger" : ""}`}>{kpis.open}</strong>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Acknowledged</span>
          <strong className="kpi-value">{kpis.acked}</strong>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Resolved</span>
          <strong className="kpi-value alert-kpi-resolved">{kpis.resolved}</strong>
        </article>
        <article className={`kpi-card${kpis.critical > 0 ? " kpi-card-danger" : ""}`}>
          <span className="kpi-label">Critical</span>
          <strong className={`kpi-value${kpis.critical > 0 ? " kpi-value-danger" : ""}`}>{kpis.critical}</strong>
        </article>
      </div>

      {/* ── Filters ── */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Alerts Queue</h3>
            <p>Filter, triage, and resolve alert lifecycle items.</p>
          </div>
          <button type="button" className="btn btn-soft" onClick={() => void alertsQuery.refetch()}>
            Refresh
          </button>
        </header>

        <div className="alert-quick-cats">
          {QUICK_CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              className={`alert-cat-chip${filters.category === cat ? " active" : ""}`}
              onClick={() => setFilters((prev) => ({ ...prev, category: prev.category === cat ? "" : cat }))}
            >
              {cat}
            </button>
          ))}
        </div>

        <div className="filters alert-filters">
          <div className="field">
            <label htmlFor="statusFilter">Status</label>
            <select id="statusFilter" value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))}>
              <option value="">All</option>
              <option value="OPEN">OPEN</option>
              <option value="ACKNOWLEDGED">ACKNOWLEDGED</option>
              <option value="RESOLVED">RESOLVED</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="severityFilter">Severity</label>
            <input id="severityFilter" value={filters.severity} onChange={(e) => setFilters((prev) => ({ ...prev, severity: e.target.value }))} placeholder="high" />
          </div>

          <div className="field">
            <label htmlFor="categoryFilter">Category</label>
            <select
              id="categoryFilter"
              value={filters.category}
              onChange={(e) => setFilters((prev) => ({ ...prev, category: e.target.value }))}
            >
              <option value="">All categories</option>
              {allDetectorCategories().map((meta) => (
                <option key={meta.code} value={meta.code}>
                  {meta.label} ({meta.code})
                </option>
              ))}
            </select>
          </div>

          <div className="actions alert-filter-actions">
            <button type="button" className="btn btn-soft" onClick={() => setFilters({ status: "", severity: "", category: "" })}>
              Clear
            </button>
          </div>
        </div>
      </section>

      {error ? <section className="panel"><p>{error}</p></section> : null}

      {/* ── Alert list ── */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Alert List</h3>
            <p>{(alertsQuery.data?.items ?? []).length} shown</p>
          </div>
        </header>

        {loading ? (
          <div className="loading" />
        ) : (alertsQuery.data?.items ?? []).length === 0 ? (
          <div className="empty">No alerts matched current filters.</div>
        ) : (
          <div className="list">
            {(alertsQuery.data?.items ?? []).map((alert) => (
              <button
                type="button"
                key={alert.alert_id}
                className={`list-row alert-list-row${selectedAlertId === alert.alert_id ? " alert-row-selected" : ""}`}
                onClick={() => setSelectedAlertId(alert.alert_id)}
                style={{ "--alert-stripe": severityStripe(alert.severity) } as React.CSSProperties}
              >
                <div className="list-main">
                  <strong>{alert.title}</strong>
                  <span className="alert-row-meta">
                    <span
                      className={detectorBadgeClass(alert.category)}
                      title={getDetectorMeta(alert.category).description}
                    >
                      <span aria-hidden="true">{getDetectorMeta(alert.category).icon}</span>{" "}
                      {detectorLabel(alert.category)}
                    </span>
                    <span>{alert.source}</span>
                    <span>{formatDateTime(alert.created_at)}</span>
                  </span>
                </div>
                <div className="alert-row-pills">
                  <StatusPill value={alert.severity} />
                  <StatusPill value={alert.status} />
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* ── Detail drawer ── */}
      {selectedAlert && (
        <>
          <button type="button" className="alert-drawer-backdrop" aria-label="Close alert drawer" onClick={() => setSelectedAlertId(null)} />

          <aside className="alert-drawer" role="dialog" aria-modal="true" aria-label="Alert detail">
            <header className="alert-drawer-header">
              <div>
                <h3>{selectedAlert.title}</h3>
                <p>
                  <span
                    className={detectorBadgeClass(selectedAlert.category)}
                    title={getDetectorMeta(selectedAlert.category).description}
                  >
                    <span aria-hidden="true">{getDetectorMeta(selectedAlert.category).icon}</span>{" "}
                    {detectorLabel(selectedAlert.category)}
                  </span>
                  <span
                    className={`detector-layer-chip layer-${getDetectorMeta(selectedAlert.category).layer}`}
                    style={{ marginLeft: "0.4rem" }}
                  >
                    {getDetectorMeta(selectedAlert.category).layer}
                  </span>
                  <span style={{ marginLeft: "0.5rem" }}>· {selectedAlert.source}</span>
                </p>
              </div>
              <button type="button" className="ai-close-btn" onClick={() => setSelectedAlertId(null)}>✕</button>
            </header>

            <div className="alert-drawer-content">
              {/* Meta strip */}
              <div className="alert-meta-strip">
                <StatusPill value={selectedAlert.severity} />
                <StatusPill value={selectedAlert.status} />
                {selectedAlert.resolved_at && (
                  <span className="alert-resolved-ts">Resolved {formatDateTime(selectedAlert.resolved_at)}</span>
                )}
              </div>

              {/* Timestamps */}
              <dl className="struct-list alert-struct-list">
                <div className="struct-row">
                  <dt className="struct-key">Created</dt>
                  <dd className="struct-val mono">{formatDateTime(selectedAlert.created_at)}</dd>
                </div>
                <div className="struct-row">
                  <dt className="struct-key">Updated</dt>
                  <dd className="struct-val mono">{formatDateTime(selectedAlert.updated_at)}</dd>
                </div>
                {selectedAlert.resolved_at && (
                  <div className="struct-row">
                    <dt className="struct-key">Resolved</dt>
                    <dd className="struct-val mono">{formatDateTime(selectedAlert.resolved_at)}</dd>
                  </div>
                )}
                <div className="struct-row">
                  <dt className="struct-key">Diagnosis ID</dt>
                  <dd className="struct-val mono">{selectedAlert.diagnosis_id || "—"}</dd>
                </div>
              </dl>

              {/* Navigation links */}
              {selectedAlert.diagnosis_id && (
                <div className="alert-drawer-links">
                  <Link href={`/calls/${selectedAlert.diagnosis_id}`} className="btn btn-primary btn-sm" onClick={() => setSelectedAlertId(null)}>
                    Open Call →
                  </Link>
                  <Link href={`/calls/${selectedAlert.diagnosis_id}#fix-guidance`} className="btn btn-soft btn-sm" onClick={() => setSelectedAlertId(null)}>
                    Fix Guidance
                  </Link>
                </div>
              )}

              {/* Evidence */}
              <section className="alert-evidence-block">
                <h4 className="alert-evidence-heading">Evidence</h4>
                <EvidenceDisplay evidence={selectedAlert.evidence} />
              </section>

              {/* Actions */}
              <div className="alert-action-bar">
                <button
                  className="btn btn-soft"
                  type="button"
                  disabled={isMutating || selectedAlert.status === "ACKNOWLEDGED"}
                  onClick={() => applyAction("ack", selectedAlert.alert_id)}
                >
                  {ackMutation.isPending ? "Saving…" : "Acknowledge"}
                </button>
                <button
                  className="btn btn-primary"
                  type="button"
                  disabled={isMutating || selectedAlert.status === "RESOLVED"}
                  onClick={() => applyAction("resolve", selectedAlert.alert_id)}
                >
                  {resolveMutation.isPending ? "Saving…" : "Resolve"}
                </button>
                <button
                  className="btn btn-danger"
                  type="button"
                  disabled={isMutating || selectedAlert.status === "OPEN"}
                  onClick={() => applyAction("reopen", selectedAlert.alert_id)}
                >
                  {reopenMutation.isPending ? "Saving…" : "Re-open"}
                </button>
              </div>
            </div>
          </aside>
        </>
      )}

      {/* ── Channel tests ── */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Channel Tests</h3>
            <p>Validate email, Slack, browser, and terminal routing.</p>
          </div>
        </header>

        <div className="actions">
          {channelOptions.map((channel) => (
            <button key={channel} type="button" className="btn btn-soft" onClick={() => void runChannelTest(channel)}>
              Test {safeString(channel)}
            </button>
          ))}
        </div>

        {channelResult && (
          <p className={`alert-channel-result${channelResult.ok ? " ok" : " err"}`}>
            {channelResult.ok ? "✓" : "✕"} {channelResult.text}
          </p>
        )}
      </section>
    </>
  );
}
