"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Activity, BadgeAlert, CircleDollarSign, Gauge, RefreshCw, type LucideIcon } from "lucide-react";

import { useDriftStatus, useJudgeHealth, useOutcomeSummary } from "@/lib/hooks";
import type {
  DimensionDriftView,
  OutcomeSummaryResponse,
  VerdictDriftView,
} from "@/lib/api";
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
  if (tone === "critical") return "border-red-500/30 bg-red-500/10 text-red-300";
  if (tone === "warn") return "border-amber-500/30 bg-amber-500/10 text-amber-300";
  if (tone === "ok") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
  return "border-white/10 bg-white/[0.03] text-slate-300";
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
    primaryHref: "/outcomes",
    primaryLabel: "Outcomes",
    secondaryHref: "/replay",
    secondaryLabel: "Replay",
  }];
}

function TabButton({
  active,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: LucideIcon;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 border-b-2 px-1 pb-3 text-sm font-semibold transition ${
        active
          ? "border-indigo-400 text-white"
          : "border-transparent text-slate-500 hover:text-slate-300"
      }`}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {label}
    </button>
  );
}

function SummaryCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{sub}</p>
    </div>
  );
}

function DriftTable({ rows, empty }: { rows: DriftRow[]; empty: string }) {
  if (rows.length === 0) {
    return (
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-10 text-center">
        <p className="text-sm font-medium text-slate-300">{empty}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-white/[0.06] bg-white/[0.02]">
      <div className="min-w-[1120px]">
        <div className="grid grid-cols-[1.4fr_0.8fr_0.8fr_0.7fr_1fr_1.4fr_1.3fr] gap-3 border-b border-white/[0.06] px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          <span>Change</span>
          <span>Baseline</span>
          <span>Current</span>
          <span>Delta</span>
          <span>Affected</span>
          <span>Evidence</span>
          <span>Recommended action</span>
        </div>
        {rows.map((row) => (
          <div
            key={row.id}
            className="grid grid-cols-[1.4fr_0.8fr_0.8fr_0.7fr_1fr_1.4fr_1.3fr] gap-3 border-b border-white/[0.04] px-4 py-4 text-sm last:border-b-0"
          >
          <div className="min-w-0">
            <span className={`mb-2 inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${toneClass(row.tone)}`}>
              {toneLabel(row.tone)}
            </span>
            <p className="font-semibold text-white">{row.title}</p>
          </div>
          <span className="font-mono text-slate-300">{row.baseline}</span>
          <span className="font-mono text-slate-200">{row.current}</span>
          <span className="font-mono text-slate-200">{row.delta}</span>
          <span className="text-slate-300">{row.affected}</span>
          <span className="text-xs leading-5 text-slate-400">{row.evidence}</span>
          <div className="space-y-2">
            <p className="text-xs leading-5 text-slate-300">{row.action}</p>
            <div className="flex flex-wrap gap-2">
              {row.primaryHref ? (
                <Link href={row.primaryHref} className="rounded-md border border-indigo-400/30 bg-indigo-500/10 px-2 py-1 text-xs font-semibold text-indigo-200 hover:bg-indigo-500/20">
                  {row.primaryLabel ?? "Open"}
                </Link>
              ) : null}
              {row.secondaryHref ? (
                <Link href={row.secondaryHref} className="rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 text-xs font-semibold text-slate-300 hover:bg-white/[0.07]">
                  {row.secondaryLabel ?? "Open"}
                </Link>
              ) : null}
            </div>
          </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function DriftPage() {
  const [activeTab, setActiveTab] = useState<DriftTab>("provider");
  const [showZero, setShowZero] = useState(false);
  const providerQuery = useDriftStatus();
  const judgeQuery = useJudgeHealth(showZero);
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

  const currentRows =
    activeTab === "provider"
      ? providerDriftRows
      : activeTab === "judge"
        ? judgeDriftRows
        : outcomeDriftRows;

  const activeLoading =
    activeTab === "provider"
      ? providerQuery.isLoading
      : activeTab === "judge"
        ? judgeQuery.isLoading
        : currentOutcomeQuery.isLoading || baselineOutcomeQuery.isLoading;

  const activeError =
    activeTab === "provider"
      ? providerQuery.isError
      : activeTab === "judge"
        ? judgeQuery.isError
        : currentOutcomeQuery.isError || baselineOutcomeQuery.isError;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Drift</h1>
          <p className="mt-1 text-sm text-slate-500">Provider, judge, and business-outcome shifts with replay-ready evidence.</p>
        </div>
        <button
          type="button"
          onClick={() => {
            void providerQuery.refetch();
            void judgeQuery.refetch();
            void currentOutcomeQuery.refetch();
            void baselineOutcomeQuery.refetch();
          }}
          className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm font-semibold text-slate-300 hover:bg-white/[0.07]"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Refresh
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <SummaryCard label="Provider alerts" value={String(providerQuery.data?.total_alerts ?? 0)} sub={`${providerQuery.data?.critical_count ?? 0} critical, ${providerQuery.data?.warn_count ?? 0} watch`} />
        <SummaryCard label="Judge breaches" value={String(judgeQuery.data?.any_breached ? judgeDriftRows.filter((row) => row.tone === "critical" || row.tone === "warn").length : 0)} sub={`${judgeQuery.data?.window_hours ?? 0}h calibration window`} />
        <SummaryCard label="Outcome cost" value={usd(currentOutcomeQuery.data?.total_outcome_usd ?? 0)} sub="Current 7d window" />
        <SummaryCard label="Replay targets" value={String(currentRows.length)} sub="Rows with action evidence" />
      </div>

      <div className="border-b border-white/[0.06]">
        <div className="flex flex-wrap gap-6">
          {TABS.map((tab) => (
            <TabButton
              key={tab.id}
              active={activeTab === tab.id}
              icon={tab.icon}
              label={tab.label}
              onClick={() => setActiveTab(tab.id)}
            />
          ))}
        </div>
      </div>

      {activeTab === "judge" ? (
        <label className="inline-flex items-center gap-2 text-xs text-slate-500">
          <input
            type="checkbox"
            checked={showZero}
            onChange={(event) => setShowZero(event.target.checked)}
            className="rounded border-white/20 bg-white/10 text-indigo-500 focus:ring-indigo-500/30"
          />
          Show zero-sample dimensions
        </label>
      ) : null}

      {activeError ? (
        <div className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          <BadgeAlert className="h-4 w-4" aria-hidden="true" />
          Drift data failed to load.
        </div>
      ) : null}

      {activeLoading ? (
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-10 text-center text-sm text-slate-500">
          Loading drift rows...
        </div>
      ) : (
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
