"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Activity, BadgeAlert, CircleDollarSign, Gauge, RefreshCw, type LucideIcon } from "lucide-react";

import { useDriftStatus, useJudgeHealth, useOutcomeSummary } from "@/lib/hooks";
import type { DimensionDriftView, OutcomeSummaryResponse, VerdictDriftView } from "@/lib/api";
import type { AlertView } from "@/lib/types";

type DriftTab = "provider" | "judge" | "outcome";
type Tone = "ok" | "warn" | "critical" | "neutral";

interface DriftRow {
  id: string;
  title: string;
  tone: Tone;
  baseline: string;
  current: string;
  delta: string;
  affected: string;
  evidence: string;
  action: string;
  primaryHref?: string;
  primaryLabel?: string;
  secondaryHref?: string;
  secondaryLabel?: string;
}

const TABS: Array<{ id: DriftTab; label: string; icon: LucideIcon }> = [
  { id: "provider", label: "Provider Drift", icon: Activity },
  { id: "judge", label: "Judge Drift", icon: Gauge },
  { id: "outcome", label: "Outcome Drift", icon: CircleDollarSign },
];

function pct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function pp(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}pp`;
}

function usd(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function rateUsd(value: number): string {
  return `${usd(value)}/day`;
}

function evidenceNumber(evidence: Record<string, unknown>, key: string): number | null {
  const value = evidence[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function toneClass(tone: Tone): string {
  if (tone === "critical") return "badge-red";
  if (tone === "warn") return "badge-yellow";
  if (tone === "ok") return "badge-green";
  return "badge-gray";
}

function toneLabel(tone: Tone): string {
  if (tone === "critical") return "Critical";
  if (tone === "warn") return "Watch";
  if (tone === "ok") return "Stable";
  return "Info";
}

function severityToTone(severity: AlertView["severity"]): Tone {
  if (severity === "critical") return "critical";
  if (severity === "warn") return "warn";
  return "neutral";
}

function providerRows(alerts: AlertView[]): DriftRow[] {
  return alerts.map((alert) => {
    const baseline = evidenceNumber(alert.evidence, "pass_rate_baseline");
    const current = evidenceNumber(alert.evidence, "pass_rate_current");
    const delta = evidenceNumber(alert.evidence, "delta_pp");
    const currentSamples = evidenceNumber(alert.evidence, "sample_size_current");
    const baselineSamples = evidenceNumber(alert.evidence, "sample_size_baseline");
    const judgeZ = evidenceNumber(alert.evidence, "judge_z");
    const embeddingZ = evidenceNumber(alert.evidence, "embedding_z");

    return {
      id: alert.id,
      title: alert.headline,
      tone: severityToTone(alert.severity),
      baseline: pct(baseline),
      current: pct(current),
      delta: pp(delta),
      affected: `All agents using ${alert.model_id} for ${alert.category}`,
      evidence: `${currentSamples ?? 0} current probes vs ${baselineSamples ?? 0} baseline probes. Judge z ${judgeZ?.toFixed(2) ?? "-"}, embedding z ${embeddingZ?.toFixed(2) ?? "-"}.`,
      action: "Replay affected prompts against the candidate model, then promote stable traces to a golden set.",
      primaryHref: "/replay",
      primaryLabel: "Replay",
      secondaryHref: "/goldens",
      secondaryLabel: "Goldens",
    };
  });
}

function verdictRows(rows: VerdictDriftView[]): DriftRow[] {
  return rows.map((row) => {
    const delta = (row.disagreement_rate - row.threshold) * 100;
    return {
      id: `verdict-${row.judge_model}`,
      title: `${row.judge_model} disagreement drift`,
      tone: row.breached ? "critical" : "ok",
      baseline: `Max ${pct(row.threshold)}`,
      current: pct(row.disagreement_rate),
      delta: pp(delta),
      affected: `All workflows evaluated by ${row.judge_model}`,
      evidence: `${row.disagreement_count} disagreements across ${row.sample_count} calibration samples.`,
      action: "Run judge calibration, review failed calibration traces, and add disputed cases to goldens.",
      primaryHref: "/settings/evaluation",
      primaryLabel: "Calibrate",
      secondaryHref: "/goldens",
      secondaryLabel: "Goldens",
    };
  });
}

function dimensionRows(rows: DimensionDriftView[]): DriftRow[] {
  return rows.map((row) => {
    const delta = row.recent_mean - row.older_mean;
    return {
      id: `dimension-${row.judge_model}-${row.dimension}`,
      title: `${row.dimension} score drift`,
      tone: row.breached ? "warn" : "ok",
      baseline: pct(row.older_mean),
      current: pct(row.recent_mean),
      delta: pp(delta * 100),
      affected: `${row.judge_model} judging ${row.dimension}`,
      evidence: `${row.sample_count} samples. Material degradation threshold is ${pct(row.threshold)}.`,
      action: "Replay failures judged on this dimension and promote representative pass/fail examples to goldens.",
      primaryHref: "/replay",
      primaryLabel: "Replay",
      secondaryHref: "/goldens",
      secondaryLabel: "Goldens",
    };
  });
}

function outcomeLabel(type: string | null): string {
  if (!type) return "mixed outcomes";
  const labels: Record<string, string> = {
    refund_issued: "refunds",
    ticket_escalated: "escalations",
    human_handoff: "human handoffs",
    churn: "churn",
    compliance_fine: "compliance fines",
    retry_cost: "retry costs",
    custom: "custom outcomes",
  };
  return labels[type] ?? type.replace(/_/g, " ");
}

function outcomeRows(current: OutcomeSummaryResponse | undefined, baseline: OutcomeSummaryResponse | undefined): DriftRow[] {
  const currentDays = Math.max(current?.window_days ?? 7, 1);
  const baselineDays = Math.max(baseline?.window_days ?? 30, 1);
  const baselineByAgent = new Map<string, number>();

  for (const cluster of baseline?.by_cluster ?? []) {
    const key = `${cluster.agent_name ?? "unattributed"}::${cluster.detector ?? "unknown"}`;
    baselineByAgent.set(key, cluster.outcome_cost_usd / baselineDays);
  }

  const rows = (current?.by_cluster ?? []).map((cluster, index) => {
    const agent = cluster.agent_name ?? "unattributed";
    const workflow = cluster.detector ?? "outcome attribution";
    const key = `${agent}::${workflow}`;
    const currentRate = cluster.outcome_cost_usd / currentDays;
    const baselineRate = baselineByAgent.get(key) ?? 0;
    const delta = currentRate - baselineRate;
    const tone: Tone = delta > 100 ? "critical" : delta > 20 ? "warn" : "neutral";

    return {
      id: `outcome-${key}-${index}`,
      title: `${agent} ${outcomeLabel(cluster.top_outcome_type)} changed`,
      tone,
      baseline: rateUsd(baselineRate),
      current: rateUsd(currentRate),
      delta: usd(delta),
      affected: `${agent} / ${workflow}`,
      evidence: `${cluster.outcome_count} outcomes, ${cluster.failure_count} linked failures, ${usd(cluster.estimated_monthly_savings_usd)} estimated monthly savings.`,
      action: "Create replay coverage for the highest-cost failure path and add the fixed trace to goldens.",
      primaryHref: "/replay",
      primaryLabel: "Replay",
      secondaryHref: "/goldens",
      secondaryLabel: "Goldens",
    };
  });

  if (rows.length > 0) return rows.slice(0, 8);

  const currentRate = (current?.total_outcome_usd ?? 0) / currentDays;
  const baselineRate = (baseline?.total_outcome_usd ?? 0) / baselineDays;
  const delta = currentRate - baselineRate;
  return [{
    id: "outcome-total",
    title: "Overall outcome cost",
    tone: delta > 100 ? "critical" : delta > 20 ? "warn" : "ok",
    baseline: rateUsd(baselineRate),
    current: rateUsd(currentRate),
    delta: usd(delta),
    affected: "All agents / all workflows",
    evidence: `${current?.linked_outcome_count ?? 0} linked and ${current?.unlinked_outcome_count ?? 0} unlinked outcomes in the current window.`,
    action: "Link outcomes to calls, then replay the top linked failure cluster.",
    primaryHref: "/cost",
    primaryLabel: "Cost",
    secondaryHref: "/replay",
    secondaryLabel: "Replay",
  }];
}

function TabButton({ active, icon: Icon, label, onClick }: { active: boolean; icon: LucideIcon; label: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={`drift-tab-btn${active ? " is-active" : ""}`}>
      <Icon aria-hidden="true" />
      {label}
    </button>
  );
}

function SummaryCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="metric-card drift-summary-card">
      <div className="notif-meta">{label}</div>
      <strong>{value}</strong>
      <span>{sub}</span>
    </div>
  );
}

function DriftTable({ rows, empty }: { rows: DriftRow[]; empty: string }) {
  if (rows.length === 0) {
    return <section className="empty drift-empty">{empty}</section>;
  }

  return (
    <section className="panel drift-table-panel">
      <div className="drift-table">
        <div className="drift-table-head">
          <span>Change</span>
          <span>Baseline</span>
          <span>Current</span>
          <span>Delta</span>
          <span>Affected</span>
          <span>Evidence</span>
          <span>Recommended action</span>
        </div>
        {rows.map((row) => (
          <div key={row.id} className="drift-row">
            <div className="drift-change-cell">
              <span className={`alert-cat-badge ${toneClass(row.tone)}`}>{toneLabel(row.tone)}</span>
              <strong>{row.title}</strong>
            </div>
            <span className="mono">{row.baseline}</span>
            <span className="mono">{row.current}</span>
            <span className="mono">{row.delta}</span>
            <span>{row.affected}</span>
            <span>{row.evidence}</span>
            <div className="drift-action-cell">
              <p>{row.action}</p>
              <div>
                {row.primaryHref ? (
                  <Link href={row.primaryHref} className="btn btn-primary btn-sm">
                    {row.primaryLabel ?? "Open"}
                  </Link>
                ) : null}
                {row.secondaryHref ? (
                  <Link href={row.secondaryHref} className="btn btn-soft btn-sm">
                    {row.secondaryLabel ?? "Open"}
                  </Link>
                ) : null}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function DriftPage() {
  const [activeTab, setActiveTab] = useState<DriftTab>("provider");
  const [showZero, setShowZero] = useState(false);
  const providerQuery = useDriftStatus();
  const judgeQuery = useJudgeHealth(showZero, { enabled: activeTab === "judge" });
  const currentOutcomeQuery = useOutcomeSummary(7);
  const baselineOutcomeQuery = useOutcomeSummary(30);

  const providerDriftRows = useMemo(
    () => providerRows(providerQuery.data?.alerts ?? []),
    [providerQuery.data?.alerts],
  );

  const judgeDriftRows = useMemo(() => {
    const data = judgeQuery.data;
    return [
      ...verdictRows(data?.verdict_drift ?? []),
      ...dimensionRows(data?.dimension_drift ?? []),
    ].sort((a, b) => {
      const rank: Record<Tone, number> = { critical: 0, warn: 1, neutral: 2, ok: 3 };
      return rank[a.tone] - rank[b.tone];
    });
  }, [judgeQuery.data]);

  const outcomeDriftRows = useMemo(
    () => outcomeRows(currentOutcomeQuery.data, baselineOutcomeQuery.data),
    [currentOutcomeQuery.data, baselineOutcomeQuery.data],
  );

  const currentRows = activeTab === "provider" ? providerDriftRows : activeTab === "judge" ? judgeDriftRows : outcomeDriftRows;
  const activeLoading = activeTab === "provider" ? providerQuery.isLoading : activeTab === "judge" ? judgeQuery.isLoading || judgeQuery.isFetching : currentOutcomeQuery.isLoading || baselineOutcomeQuery.isLoading;
  const activeError = activeTab === "provider" ? providerQuery.isError : activeTab === "judge" ? judgeQuery.isError : currentOutcomeQuery.isError || baselineOutcomeQuery.isError;
  const judgeSummaryValue = judgeQuery.isError
    ? "Delayed"
    : judgeQuery.data
      ? String(judgeQuery.data.any_breached ? judgeDriftRows.filter((row) => row.tone === "critical" || row.tone === "warn").length : 0)
      : "-";
  const judgeSummarySub = judgeQuery.data
    ? `${judgeQuery.data.window_hours}h calibration window`
    : activeTab === "judge"
      ? "Loading judge diagnostics"
      : "Open judge tab to load";

  return (
    <div className="drift-workspace">
      <section className="module-hero drift-hero">
        <div className="module-hero-header">
          <div>
            <div className="module-eyebrow">
              <Activity aria-hidden="true" />
              What changed and what to test
            </div>
            <h1>Drift</h1>
            <p>Provider, judge, and business-outcome shifts with baseline, current value, delta, evidence, and replay/golden action.</p>
          </div>
          <button
            type="button"
            onClick={() => {
              void providerQuery.refetch();
              void judgeQuery.refetch();
              void currentOutcomeQuery.refetch();
              void baselineOutcomeQuery.refetch();
            }}
            className="btn btn-soft"
          >
            <RefreshCw aria-hidden="true" />
            Refresh
          </button>
        </div>
      </section>

      <section className="metric-strip" aria-label="Drift summary">
        <SummaryCard label="Provider alerts" value={String(providerQuery.data?.total_alerts ?? 0)} sub={`${providerQuery.data?.critical_count ?? 0} critical, ${providerQuery.data?.warn_count ?? 0} watch`} />
        <SummaryCard label="Judge breaches" value={judgeSummaryValue} sub={judgeSummarySub} />
        <SummaryCard label="Outcome cost" value={usd(currentOutcomeQuery.data?.total_outcome_usd ?? 0)} sub="Current 7d window" />
        <SummaryCard label="Replay targets" value={String(currentRows.length)} sub="Rows with action evidence" />
      </section>

      <section className="drift-tabs" role="tablist" aria-label="Drift tabs">
        {TABS.map((tab) => (
          <TabButton key={tab.id} active={activeTab === tab.id} icon={tab.icon} label={tab.label} onClick={() => setActiveTab(tab.id)} />
        ))}
      </section>

      {activeTab === "judge" ? (
        <label className="drift-zero-toggle">
          <input type="checkbox" checked={showZero} onChange={(event) => setShowZero(event.target.checked)} />
          Show zero-sample dimensions
        </label>
      ) : null}

      {activeError ? (
        <div className="drift-error">
          <BadgeAlert aria-hidden="true" />
          <span>{activeTab === "judge" ? "Judge health is taking longer than expected. Replay and outcome drift remain available." : "Drift data failed to load."}</span>
        </div>
      ) : null}

      {activeLoading ? (
        <section className="panel issue-loading-panel" aria-label="Loading drift rows">
          <RefreshCw aria-hidden="true" />
          <div>
            <strong>{activeTab === "judge" ? "Checking judge health" : "Loading drift rows"}</strong>
            <p className="notif-meta">{activeTab === "judge" ? "Reading calibration drift with a bounded dashboard wait." : "Reading provider, judge, and outcome evidence."}</p>
          </div>
        </section>
      ) : activeError ? null : (
        <DriftTable
          rows={currentRows}
          empty={
            activeTab === "provider"
              ? "No provider drift alerts in the latest run."
              : activeTab === "judge"
                ? "No judge drift rows for this project yet."
                : "No outcome drift rows for the current window."
          }
        />
      )}
    </div>
  );
}
