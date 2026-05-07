"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { StatusPill } from "@/components/status-pill";
import { getFixAnalytics, markDiagnosisFixCopied } from "@/lib/api";
import { formatCount, formatDate, formatDateTime } from "@/lib/format";
import {
  useCallDetail,
  useDiagnosisFixWatch,
  useDiagnosisPrLinks,
  useDiagnosisState,
  useResolveDiagnosis,
  useSetDiagnosisAssignment,
  useSetDiagnosisSnooze,
  useSetDiagnosisDismissed,
  useTeamMembers,
  useCreateSupportTicket,
  useUpdateSupportTicket,
  useSupportTickets,
} from "@/lib/hooks";
import { useDashboardStore } from "@/lib/store";
import type {
  FixActionQueueItem,
  FixAnalyticsResponse,
  FixDiagnosisPerformanceItem,
  FixFunnelStep,
  FixTrendPoint,
} from "@/lib/types";

const pollMs = 15000;
const deltaContextLabel = "Last 24h vs previous 24h";
type QueueFilter = "all" | "p0" | "regressed" | "high_risk";

function formatRate(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "0.00%";
  }
  return `${(value * 100).toFixed(2)}%`;
}

function formatHours(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  if (value < 1) {
    return `${Math.round(value * 60)}m`;
  }
  if (value < 72) {
    return `${value.toFixed(1)}h`;
  }
  return `${(value / 24).toFixed(1)}d`;
}

function formatDelta(value: number | null | undefined, kind: "rate" | "hours" | "count"): string {
  if (value == null || Number.isNaN(value)) {
    return "no baseline";
  }
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const absolute = Math.abs(value);
  if (kind === "rate") {
    return `${sign}${(absolute * 100).toFixed(1)}% vs last 24h`;
  }
  if (kind === "hours") {
    return `${sign}${formatHours(absolute)} vs last 24h`;
  }
  return `${sign}${formatCount(absolute)} vs last 24h`;
}

function deltaTone(value: number | null | undefined, lowerIsBetter = false): string {
  if (value == null || Number.isNaN(value) || value === 0) {
    return "fix-delta-flat";
  }
  const isGood = lowerIsBetter ? value < 0 : value > 0;
  return isGood ? "fix-delta-good" : "fix-delta-bad";
}

function barWidth(value: number): string {
  return `${Math.max(2, Math.min(100, value * 100))}%`;
}

function normalizedStatus(value: string): string {
  if (value === "needs_attention") {
    return "watch";
  }
  return value;
}

function statusLabel(value: string): string {
  return normalizedStatus(value).replace(/_/g, " ");
}

function healthTone(value: string): string {
  const normalized = normalizedStatus(value);
  if (normalized === "critical") {
    return "fix-tone-critical";
  }
  if (normalized === "watch") {
    return "fix-tone-watch";
  }
  return "fix-tone-stable";
}

function confidenceClass(value: number | null | undefined): string {
  if (value == null) {
    return "fix-confidence-unknown";
  }
  if (value >= 0.85) {
    return "fix-confidence-high";
  }
  if (value >= 0.65) {
    return "fix-confidence-medium";
  }
  return "fix-confidence-low";
}

function queueRank(item: FixActionQueueItem): number {
  if (item.status_badge === "critical") {
    return 0;
  }
  if (item.status_badge === "watch") {
    return 1;
  }
  return 2;
}

function isHighRisk(item: FixActionQueueItem): boolean {
  return item.risk_level === "high" || item.blast_radius === "high" || item.status_badge === "critical";
}

function filterQueueItem(item: FixActionQueueItem, activeFilter: QueueFilter): boolean {
  if (activeFilter === "p0") {
    return item.priority.toUpperCase() === "P0";
  }
  if (activeFilter === "regressed") {
    return item.success_status === "regressed";
  }
  if (activeFilter === "high_risk") {
    return isHighRisk(item);
  }
  return true;
}

function prDraftTitle(item: FixActionQueueItem): string {
  return `${item.priority}: ${item.fix_title}`;
}

function prDraftBranch(item: FixActionQueueItem): string {
  const diagnosis = item.diagnosis_type.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const id = item.fix_id.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 32);
  return `zroky/fix-${diagnosis || "diagnosis"}-${id || "draft"}`;
}

function prDraftBody(item: FixActionQueueItem): string {
  return [
    `Fix: ${item.fix_title}`,
    `Diagnosis: ${item.diagnosis_type}`,
    `Fix ID: ${item.fix_id}`,
    `Priority: ${item.priority}`,
    `Risk: ${item.risk_level ?? "unknown"}`,
    `Blast radius: ${item.blast_radius ?? "unknown"}`,
    `Resolution confidence: ${item.resolution_confidence == null ? "unknown" : formatRate(item.resolution_confidence)}`,
    `Correlation: ${item.resolution_correlation ?? "unknown"}`,
    `Attribution: ${item.attribution_mode ?? "unknown"}`,
    "",
    `Recommended next action: ${item.recommended_next_action}`,
  ].join("\n");
}

