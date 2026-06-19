"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  CircleDollarSign,
  Copy,
  Download,
  Gauge,
  Landmark,
  LineChart,
  Loader2,
  Play,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  TriangleAlert,
  WalletCards,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { getSavingsSummary, listIssues, type ReplayMode } from "@/lib/api";
import { formatCount, formatDate } from "@/lib/format";
import {
  useBudget,
  useBudgetStatus,
  useCacheSavings,
  useCostByAgent,
  useCostByModel,
  useCostByUser,
  useCostDailyTrend,
  useCostTopCalls,
  useCreateReplayRunFromCall,
  useCreateReplayRunFromIssue,
  useReasoningShare,
  useReplayRuns,
  useUpdateBudget,
} from "@/lib/hooks";
import { replayLabel, severityRank } from "@/lib/issue-format";
import { DEFAULT_VERIFICATION_REPLAY_MODE } from "@/lib/replay-mode";
import type {
  BudgetStatusResponse,
  CostBreakdownItem,
  CostDailyTrendPoint,
  CostTopCallItem,
  IssueItem,
  SavingsSummaryResponse,
} from "@/lib/types";

const DASH = "-";
const WINDOW_OPTIONS = [7, 14, 30, 90] as const;
const TOP_CALL_LIMIT = 12;
const ISSUE_LIMIT = 100;
const REPLAY_LIMIT = 50;

type WindowDays = (typeof WINDOW_OPTIONS)[number];
type CostLens = "all" | "failures" | "spend" | "replay" | "protected" | "budget";
type BreakdownView = "agent" | "model" | "user";
type ActionState = { kind: "success" | "error"; message: string } | null;
type BudgetMessage = { kind: "success" | "error"; text: string } | null;

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function classNames(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}

function moneyOrDash(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? USD.format(value) : DASH;
}

