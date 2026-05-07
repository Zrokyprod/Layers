"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { formatCount, formatDate, formatDateTime, formatPercent, formatUsd } from "@/lib/format";
import {
  useCostDailyTrend,
  useCostByModel,
  useCostByUser,
  useCostByAgent,
  useCostTopCalls,
  useCostHourly,
  useReasoningShare,
  useCacheSavings,
  useBudget,
  useBudgetStatus,
  useUpdateBudget,
  useCostForecast,
  useCostAnomalyRisk,
} from "@/lib/hooks";
import { listCalls } from "@/lib/api";
import { budgetSchema, type BudgetFormData } from "@/lib/schemas";
import { StatusPill } from "@/components/status-pill";

const WINDOW_OPTIONS = [7, 14, 30] as const;
type WindowDays = (typeof WINDOW_OPTIONS)[number];

type CostBreakdownItem = { key: string; total_cost_usd: number; call_count: number; failed_call_count: number; failed_cost_usd: number };

function CostShareList({ items }: { items: CostBreakdownItem[] }) {
  const visible = items.slice(0, 8);
  const total = visible.reduce((sum, item) => sum + item.total_cost_usd, 0) || 1;
  return (
    <div className="list">
      {visible.map((item) => {
        const pct = (item.total_cost_usd / total) * 100;
        return (
          <div key={item.key} className="list-row cost-share-row">
            <div className="cost-share-header">
              <strong className="cost-share-key">{item.key}</strong>
              <span className="mono cost-share-val">{formatUsd(item.total_cost_usd)}</span>
            </div>
            <div className="cost-share-track">
              <div className="cost-share-fill" style={{ width: `${pct}%` }} />
            </div>
            <span className="cost-share-meta">
              {pct.toFixed(1)}% · {formatCount(item.call_count)} calls
              {item.failed_call_count > 0 ? ` · ${formatCount(item.failed_call_count)} failed (${formatUsd(item.failed_cost_usd)})` : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}


const SOURCE_LABELS: Record<string, string> = {
  litellm_public: "LiteLLM Public",
  litellm: "LiteLLM",
  manual: "Manual Override",
  openai: "OpenAI",
  anthropic: "Anthropic",
  bedrock: "AWS Bedrock",
  vertex: "Google Vertex",
};

function formatAgeDays(days: number | null): string {
  if (days == null) return "—";
  if (days === 0) return "< 1 day";
  if (days === 1) return "1 day";
  return `${days} days`;
}

function formatPricingSource(source: string | null): string {
  if (!source) return "—";
  return SOURCE_LABELS[source] ?? source;
}

function getMaxValue(points: Array<{ value: number }>): number {
  const max = points.reduce((running, point) => Math.max(running, point.value), 0);
  return max <= 0 ? 1 : max;
}

function BudgetStatusCard({
  spent_usd,
  limit_usd,
  percent_used,
  days_remaining_in_period,
  forecast_exhaust_in_days,
  status,
  forecast_risk_level,
  forecast_recommendation,
}: {
  spent_usd: number;
  limit_usd: number | null;
  percent_used: number | null;
  days_remaining_in_period: number;
  forecast_exhaust_in_days: number | null;
  status: "ok" | "warning" | "critical" | "no_limit";
  forecast_risk_level: string;
  forecast_recommendation: string;
}) {
  const barPct = Math.min(percent_used ?? 0, 100);
  const barColor =
    status === "critical" ? "#ef4444" : status === "warning" ? "#f59e0b" : "#22c55e";

  return (
    <article className="panel">
      <header className="panel-header">
        <div>
          <h3>Budget Status</h3>
          <p>Current-month spend vs. monthly limit.</p>
        </div>
        <StatusPill value={status} />
      </header>

      <div className="budget-status-body">
        <div className="budget-meta-row">
          <span className="mono">{formatUsd(spent_usd)} spent</span>
          <span className="mono">
            {limit_usd != null ? `${formatUsd(limit_usd)} limit` : "No limit set"}
          </span>
        </div>
        {limit_usd != null && (
          <div className="budget-track">
            <div
              className="budget-fill"
              style={{ width: `${barPct}%`, background: barColor }}
            />
          </div>
        )}
        {percent_used != null && (
          <p className="hint">
            {formatPercent(percent_used)} used · {days_remaining_in_period}d remaining in period
          </p>
        )}
      </div>

      {forecast_exhaust_in_days != null && (
          <p className={`hint${forecast_exhaust_in_days <= 3 ? " cost-forecast-warning" : ""}`}>
          Forecast exhaust in {forecast_exhaust_in_days}d · Risk:{" "}
          <strong>{forecast_risk_level}</strong>
        </p>
      )}
      <p className="hint">{forecast_recommendation}</p>
    </article>
  );
}

export default function CostPage() {
  const [windowDays, setWindowDays] = useState<WindowDays>(14);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [agentDailyTrend, setAgentDailyTrend] = useState<Array<{ day: string; total_cost_usd: number; call_count: number }>>([]);
  const [isFetchingAgentTrend, setIsFetchingAgentTrend] = useState(false);
  const [comparePrev, setComparePrev] = useState(false);

  const dailyTrend = useCostDailyTrend(windowDays);
  const combinedTrend = useCostDailyTrend(windowDays * 2);
  const byModel = useCostByModel(windowDays);
  const byUser = useCostByUser(windowDays);
  const byAgent = useCostByAgent(windowDays);
  const topCallsHours = windowDays * 24;
  const topCalls = useCostTopCalls(10, topCallsHours);
  const reasoning = useReasoningShare(14);
  const cacheSavings = useCacheSavings(14);
  const budget = useBudget();
  const budgetStatus = useBudgetStatus();
  const updateBudget = useUpdateBudget();
  const forecast = useCostForecast(4);
  const anomalyRisk = useCostAnomalyRisk();

  const [hourlyDayKey, setHourlyDayKey] = useState<string | null>(null);
  const hourlyHours = 48;
  const hourly = useCostHourly(hourlyHours);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<BudgetFormData>({
    resolver: zodResolver(budgetSchema),
    defaultValues: {
      monthlyLimit: budget.data?.monthly_limit_usd != null ? String(budget.data.monthly_limit_usd) : "",
      threshold: String(budget.data?.threshold_percentage ?? "80"),
    },
  });

  useEffect(() => {
    if (budget.data) {
      reset({
        monthlyLimit: budget.data.monthly_limit_usd != null ? String(budget.data.monthly_limit_usd) : "",
        threshold: String(budget.data.threshold_percentage ?? "80"),
      });
    }
  }, [budget.data, reset]);

  const loading =
    dailyTrend.isLoading ||
    byModel.isLoading ||
    byUser.isLoading ||
    byAgent.isLoading ||
    topCalls.isLoading ||
    reasoning.isLoading ||
    cacheSavings.isLoading ||
    budget.isLoading;

  const error =
    dailyTrend.error?.message ??
    byModel.error?.message ??
    byUser.error?.message ??
    byAgent.error?.message ??
    topCalls.error?.message ??
    reasoning.error?.message ??
    cacheSavings.error?.message ??
    budget.error?.message ??
    null;

  const trendBars = useMemo(() => {
    const points = (dailyTrend.data?.points ?? []).map((point) => ({
      label: point.day,
      value: point.total_cost_usd,
      count: point.call_count,
      failedCost: point.failed_cost_usd,
      failedCount: point.failed_call_count,
    }));

    const max = getMaxValue(points);
    return points.map((point) => ({
      ...point,
      height: Math.max(4, Math.round((point.value / max) * 118)),
    }));
  }, [dailyTrend.data]);

  const comparePeriods = useMemo(() => {
    const pts = combinedTrend.data?.points ?? null;
    if (!pts || pts.length < windowDays * 2) return null;
    const split = pts.length - windowDays;
    const prev = pts.slice(split - windowDays, split).map((p) => ({ label: p.day, value: p.total_cost_usd }));
    const cur = pts.slice(split).map((p) => ({ label: p.day, value: p.total_cost_usd }));
    return { prev, cur };
  }, [combinedTrend.data, windowDays]);

  const agentBars = useMemo(() => {
    if (!agentDailyTrend || agentDailyTrend.length === 0) return [] as Array<{ day: string; total_cost_usd: number; call_count: number; height: number }>;
    const max = Math.max(...agentDailyTrend.map((p) => p.total_cost_usd), 1);
    return agentDailyTrend.map((p) => ({ ...p, height: Math.max(4, Math.round((p.total_cost_usd / max) * 118)) }));
  }, [agentDailyTrend]);

  const compareBars = useMemo(() => {
    if (!comparePeriods) return null;
    const all = [...comparePeriods.prev.map((p) => p.value), ...comparePeriods.cur.map((p) => p.value)];
    const max = Math.max(...all, 1);
    const prevBars = comparePeriods.prev.map((p) => ({ label: p.label, height: Math.max(4, Math.round((p.value / max) * 80)) }));
    const curBars = comparePeriods.cur.map((p) => ({ label: p.label, height: Math.max(4, Math.round((p.value / max) * 118)) }));
    return { prevBars, curBars };
  }, [comparePeriods]);

  async function fetchAgentTrend(agentName: string | null) {
    if (!agentName) {
      setAgentDailyTrend([]);
      return;
    }
    setIsFetchingAgentTrend(true);
    try {
      const pageSize = 200;
      const maxRows = 2000;
      let offset = 0;
      let total = 0;
      const items: Array<any> = [];
      const end = new Date();
      const start = new Date(Date.now() - windowDays * 24 * 60 * 60 * 1000);
      const startIso = start.toISOString();
      const endIso = end.toISOString();

      while (items.length < maxRows) {
        const page = await listCalls({ agent_name: agentName, start_time: startIso, end_time: endIso, limit: Math.min(pageSize, maxRows - items.length), offset });
        total = page.total;
        items.push(...page.items);
        offset += page.items.length;
        if (page.items.length === 0 || offset >= total) break;
      }

      const byDay: Record<string, { total_cost_usd: number; call_count: number }> = {};
      for (const c of items) {
        const d = new Date(c.created_at).toISOString().slice(0, 10);
        if (!byDay[d]) byDay[d] = { total_cost_usd: 0, call_count: 0 };
        byDay[d].total_cost_usd += Number(c.cost_usd ?? 0);
        byDay[d].call_count += 1;
      }

      const list: Array<{ day: string; total_cost_usd: number; call_count: number }> = [];
      for (let i = windowDays - 1; i >= 0; i--) {
        const dt = new Date();
        dt.setDate(dt.getDate() - i);
        const key = dt.toISOString().slice(0, 10);
        const row = byDay[key] ?? { total_cost_usd: 0, call_count: 0 };
        list.push({ day: key, total_cost_usd: Math.round((row.total_cost_usd + Number.EPSILON) * 1000000) / 1000000, call_count: row.call_count });
      }
      setAgentDailyTrend(list);
    } catch (err) {
      setAgentDailyTrend([]);
    } finally {
      setIsFetchingAgentTrend(false);
    }
  }

  function exportDailyTrendCsv() {
    const rows: string[] = [];
    if (selectedAgent && agentDailyTrend.length > 0) {
      rows.push(["day", "total_cost_usd", "call_count"].join(","));
      for (const p of agentDailyTrend) {
        rows.push([p.day, String(p.total_cost_usd), String(p.call_count)].join(","));
      }
    } else if (dailyTrend.data?.points) {
      rows.push(["day", "total_cost_usd", "total_cost_display", "call_count", "failed_cost_usd", "failed_call_count"].join(","));
      for (const p of dailyTrend.data.points) {
        rows.push([p.day, String(p.total_cost_usd), String(p.total_cost_display), String(p.call_count), String(p.failed_cost_usd), String(p.failed_call_count)].join(","));
      }
    } else {
      return;
    }

    const csv = rows.join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = selectedAgent ? `cost-daily-trend-${selectedAgent}-${windowDays}d.csv` : `cost-daily-trend-${windowDays}d.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  const cacheBars = useMemo(() => {
    const points = (cacheSavings.data?.points ?? []).map((point) => ({
      label: point.day,
      value: point.cache_savings_usd,
    }));
    const max = getMaxValue(points);
    return points.map((point) => ({
      ...point,
      height: Math.max(4, Math.round((point.value / max) * 118)),
    }));
  }, [cacheSavings.data]);

  const hourlyBarsForDay = useMemo(() => {
    if (!hourlyDayKey) return [];
    const points = (hourly.data?.points ?? []).filter((p) =>
      p.hour.startsWith(hourlyDayKey)
    );
    const max = points.reduce((m, p) => Math.max(m, p.total_cost_usd), 0) || 1;
    return points.map((p) => ({
      label: p.hour.slice(11, 16),
      value: p.total_cost_usd,
      count: p.call_count,
      failedCost: p.failed_cost_usd,
      failedCount: p.failed_count,
      height: Math.max(4, Math.round((p.total_cost_usd / max) * 80)),
    }));
  }, [hourly.data, hourlyDayKey]);

  const pricingFreshness = useMemo(() => {
    if (!dailyTrend.data) {
      return {
        pricing_last_updated_at: null as string | null,
        pricing_age_days: null as number | null,
        pricing_source: null as string | null,
        cost_confidence: "unknown",
        confidence_reason: null as string | null,
      };
    }

    const ageDays = typeof dailyTrend.data.pricing_age_days === "number" ? dailyTrend.data.pricing_age_days : null;
    const rawConfidence = (dailyTrend.data.cost_confidence ?? "").toLowerCase();

    let confidence: string;
    if (rawConfidence === "high" || rawConfidence === "stale" || rawConfidence === "degraded") {
      confidence = rawConfidence;
    } else if (typeof ageDays === "number") {
      confidence = ageDays > 14 ? "stale" : "high";
    } else {
      confidence = "unknown";
    }

    return {
      pricing_last_updated_at: dailyTrend.data.pricing_last_updated_at,
      pricing_age_days: ageDays,
      pricing_source: dailyTrend.data.pricing_source ?? null,
      cost_confidence: confidence,
      confidence_reason: dailyTrend.data.confidence_reason ?? null,
    };
  }, [dailyTrend.data]);

  const onSaveBudget = handleSubmit((data: BudgetFormData) => {
    const parsedLimit = data.monthlyLimit.trim() === "" ? null : Number(data.monthlyLimit);
    const parsedThreshold = Number(data.threshold);
    updateBudget.mutate({
      monthly_limit_usd: Number.isFinite(parsedLimit ?? 0) ? parsedLimit : null,
      threshold_percentage: parsedThreshold,
    });
  });

  return (
    <>
      <div className="cost-window-bar">
        <span className="cost-window-label">Window:</span>
        {WINDOW_OPTIONS.map((d) => (
          <button
            key={d}
            type="button"
            className={`cost-window-btn${windowDays === d ? " active" : ""}`}
            onClick={() => setWindowDays(d)}
          >
            {d}d
          </button>
        ))}
      </div>

      <div className="cost-controls">
        <div className="field">
          <label htmlFor="agentSelect">Agent</label>
          <select
            id="agentSelect"
            value={selectedAgent ?? ""}
            onChange={(e) => {
              const v = e.target.value || null;
              setSelectedAgent(v);
              void fetchAgentTrend(v);
            }}
          >
            <option value="">All agents</option>
            {(byAgent.data?.items ?? []).map((it) => (
              <option key={it.key} value={it.key}>{it.key}</option>
            ))}
          </select>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button className="btn btn-soft" type="button" onClick={() => exportDailyTrendCsv()}>
            Export CSV
          </button>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input type="checkbox" checked={comparePrev} onChange={(e) => setComparePrev(e.target.checked)} />
            <span style={{ fontSize: 12 }}>Compare previous period</span>
          </label>
        </div>
      </div>

      {error ? <section className="panel"><p>{error}</p></section> : null}

      {loading ? (
        <section className="panel">
          <div className="loading" />
        </section>
      ) : null}

      {!loading ? (
        <>
          {/* ── Row 1: Budget Status + Budget Config ── */}
          <section className="grid-two">
            {budgetStatus.data ? (
              <BudgetStatusCard {...budgetStatus.data} />
            ) : (
              <article className="panel panel-muted">
                <h3>Budget Status</h3>
                <p className="hint">
                  {budgetStatus.isLoading ? "Loading…" : "No budget configured yet."}
                </p>
              </article>
            )}

            <article className="panel panel-muted">
              <header className="panel-header">
                <div>
                  <h3>Budget Control</h3>
                  <p>Threshold controls alerting behavior.</p>
                </div>
                <StatusPill value={budget.data ? "configured" : "unconfigured"} />
              </header>

              <form className="grid-two" onSubmit={onSaveBudget}>
                <div className="field">
                  <label htmlFor="monthlyLimit">Monthly Limit (USD)</label>
                  <input
                    id="monthlyLimit"
                    {...register("monthlyLimit")}
                    placeholder="2500"
                  />
                  {errors.monthlyLimit && (
                    <span className="field-error">{errors.monthlyLimit.message}</span>
                  )}
                </div>

                <div className="field">
                  <label htmlFor="threshold">Threshold (%)</label>
                  <input
                    id="threshold"
                    {...register("threshold")}
                    placeholder="80"
                  />
                  {errors.threshold && (
                    <span className="field-error">{errors.threshold.message}</span>
                  )}
                </div>

                <div className="actions settings-grid-full">
                  <button className="btn btn-primary" type="submit" disabled={updateBudget.isPending}>
                    {updateBudget.isPending ? "Saving…" : "Save Budget"}
                  </button>
                </div>
              </form>

              <p className="hint">Updated: {formatDateTime(budget.data?.updated_at ?? null)}</p>
            </article>
          </section>

          {/* ── Row 1b: Cost Forecast + Anomaly Risk ── */}
          <section className="grid-two">
            <article className="panel">
              <header className="panel-header">
                <div>
                  <h3>Cost Forecast (Next 4h)</h3>
                  <p>AI-predicted spend with confidence bands.</p>
                </div>
                {forecast.data && (
                  <span
                    className={`status-pill ${
                      forecast.data.trend === "rising"
                        ? "status-pill--warning"
                        : forecast.data.trend === "falling"
                          ? "status-pill--ok"
                          : "status-pill--neutral"
                    }`}
                  >
                    {forecast.data.trend}
                  </span>
                )}
              </header>

              {forecast.isLoading && <div className="loading" />}
              {!forecast.isLoading && forecast.data?.status === "insufficient_data" && (
                <div className="empty">Insufficient data for forecast. Ingest more calls first.</div>
              )}
              {!forecast.isLoading && forecast.data?.status === "ok" && (
                <>
                  <div className="spark">
                    {forecast.data.points.map((pt) => {
                      const maxVal = Math.max(...forecast.data!.points.map((p) => p.upper_bound_usd), 0.0001);
                      return (
                        <div
                          key={pt.hour}
                          className="spark-bar"
                          style={{ height: Math.max(4, Math.round((pt.predicted_cost_usd / maxVal) * 80)) }}
                          title={`${pt.hour} | predicted: ${formatUsd(pt.predicted_cost_usd)} [${formatUsd(pt.lower_bound_usd)} – ${formatUsd(pt.upper_bound_usd)}]`}
                        />
                      );
                    })}
                  </div>
                  <div className="list">
                    {forecast.data.points.map((pt) => (
                      <div key={pt.hour} className="list-row">
                        <span className="hint">{pt.hour.slice(11, 16)}</span>
                        <span className="mono">{formatUsd(pt.predicted_cost_usd)}</span>
                      </div>
                    ))}
                  </div>
                  <p className="hint">
                    Confidence: {formatPercent((forecast.data.confidence ?? 0) * 100)} · Generated{" "}
                    {formatDateTime(forecast.data.generated_at)}
                  </p>
                </>
              )}
            </article>

            <article className="panel">
              <header className="panel-header">
                <div>
                  <h3>Anomaly Risk</h3>
                  <p>AI-assessed cost spike risk for the current period.</p>
                </div>
                {anomalyRisk.data && anomalyRisk.data.status !== "error" && (
                  <span
                    className={`status-pill ${
                      anomalyRisk.data.status === "high"
                        ? "status-pill--critical"
                        : anomalyRisk.data.status === "elevated"
                          ? "status-pill--warning"
                          : "status-pill--ok"
                    }`}
                  >
                    {anomalyRisk.data.risk_label ?? anomalyRisk.data.status}
                  </span>
                )}
              </header>

              {anomalyRisk.isLoading && <div className="loading" />}
              {!anomalyRisk.isLoading && anomalyRisk.data && anomalyRisk.data.status !== "error" && (
                <>
                  <strong className="kpi-value">
                    Risk score: {((anomalyRisk.data.risk_score ?? 0) * 100).toFixed(0)}%
                  </strong>
                  {Array.isArray(anomalyRisk.data.contributing_factors) &&
                    anomalyRisk.data.contributing_factors.length > 0 && (
                        <div className="list cost-factor-list">
                        {anomalyRisk.data.contributing_factors.map((factor: string, i: number) => (
                          <div key={i} className="list-row">
                            <span className="hint">⚠ {factor}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  {anomalyRisk.data.recommended_action && (
                      <p className="hint">
                      {anomalyRisk.data.recommended_action}
                    </p>
                  )}
                </>
              )}
              {!anomalyRisk.isLoading && (!anomalyRisk.data || anomalyRisk.data.status === "error") && (
                <div className="empty">Risk analysis unavailable.</div>
              )}
            </article>
          </section>

          {/* ── Row 2: Daily Spend Trend (clickable bars for hourly drill-down) ── */}
          <section className="grid-two">
            <article className="panel">
              <header className="panel-header">
                <div>
                  <h3>Daily Spend Trend</h3>
                  <p>14-day cost. Click a bar to drill into hourly breakdown.</p>
                </div>
              </header>

              {selectedAgent ? (
                isFetchingAgentTrend ? (
                  <div className="loading" />
                ) : agentBars.length === 0 ? (
                  <div className="empty">No spend data for selected agent.</div>
                ) : (
                  <div className="spark">
                    {agentBars.map((p) => (
                      <div
                        key={p.day}
                        className={`spark-bar`}
                        style={{ height: p.height }}
                        title={`${p.day} | ${formatUsd(p.total_cost_usd)} | ${formatCount(p.call_count)} calls`}
                        onClick={() => setHourlyDayKey((prev) => (prev === p.day ? null : p.day))}
                      />
                    ))}
                  </div>
                )
              ) : comparePrev && compareBars ? (
                <div style={{ display: "grid", gap: 8 }}>
                  <div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>Previous period</div>
                  <div className="spark spark-compare-prev">
                    {compareBars.prevBars.map((b) => (
                      <div key={b.label} className="spark-bar spark-bar-prev" style={{ height: b.height }} title={`${b.label} | ${formatUsd(0)}`} />
                    ))}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>Current period</div>
                  <div className="spark spark-compare-cur">
                    {compareBars.curBars.map((b) => (
                      <div key={b.label} className="spark-bar" style={{ height: b.height }} title={`${b.label} | ${formatUsd(0)}`} onClick={() => setHourlyDayKey((prev) => (prev === b.label ? null : b.label))} />
                    ))}
                  </div>
                </div>
              ) : trendBars.length === 0 ? (
                <div className="empty">No spend data yet.</div>
              ) : (
                <div className="spark">
                  {trendBars.map((point) => (
                    <div
                      key={point.label}
                      className={`spark-bar cost-trend-bar${hourlyDayKey && hourlyDayKey !== point.label ? " cost-trend-bar-dim" : ""}`}
                      style={{ height: point.height }}
                      title={`${point.label} | ${formatUsd(point.value)} | ${formatCount(point.count)} calls${point.failedCount > 0 ? ` | ${formatCount(point.failedCount)} failed (${formatUsd(point.failedCost)})` : ""}`}
                      onClick={() =>
                        setHourlyDayKey((prev) => (prev === point.label ? null : point.label))
                      }
                    />
                  ))}
                </div>
              )}

              <p className="hint">Latest day: {formatDate(dailyTrend.data?.points.at(-1)?.day ?? null)}</p>

              {hourlyDayKey && (
                <div className="cost-hourly-breakdown">
                  <p className="hint cost-hourly-label">
                    Hourly breakdown — {hourlyDayKey}
                  </p>
                  {hourly.isLoading ? (
                    <div className="loading" />
                  ) : hourlyBarsForDay.length === 0 ? (
                    <p className="hint">No data for this day in the 48-hour window.</p>
                  ) : (
                    <div className="spark cost-spark-bottom">
                      {hourlyBarsForDay.map((bar) => (
                        <div
                          key={bar.label}
                          className="spark-bar"
                          style={{ height: bar.height }}
                          title={`${bar.label} | ${formatUsd(bar.value)} | ${formatCount(bar.count)} calls${bar.failedCount > 0 ? ` | ${formatCount(bar.failedCount)} failed (${formatUsd(bar.failedCost)})` : ""}`}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </article>

            {/* ── Top 10 Expensive Calls ── */}
            <article className="panel">
              <header className="panel-header">
                <div>
                  <h3>Top Expensive Calls</h3>
                  <p>Highest single-call cost in last 7 days.</p>
                </div>
              </header>

              <div className="list">
                {(topCalls.data?.items ?? []).length === 0 ? (
                  <div className="empty">No calls yet.</div>
                ) : (
                  (topCalls.data?.items ?? []).map((item) => (
                    <Link key={item.call_id} href={`/calls/${item.call_id}`} className="list-row list-row-link">
                      <div className="list-main">
                        <strong>{item.model ?? "unknown"}</strong>
                        <span>
                          {item.provider ?? "unknown"}
                          {item.agent_name ? ` · ${item.agent_name}` : ""}
                          {item.user_id ? ` · ${item.user_id}` : ""}
                          {item.call_type ? ` · ${item.call_type}` : ""}
                          {item.status !== "success" && item.status !== "ok"
                            ? ` · ⚠ ${item.status}`
                            : ""}
                        </span>
                        <span>
                          {item.cost_confidence ?? "unknown"} confidence
                          {item.pricing_source ? ` · ${formatPricingSource(item.pricing_source)}` : ""}
                        </span>
                      </div>
                      <span className="mono">{formatUsd(item.cost_usd)}</span>
                    </Link>
                  ))
                )}
              </div>
            </article>
          </section>

          {/* ── Row 3: Spend by Model + Spend by Agent ── */}
          <section className="grid-two">
            <article className="panel">
              <header className="panel-header">
                <div>
                  <h3>Spend by Model</h3>
                  <p>Top model cost distribution ({windowDays}d).</p>
                </div>
              </header>

              <CostShareList items={byModel.data?.items ?? []} />
            </article>

            <article className="panel">
              <header className="panel-header">
                <div>
                  <h3>Spend by Agent</h3>
                  <p>Agent-level cost attribution ({windowDays}d).</p>
                </div>
              </header>

              {(byAgent.data?.items ?? []).length === 0 ? (
                <div className="empty">No agent data yet.</div>
              ) : (
                <CostShareList items={byAgent.data?.items ?? []} />
              )}
            </article>
          </section>

          {/* ── Row 4: Spend by User ── */}
          <section className="grid-two">
            <article className="panel">
              <header className="panel-header">
                <div>
                  <h3>Spend by User</h3>
                  <p>User-level spend concentration ({windowDays}d).</p>
                </div>
              </header>

              {(byUser.data?.items ?? []).length === 0 ? (
                <div className="empty">No user data yet.</div>
              ) : (
                <CostShareList items={byUser.data?.items ?? []} />
              )}
            </article>

            <article className="panel panel-muted">
              <h3>Reasoning Cost Share</h3>
              <p className="hint">Reasoning-heavy prompts can silently inflate total spend.</p>
              <strong className="kpi-value">{formatPercent(reasoning.data?.reasoning_share_percent ?? 0)}</strong>
              <span className="hint mono">
                {formatUsd(reasoning.data?.reasoning_cost_usd ?? 0)} of {formatUsd(reasoning.data?.total_cost_usd ?? 0)}
              </span>
            </article>
          </section>

          {/* ── Row 5: Cache Savings + Pricing Freshness ── */}
          <section className="grid-two">
            <article className="panel panel-muted">
              <h3>Cache Savings Trend</h3>
              <p className="hint">Recovered spend through cached responses.</p>
              {cacheBars.length > 0 ? (
                <div className="spark cost-spark-bottom">
                  {cacheBars.map((point) => (
                    <div
                      key={point.label}
                      className="spark-bar"
                      style={{ height: point.height }}
                      title={`${point.label} | ${formatUsd(point.value)}`}
                    />
                  ))}
                </div>
              ) : (
                <div className="empty">No cache savings yet.</div>
              )}
              <strong className="kpi-value mono">{formatUsd(cacheSavings.data?.total_cache_savings_usd ?? 0)}</strong>
            </article>

            <article className="panel panel-muted">
              <h3>Pricing Freshness</h3>
              <p className="hint">Confidence falls as pricing data ages.</p>
              <div className="list">
                <div className="list-row">
                  <div className="list-main"><strong>Last updated</strong></div>
                  <span className="mono">{formatDateTime(pricingFreshness.pricing_last_updated_at)}</span>
                </div>
                <div className="list-row">
                  <div className="list-main"><strong>Age</strong></div>
                  <span className="mono">{formatAgeDays(pricingFreshness.pricing_age_days)}</span>
                </div>
                <div className="list-row">
                  <div className="list-main"><strong>Source</strong></div>
                  <span className="mono">{formatPricingSource(pricingFreshness.pricing_source)}</span>
                </div>
                <div className="list-row">
                  <div className="list-main"><strong>Confidence</strong></div>
                  <StatusPill value={pricingFreshness.cost_confidence} />
                </div>
                {pricingFreshness.confidence_reason ? (
                  <div className="list-row">
                    <div className="list-main"><strong>Reason</strong></div>
                    <span className="mono">{pricingFreshness.confidence_reason}</span>
                  </div>
                ) : null}
              </div>
              {(pricingFreshness.pricing_age_days ?? 0) > 14 ? (
                <p className="cost-stale-warning">⚠ Pricing data is over 14 days old — cost figures may be inaccurate.</p>
              ) : null}
            </article>
          </section>
        </>
      ) : null}
    </>
  );
}
