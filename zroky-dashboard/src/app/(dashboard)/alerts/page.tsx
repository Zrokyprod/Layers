"use client";

import Link from "next/link";
import {
  Bell,
  CheckCircle2,
  Inbox,
  RefreshCw,
  RotateCcw,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  TriangleAlert,
  X,
} from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { StatusPill } from "@/components/status-pill";
import { testAlertChannel } from "@/lib/api";
import {
  allDetectorCategories,
  detectorBadgeClass,
  detectorLabel,
  getDetectorMeta,
  QUICK_FILTER_CATEGORIES,
} from "@/lib/detector-meta";
import { formatDateTime, safeString } from "@/lib/format";
import {
  useAcknowledgeAlert,
  useAlertDetail,
  useAlerts,
  useReopenAlert,
  useResolveAlert,
} from "@/lib/hooks";
import type { AlertChannel, AlertItemResponse } from "@/lib/types";

type Filters = { status: string; severity: string; category: string };
type AlertAction = "ack" | "resolve" | "reopen";

const channelOptions: AlertChannel[] = ["email", "slack", "browser", "terminal"];
const QUICK_CATEGORIES = QUICK_FILTER_CATEGORIES;

const SEVERITY_ACCENT: Record<string, string> = {
  critical: "var(--dashboard-danger)",
  high: "var(--dashboard-accent)",
  medium: "var(--dashboard-warning)",
  low: "var(--dashboard-success)",
};

function severityAccent(severity: string): string {
  return SEVERITY_ACCENT[severity.toLowerCase()] ?? "var(--dashboard-muted)";
}

