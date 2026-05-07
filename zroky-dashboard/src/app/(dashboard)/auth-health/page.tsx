"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { formatDateTime } from "@/lib/format";
import { useAuthSummary, useAlerts, useAcknowledgeAlert, useResolveAlert } from "@/lib/hooks";
import { StatusPill } from "@/components/status-pill";
import type { AlertItemResponse } from "@/lib/types";

// ── Helpers ──────────────────────────────────────────────────────────────────

function getMaxBarValue(counts: number[]): number {
  const max = counts.reduce((m, v) => Math.max(m, v), 0);
  return max <= 0 ? 1 : max;
}

function hourLabel(isoHour: string): string {
  // "2026-05-05T14:00:00+00:00" → "14:00"
  const match = /T(\d{2}:\d{2})/.exec(isoHour);
  return match ? match[1] : isoHour.slice(11, 16);
}

function providerFromEvidence(evidence: Record<string, unknown> | null): string {
  if (!evidence) return "—";
  const p = String(evidence["provider"] ?? "").trim();
  return p || "—";
}

function errorCodeFromEvidence(evidence: Record<string, unknown> | null): string {
  if (!evidence) return "—";
  const code = String(evidence["error_code"] ?? "").trim();
  const status = String(evidence["status_code"] ?? "").trim();
  if (code && status) return `${code} (${status})`;
  if (code) return code;
  if (status) return `HTTP ${status}`;
  return "—";
}

function mttaLabel(minutes: number | null | undefined): string {
  if (minutes == null) return "—";
  if (minutes < 60) return `${minutes.toFixed(1)} min`;
  return `${(minutes / 60).toFixed(1)} hr`;
}

// ── Component ────────────────────────────────────────────────────────────────