function percentOrDash(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}%` : DASH;
}

function numberOrDash(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString() : DASH;
}

function titleCase(value: string | null | undefined): string {
  const normalized = (value ?? "").trim().replaceAll("_", " ").replaceAll("-", " ");
  if (!normalized) return DASH;
  return normalized.replace(/\b\w/g, (char) => char.toUpperCase());
}

function normalizedMode(value: string | null | undefined): string {
  const normalized = (value ?? "").trim().toLowerCase().replaceAll("-", "_");
  const labels: Record<string, string> = {
    live_sandbox: "Sandbox replay",
    mocked_tool: "Repository replay",
    real_llm: "Managed provider replay",
    shadow: "Shadow comparison",
    stub: "Fixture validation",
  };
  return labels[normalized] ?? titleCase(normalized);
}

function statusLabel(value: string | null | undefined): string {
  const normalized = (value ?? "").trim().toLowerCase();
  const labels: Record<string, string> = {
    covered_failed: "Replay failed",
    no_limit: "No limit",
    not_verified: "Not verified",
    verified_fix: "Verified fix",
  };
  return labels[normalized] ?? titleCase(normalized);
}

function statusTone(value: string | null | undefined): "safe" | "warn" | "danger" | "neutral" {
  const normalized = (value ?? "").trim().toLowerCase();
  if (["ok", "pass", "success", "known", "high", "verified_fix"].includes(normalized)) return "safe";
  if (["warning", "pending", "running", "medium", "estimated", "not_verified"].includes(normalized)) return "warn";
  if (["critical", "fail", "failed", "error", "low", "unknown", "covered_failed"].includes(normalized)) return "danger";
  return "neutral";
}

function isFailedStatus(value: string | null | undefined): boolean {
  const normalized = (value ?? "").trim().toLowerCase();
  return ["failed", "failure", "error", "timeout"].includes(normalized);
}

function issueCost(issue: IssueItem): number | null {
  if (issue.cost_impact_usd > 0) return issue.cost_impact_usd;
  if (issue.blast_radius_usd > 0) return issue.blast_radius_usd;
  return null;
}

function agentLabel(issue: IssueItem): string {
  return issue.affected_agent ?? issue.agent_name ?? "Unknown agent";
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function topCallLabel(call: CostTopCallItem): string {
  return call.model ?? call.provider ?? call.call_type ?? call.call_id;
}

function costConfidenceLabel(confidence: string | null | undefined): string {
  if (!confidence) return DASH;
  return titleCase(confidence);
}

function budgetRiskCopy(status: BudgetStatusResponse | null | undefined): string {
  if (!status) return "Budget telemetry unavailable.";
  if (status.forecast_recommendation) return status.forecast_recommendation;
  if (status.status === "no_limit") return "No monthly spend guardrail configured.";
  return `${status.days_remaining_in_period} days remain in this billing period.`;
}

function KpiButton({
  icon: Icon,
  label,
  value,
  helper,
  active,
  tone = "neutral",
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  helper: string;
  active: boolean;
  tone?: "neutral" | "risk" | "safe";
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={classNames("cost-command-kpi", active && "is-active", `tone-${tone}`)}
      aria-pressed={active}
      onClick={onClick}
    >
      <span className="cost-command-kpi-top">
        <Icon aria-hidden="true" />
        <span>{label}</span>
      </span>
      <strong>{value}</strong>
      <p>{helper}</p>
    </button>
  );
}

function CostBadge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "safe" | "warn" | "danger" | "neutral" }) {
  return <span className={classNames("cost-command-badge", `tone-${tone}`)}>{children}</span>;
}

function CompactEmpty({ children, loading = false }: { children: string; loading?: boolean }) {
  return (
    <div className="cost-command-empty">
      {loading ? <Loader2 className="is-loading" aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
      <span>{children}</span>
    </div>
  );
}

function TrendChart({ points }: { points: CostDailyTrendPoint[] }) {
  const maxCost = Math.max(...points.map((point) => Math.max(point.total_cost_usd, point.failed_cost_usd)), 0);
  const labelEvery = Math.max(1, Math.ceil(points.length / 12));
  if (points.length === 0 || maxCost <= 0) {
    return <CompactEmpty>No cost trend data available in this window.</CompactEmpty>;
  }

  return (
    <div className="cost-command-chart" aria-label="Spend timeline">
      {points.map((point, index) => {
        const totalHeight = Math.max(4, Math.round((point.total_cost_usd / maxCost) * 100));
        const failedHeight = Math.max(point.failed_cost_usd > 0 ? 3 : 0, Math.round((point.failed_cost_usd / maxCost) * 100));
        const showLabel = index % labelEvery === 0 || index === points.length - 1;
        return (
          <div key={`${point.day}-${index}`} className="cost-command-chart-bar" title={`${point.day}: ${moneyOrDash(point.total_cost_usd)} total, ${moneyOrDash(point.failed_cost_usd)} failed`}>
            <span className="cost-command-chart-track" aria-hidden="true">
              <span className="cost-command-chart-total" style={{ height: `${totalHeight}%` }} />
              <span className="cost-command-chart-failed" style={{ height: `${failedHeight}%` }} />
            </span>
            <span className="cost-command-chart-label">{showLabel ? formatDate(point.day) : ""}</span>
          </div>
        );
      })}
    </div>
  );
}

function BreakdownRows({
  items,
  view,
}: {
  items: CostBreakdownItem[];
  view: BreakdownView;
}) {
  const maxCost = Math.max(...items.map((item) => item.total_cost_usd), 0);
  if (items.length === 0 || maxCost <= 0) {
    return <CompactEmpty>No breakdown data available in this window.</CompactEmpty>;
  }

  return (
    <div className="cost-command-breakdown-list">
      {items.slice(0, 10).map((item) => {
        const width = Math.max(4, Math.round((item.total_cost_usd / maxCost) * 100));
        const href = view === "agent"
          ? `/issues?agent_name=${encodeURIComponent(item.key)}`
          : `/calls?${view === "model" ? "model" : "user_id"}=${encodeURIComponent(item.key)}`;
        return (
          <Link key={`${view}-${item.key || "unknown"}`} href={href} className="cost-command-breakdown-row">
            <span className="cost-command-breakdown-main">
              <strong>{item.key || `Unknown ${view}`}</strong>
              <span>{formatCount(item.call_count)} calls / {formatCount(item.failed_call_count)} failed</span>
            </span>
            <span className="cost-command-breakdown-meter" aria-hidden="true">
              <span style={{ width: `${width}%` }} />
            </span>
            <span className="cost-command-breakdown-money">{moneyOrDash(item.total_cost_usd)}</span>
          </Link>
        );
      })}
    </div>
  );
}

function buildReportText({
  windowDays,
  failureCost,
  aiSpend,
  replaySpend,
  preventedImpact,
  budgetStatus,
  topIssue,
  topCall,
}: {
  windowDays: WindowDays;
  failureCost: number | null;
  aiSpend: number | null;
  replaySpend: number | null;
  preventedImpact: number | null;
  budgetStatus: BudgetStatusResponse | null | undefined;
  topIssue: IssueItem | undefined;
  topCall: CostTopCallItem | undefined;
}) {
  return [
    `Zroky cost report (${windowDays}d)`,
    `Failed runs wasted: ${moneyOrDash(failureCost)}`,
    `AI spend: ${moneyOrDash(aiSpend)}`,
    `Replay verification spend: ${moneyOrDash(replaySpend)}`,
    `Projected prevented impact: ${moneyOrDash(preventedImpact)}`,
    `Budget status: ${budgetStatus ? statusLabel(budgetStatus.status) : DASH}`,
    `Top issue: ${topIssue ? `${topIssue.title} (${moneyOrDash(issueCost(topIssue))})` : DASH}`,
    `Top call: ${topCall ? `${topCall.call_id} (${moneyOrDash(topCall.cost_usd)})` : DASH}`,
  ].join("\n");
}

export default function CostOverviewPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [windowDays, setWindowDays] = useState<WindowDays>(30);
  const [activeLens, setActiveLens] = useState<CostLens>("all");
  const [breakdownView, setBreakdownView] = useState<BreakdownView>("agent");
  const [actionState, setActionState] = useState<ActionState>(null);
  const [budgetLimit, setBudgetLimit] = useState("");
  const [budgetThreshold, setBudgetThreshold] = useState("80");
  const [budgetMessage, setBudgetMessage] = useState<BudgetMessage>(null);

  const topCallHours = Math.min(windowDays * 24, 720);
  const trendQuery = useCostDailyTrend(windowDays);
  const agentQuery = useCostByAgent(windowDays);
  const modelQuery = useCostByModel(windowDays);
  const userQuery = useCostByUser(windowDays);
  const topCallsQuery = useCostTopCalls(TOP_CALL_LIMIT, topCallHours);
  const reasoningQuery = useReasoningShare(windowDays);
  const cacheQuery = useCacheSavings(windowDays);
  const budgetQuery = useBudget();
  const budgetStatusQuery = useBudgetStatus();
  const replayRunsQuery = useReplayRuns({ limit: REPLAY_LIMIT }, {
    refetchInterval: (query) =>
      query.state.data?.items.some((run) => run.status === "pending" || run.status === "running")
        ? 4_000
        : false,
  });
  const issuesQuery = useQuery({
    queryKey: ["issues", "cost-command", "open", ISSUE_LIMIT],
    queryFn: ({ signal }) => listIssues({ status: "open", limit: ISSUE_LIMIT }, signal),
    staleTime: 30_000,
  });
  const savingsQuery = useQuery<SavingsSummaryResponse>({
    queryKey: ["savings", "cost-command", windowDays],
    queryFn: ({ signal }) => getSavingsSummary(windowDays, signal),
    staleTime: 30_000,
  });
  const updateBudgetMutation = useUpdateBudget();

  const callReplayMutation = useCreateReplayRunFromCall({
    onSuccess: (run) => {
      setActionState({ kind: "success", message: `Replay created from call: ${run.id}` });
      void queryClient.invalidateQueries({ queryKey: ["replay-runs"] });
      router.push(`/replay/${run.id}`);
    },
    onError: (error) => setActionState({ kind: "error", message: error instanceof Error ? error.message : "Replay from call failed." }),
  });
  const issueReplayMutation = useCreateReplayRunFromIssue({
    onSuccess: (run) => {
      setActionState({ kind: "success", message: `Replay created from issue: ${run.id}` });
      void queryClient.invalidateQueries({ queryKey: ["replay-runs"] });
      router.push(`/replay/${run.id}`);
    },
    onError: (error) => setActionState({ kind: "error", message: error instanceof Error ? error.message : "Replay from issue failed." }),
  });

  useEffect(() => {
    if (!budgetQuery.data) return;
    setBudgetLimit(budgetQuery.data.monthly_limit_usd != null ? String(budgetQuery.data.monthly_limit_usd) : "");
    setBudgetThreshold(String(budgetQuery.data.threshold_percentage ?? 80));
  }, [budgetQuery.data]);

  const issues = useMemo(() => issuesQuery.data?.items ?? [], [issuesQuery.data?.items]);
  const trendPoints = trendQuery.data?.points ?? [];
  const savings = savingsQuery.data ?? null;
  const topCalls = topCallsQuery.data?.items ?? [];
  const replayRuns = replayRunsQuery.data?.items ?? [];

  const failureRows = useMemo(() => {
    return [...issues]
      .filter((issue) => issueCost(issue) != null)
      .sort((a, b) => {
        const costDelta = (issueCost(b) ?? 0) - (issueCost(a) ?? 0);
        if (costDelta !== 0) return costDelta;
        return severityRank(b.severity) - severityRank(a.severity);
      })
      .slice(0, 12);
  }, [issues]);

  const visibleIssueCost = failureRows.length > 0
    ? failureRows.reduce((sum, issue) => sum + (issueCost(issue) ?? 0), 0)
    : null;
  const trendSpend = trendPoints.length > 0
    ? trendPoints.reduce((sum, point) => sum + point.total_cost_usd, 0)
    : null;
  const trendFailedSpend = trendPoints.length > 0
    ? trendPoints.reduce((sum, point) => sum + point.failed_cost_usd, 0)
    : null;
  const aiSpend = trendSpend;
  const failureCost = savings?.cumulative_wasted_usd ?? visibleIssueCost;
  const failedSpendShare = aiSpend && trendFailedSpend != null ? (trendFailedSpend / aiSpend) * 100 : null;
  const replayRows = replayRuns
    .filter((run) => run.summary.replay_cost_usd != null || run.summary.cost_delta_usd != null)
    .slice(0, 10);
  const replaySpend = replayRows.length > 0
    ? replayRows.reduce((sum, run) => sum + (run.summary.replay_cost_usd ?? 0), 0)
    : null;
  const preventedImpact = savings?.projected_averted_usd ?? null;
  const protectedNet = preventedImpact != null && replaySpend != null ? preventedImpact - replaySpend : null;
  const budgetStatus = budgetStatusQuery.data ?? null;
  const budgetPercent = budgetStatus?.percent_used ?? null;
  const cacheSavings = cacheQuery.data?.total_cache_savings_usd ?? null;
  const reasoningShare = reasoningQuery.data?.reasoning_share_percent ?? null;
  const breakdownItems = (
    breakdownView === "agent" ? agentQuery.data?.items :
      breakdownView === "model" ? modelQuery.data?.items :
        userQuery.data?.items
  ) ?? [];

  const loadProblems = [
    issuesQuery.error ? "open issues" : null,
    trendQuery.error ? "cost trend" : null,
    agentQuery.error ? "agent cost" : null,
    modelQuery.error ? "model cost" : null,
    userQuery.error ? "user cost" : null,
    topCallsQuery.error ? "top calls" : null,
    replayRunsQuery.error ? "replay runs" : null,
    savingsQuery.error ? "savings" : null,
    budgetQuery.error ? "budget config" : null,
    budgetStatusQuery.error ? "budget status" : null,
  ].filter(Boolean);
  const isRefreshing = [
    issuesQuery,
    trendQuery,
    agentQuery,
    modelQuery,
    userQuery,
    topCallsQuery,
    replayRunsQuery,
    savingsQuery,
    budgetQuery,
    budgetStatusQuery,
    reasoningQuery,
    cacheQuery,
  ].some((query) => query.isFetching);

  const focusCopy = useMemo(() => {
    if (activeLens === "failures") return { title: "Failure cost focus", body: "Open issues are sorted by money at risk, with direct replay dispatch for unverified failures." };
    if (activeLens === "spend") return { title: "Spend focus", body: "Trend, top calls, and breakdowns show where provider cost is actually coming from." };
    if (activeLens === "replay") return { title: "Replay ROI focus", body: "Replay spend is compared against projected repeat impact so verification cost has business context." };
    if (activeLens === "protected") return { title: "Protected impact focus", body: "Projected prevented impact stays separate from booked savings and visible spend." };
    if (activeLens === "budget") return { title: "Budget focus", body: "Budget status and inline guardrails stay tied to the live budget API." };
    return { title: "Cost-risk evidence", body: "Use the cards as supporting lenses, then drill into the exact issue, call, replay run, or guardrail." };
  }, [activeLens]);

  const reportPayload = {
    window_days: windowDays,
    generated_at: new Date().toISOString(),
    totals: {
      failed_runs_wasted_usd: failureCost,
      ai_spend_usd: aiSpend,
      replay_spend_usd: replaySpend,
      projected_prevented_impact_usd: preventedImpact,
      projected_net_protected_usd: protectedNet,
      failed_spend_share_percent: failedSpendShare,
    },
    pricing_trust: {
      cost_confidence: trendQuery.data?.cost_confidence ?? null,
      confidence_reason: trendQuery.data?.confidence_reason ?? null,
      pricing_source: trendQuery.data?.pricing_source ?? null,
      pricing_last_updated_at: trendQuery.data?.pricing_last_updated_at ?? null,
      pricing_age_days: trendQuery.data?.pricing_age_days ?? null,
    },
    budget: budgetStatus,
    top_issue: failureRows[0] ?? null,
    top_call: topCalls[0] ?? null,
  };

  async function refreshAll() {
    setActionState(null);
    const results = await Promise.allSettled([
      issuesQuery.refetch(),
      trendQuery.refetch(),
      agentQuery.refetch(),
      modelQuery.refetch(),
      userQuery.refetch(),
      topCallsQuery.refetch(),
      replayRunsQuery.refetch(),
      savingsQuery.refetch(),
      budgetQuery.refetch(),
      budgetStatusQuery.refetch(),
      reasoningQuery.refetch(),
      cacheQuery.refetch(),
    ]);
    const failed = results.filter((result) => result.status === "rejected").length;
    setActionState(failed > 0
      ? { kind: "error", message: `Refresh completed with ${failed} failed source${failed === 1 ? "" : "s"}.` }
      : { kind: "success", message: "Cost-risk evidence refreshed." });
  }

  async function copyReport() {
    try {
      await navigator.clipboard.writeText(buildReportText({
        windowDays,
        failureCost,
        aiSpend,
        replaySpend,
        preventedImpact,
        budgetStatus,
        topIssue: failureRows[0],
        topCall: topCalls[0],
      }));
      setActionState({ kind: "success", message: "Cost report copied." });
    } catch {
      setActionState({ kind: "error", message: "Clipboard copy failed." });
    }
  }

  function exportReport() {
    downloadJson(`zroky-cost-report-${windowDays}d.json`, reportPayload);
    setActionState({ kind: "success", message: "Cost report exported." });
  }

  async function copyValue(value: string, successMessage: string) {
    try {
      await navigator.clipboard.writeText(value);
      setActionState({ kind: "success", message: successMessage });
    } catch {
      setActionState({ kind: "error", message: "Clipboard copy failed." });
    }
  }

  function runReplayFromIssue(issue: IssueItem) {
    setActionState(null);
    issueReplayMutation.mutate({
      issueId: issue.id,
      payload: { replay_mode: DEFAULT_VERIFICATION_REPLAY_MODE as ReplayMode },
    });
  }

  function runReplayFromCall(callId: string) {
    setActionState(null);
    callReplayMutation.mutate({
      callId,
      payload: { replay_mode: DEFAULT_VERIFICATION_REPLAY_MODE as ReplayMode },
    });
  }

  function saveBudget(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBudgetMessage(null);

    const parsedLimit = budgetLimit.trim() === "" ? null : Number(budgetLimit);
    const parsedThreshold = Number(budgetThreshold);
    if (parsedLimit != null && (!Number.isFinite(parsedLimit) || parsedLimit < 0)) {
      setBudgetMessage({ kind: "error", text: "Monthly budget must be a positive number or blank." });
      return;
    }
    if (!Number.isFinite(parsedThreshold) || parsedThreshold < 1 || parsedThreshold > 100) {
      setBudgetMessage({ kind: "error", text: "Alert threshold must be between 1 and 100." });
      return;
    }

    updateBudgetMutation.mutate(
      {
        monthly_limit_usd: parsedLimit,
        threshold_percentage: parsedThreshold,
      },
      {
        onSuccess: () => {
          setBudgetMessage({ kind: "success", text: "Budget guardrail saved." });
          void budgetStatusQuery.refetch();
        },
        onError: (error) => {
          setBudgetMessage({ kind: "error", text: error instanceof Error ? error.message : "Budget save failed." });
        },
      },
    );
  }

  return (
    <div className="cost-command">
      <section className="cost-command-hero">
        <div className="cost-command-hero-copy">
          <div className="cost-command-eyebrow">
            <CircleDollarSign aria-hidden="true" />
            Cost of failure
          </div>
          <h1>Cost Risk</h1>
          <p>See where AI failures burn money, prove which replays protected spend, and enforce live budget guardrails before repeat regressions ship.</p>
        </div>
        <div className="cost-command-hero-actions">
          <button type="button" className="btn btn-soft" onClick={() => void refreshAll()} disabled={isRefreshing}>
            <RefreshCw aria-hidden="true" />
            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
          <button type="button" className="btn btn-soft" onClick={() => void copyReport()}>
            <Copy aria-hidden="true" />
            Copy report
          </button>
          <button type="button" className="btn btn-primary" onClick={exportReport}>
            <Download aria-hidden="true" />
            Export JSON
          </button>
        </div>
        <div className="cost-command-hero-proof" aria-label="Cost proof summary">
          <span>top leak: {failureRows[0]?.failure_code ?? topCalls[0]?.error_code ?? DASH}</span>
          <span>price trust: {costConfidenceLabel(trendQuery.data?.cost_confidence)}</span>
          <span>window: {windowDays}d</span>
        </div>
      </section>

      {actionState ? (
        <div className={classNames("cost-command-action", actionState.kind === "error" && "is-error")} role="status">
          {actionState.message}
        </div>
      ) : null}

      {loadProblems.length > 0 ? (
        <div className="cost-command-action is-error" role="status">
          Some live sources are unavailable: {loadProblems.join(", ")}.
        </div>
      ) : null}

      <section className="cost-command-toolbar" aria-label="Cost controls">
        <div>
          <h2>Live window</h2>
          <p>{topCallHours / 24 === windowDays ? `${windowDays} day window` : `${windowDays} day window, top calls capped at 30 days by backend guardrail`}.</p>
        </div>
        <div className="cost-command-window-tabs" role="tablist" aria-label="Cost window">
          {WINDOW_OPTIONS.map((days) => (
            <button
              key={days}
              type="button"
              className={days === windowDays ? "is-active" : ""}
              onClick={() => {
                setWindowDays(days);
                setActionState(null);
              }}
            >
              {days}d
            </button>
          ))}
        </div>
      </section>

      <section className="cost-command-kpis" aria-label="Cost overview">
        <KpiButton
          icon={TriangleAlert}
          label="Failed runs wasted"
          value={moneyOrDash(failureCost)}
          helper={savings ? `${formatCount(savings.affected_calls)} affected calls in this window.` : `${moneyOrDash(visibleIssueCost)} visible open issue impact.`}
          active={activeLens === "failures"}
          tone="risk"
          onClick={() => setActiveLens(activeLens === "failures" ? "all" : "failures")}
        />
        <KpiButton
          icon={LineChart}
          label="AI spend"
          value={moneyOrDash(aiSpend)}
          helper={`${percentOrDash(failedSpendShare)} of provider spend is failed-call cost.`}
          active={activeLens === "spend"}
          onClick={() => setActiveLens(activeLens === "spend" ? "all" : "spend")}
        />
        <KpiButton
          icon={ShieldCheck}
          label="Replay spend"
          value={moneyOrDash(replaySpend)}
          helper={`${formatCount(replayRows.length)} verification runs loaded.`}
          active={activeLens === "replay"}
          onClick={() => setActiveLens(activeLens === "replay" ? "all" : "replay")}
        />
        <KpiButton
          icon={CheckCircle2}
          label="Projected prevented impact"
          value={moneyOrDash(preventedImpact)}
          helper={`${moneyOrDash(protectedNet)} projected net after replay spend.`}
          active={activeLens === "protected"}
          tone="safe"
          onClick={() => setActiveLens(activeLens === "protected" ? "all" : "protected")}
        />
        <KpiButton
          icon={Gauge}
          label="Budget risk"
          value={budgetStatus ? statusLabel(budgetStatus.status) : DASH}
          helper={budgetStatus?.percent_used != null ? `${percentOrDash(budgetPercent)} of monthly limit used.` : budgetRiskCopy(budgetStatus)}
          active={activeLens === "budget"}
          tone={budgetStatus?.status === "ok" ? "safe" : "risk"}
          onClick={() => setActiveLens(activeLens === "budget" ? "all" : "budget")}
        />
      </section>

      <section className="cost-command-focus" aria-label="Cost focus">
        <div>
          <span>Current lens</span>
          <strong>{focusCopy.title}</strong>
          <p>{focusCopy.body}</p>
        </div>
        <Link href="/issues?sort=cost" className="btn btn-soft btn-sm">
          View costly failures
          <ArrowRight aria-hidden="true" />
        </Link>
      </section>

      <section className={classNames("cost-command-section", activeLens === "spend" && "is-focused")}>
        <header className="cost-command-section-header">
          <div>
            <h2>Spend timeline</h2>
            <p>Total provider spend with failed-call spend highlighted.</p>
          </div>
          <CostBadge tone={statusTone(trendQuery.data?.cost_confidence)}>
            confidence: {costConfidenceLabel(trendQuery.data?.cost_confidence)}
          </CostBadge>
        </header>
        {trendQuery.isLoading ? <CompactEmpty loading>Loading spend trend...</CompactEmpty> : <TrendChart points={trendPoints} />}
      </section>

      <section className="cost-command-grid-two">
        <section className={classNames("cost-command-section", activeLens === "failures" && "is-focused")}>
          <header className="cost-command-section-header">
            <div>
              <h2>Cost of failure</h2>
              <p>Open issues sorted by visible business impact. Run replay directly from each unverified issue.</p>
            </div>
          </header>
          {issuesQuery.isLoading ? (
            <CompactEmpty loading>Loading failure cost data...</CompactEmpty>
          ) : failureRows.length === 0 ? (
            <CompactEmpty>No failure cost data yet. Link outcomes or capture failed calls to estimate cost of failure.</CompactEmpty>
          ) : (
            <div className="cost-command-table-wrap">
              <table className="cost-command-table">
                <thead>
                  <tr>
                    <th>Issue</th>
                    <th>Agent</th>
                    <th>Calls</th>
                    <th>Cost</th>
                    <th>Proof</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {failureRows.map((issue) => (
                    <tr key={issue.id}>
                      <td data-label="Issue">
                        <div className="cost-command-primary-cell">
                          <Link href={`/issues/${issue.id}`}>{issue.title}</Link>
                          <span>{issue.failure_code} / {issue.severity.toUpperCase()}</span>
                        </div>
                      </td>
                      <td data-label="Agent">{agentLabel(issue)}</td>
                      <td data-label="Calls">{numberOrDash(issue.occurrence_count)}</td>
                      <td data-label="Cost">{moneyOrDash(issueCost(issue))}</td>
                      <td data-label="Proof"><CostBadge tone={statusTone(issue.replay_coverage_status)}>{replayLabel(issue.replay_coverage_status)}</CostBadge></td>
                      <td data-label="Action">
                        <div className="cost-command-row-actions">
                          <Link href={`/issues/${issue.id}`} className="btn btn-soft btn-sm">View issue</Link>
                          {issue.replay_coverage_status === "verified_fix" ? null : (
                            <button
                              type="button"
                              className="btn btn-primary btn-sm"
                              onClick={() => runReplayFromIssue(issue)}
                              disabled={issueReplayMutation.isPending}
                            >
                              <Play aria-hidden="true" />
                              Run replay
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className={classNames("cost-command-section", activeLens === "replay" && "is-focused")}>
          <header className="cost-command-section-header">
            <div>
              <h2>Replay ROI</h2>
              <p>Verification spend compared with projected repeat impact avoided.</p>
            </div>
          </header>
          <div className="cost-command-roi-grid">
            <div>
              <span>Replay cost</span>
              <strong>{moneyOrDash(replaySpend)}</strong>
            </div>
            <div>
              <span>Projected protected</span>
              <strong>{moneyOrDash(preventedImpact)}</strong>
            </div>
            <div>
              <span>Projected net</span>
              <strong>{moneyOrDash(protectedNet)}</strong>
            </div>
          </div>
          {replayRows.length === 0 ? (
            <CompactEmpty>No replay spend data available yet.</CompactEmpty>
          ) : (
            <div className="cost-command-table-wrap compact">
              <table className="cost-command-table">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Mode</th>
                    <th>Status</th>
                    <th>Replay cost</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {replayRows.map((run) => (
                    <tr key={run.id}>
                      <td data-label="Run"><Link href={`/replay/${run.id}`}>{run.id}</Link></td>
                      <td data-label="Mode">{normalizedMode(run.replay_mode || run.executor_replay_mode)}</td>
                      <td data-label="Status"><CostBadge tone={statusTone(run.summary.verification_status || run.status)}>{statusLabel(run.summary.verification_status || run.status)}</CostBadge></td>
                      <td data-label="Replay cost">{moneyOrDash(run.summary.replay_cost_usd)}</td>
                      <td data-label="Action"><Link href={`/replay/${run.id}`} className="btn btn-soft btn-sm">View replay</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </section>

      <section className={classNames("cost-command-section", activeLens === "spend" && "is-focused")}>
        <header className="cost-command-section-header">
          <div>
            <h2>Top expensive calls</h2>
            <p>Individual calls driving spend. Failed calls can be replayed directly.</p>
          </div>
          <CostBadge>{topCallHours}h source window</CostBadge>
        </header>
        {topCallsQuery.isLoading ? (
          <CompactEmpty loading>Loading top calls...</CompactEmpty>
        ) : topCalls.length === 0 ? (
          <CompactEmpty>No expensive calls recorded in this window.</CompactEmpty>
        ) : (
          <div className="cost-command-table-wrap">
            <table className="cost-command-table">
              <thead>
                <tr>
                  <th>Call</th>
                  <th>Agent</th>
                  <th>Status</th>
                  <th>Error</th>
                  <th>Cost</th>
                  <th>Trust</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {topCalls.map((call) => (
                  <tr key={call.call_id}>
                    <td data-label="Call">
                      <div className="cost-command-primary-cell">
                        <Link href={`/calls/${call.call_id}`}>{topCallLabel(call)}</Link>
                        <span>{call.call_id}</span>
                      </div>
                    </td>
                    <td data-label="Agent">{call.agent_name ?? "Unknown agent"}</td>
                    <td data-label="Status"><CostBadge tone={statusTone(call.status)}>{statusLabel(call.status)}</CostBadge></td>
                    <td data-label="Error">{call.error_code ?? DASH}</td>
                    <td data-label="Cost">{moneyOrDash(call.cost_usd)}</td>
                    <td data-label="Trust">{costConfidenceLabel(call.cost_confidence)}</td>
                    <td data-label="Action">
                      <div className="cost-command-row-actions">
                        <Link href={`/calls/${call.call_id}`} className="btn btn-soft btn-sm">View call</Link>
                        <button type="button" className="btn btn-soft btn-sm" onClick={() => void copyValue(call.call_id, "Call ID copied.")}>
                          <Copy aria-hidden="true" />
                          Copy ID
                        </button>
                        {isFailedStatus(call.status) ? (
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            onClick={() => runReplayFromCall(call.call_id)}
                            disabled={callReplayMutation.isPending}
                          >
                            <Play aria-hidden="true" />
                            Replay
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="cost-command-grid-two">
        <section className="cost-command-section">
          <header className="cost-command-section-header">
            <div>
              <h2>Cost breakdown</h2>
              <p>Switch between agent, model, and user spend without leaving the page.</p>
            </div>
            <div className="cost-command-mini-tabs" role="tablist" aria-label="Breakdown type">
              {(["agent", "model", "user"] as const).map((view) => (
                <button
                  key={view}
                  type="button"
                  className={breakdownView === view ? "is-active" : ""}
                  onClick={() => setBreakdownView(view)}
                >
                  {titleCase(view)}
                </button>
              ))}
            </div>
          </header>
          <BreakdownRows items={breakdownItems} view={breakdownView} />
        </section>

        <section className="cost-command-section">
          <header className="cost-command-section-header">
            <div>
              <h2>Cost trust</h2>
              <p>Pricing confidence and optimization signals from live analytics endpoints.</p>
            </div>
          </header>
          <div className="cost-command-trust-grid">
            <div>
              <span>Cost confidence</span>
              <strong>{costConfidenceLabel(trendQuery.data?.cost_confidence)}</strong>
              <p>{trendQuery.data?.confidence_reason ?? "Provider pricing source did not return a reason."}</p>
            </div>
            <div>
              <span>Pricing age</span>
              <strong>{trendQuery.data?.pricing_age_days != null ? `${trendQuery.data.pricing_age_days}d` : DASH}</strong>
              <p>{trendQuery.data?.pricing_source ?? trendQuery.data?.pricing_last_updated_at ?? "Pricing timestamp unavailable."}</p>
            </div>
            <div>
              <span>Cache savings</span>
              <strong>{moneyOrDash(cacheSavings)}</strong>
              <p>Saved by cache hits in the selected window.</p>
            </div>
            <div>
              <span>Reasoning share</span>
              <strong>{percentOrDash(reasoningShare)}</strong>
              <p>Share of spend attributed to reasoning tokens.</p>
            </div>
          </div>
        </section>
      </section>

      <section className={classNames("cost-command-section", activeLens === "budget" && "is-focused")}>
        <header className="cost-command-section-header">
          <div>
            <h2>Budget guardrails</h2>
            <p>View current spend risk and update the live monthly AI spend guardrail.</p>
          </div>
          <Link href="/settings/billing" className="btn btn-soft btn-sm">
            Billing settings
            <ArrowRight aria-hidden="true" />
          </Link>
        </header>
        <div className="cost-command-budget-layout">
          <div className="cost-command-budget-status">
            <div className="cost-command-budget-ring" style={{ "--budget-progress": `${Math.min(100, Math.max(0, budgetPercent ?? 0))}%` } as React.CSSProperties}>
              <span>{percentOrDash(budgetPercent)}</span>
            </div>
            <div>
              <CostBadge tone={statusTone(budgetStatus?.status)}>{budgetStatus ? statusLabel(budgetStatus.status) : "Unavailable"}</CostBadge>
              <h3>{moneyOrDash(budgetStatus?.spent_usd)} spent of {moneyOrDash(budgetStatus?.limit_usd)}</h3>
              <p>{budgetRiskCopy(budgetStatus)}</p>
            </div>
          </div>
          <form className="cost-command-budget-form" onSubmit={saveBudget}>
            <label>
              <span>Monthly budget USD</span>
              <input
                className="input"
                type="number"
                min="0"
                step="0.01"
                value={budgetLimit}
                onChange={(event) => setBudgetLimit(event.target.value)}
                placeholder="blank for no limit"
                disabled={updateBudgetMutation.isPending}
              />
            </label>
            <label>
              <span>Alert threshold</span>
              <input
                className="input"
                type="number"
                min="1"
                max="100"
                value={budgetThreshold}
                onChange={(event) => setBudgetThreshold(event.target.value)}
                disabled={updateBudgetMutation.isPending}
              />
            </label>
            {budgetMessage ? <p className={budgetMessage.kind === "error" ? "cost-command-form-error" : "cost-command-form-success"}>{budgetMessage.text}</p> : null}
            <button type="submit" className="btn btn-primary" disabled={updateBudgetMutation.isPending}>
              <WalletCards aria-hidden="true" />
              {updateBudgetMutation.isPending ? "Saving..." : "Save budget"}
            </button>
          </form>
        </div>
      </section>

      <section className="cost-command-footer-proof" aria-label="Cost operating model">
        <div>
          <Landmark aria-hidden="true" />
          <strong>Cost operating model</strong>
          <span>failure cost to replay proof to protected impact to budget gate</span>
        </div>
        <div>
          <BarChart3 aria-hidden="true" />
          <strong>Business rule</strong>
          <span>Projected prevented impact is not shown as booked savings until outcomes are linked.</span>
        </div>
        <div>
          <SlidersHorizontal aria-hidden="true" />
          <strong>Live controls</strong>
          <span>Every action routes to a real issue, call, replay run, budget mutation, export, or clipboard event.</span>
        </div>
      </section>
    </div>
  );
}