function EvidenceDisplay({ evidence }: { evidence: AlertItemResponse["evidence"] }) {
  if (!evidence || Object.keys(evidence).length === 0) {
    return <div className="empty alert-empty">No evidence payload attached to this alert.</div>;
  }

  return (
    <dl className="alert-evidence-list">
      {Object.entries(evidence).map(([key, value]) => (
        <div key={key} className="alert-evidence-row">
          <dt>{key}</dt>
          <dd>
            {typeof value === "object" && value !== null ? (
              <pre>{JSON.stringify(value, null, 2)}</pre>
            ) : (
              String(value ?? "-")
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function AlertMetric({
  label,
  value,
  tone = "neutral",
  icon,
}: {
  label: string;
  value: number;
  tone?: "neutral" | "danger" | "success" | "warning";
  icon: ReactNode;
}) {
  return (
    <article className={`metric-card alert-metric-card tone-${tone}`}>
      <span className="alert-metric-icon" aria-hidden="true">
        {icon}
      </span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </article>
  );
}

function alertSubtitle(alert: AlertItemResponse): string {
  const meta = getDetectorMeta(alert.category);
  return `${meta.layer} signal from ${safeString(alert.source)}`;
}

export default function AlertsPage() {
  const [filters, setFilters] = useState<Filters>({ status: "", severity: "", category: "" });
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [channelResult, setChannelResult] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const category = params.get("category") ?? "";
    if (category) setFilters((prev) => ({ ...prev, category }));
  }, []);

  const alertsQuery = useAlerts({
    status: filters.status,
    severity: filters.severity,
    category: filters.category,
    limit: 100,
    offset: 0,
  });
  const alertDetail = useAlertDetail(selectedAlertId);

  const ackMutation = useAcknowledgeAlert();
  const resolveMutation = useResolveAlert();
  const reopenMutation = useReopenAlert();
  const isMutating = ackMutation.isPending || resolveMutation.isPending || reopenMutation.isPending;

  const alerts = useMemo(() => alertsQuery.data?.items ?? [], [alertsQuery.data?.items]);
  const selectedAlert = selectedAlertId
    ? (alertDetail.data ?? alerts.find((alert) => alert.alert_id === selectedAlertId) ?? null)
    : null;
  const error = alertsQuery.error?.message ?? alertDetail.error?.message ?? null;

  const kpis = useMemo(
    () => ({
      total: alertsQuery.data?.total ?? alerts.length,
      open: alerts.filter((alert) => alert.status === "OPEN").length,
      acked: alerts.filter((alert) => alert.status === "ACKNOWLEDGED").length,
      resolved: alerts.filter((alert) => alert.status === "RESOLVED").length,
      critical: alerts.filter((alert) => alert.severity.toLowerCase() === "critical").length,
    }),
    [alerts, alertsQuery.data?.total],
  );

  useEffect(() => {
    if (!selectedAlertId) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedAlertId(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedAlertId]);

  function applyAction(action: AlertAction, alertId: string) {
    if (action === "ack") ackMutation.mutate(alertId);
    if (action === "resolve") resolveMutation.mutate(alertId);
    if (action === "reopen") reopenMutation.mutate(alertId);
  }

  async function runChannelTest(channel: AlertChannel) {
    setChannelResult(null);
    try {
      const payload = await testAlertChannel(channel);
      setChannelResult({
        text: `${payload.channel}: ${payload.message}`,
        ok: payload.status === "sent" || payload.status === "queued",
      });
    } catch (err) {
      setChannelResult({ text: err instanceof Error ? err.message : "Channel test failed.", ok: false });
    }
  }

  return (
    <div className="alerts-workspace">
      <section className="module-hero alert-hero">
        <div className="module-hero-header">
          <div>
            <span className="module-eyebrow">
              <Bell aria-hidden="true" />
              Attention queue
            </span>
            <h1>Alert Evidence</h1>
            <p>
              Supporting operational signals from capture, replay, policy, CI, and budget checks.
              Keep primary action in Command Center, Failures, Policies, and Approvals.
            </p>
          </div>
          <div className="alert-hero-actions">
            <button type="button" className="btn btn-soft" onClick={() => void alertsQuery.refetch()}>
              <RefreshCw aria-hidden="true" />
              Refresh
            </button>
          </div>
        </div>
      </section>

      <section className="alert-metric-grid" aria-label="Alert summary">
        <AlertMetric label="Total" value={kpis.total} icon={<Inbox />} />
        <AlertMetric label="Open" value={kpis.open} tone={kpis.open > 0 ? "danger" : "neutral"} icon={<TriangleAlert />} />
        <AlertMetric label="Acknowledged" value={kpis.acked} tone="warning" icon={<ShieldCheck />} />
        <AlertMetric label="Resolved" value={kpis.resolved} tone="success" icon={<CheckCircle2 />} />
        <AlertMetric label="Critical" value={kpis.critical} tone={kpis.critical > 0 ? "danger" : "neutral"} icon={<TriangleAlert />} />
      </section>

      <section className="alerts-filter-panel">
        <header className="alerts-section-header">
          <div>
            <span className="module-eyebrow">
              <SlidersHorizontal aria-hidden="true" />
              Filters
            </span>
            <h2>Find the signal that needs action</h2>
          </div>
          <button type="button" className="btn btn-soft" onClick={() => setFilters({ status: "", severity: "", category: "" })}>
            Clear
          </button>
        </header>

        <div className="alert-quick-cats">
          {QUICK_CATEGORIES.map((category) => (
            <button
              key={category}
              type="button"
              className={`alert-cat-chip${filters.category === category ? " active" : ""}`}
              onClick={() =>
                setFilters((prev) => ({ ...prev, category: prev.category === category ? "" : category }))
              }
            >
              {detectorLabel(category)}
            </button>
          ))}
        </div>

        <div className="alerts-filter-grid">
          <div className="field">
            <label htmlFor="statusFilter">Status</label>
            <select
              id="statusFilter"
              value={filters.status}
              onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))}
            >
              <option value="">All</option>
              <option value="OPEN">Open</option>
              <option value="ACKNOWLEDGED">Acknowledged</option>
              <option value="RESOLVED">Resolved</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="severityFilter">Severity</label>
            <select
              id="severityFilter"
              value={filters.severity}
              onChange={(event) => setFilters((prev) => ({ ...prev, severity: event.target.value }))}
            >
              <option value="">All</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="categoryFilter">Category</label>
            <select
              id="categoryFilter"
              value={filters.category}
              onChange={(event) => setFilters((prev) => ({ ...prev, category: event.target.value }))}
            >
              <option value="">All categories</option>
              {allDetectorCategories().map((meta) => (
                <option key={meta.code} value={meta.code}>
                  {meta.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {error ? (
        <section className="alert-error-panel">
          <TriangleAlert aria-hidden="true" />
          <p>{error}</p>
        </section>
      ) : null}

      <section className="alerts-list-panel">
        <header className="alerts-section-header">
          <div>
            <span className="module-eyebrow">Queue</span>
            <h2>{alerts.length} alerts shown</h2>
          </div>
        </header>

        {alertsQuery.isLoading ? (
          <div className="loading" />
        ) : alerts.length === 0 ? (
          <div className="alert-empty-state">
            <CheckCircle2 aria-hidden="true" />
            <strong>No alerts matched current filters.</strong>
            <span>Production attention is clean for this view.</span>
          </div>
        ) : (
          <div className="alert-card-stack">
            {alerts.map((alert) => {
              const meta = getDetectorMeta(alert.category);
              return (
                <button
                  type="button"
                  key={alert.alert_id}
                  className={`alert-card-row${selectedAlertId === alert.alert_id ? " active" : ""}`}
                  onClick={() => setSelectedAlertId(alert.alert_id)}
                  style={{ "--alert-accent": severityAccent(alert.severity) } as CSSProperties}
                >
                  <span className="alert-card-accent" aria-hidden="true" />
                  <span className="alert-card-main">
                    <span className="alert-card-title">{alert.title}</span>
                    <span className="alert-card-meta">
                      <span className={detectorBadgeClass(alert.category)} title={meta.description}>
                        <span aria-hidden="true">{meta.icon}</span>
                        {detectorLabel(alert.category)}
                      </span>
                      <span>{alertSubtitle(alert)}</span>
                      <span>{formatDateTime(alert.created_at)}</span>
                    </span>
                  </span>
                  <span className="alert-card-pills">
                    <StatusPill value={alert.severity} />
                    <StatusPill value={alert.status} />
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </section>

      <section className="alerts-channel-panel">
        <header className="alerts-section-header">
          <div>
            <span className="module-eyebrow">
              <Send aria-hidden="true" />
              Routing
            </span>
            <h2>Channel tests</h2>
            <p>Validate email, Slack, browser, and terminal delivery without leaving the queue.</p>
          </div>
        </header>

        <div className="alerts-channel-actions">
          {channelOptions.map((channel) => (
            <button key={channel} type="button" className="btn btn-soft" onClick={() => void runChannelTest(channel)}>
              Test {safeString(channel)}
            </button>
          ))}
        </div>

        {channelResult ? (
          <p className={`alert-channel-result${channelResult.ok ? " ok" : " err"}`}>
            {channelResult.ok ? "Sent" : "Failed"} - {channelResult.text}
          </p>
        ) : null}
      </section>

      {selectedAlert ? (
        <>
          <button
            type="button"
            className="alert-drawer-backdrop"
            aria-label="Close alert drawer"
            onClick={() => setSelectedAlertId(null)}
          />

          <aside className="alert-drawer alert-detail-drawer" role="dialog" aria-modal="true" aria-label="Alert detail">
            <header className="alert-drawer-header">
              <div>
                <span className="module-eyebrow">Alert detail</span>
                <h3>{selectedAlert.title}</h3>
                <p>{alertSubtitle(selectedAlert)}</p>
              </div>
              <button type="button" className="ai-close-btn" onClick={() => setSelectedAlertId(null)} aria-label="Close">
                <X aria-hidden="true" />
              </button>
            </header>

            <div className="alert-drawer-content">
              <div className="alert-meta-strip">
                <StatusPill value={selectedAlert.severity} />
                <StatusPill value={selectedAlert.status} />
                <span className={detectorBadgeClass(selectedAlert.category)}>
                  <span aria-hidden="true">{getDetectorMeta(selectedAlert.category).icon}</span>
                  {detectorLabel(selectedAlert.category)}
                </span>
                {selectedAlert.resolved_at ? (
                  <span className="alert-resolved-ts">Resolved {formatDateTime(selectedAlert.resolved_at)}</span>
                ) : null}
              </div>

              <dl className="alert-detail-grid">
                <div>
                  <dt>Created</dt>
                  <dd>{formatDateTime(selectedAlert.created_at)}</dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd>{formatDateTime(selectedAlert.updated_at)}</dd>
                </div>
                <div>
                  <dt>Diagnosis ID</dt>
                  <dd className="mono">{selectedAlert.diagnosis_id || "-"}</dd>
                </div>
              </dl>

              {selectedAlert.diagnosis_id ? (
                <div className="alert-drawer-links">
                  <Link
                    href={`/calls/${selectedAlert.diagnosis_id}`}
                    className="btn btn-primary btn-sm"
                    onClick={() => setSelectedAlertId(null)}
                  >
                    Open Call
                  </Link>
                  <Link
                    href={`/calls/${selectedAlert.diagnosis_id}#fix-guidance`}
                    className="btn btn-soft btn-sm"
                    onClick={() => setSelectedAlertId(null)}
                  >
                    Fix Guidance
                  </Link>
                </div>
              ) : null}

              <section className="alert-evidence-block">
                <h4>Evidence</h4>
                <EvidenceDisplay evidence={selectedAlert.evidence} />
              </section>

              <div className="alert-action-bar">
                <button
                  className="btn btn-soft"
                  type="button"
                  disabled={isMutating || selectedAlert.status === "ACKNOWLEDGED"}
                  onClick={() => applyAction("ack", selectedAlert.alert_id)}
                >
                  <ShieldCheck aria-hidden="true" />
                  {ackMutation.isPending ? "Saving..." : "Acknowledge"}
                </button>
                <button
                  className="btn btn-primary"
                  type="button"
                  disabled={isMutating || selectedAlert.status === "RESOLVED"}
                  onClick={() => applyAction("resolve", selectedAlert.alert_id)}
                >
                  <CheckCircle2 aria-hidden="true" />
                  {resolveMutation.isPending ? "Saving..." : "Resolve"}
                </button>
                <button
                  className="btn btn-danger"
                  type="button"
                  disabled={isMutating || selectedAlert.status === "OPEN"}
                  onClick={() => applyAction("reopen", selectedAlert.alert_id)}
                >
                  <RotateCcw aria-hidden="true" />
                  {reopenMutation.isPending ? "Saving..." : "Re-open"}
                </button>
              </div>
            </div>
          </aside>
        </>
      ) : null}
    </div>
  );
}