export default function AuthHealthPage() {
  const [windowHours, setWindowHours] = useState(24);
  const [filterHour, setFilterHour] = useState<string | null>(null);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [providerFilter, setProviderFilter] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [busyBulk, setBusyBulk] = useState(false);

  const summaryQuery = useAuthSummary(windowHours);
  const alertsQuery = useAlerts({ category: "AUTH_FAILURE", status: "", limit: 200 });

  const ackMutation = useAcknowledgeAlert();
  const resolveMutation = useResolveAlert();

  const summaryData = summaryQuery.data;
  const allAlerts: AlertItemResponse[] = alertsQuery.data?.items ?? [];

  // Bar chart points with percentage heights
  const barPoints = useMemo(() => {
    const points = summaryData?.trend ?? [];
    const max = getMaxBarValue(points.map((p) => p.count));
    return points.map((p) => ({ ...p, pct: Math.round((p.count / max) * 100) }));
  }, [summaryData]);

  // Filter incidents to the selected hour
  const filteredAlerts = useMemo(() => {
    let items = allAlerts.slice();
    if (filterHour) {
      const prefix = filterHour.substring(0, 13); // "2026-05-05T14"
      items = items.filter((a) => a.created_at.substring(0, 13) === prefix);
    }
    if (providerFilter) {
      items = items.filter((a) => providerFromEvidence(a.evidence as Record<string, unknown> | null) === providerFilter);
    }
    if (severityFilter) {
      items = items.filter((a) => a.severity === severityFilter);
    }
    if (statusFilter && statusFilter !== "ALL") {
      items = items.filter((a) => a.status === statusFilter);
    }
    return items;
  }, [allAlerts, filterHour, providerFilter, severityFilter, statusFilter]);

  const selectedAlert = useMemo(
    () => filteredAlerts.find((a) => a.alert_id === selectedAlertId) ?? null,
    [filteredAlerts, selectedAlertId],
  );

  const providerNames = useMemo(() => {
    if (summaryData?.affected_providers && summaryData.affected_providers.length > 0) {
      return summaryData.affected_providers;
    }
    const s = new Set<string>();
    for (const a of allAlerts) s.add(providerFromEvidence(a.evidence as Record<string, unknown> | null));
    return Array.from(s).filter((p) => p && p !== "—").sort();
  }, [allAlerts, summaryData]);

  const severityNames = useMemo(() => {
    const s = new Set<string>();
    for (const a of allAlerts) s.add(a.severity);
    return Array.from(s).sort();
  }, [allAlerts]);

  function downloadBlob(filename: string, contents: string, type = "text/plain") {
    const blob = new Blob([contents], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function exportAlertsJson(items: typeof filteredAlerts) {
    try {
      const json = JSON.stringify(items, null, 2);
      downloadBlob(`auth-alerts-${Date.now()}.json`, json, "application/json");
    } catch (e) {
      // ignore
    }
  }

  function exportAlertsCsv(items: typeof filteredAlerts) {
    const header = ["alert_id", "created_at", "provider", "error_code", "severity", "status", "title", "diagnosis_id", "evidence_json"];
    const rows = items.map((i) => {
      const ev = i.evidence ? JSON.stringify(i.evidence) : "";
      const provider = providerFromEvidence(i.evidence as Record<string, unknown> | null);
      const code = errorCodeFromEvidence(i.evidence as Record<string, unknown> | null);
      const cols = [i.alert_id, i.created_at, provider, code, i.severity, i.status, i.title ?? "", i.diagnosis_id ?? "", ev];
      return cols.map((c) => JSON.stringify(c ?? "")).join(",");
    });
    const csv = [header.join(","), ...rows].join("\n");
    downloadBlob(`auth-alerts-${Date.now()}.csv`, csv, "text/csv;charset=utf-8");
  }

  async function acknowledgeAllVisible() {
    if (busyBulk) return;
    setBusyBulk(true);
    try {
      const list = filteredAlerts.slice();
      const promises = list.map((a) => {
        if ((ackMutation as any).mutateAsync) return (ackMutation as any).mutateAsync(a.alert_id);
        return new Promise((resolve, reject) => ackMutation.mutate(a.alert_id, { onSuccess: resolve, onError: reject }));
      });
      await Promise.allSettled(promises);
      await summaryQuery.refetch();
      await alertsQuery.refetch();
    } finally {
      setBusyBulk(false);
    }
  }

  async function resolveAllVisible() {
    if (busyBulk) return;
    setBusyBulk(true);
    try {
      const list = filteredAlerts.slice();
      const promises = list.map((a) => {
        if ((resolveMutation as any).mutateAsync) return (resolveMutation as any).mutateAsync(a.alert_id);
        return new Promise((resolve, reject) => resolveMutation.mutate(a.alert_id, { onSuccess: resolve, onError: reject }));
      });
      await Promise.allSettled(promises);
      await summaryQuery.refetch();
      await alertsQuery.refetch();
    } finally {
      setBusyBulk(false);
    }
  }

  const isOngoing = summaryData?.is_ongoing ?? false;

  return (
    <>
      {/* ── Ongoing incident banner ── */}
      {isOngoing ? (
        <section className="panel auth-incident-banner">
          <p className="auth-incident-banner-text">
            ⚠ Active auth failures detected — {summaryData?.open_alert_count ?? 0} unacknowledged
            {summaryData?.affected_providers && summaryData.affected_providers.length > 0
              ? `. Affected providers: ${summaryData.affected_providers.join(", ")}`
              : ""}
            {summaryData?.last_failure_at
              ? `. Last seen: ${formatDateTime(summaryData.last_failure_at)}`
              : ""}
          </p>
        </section>
      ) : null}

      {/* ── KPI strip ── */}
      <div className="kpi-grid auth-kpi-grid">
        <article className="kpi-card">
          <span className="kpi-label">Total Failures</span>
          <strong className="kpi-value">{summaryQuery.isLoading ? "—" : (summaryData?.total_auth_failures ?? 0)}</strong>
          <span className="kpi-sub">Last {windowHours}h</span>
        </article>
        <article className={`kpi-card${(summaryData?.open_alert_count ?? 0) > 0 ? " kpi-card-danger" : ""}`}>
          <span className="kpi-label">Open Alerts</span>
          <strong className={`kpi-value${(summaryData?.open_alert_count ?? 0) > 0 ? " kpi-value-danger" : ""}`}>
            {summaryQuery.isLoading ? "—" : (summaryData?.open_alert_count ?? 0)}
          </strong>
          <span className="kpi-sub">Unacknowledged</span>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Providers Affected</span>
          <strong className="kpi-value loop-kpi-compact loop-kpi-break">
            {summaryQuery.isLoading ? "—" : (summaryData?.affected_providers ?? []).length > 0 ? summaryData!.affected_providers.join(", ") : "none"}
          </strong>
          <span className="kpi-sub">Distinct auth endpoints</span>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Mean Time to Ack</span>
          <strong className="kpi-value">{summaryQuery.isLoading ? "—" : mttaLabel(summaryData?.mean_time_to_acknowledge_minutes)}</strong>
          <span className="kpi-sub">Alert → acknowledged</span>
        </article>
      </div>

      {/* ── Hourly trend chart ── */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Auth Failures per Hour</h3>
            <p>
              {filterHour
                ? `Showing incidents at ${hourLabel(filterHour)} UTC · click bar again to clear`
                : "Click a bar to drill into that hour's incidents."}
            </p>
          </div>
          <div className="actions">
            {([6, 24, 48] as const).map((h) => (
              <button
                key={h}
                type="button"
                className={`btn btn-soft${windowHours === h ? " btn-active" : ""}`}
                onClick={() => {
                  setWindowHours(h);
                  setFilterHour(null);
                }}
              >
                {h}h
              </button>
            ))}
            {filterHour ? (
              <button
                type="button"
                className="btn btn-soft"
                onClick={() => setFilterHour(null)}
              >
                Clear filter
              </button>
            ) : null}
          </div>
        </header>

        {summaryQuery.isLoading ? (
          <div className="loading" />
        ) : barPoints.length === 0 ? (
          <div className="empty">No auth failures in this window. Credentials are healthy.</div>
        ) : (
          <div className="loop-bar-chart">
            {barPoints.map((point) => (
              <div key={point.hour} className="loop-bar-col">
                <div
                  className={`loop-bar${filterHour === point.hour ? " loop-bar-active" : ""}`}
                  style={{ height: `${point.pct}%`, minHeight: point.count > 0 ? 4 : 0 }}
                  title={`${hourLabel(point.hour)} UTC: ${point.count} failure${point.count !== 1 ? "s" : ""}`}
                  onClick={() => { setFilterHour(point.hour === filterHour ? null : point.hour); setSelectedAlertId(null); }}
                />
                <span className="loop-bar-label">{hourLabel(point.hour)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Incident table ── */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Auth Failure Incidents</h3>
            <p>
              {alertsQuery.isLoading
                ? "Loading…"
                : filterHour
                ? `${filteredAlerts.length} incident${filteredAlerts.length !== 1 ? "s" : ""} at ${hourLabel(filterHour)} UTC`
                : `${alertsQuery.data?.total ?? 0} total incidents`}
            </p>
          </div>
          <div className="actions">
            <button
              type="button"
              className="btn btn-soft"
              onClick={() => {
                void summaryQuery.refetch();
                void alertsQuery.refetch();
              }}
            >
              Refresh
            </button>
            <Link href="/alerts?category=AUTH_FAILURE&status=OPEN" className="btn btn-primary">
              Triage All Open
            </Link>
          </div>
        </header>

        {alertsQuery.isLoading ? (
          <div className="loading" />
        ) : filteredAlerts.length === 0 ? (
          <div className="empty">
            {filterHour
              ? `No auth failures at ${hourLabel(filterHour)} UTC.`
              : "No AUTH_FAILURE alerts on record. Credentials are healthy."}
          </div>
        ) : (
          <div className="list">
            <div className="list-row loop-incident-header">
              <span className="auth-col-time">Time</span>
              <span className="auth-col-provider">Provider</span>
              <span className="auth-col-error">Error Code</span>
              <span className="auth-col-pill">Severity</span>
              <span className="auth-col-pill">Status</span>
            </div>
            {filteredAlerts.map((alert) => {
              const evidence = alert.evidence as Record<string, unknown> | null;
              return (
                <button
                  key={alert.alert_id}
                  type="button"
                  className={`list-row loop-incident-row${selectedAlertId === alert.alert_id ? " auth-row-selected" : ""}`}
                  onClick={() => setSelectedAlertId(alert.alert_id === selectedAlertId ? null : alert.alert_id)}
                >
                  <span className="auth-col-time">{formatDateTime(alert.created_at)}</span>
                  <span className="auth-col-provider">{providerFromEvidence(evidence)}</span>
                  <span className="auth-col-error mono">{errorCodeFromEvidence(evidence)}</span>
                  <span className="auth-col-pill"><StatusPill value={alert.severity} /></span>
                  <span className="auth-col-pill"><StatusPill value={alert.status} /></span>
                </button>
              );
            })}
          </div>
        )}
      </section>

      {/* ── Detail drawer ── */}
      {selectedAlert ? (
        <>
          <button
            type="button"
            className="alert-drawer-backdrop"
            aria-label="Close drawer"
            onClick={() => setSelectedAlertId(null)}
          />

          <aside
            className="alert-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Auth failure detail"
          >
            <header className="alert-drawer-header">
              <div>
                <h3>Auth Failure Detail</h3>
                <p>{selectedAlert.title}</p>
              </div>
              <button
                type="button"
                className="btn btn-soft"
                onClick={() => setSelectedAlertId(null)}
              >
                Close
              </button>
            </header>

            <div className="alert-drawer-content">
              <div className="list">
                {/* Core fields */}
                <div className="list-row">
                  <div className="list-main">
                    <strong>Status</strong>
                  </div>
                  <StatusPill value={selectedAlert.status} />
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Severity</strong>
                  </div>
                  <StatusPill value={selectedAlert.severity} />
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Detected at</strong>
                  </div>
                  <span className="mono">{formatDateTime(selectedAlert.created_at)}</span>
                </div>

                {/* Evidence fields */}
                {selectedAlert.evidence ? (
                  <>
                    <div className="list-row">
                      <div className="list-main">
                        <strong>Provider</strong>
                      </div>
                      <span className="mono">
                        {providerFromEvidence(
                          selectedAlert.evidence as Record<string, unknown>,
                        )}
                      </span>
                    </div>
                    <div className="list-row">
                      <div className="list-main">
                        <strong>Error Code</strong>
                      </div>
                      <span className="mono">
                        {errorCodeFromEvidence(
                          selectedAlert.evidence as Record<string, unknown>,
                        )}
                      </span>
                    </div>
                  </>
                ) : null}

                {selectedAlert.resolved_at ? (
                  <div className="list-row">
                    <div className="list-main">
                      <strong>Resolved at</strong>
                    </div>
                    <span className="mono">{formatDateTime(selectedAlert.resolved_at)}</span>
                  </div>
                ) : null}

                <div className="list-row">
                  <div className="list-main">
                    <strong>Diagnosis ID</strong>
                    <span className="mono">{selectedAlert.diagnosis_id}</span>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="actions auth-detail-actions">
                <Link
                  href={`/calls/${selectedAlert.diagnosis_id}`}
                  className="btn btn-primary"
                  onClick={() => setSelectedAlertId(null)}
                >
                  Open Call
                </Link>
                {selectedAlert.status === "OPEN" ? (
                  <button
                    type="button"
                    className="btn btn-soft"
                    disabled={ackMutation.isPending}
                    onClick={() =>
                      ackMutation.mutate(selectedAlert.alert_id, {
                        onSuccess: () => setSelectedAlertId(null),
                      })
                    }
                  >
                    {ackMutation.isPending ? "Acknowledging…" : "Acknowledge"}
                  </button>
                ) : null}
                {selectedAlert.status !== "RESOLVED" ? (
                  <button
                    type="button"
                    className="btn btn-soft"
                    disabled={resolveMutation.isPending}
                    onClick={() =>
                      resolveMutation.mutate(selectedAlert.alert_id, {
                        onSuccess: () => setSelectedAlertId(null),
                      })
                    }
                  >
                    {resolveMutation.isPending ? "Resolving…" : "Mark Resolved"}
                  </button>
                ) : null}
              </div>

              {/* Raw evidence */}
              <section className="alert-evidence-block">
                <h4 className="alert-evidence-heading">Evidence Payload</h4>
                {selectedAlert.evidence && Object.keys(selectedAlert.evidence).length > 0 ? (
                  <dl className="struct-list">
                    {Object.entries(selectedAlert.evidence as Record<string, unknown>).map(([k, v]) => (
                      <div key={k} className="struct-row">
                        <dt className="struct-key">{k}</dt>
                        <dd className="struct-val mono">{typeof v === "object" && v !== null ? JSON.stringify(v) : String(v ?? "—")}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <div className="empty">No evidence payload attached.</div>
                )}
              </section>

              {/* Fix guidance */}
              <section className="alert-evidence-block">
                <h4>Recommended Fix</h4>
                <div className="panel panel-muted auth-fix-guidance">
                  <strong>Immediate:</strong> Rotate or re-issue the API key for the affected
                  provider. Verify the key is active in the provider dashboard.
                  <br />
                  <strong>Prevention:</strong> Add a secrets rotation schedule (&lt;90 days).
                  Store keys in a secrets manager (Vault, AWS Secrets Manager) — never in env
                  files. Set up expiry alerts so you know <em>before</em> production breaks.
                  <br />
                  <strong>Detection:</strong> This page auto-refreshes every 30 seconds. Auth
                  failures fire a realtime <code>auth_failure_alert</code> event and appear on
                  the Command Center banner within one polling cycle.
                </div>
              </section>
            </div>
          </aside>
        </>
      ) : null}
    </>
  );
}
