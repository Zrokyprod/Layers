"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { formatDateTime, formatUsd } from "@/lib/format";
import { useLoopSummary, useLoopIncidents, useCallDetail } from "@/lib/hooks";
import { useDashboardStore } from "@/lib/store";
import { StatusPill } from "@/components/status-pill";

function getMaxBarValue(counts: number[]): number {
  const max = counts.reduce((m, v) => Math.max(m, v), 0);
  return max <= 0 ? 1 : max;
}

function patternLabel(pattern: string | null): string {
  if (!pattern) return "unknown";
  const p = pattern.toLowerCase();
  if (p.includes("output")) return "output repeat";
  if (p.includes("tool")) return "tool cycle";
  if (p.includes("retry")) return "retry storm";
  if (p.includes("prompt")) return "prompt repeat";
  return pattern;
}

function scoreClass(score: number): string {
  if (score >= 0.85) return "loop-score-high";
  if (score >= 0.72) return "loop-score-medium";
  return "loop-score-low";
}

export default function LoopsPage() {
  const [summaryDays, setSummaryDays] = useState(7);
  const [incidentDays, setIncidentDays] = useState(30);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterDay, setFilterDay] = useState<string | null>(null);
  const [agentFilter, setAgentFilter] = useState<string | null>(null);
  const [patternFilter, setPatternFilter] = useState<string | null>(null);
  const [includeSuppressed, setIncludeSuppressed] = useState(false);

  const summary = useLoopSummary(summaryDays);
  const incidents = useLoopIncidents({ days: incidentDays, limit: 100 });

  const summaryData = summary.data;
  const incidentItems = incidents.data?.items ?? [];
  // Filter incidents to a specific day when a bar is clicked
  const filteredIncidentItems = useMemo(() => {
    if (!filterDay) return incidentItems;
    return incidentItems.filter((item) => item.created_at.startsWith(filterDay));
  }, [incidentItems, filterDay]);

  const agentNames = useMemo(() => {
    const s = new Set(filteredIncidentItems.map((i) => i.agent_name ?? "unknown"));
    return Array.from(s).sort();
  }, [filteredIncidentItems]);

  const patternNames = useMemo(() => {
    const s = new Set(filteredIncidentItems.map((i) => i.dominant_pattern ?? "unknown"));
    return Array.from(s).sort();
  }, [filteredIncidentItems]);

  const snoozes = useDashboardStore((s) => s.snoozes);
  const dismissed = useDashboardStore((s) => s.dismissed);
  const setSnooze = useDashboardStore((s) => s.setSnooze);
  const setDismissed = useDashboardStore((s) => s.setDismissed);

  const visibleIncidentItems = useMemo(() => {
    return filteredIncidentItems.filter((item) => {
      const id = (item.diagnosis_id ?? "").toLowerCase();
      if (!includeSuppressed) {
        if (dismissed && dismissed[id]) return false;
        const iso = snoozes && snoozes[id];
        if (iso) {
          const d = new Date(iso as string);
          if (!Number.isNaN(d.getTime()) && d.getTime() > Date.now()) return false;
        }
      }
      if (agentFilter && (item.agent_name ?? "unknown") !== agentFilter) return false;
      if (patternFilter && (item.dominant_pattern ?? "unknown") !== patternFilter) return false;
      return true;
    });
  }, [filteredIncidentItems, includeSuppressed, agentFilter, patternFilter, snoozes, dismissed]);

  const selectedIncident = useMemo(
    () => visibleIncidentItems.find((item) => item.diagnosis_id === selectedId) ?? null,
    [visibleIncidentItems, selectedId],
  );

  const barPoints = useMemo(() => {
    const points = summaryData?.loop_count_by_day ?? [];
    const max = getMaxBarValue(points.map((p) => p.count));
    return points.map((p) => ({ ...p, pct: Math.round((p.count / max) * 100) }));
  }, [summaryData]);

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

  function exportJson(items: typeof visibleIncidentItems) {
    try {
      const json = JSON.stringify(items, null, 2);
      downloadBlob(`loops-${Date.now()}.json`, json, "application/json");
    } catch (e) {
      // ignore
    }
  }

  function exportCsv(items: typeof visibleIncidentItems) {
    const header = [
      "diagnosis_id",
      "created_at",
      "agent_name",
      "dominant_pattern",
      "repeat_count",
      "loop_score",
      "estimated_cost_usd",
      "retry_suppression_applied",
      "no_progress",
    ];
    const rows = items.map((i) =>
      header
        .map((h) => {
          const v = (i as any)[h];
          return JSON.stringify(v ?? "");
        })
        .join(","),
    );
    const csv = [header.join(","), ...rows].join("\n");
    downloadBlob(`loops-${Date.now()}.csv`, csv, "text/csv;charset=utf-8");
  }

  function LoopDetailPanel({ incident, onClose }: { incident: any; onClose: () => void }) {
    const callDetail = useCallDetail(incident.diagnosis_id);
    const [snoozeUntil, setSnoozeUntil] = useState("");
    const storeSnoozes = useDashboardStore((s) => s.snoozes);
    const storeDismissed = useDashboardStore((s) => s.dismissed);
    const setSnoozeStore = useDashboardStore((s) => s.setSnooze);
    const setDismissedStore = useDashboardStore((s) => s.setDismissed);

    const currentSnooze = storeSnoozes?.[incident.diagnosis_id?.toLowerCase()] ?? null;
    const isDismissed = Boolean(storeDismissed?.[incident.diagnosis_id?.toLowerCase()]);

    async function copyPayload() {
      try {
        const payload = callDetail.data?.payload ?? callDetail.data?.diagnosis_result ?? {};
        if (typeof navigator !== "undefined" && navigator.clipboard) {
          await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
        }
      } catch (e) {
        // ignore
      }
    }

    return (
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Incident Detail</h3>
            <p className="mono">{incident.diagnosis_id}</p>
          </div>
          <div className="loop-detail-actions">
            <Link href={`/calls/${incident.diagnosis_id}`} className="btn btn-primary btn-sm">
              Open Call →
            </Link>
            <button type="button" className="btn btn-soft" onClick={() => onClose()}>
              Close
            </button>
          </div>
        </header>

        <dl className="struct-list">
          <div className="struct-row">
            <dt className="struct-key">Agent</dt>
            <dd className="struct-val">{incident.agent_name ?? "unknown"}</dd>
          </div>
          <div className="struct-row">
            <dt className="struct-key">Detected at</dt>
            <dd className="struct-val mono">{formatDateTime(incident.created_at)}</dd>
          </div>
          <div className="struct-row">
            <dt className="struct-key">Loop score</dt>
            <dd className={`struct-val mono loop-score-strong ${scoreClass(incident.loop_score)}`}>
              {incident.loop_score.toFixed(3)}
            </dd>
          </div>
          <div className="struct-row">
            <dt className="struct-key">Dominant pattern</dt>
            <dd className="struct-val">{patternLabel(incident.dominant_pattern)}</dd>
          </div>
          <div className="struct-row">
            <dt className="struct-key">Repeat count</dt>
            <dd className="struct-val">{incident.repeat_count}×</dd>
          </div>
          <div className="struct-row">
            <dt className="struct-key">No-progress detected</dt>
            <dd className="struct-val"><StatusPill value={incident.no_progress ? "yes" : "no"} /></dd>
          </div>
          <div className="struct-row">
            <dt className="struct-key">Estimated waste</dt>
            <dd className="struct-val mono kpi-value-danger loop-strong-md">{incident.estimated_cost_usd > 0 ? formatUsd(incident.estimated_cost_usd) : "—"}</dd>
          </div>
          <div className="struct-row">
            <dt className="struct-key">Retry suppression</dt>
            <dd className="struct-val"><StatusPill value={incident.retry_suppression_applied ? "applied" : "not applied"} /></dd>
          </div>
        </dl>

        <div style={{ marginTop: 12 }}>
          <header className="panel-header"><div><h4>Raw payload</h4></div></header>
          {callDetail.isLoading ? <div className="loading" /> : null}
          {callDetail.error ? <div className="hint">Failed to load call payload.</div> : null}
          {callDetail.data ? (
            <div>
              <div style={{ marginBottom: 8 }}>
                <button className="btn btn-soft" onClick={() => void copyPayload()}>Copy payload</button>
              </div>
              <pre className="raw-json mono" style={{ maxHeight: 360, overflow: "auto" }}>{JSON.stringify(callDetail.data.payload ?? callDetail.data.diagnosis_result ?? {}, null, 2)}</pre>
            </div>
          ) : null}
        </div>

        <div style={{ marginTop: 12 }}>
          <header className="panel-header"><div><h4>Local actions</h4></div></header>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
            <input type="datetime-local" value={snoozeUntil} onChange={(e) => setSnoozeUntil(e.target.value)} />
            <button className="btn btn-soft" onClick={() => { if (snoozeUntil) { setSnoozeStore(incident.diagnosis_id, snoozeUntil); onClose(); } }}>Snooze</button>
            {!isDismissed ? (
              <button className="btn btn-danger" onClick={() => { setDismissedStore(incident.diagnosis_id, true); onClose(); }}>Dismiss</button>
            ) : (
              <button className="btn btn-soft" onClick={() => { setDismissedStore(incident.diagnosis_id, false); }}>Undismiss</button>
            )}
          </div>
        </div>
      </section>
    );
  }

  return (
    <>
      {/* ── KPI strip ── */}
      <div className="kpi-grid loop-kpi-grid">
        <article className="kpi-card">
          <span className="kpi-label">Total Loops</span>
          <strong className="kpi-value">{summary.isLoading ? "—" : (summaryData?.total_loop_count ?? 0)}</strong>
          <span className="kpi-sub">Last {summaryDays}d</span>
        </article>
        <article className={`kpi-card${(summaryData?.estimated_waste_usd ?? 0) > 0 ? " kpi-card-danger" : ""}`}>
          <span className="kpi-label">Estimated Waste</span>
          <strong className="kpi-value mono kpi-value-danger">
            {summary.isLoading ? "—" : formatUsd(summaryData?.estimated_waste_usd ?? 0)}
          </strong>
          <span className="kpi-sub">Cost at loop time</span>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Top Looping Agent</span>
          <strong className="kpi-value loop-kpi-compact loop-kpi-break">
            {summary.isLoading ? "—" : (summaryData?.top_looping_agent ?? "none")}
          </strong>
          <span className="kpi-sub">Most incidents</span>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Common Pattern</span>
          <strong className="kpi-value loop-kpi-compact">
            {summary.isLoading ? "—" : patternLabel(summaryData?.most_common_pattern ?? null)}
          </strong>
          <span className="kpi-sub">Most frequent type</span>
        </article>
      </div>

      {/* ── Bar chart ── */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Loops per Day</h3>
            <p>Click a bar to filter incidents to that day.</p>
          </div>
          <div className="loop-window-btns">
            {([7, 14, 30] as const).map((d) => (
              <button
                key={d}
                type="button"
                className={`cost-window-btn${summaryDays === d ? " active" : ""}`}
                onClick={() => setSummaryDays(d)}
              >
                {d}d
              </button>
            ))}
          </div>
        </header>

        {summary.isLoading ? (
          <div className="loading" />
        ) : barPoints.length === 0 ? (
          <div className="empty">No loop incidents in this window.</div>
        ) : (
          <div className="loop-bar-chart">
            {barPoints.map((point) => (
              <div key={point.day} className="loop-bar-col">
                <div
                  className={`loop-bar${filterDay === point.day ? " loop-bar-active" : ""}`}
                  style={{ height: `${point.pct}%`, minHeight: point.count > 0 ? 4 : 0 }}
                  title={`${point.day}: ${point.count} loop${point.count !== 1 ? "s" : ""}`}
                  onClick={() => {
                    setFilterDay(point.day === filterDay ? null : point.day);
                    setSelectedId(null);
                  }}
                />
                <span className="loop-bar-label">{point.day.slice(5)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Incident list ── */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Loop Incidents</h3>
            <p>
              {incidents.isLoading
                ? "Loading…"
                : filterDay
                ? `${filteredIncidentItems.length} incidents on ${filterDay} · click bar to clear`
                : `${visibleIncidentItems.length} incidents · last ${incidentDays}d`}
            </p>
          </div>
          <div className="loop-window-btns" style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {([7, 14, 30] as const).map((d) => (
              <button
                key={d}
                type="button"
                className={`cost-window-btn${incidentDays === d ? " active" : ""}`}
                onClick={() => setIncidentDays(d)}
              >
                {d}d
              </button>
            ))}
            <button type="button" className="btn btn-soft" onClick={() => void incidents.refetch()}>
              Refresh
            </button>
            {filterDay && (
              <button type="button" className="btn btn-soft" onClick={() => setFilterDay(null)}>
                Clear
              </button>
            )}
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginLeft: 8 }}>
              <label style={{ fontSize: 12, color: "var(--muted)", marginRight: 6 }}>Agent</label>
              <select value={agentFilter ?? ""} onChange={(e) => setAgentFilter(e.target.value || null)}>
                <option value="">All</option>
                {agentNames.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
              <label style={{ fontSize: 12, color: "var(--muted)", marginLeft: 8, marginRight: 6 }}>Pattern</label>
              <select value={patternFilter ?? ""} onChange={(e) => setPatternFilter(e.target.value || null)}>
                <option value="">All</option>
                {patternNames.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
              <button type="button" className="btn btn-soft" onClick={() => exportCsv(visibleIncidentItems)}>Export CSV</button>
              <button type="button" className="btn btn-soft" onClick={() => exportJson(visibleIncidentItems)}>Export JSON</button>
              <label style={{ marginLeft: 8, fontSize: 13 }}>
                <input type="checkbox" checked={includeSuppressed} onChange={(e) => setIncludeSuppressed(e.target.checked)} /> Show suppressed
              </label>
            </div>
          </div>
        </header>

        {incidents.isLoading ? (
          <div className="loading" />
        ) : visibleIncidentItems.length === 0 ? (
          <div className="empty">
            {filterDay
              ? `No loop incidents on ${filterDay}.`
              : "No loop incidents in this window. Your agents are clean."}
          </div>
        ) : (
          <div className="list">
            <div className="list-row loop-incident-header">
              <span className="loop-col-time">Time</span>
              <span className="loop-col-agent">Agent</span>
              <span className="loop-col-pattern">Pattern</span>
              <span className="loop-col-stat">Repeats</span>
              <span className="loop-col-stat">Score</span>
              <span className="loop-col-stat">Waste</span>
              <span className="loop-col-stat">Suppressed</span>
            </div>
            {visibleIncidentItems.map((item) => (
              <button
                key={item.diagnosis_id}
                type="button"
                className={`list-row loop-incident-row${selectedId === item.diagnosis_id ? " loop-row-selected" : ""}`}
                onClick={() => setSelectedId(item.diagnosis_id === selectedId ? null : item.diagnosis_id)}
              >
                <span className="loop-col-time">{formatDateTime(item.created_at)}</span>
                <span className="loop-col-agent">{item.agent_name ?? "unknown"}</span>
                <span className="loop-col-pattern">{patternLabel(item.dominant_pattern)}</span>
                <span className="loop-col-stat">{item.repeat_count}×</span>
                <span className={`loop-col-stat mono ${scoreClass(item.loop_score)}`}>
                  {item.loop_score.toFixed(2)}
                </span>
                <span className="loop-col-stat mono">
                  {item.estimated_cost_usd > 0 ? formatUsd(item.estimated_cost_usd) : "—"}
                </span>
                <span className="loop-col-stat">
                  <StatusPill value={item.retry_suppression_applied ? "suppressed" : "live"} />
                </span>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* ── Incident detail ── */}
      {selectedIncident ? <LoopDetailPanel incident={selectedIncident} onClose={() => setSelectedId(null)} /> : null}
    </>
  );
}