function MicroInsight({ payload }: { payload: FixAnalyticsResponse }) {
  const severityClass = healthTone(payload.micro_insight.severity);
  return (
    <section className={`fix-insight ${severityClass}`}>
      <span className="fix-insight-label">Micro-insight</span>
      <strong>{payload.micro_insight.message}</strong>
      <div className="fix-insight-actions">
        {payload.micro_insight.priority_hint ? <span>{payload.micro_insight.priority_hint}</span> : null}
        {payload.micro_insight.action_label ? <span>{payload.micro_insight.action_label}</span> : null}
      </div>
      <span className="mono">Updated {formatDateTime(payload.generated_at)}</span>
    </section>
  );
}

function HealthTrustStrip({ payload }: { payload: FixAnalyticsResponse }) {
  const cards = [
    {
      label: "Adoption",
      value: formatRate(payload.health.adoption_rate),
      helper: "shown to acted on",
      tooltip: "Adoption Rate = % of shown fixes that were copied, turned into a PR, applied, resolved, or regressed.",
      delta: payload.health.adoption_rate_delta,
      deltaKind: "rate" as const,
    },
    {
      label: "Success",
      value: formatRate(payload.health.success_rate),
      helper: "applied to resolved",
      tooltip: "Success Rate = % of applied or merged fixes that reached resolved without regression.",
      delta: payload.health.success_rate_delta,
      deltaKind: "rate" as const,
    },
    {
      label: "Regression",
      value: formatRate(payload.health.regression_rate),
      helper: "resolved fixes reopened",
      tooltip: "Regression Rate = % of resolved fixes where the same diagnosis returned after resolution.",
      delta: payload.health.regression_rate_delta,
      deltaKind: "rate" as const,
      lowerIsBetter: true,
    },
    {
      label: "Median Resolve",
      value: formatHours(payload.health.median_time_to_resolution_hours),
      helper: "applied to resolved",
      tooltip: "Median Resolve = median time from applied or merged to resolved.",
      delta: payload.health.median_time_to_resolution_hours_delta,
      deltaKind: "hours" as const,
      lowerIsBetter: true,
    },
    {
      label: "Trust",
      value: formatRate(payload.health.average_resolution_confidence),
      helper: "avg resolution confidence",
      tooltip: "Trust = average confidence that resolved fixes actually caused the issue to stop recurring.",
      delta: payload.health.average_resolution_confidence_delta,
      deltaKind: "rate" as const,
    },
    {
      label: "Major Regressions",
      value: formatCount(payload.health.major_regressions_count),
      helper: statusLabel(payload.health.severity_indicator),
      tooltip: "Major Regressions = high-impact recurring failures after a fix was marked resolved.",
      delta: payload.health.major_regressions_count_delta,
      deltaKind: "count" as const,
      lowerIsBetter: true,
    },
  ];

  return (
    <section className="fix-health-section">
      <div className="fix-section-meta">
        <span>Fix Health & Trust</span>
        <span>{deltaContextLabel}</span>
      </div>
      <div className="fix-health-strip">
        {cards.map((card) => (
          <article className="fix-health-card" key={card.label} title={card.tooltip}>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
            <em className={`fix-kpi-delta ${deltaTone(card.delta, card.lowerIsBetter)}`}>
              {formatDelta(card.delta, card.deltaKind)}
            </em>
            <small>{card.helper}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function FunnelChart({ steps }: { steps: FixFunnelStep[] }) {
  const maxCount = Math.max(1, ...steps.map((step) => step.count));

  return (
    <article className="panel fix-chart-card">
      <header className="panel-header">
        <div>
          <h3>Fix Funnel</h3>
          <p>Where fixes fail to convert.</p>
        </div>
      </header>
      <div className="fix-funnel">
        {steps.map((step) => (
          <div className="fix-funnel-row" key={step.state}>
            <div className="fix-funnel-label">
              <strong>{step.label}</strong>
              <span>{formatRate(step.conversion_rate)} from previous</span>
            </div>
            <div className="fix-funnel-track" aria-hidden="true">
              <div className={`fix-funnel-fill fix-state-${step.state}`} style={{ width: `${(step.count / maxCount) * 100}%` }} />
            </div>
            <span className="mono fix-funnel-count">{formatCount(step.count)}</span>
          </div>
        ))}
      </div>
    </article>
  );
}

function TrendChart({ points }: { points: FixTrendPoint[] }) {
  const visiblePoints = points.slice(-14);

  return (
    <article className="panel fix-chart-card">
      <header className="panel-header">
        <div>
          <h3>Success vs Regression</h3>
          <p>Resolved fixes are only useful if they stay resolved.</p>
        </div>
      </header>
      <div className="fix-trend">
        {visiblePoints.map((point) => (
          <div className="fix-trend-day" key={point.day}>
            <div className="fix-trend-bars" title={`${point.day}: ${formatRate(point.success_rate)} success, ${formatRate(point.regression_rate)} regression`}>
              <span className="fix-trend-success" style={{ height: barWidth(point.success_rate) }} />
              <span className="fix-trend-regression" style={{ height: barWidth(point.regression_rate) }} />
            </div>
            <span>{formatDate(point.day)}</span>
          </div>
        ))}
      </div>
      <div className="fix-chart-legend">
        <span><i className="legend-dot legend-success" /> Success</span>
        <span><i className="legend-dot legend-danger" /> Regression</span>
      </div>
    </article>
  );
}

function DiagnosisPerformance({ items }: { items: FixDiagnosisPerformanceItem[] }) {
  const visible = items.slice(0, 6);

  return (
    <article className="panel fix-chart-card">
      <header className="panel-header">
        <div>
          <h3>Performance by Diagnosis</h3>
          <p>Which fix strategies need product attention.</p>
        </div>
      </header>
      <div className="fix-diagnosis-list">
        {visible.length === 0 ? (
          <div className="empty">No diagnosis performance data yet.</div>
        ) : (
          visible.map((item) => (
            <div className="fix-diagnosis-row" key={item.diagnosis_type}>
              <div className="fix-diagnosis-main">
                <strong>{item.diagnosis_type}</strong>
                <span>{item.fix_tags.length > 0 ? item.fix_tags.join(", ") : "untagged"}</span>
              </div>
              <div className="fix-diagnosis-bars">
                <span className="fix-mini-label">Adopt {formatRate(item.adoption_rate)}</span>
                <div className="fix-mini-track"><i style={{ width: barWidth(item.adoption_rate) }} /></div>
                <span className="fix-mini-label">Success {formatRate(item.success_rate)}</span>
                <div className="fix-mini-track"><i style={{ width: barWidth(item.success_rate) }} /></div>
                <span className="fix-mini-label danger-text">Regress {formatRate(item.regression_rate)}</span>
              </div>
              <span className="mono">{formatHours(item.median_resolution_hours)}</span>
            </div>
          ))
        )}
      </div>
    </article>
  );
}

function ActionQueue({ items, onOpenItem, hiddenDiagnosisIds }: { items: FixActionQueueItem[]; onOpenItem?: (item: FixActionQueueItem) => void; hiddenDiagnosisIds?: Set<string> }) {
  const [copiedFixId, setCopiedFixId] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<QueueFilter>("all");
  const [prDraftItem, setPrDraftItem] = useState<FixActionQueueItem | null>(null);
  const [diagFilter, setDiagFilter] = useState<string | null>(null);
  const [agentFilter, setAgentFilter] = useState<string | null>(null);
  const sorted = useMemo(() => {
    return [...items]
      .filter((item) => filterQueueItem(item, activeFilter))
      .filter((item) => (diagFilter ? item.diagnosis_type === diagFilter : true))
      .filter((item) => (agentFilter ? (item.agent_name ?? "unknown") === agentFilter : true))
      .filter((item) => !(hiddenDiagnosisIds && hiddenDiagnosisIds.has((item.diagnosis_id ?? "").toLowerCase())))
      .sort((left, right) => queueRank(left) - queueRank(right) || right.time_open_hours - left.time_open_hours);
  }, [activeFilter, items, diagFilter, hiddenDiagnosisIds]);
  const counts = useMemo(() => {
    return {
      all: items.length,
      p0: items.filter((item) => item.priority.toUpperCase() === "P0").length,
      regressed: items.filter((item) => item.success_status === "regressed").length,
      high_risk: items.filter(isHighRisk).length,
    };
  }, [items]);

  const diagTypes = useMemo(() => {
    const s = new Set(items.map((i) => i.diagnosis_type));
    return Array.from(s).sort();
  }, [items]);

  const agentNames = useMemo(() => {
    const s = new Set(items.map((i) => i.agent_name ?? "unknown"));
    return Array.from(s).sort();
  }, [items]);

  const projectId = useDashboardStore((s) => s.selectedProject);
  const team = useTeamMembers(projectId ?? "");
  const assignments = useDashboardStore((s) => s.assignments);
  const setAssignment = useDashboardStore((s) => s.setAssignment);
  const clearAssignment = useDashboardStore((s) => s.clearAssignment);
  const setSnooze = useDashboardStore((s) => s.setSnooze);
  const clearSnooze = useDashboardStore((s) => s.clearSnooze);
  const setDismissed = useDashboardStore((s) => s.setDismissed);
  const resolveMutation = useResolveDiagnosis();
  const assignMutation = useSetDiagnosisAssignment();
  const snoozeMutation = useSetDiagnosisSnooze();
  const dismissMutation = useSetDiagnosisDismissed();
  const [assignSelection, setAssignSelection] = useState<Record<string, string | null>>({});
  const storeSnoozes = useDashboardStore((s) => s.snoozes);

  async function copyFix(item: FixActionQueueItem) {
    const text = [
      item.fix_title,
      `Fix ID: ${item.fix_id}`,
      `Diagnosis: ${item.diagnosis_type}`,
      `Priority: ${item.priority}`,
      `Next action: ${item.recommended_next_action}`,
    ].join("\n");

    if (typeof navigator === "undefined" || !navigator.clipboard) {
      return;
    }

    await navigator.clipboard.writeText(text);
    setCopiedFixId(item.fix_id);
    window.setTimeout(() => setCopiedFixId((current) => (current === item.fix_id ? null : current)), 1800);
    markDiagnosisFixCopied(item.diagnosis_id).catch(() => undefined);
  }

  async function copyPrPayload(item: FixActionQueueItem) {
    if (typeof navigator === "undefined" || !navigator.clipboard) {
      return;
    }

    const text = [
      `Branch: ${prDraftBranch(item)}`,
      `Commit: ${item.fix_title}`,
      `PR title: ${prDraftTitle(item)}`,
      "",
      prDraftBody(item),
    ].join("\n");
    await navigator.clipboard.writeText(text);
  }

  function handleAssignRow(item: FixActionQueueItem) {
    const key = (item.diagnosis_id ?? item.fix_id ?? "").toLowerCase();
    const sel = assignSelection[key] ?? assignments[key] ?? null;
    if (!sel) return;
    const prev = assignments[key] ?? null;
    // optimistic
    setAssignment(item.diagnosis_id ?? "", sel);
    assignMutation.mutate({ diagnosisId: item.diagnosis_id ?? "", assigned_subject: sel }, {
      onError: () => {
        if (prev) setAssignment(item.diagnosis_id ?? "", prev);
        else clearAssignment(item.diagnosis_id ?? "");
      },
    });
  }

  function handleClearAssignRow(item: FixActionQueueItem) {
    const key = (item.diagnosis_id ?? item.fix_id ?? "").toLowerCase();
    const prev = assignments[key] ?? null;
    // optimistic
    clearAssignment(item.diagnosis_id ?? "");
    assignMutation.mutate({ diagnosisId: item.diagnosis_id ?? "", assigned_subject: null }, {
      onError: () => {
        if (prev) setAssignment(item.diagnosis_id ?? "", prev);
      },
    });
  }

  function handleSnoozeRow(item: FixActionQueueItem, hours: number) {
    const iso = new Date(Date.now() + hours * 3600 * 1000).toISOString();
    const key = (item.diagnosis_id ?? item.fix_id ?? "").toLowerCase();
    const prev = storeSnoozes[key] ?? null;
    // optimistic
    setSnooze(item.diagnosis_id ?? "", iso);
    snoozeMutation.mutate({ diagnosisId: item.diagnosis_id ?? "", snoozed_until: iso }, {
      onError: () => {
        if (prev) setSnooze(item.diagnosis_id ?? "", prev);
        else clearSnooze(item.diagnosis_id ?? "");
      },
    });
  }

  async function handleWontFixRow(item: FixActionQueueItem) {
    try {
      await resolveMutation.mutateAsync(item.diagnosis_id);
    } catch (e) {
      // ignore
      return;
    }
    // optimistic
    setDismissed(item.diagnosis_id ?? "", true);
    dismissMutation.mutate({ diagnosisId: item.diagnosis_id ?? "", dismissed: true }, {
      onError: () => {
        setDismissed(item.diagnosis_id ?? "", false);
      },
    });
  }

  return (
    <section className="panel fix-action-panel" aria-label="Action Queue">
      <header className="panel-header">
        <div>
          <h3>Action Queue</h3>
          <p>Critical regressions, unresolved P0s, low-confidence resolutions, and aging P1s.</p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div className="fix-filter-chips" aria-label="Action queue filters">
          {[
            ["all", "All"],
            ["p0", "P0"],
            ["regressed", "Regressed"],
            ["high_risk", "High Risk"],
          ].map(([value, label]) => (
            <button
              className={`fix-filter-chip ${activeFilter === value ? "active" : ""}`}
              key={value}
              type="button"
              onClick={() => setActiveFilter(value as QueueFilter)}
            >
              {label} <span>{formatCount(counts[value as QueueFilter])}</span>
            </button>
          ))}
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--muted)", marginRight: 6 }}>Type</label>
            <select value={diagFilter ?? ""} onChange={(e) => setDiagFilter(e.target.value || null)}>
              <option value="">All</option>
              {diagTypes.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--muted)", marginRight: 6 }}>Agent</label>
            <select value={agentFilter ?? ""} onChange={(e) => setAgentFilter(e.target.value || null)}>
              <option value="">All</option>
              {agentNames.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
        </div>
      </header>
      <div className="table-wrap fix-table-wrap">
        <table className="fix-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Priority</th>
              <th>Assignee</th>
              <th>Diagnosis</th>
              <th>Fix</th>
              <th>State</th>
              <th>Trust</th>
              <th>Risk</th>
              <th>Open</th>
              <th>Next action</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={10}>
                  <div className="empty">
                    {items.length === 0
                      ? "No active issues. Recent fixes are stable."
                      : "No fixes match this filter."}
                  </div>
                </td>
              </tr>
              ) : (
              sorted.map((item) => (
                <tr
                  key={item.fix_id}
                  onClick={(e) => {
                    const target = e.target as HTMLElement;
                    if (target.closest("button, a, select, input")) return;
                    onOpenItem?.(item);
                  }}
                  style={{ cursor: "pointer" }}
                >
                  <td><StatusPill value={statusLabel(item.status_badge)} /></td>
                  <td><span className="mono">{item.priority}</span></td>
                  <td>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <div style={{ minWidth: 120 }}>
                        {assignments[(item.diagnosis_id ?? "").toLowerCase()] ? (
                          team.data?.items?.find((m) => m.user_id === assignments[(item.diagnosis_id ?? "").toLowerCase()])?.subject ?? assignments[(item.diagnosis_id ?? "").toLowerCase()]
                        ) : (
                          <em>unassigned</em>
                        )}
                      </div>
                      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        <select
                          value={assignSelection[(item.diagnosis_id ?? "").toLowerCase()] ?? assignments[(item.diagnosis_id ?? "").toLowerCase()] ?? ""}
                          onChange={(e) => setAssignSelection((prev) => ({ ...prev, [(item.diagnosis_id ?? "").toLowerCase()]: e.target.value || null }))}
                        >
                          <option value="">Unassigned</option>
                          {team.data?.items?.map((m) => (
                            <option key={m.membership_id} value={m.user_id ?? ""}>{m.subject ?? m.email ?? m.user_id}</option>
                          ))}
                        </select>
                        <button className="btn btn-soft btn-compact" type="button" onClick={() => handleAssignRow(item)} disabled={!((assignSelection[(item.diagnosis_id ?? "").toLowerCase()] ?? assignments[(item.diagnosis_id ?? "").toLowerCase()]))}>
                          Assign
                        </button>
                        {assignments[(item.diagnosis_id ?? "").toLowerCase()] ? (
                          <button className="btn btn-soft btn-compact" type="button" onClick={() => handleClearAssignRow(item)}>
                            Unassign
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </td>
                  <td>
                    <strong>{item.diagnosis_type}</strong>
                    <span className="fix-table-sub">{item.success_status}</span>
                  </td>
                  <td>
                    <strong>{item.fix_title}</strong>
                    <span className="fix-table-sub mono">{item.fix_id}</span>
                  </td>
                  <td>{statusLabel(item.current_state)}</td>
                  <td title="Correlation = how strongly resolution is attributed to this fix. Attribution = whether one fix, multiple fixes, or ambiguous changes may explain the outcome.">
                    <span className={`mono fix-confidence ${confidenceClass(item.resolution_confidence)}`}>
                      {item.resolution_confidence == null ? "-" : formatRate(item.resolution_confidence)}
                    </span>
                    <span className="fix-table-sub">{item.resolution_correlation ?? "unknown"} / {item.attribution_mode ?? "unknown"}</span>
                  </td>
                  <td>
                    <span>{item.risk_level ?? "unknown"}</span>
                    <span className="fix-table-sub">blast {item.blast_radius ?? "unknown"}</span>
                  </td>
                  <td className="mono">{formatHours(item.time_open_hours)}</td>
                  <td>{item.recommended_next_action}</td>
                  <td>
                    <div className="fix-row-actions">
                      <button className="btn btn-soft btn-compact" type="button" onClick={() => onOpenItem?.(item)}>
                        Details
                      </button>
                      <button className="btn btn-soft btn-compact" type="button" onClick={() => void copyFix(item)}>
                        {copiedFixId === item.fix_id ? "Copied" : "Copy Fix"}
                      </button>
                      <button className="btn btn-primary btn-compact" type="button" onClick={() => setPrDraftItem(item)}>
                        Open PR Draft
                      </button>
                      <button className="btn btn-soft btn-compact" type="button" onClick={() => handleSnoozeRow(item, 24)}>
                        Snooze 24h
                      </button>
                      <button className="btn btn-soft btn-compact" type="button" onClick={() => handleSnoozeRow(item, 168)}>
                        Snooze 7d
                      </button>
                      <button className="btn btn-danger btn-compact" type="button" onClick={() => handleWontFixRow(item)}>
                        Won't Fix
                      </button>
                      {copiedFixId === item.fix_id ? <span className="fix-copy-feedback">✓ Copied to clipboard</span> : null}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {prDraftItem ? (
        <div className="fix-modal-backdrop" role="presentation" onClick={() => setPrDraftItem(null)}>
          <section className="fix-pr-modal" role="dialog" aria-modal="true" aria-label="PR draft" onClick={(event) => event.stopPropagation()}>
            <header className="panel-header">
              <div>
                <h3>PR Draft</h3>
                <p>Reviewable payload only. No code is pushed or modified.</p>
              </div>
              <button className="btn btn-soft btn-compact" type="button" onClick={() => setPrDraftItem(null)}>
                Close
              </button>
            </header>
            <div className="fix-pr-grid">
              <div>
                <span>Branch</span>
                <strong className="mono">{prDraftBranch(prDraftItem)}</strong>
              </div>
              <div>
                <span>PR title</span>
                <strong>{prDraftTitle(prDraftItem)}</strong>
              </div>
            </div>
            <pre className="fix-pr-body">{prDraftBody(prDraftItem)}</pre>
            <div className="fix-row-actions">
              <button className="btn btn-primary" type="button" onClick={() => void copyPrPayload(prDraftItem)}>
                Copy PR Payload
              </button>
              <Link className="btn btn-soft" href={`/calls/${prDraftItem.diagnosis_id}#fix-guidance`}>
                Open Call Detail
              </Link>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}

export default function FixesPage() {
  const [selectedItem, setSelectedItem] = useState<FixActionQueueItem | null>(null);
  const [payload, setPayload] = useState<FixAnalyticsResponse | null>(null);
  const ticketsQueryGlobal = useSupportTickets({ limit: 200 });

  const storeSnoozes = useDashboardStore((s) => s.snoozes);
  const dismissedMap = useDashboardStore((s) => s.dismissed);

  const hiddenDiagnosisIds = useMemo(() => {
    const items = ticketsQueryGlobal.data?.items ?? [];
    const set = new Set<string>();
    // keep existing ticket-based snooze parsing for compatibility
    for (const t of items) {
      const desc = String(t.description ?? "");
      const diagMatch = /Diagnosis:\s*([A-Za-z0-9-_]+)/i.exec(desc);
      const snoozeMatch = /Snoozed until:\s*([0-9T:\- ]+)/i.exec(desc);
      if (diagMatch && snoozeMatch) {
        const diagId = diagMatch[1];
        const d = new Date(snoozeMatch[1]);
        if (!Number.isNaN(d.getTime()) && d.getTime() > Date.now()) {
          set.add(diagId.toLowerCase());
        }
      }
    }
    // include store-based snoozes
    for (const [diag, iso] of Object.entries(storeSnoozes ?? {})) {
      const d = new Date(iso as string);
      if (!Number.isNaN(d.getTime()) && d.getTime() > Date.now()) {
        set.add(diag.toLowerCase());
      }
    }
    // include dismissed items
    for (const [diag, v] of Object.entries(dismissedMap ?? {})) {
      if (v) set.add(diag.toLowerCase());
    }
    return set;
  }, [ticketsQueryGlobal.data, storeSnoozes, dismissedMap]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const response = await getFixAnalytics(30);
      setPayload(response);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load fix analytics.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, pollMs);
    return () => window.clearInterval(timer);
  }, [load]);

  if (loading && payload == null) {
    return (
      <section className="fix-dashboard">
        <div className="loading" />
        <div className="loading" />
        <div className="loading" />
      </section>
    );
  }

  if (error && payload == null) {
    return <section className="panel"><p>{error}</p></section>;
  }

  if (!payload) {
    return <section className="panel"><p>Fix analytics unavailable.</p></section>;
  }

  return (
    <section className="fix-dashboard page-enter">
      <section className="fix-page-heading">
        <div>
          <span className="fix-eyebrow">Fix Analytics</span>
          <h1>Are generated fixes working?</h1>
          <p>Adoption, trust, regressions, and the exact queue engineers should work through next.</p>
        </div>
        <div className="fix-page-meta">
          <StatusPill value={statusLabel(payload.health.severity_indicator)} />
          <span className="mono">Window {payload.window_days}d</span>
        </div>
      </section>

      {error ? <section className="panel"><p>{error}</p></section> : null}

      <HealthTrustStrip payload={payload} />
      <MicroInsight payload={payload} />

      <section className="fix-graph-grid">
        <FunnelChart steps={payload.funnel} />
        <TrendChart points={payload.trend} />
        <DiagnosisPerformance items={payload.diagnosis_performance} />
      </section>

      <ActionQueue items={payload.action_queue} onOpenItem={(it) => setSelectedItem(it)} hiddenDiagnosisIds={hiddenDiagnosisIds} />

      {selectedItem ? (
        <FixDrawer item={selectedItem} onClose={() => setSelectedItem(null)} />
      ) : null}
    </section>
  );
}

function FixDrawer({ item, onClose }: { item: FixActionQueueItem; onClose: () => void }) {
  const callDetail = useCallDetail(item.diagnosis_id);
  const fixWatch = useDiagnosisFixWatch(item.diagnosis_id);
  const prLinks = useDiagnosisPrLinks(item.diagnosis_id);
  const resolveMutation = useResolveDiagnosis();

  const diagnosisState = useDiagnosisState(item.diagnosis_id);

  const projectId = useDashboardStore((s) => s.selectedProject);
  const team = useTeamMembers(projectId ?? "");
  const createTicket = useCreateSupportTicket();
  const updateTicket = useUpdateSupportTicket();
  const ticketsQuery = useSupportTickets({ limit: 200 });
  const setAssignment = useDashboardStore((s) => s.setAssignment);
  const clearAssignment = useDashboardStore((s) => s.clearAssignment);
  const setSnooze = useDashboardStore((s) => s.setSnooze);
  const clearSnooze = useDashboardStore((s) => s.clearSnooze);
  const setDismissed = useDashboardStore((s) => s.setDismissed);
  const assignmentsMap = useDashboardStore((s) => s.assignments);

  const relatedTickets = useMemo(() => {
    const items = ticketsQuery.data?.items ?? [];
    const needle1 = (item.diagnosis_id ?? "").toLowerCase();
    const needle2 = (item.fix_id ?? "").toLowerCase();
    return items.filter((t) => {
      const text = `${t.title ?? ""} ${t.description ?? ""}`.toLowerCase();
      return (needle1 && text.includes(needle1)) || (needle2 && text.includes(needle2));
    });
  }, [ticketsQuery.data, item.diagnosis_id, item.fix_id]);

  const [assignTo, setAssignTo] = useState<string | null>(null);
  const [snoozeUntil, setSnoozeUntil] = useState<string>("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const data = diagnosisState.data;
    if (!data) return;
    const diagId = item.diagnosis_id ?? "";
    if (data.assigned_subject) setAssignment(diagId, data.assigned_subject);
    else clearAssignment(diagId);

    if (data.snoozed_until) {
      setSnooze(diagId, data.snoozed_until);
      try {
        const d = new Date(data.snoozed_until);
        const pad = (n: number) => String(n).padStart(2, "0");
        setSnoozeUntil(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`);
      } catch (e) {
        // ignore formatting errors
      }
    } else {
      clearSnooze(diagId);
      setSnoozeUntil("");
    }

    setDismissed(diagId, !!data.dismissed);
  }, [diagnosisState.data, item.diagnosis_id, setAssignment, clearAssignment, setSnooze, clearSnooze, setDismissed]);

  async function handleCreateTicketAssign() {
    if (busy) return;
    setBusy(true);
    try {
      const title = `Fix: ${item.fix_title} (${item.fix_id})`;
      const description = `Diagnosis: ${item.diagnosis_id}\nRecommended: ${item.recommended_next_action}\nLink: ${window.location.origin}/calls/${item.diagnosis_id}`;
      const ticket = await createTicket.mutateAsync({ title, description, category: "fix", priority: "normal" });
      if (assignTo) {
        await updateTicket.mutateAsync({ ticketId: ticket.ticket_id, body: { assigned_to: assignTo } });
      }
      onClose();
    } catch (e) {
      // ignore for now
    } finally {
      setBusy(false);
    }
  }

  async function handleWontFix() {
    if (busy) return;
    setBusy(true);
    try {
      await resolveMutation.mutateAsync(item.diagnosis_id);
      // mark dismissed locally so it disappears from the queue
      setDismissed(item.diagnosis_id ?? "", true);
      onClose();
    } catch (e) {
      // noop
    } finally {
      setBusy(false);
    }
  }

  async function handleSnooze() {
    if (!snoozeUntil || busy) return;
    setBusy(true);
    try {
      setSnooze(item.diagnosis_id ?? "", snoozeUntil);
      onClose();
    } catch (e) {
      // noop
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="fix-modal-backdrop" role="presentation" onClick={onClose} />
      <aside className="fix-drawer" role="dialog" aria-modal="true" aria-label="Fix detail" onClick={(e) => e.stopPropagation()}>
        <header className="panel-header">
          <div>
            <h3>Fix Detail</h3>
            <p className="mono">{item.fix_id} · {item.diagnosis_type}</p>
          </div>
          <div>
            <button className="btn btn-soft" onClick={onClose}>Close</button>
          </div>
        </header>

        <div className="panel-body">
          <div style={{ display: "flex", gap: 16, flexDirection: "column" }}>
            <div>
              <strong>Title</strong>
              <div>{item.fix_title}</div>
            </div>

            <div>
              <strong>Recommended</strong>
              <div>{item.recommended_next_action}</div>
            </div>

            <div>
              <strong>Call detail</strong>
              {callDetail.isLoading ? <div className="loading" /> : null}
              {callDetail.error ? <div className="hint">Failed to load call detail.</div> : null}
              {callDetail.data ? (
                <dl className="struct-list">
                  <div className="struct-row"><dt className="struct-key">Status</dt><dd className="struct-val mono">{callDetail.data.status}</dd></div>
                  <div className="struct-row"><dt className="struct-key">Created</dt><dd className="struct-val mono">{formatDateTime(callDetail.data.created_at)}</dd></div>
                  <div className="struct-row"><dt className="struct-key">Agent</dt><dd className="struct-val">{callDetail.data.agent_name ?? "unknown"}</dd></div>
                </dl>
              ) : null}
            </div>

            <div>
              <strong>Fix-watch</strong>
              {fixWatch.isLoading ? <div className="loading" /> : null}
              {fixWatch.data ? (
                <div>
                  <div className="mono">Status: {fixWatch.data.status}</div>
                  <div className="mono">Message: {fixWatch.data.message}</div>
                </div>
              ) : <div className="empty">No fix-watch</div>}
            </div>

            <div>
              <strong>PR Links</strong>
              {prLinks.isLoading ? <div className="loading" /> : null}
              {prLinks.data && prLinks.data.length > 0 ? (
                <ul>
                  {prLinks.data.map((p) => (
                    <li key={p.pr_link_id}><a href={p.pull_request_url} target="_blank" rel="noreferrer">{p.pull_request_title ?? p.pull_request_url}</a></li>
                  ))}
                </ul>
              ) : <div className="empty">No PR links</div>}
            </div>

            <div>
              <strong>Related Tickets</strong>
              {ticketsQuery.isLoading ? <div className="loading" /> : null}
              {!ticketsQuery.isLoading && relatedTickets.length === 0 ? (
                <div className="empty">No related tickets found.</div>
              ) : (
                <ul>
                  {relatedTickets.map((t) => (
                    <li key={t.ticket_id} style={{ marginBottom: 8 }}>
                      <strong>{t.title}</strong>
                      <div className="mono">{t.status} · {t.assigned_to ?? "unassigned"} · {formatDateTime(t.created_at)}</div>
                      <div style={{ marginTop: 4 }}>{t.description ? String(t.description).slice(0, 300) : ""}</div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <strong>Assign / Create ticket</strong>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <select value={assignTo ?? ""} onChange={(e) => setAssignTo(e.target.value || null)}>
                  <option value="">Unassigned</option>
                  {team.data?.items?.map((m) => (
                    <option key={m.membership_id} value={m.user_id ?? ""}>{m.subject ?? m.email ?? m.user_id}</option>
                  ))}
                </select>
                <button className="btn btn-primary" onClick={handleCreateTicketAssign} disabled={createTicket.isLoading || busy}>Create Ticket</button>
                <button
                  className="btn btn-soft"
                  onClick={() => {
                    if (!assignTo) return;
                    setAssignment(item.diagnosis_id ?? "", assignTo);
                    onClose();
                  }}
                  disabled={busy || !assignTo}
                >
                  Assign
                </button>
                {assignmentsMap[(item.diagnosis_id ?? "").toLowerCase()] ? (
                  <button
                    className="btn btn-soft"
                    onClick={() => {
                      clearAssignment(item.diagnosis_id ?? "");
                    }}
                  >
                    Unassign
                  </button>
                ) : null}
              </div>
            </div>

            <div>
              <strong>Quick actions</strong>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-soft" onClick={() => window.open(`/calls/${item.diagnosis_id}`, "_self")}>Open Call</button>
                <button className="btn btn-soft" onClick={() => void markDiagnosisFixCopied(item.diagnosis_id)}>Copy Fix</button>
                <button className="btn btn-soft" onClick={() => void resolveMutation.mutate(item.diagnosis_id)}>Mark Resolved</button>
                <button className="btn btn-danger" onClick={handleWontFix} disabled={busy}>Won't Fix</button>
              </div>
            </div>

            <div>
              <strong>Snooze</strong>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input type="datetime-local" value={snoozeUntil} onChange={(e) => setSnoozeUntil(e.target.value)} />
                <button className="btn btn-soft" onClick={handleSnooze} disabled={busy || !snoozeUntil}>Snooze</button>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
