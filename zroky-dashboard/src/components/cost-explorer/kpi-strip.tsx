"use client";

import { useEffect, useState } from "react";
import {
  getAnalyticsSummary,
  getCostAnomalyRisk,
  getCostForecast,
  getSavingsSummary,
} from "@/lib/api";
import { formatUsd, formatPercent } from "@/lib/format";
import type {
  AnalyticsSummaryResponse,
  CostAnomalyRiskResponse,
  CostForecastResponse,
  SavingsSummaryResponse,
} from "@/lib/types";

/**
 * CostKpiStrip — 4 hero KPIs at the top of the Cost Explorer.
 *
 *   1. Spent today        — `cost_today_usd` vs `cost_yesterday_usd` (Δ%)
 *   2. Forecast next window — projected total from `/ai/cost/forecast`
 *   3. Wasted % of spend  — `cumulative_wasted_usd / total spend`
 *   4. Anomaly risk pill  — current `/ai/cost/anomaly-risk` status
 *
 * Each card has a sparkline-free numeric framing — the hero chart below shows
 * the time-series. This row is for "is anything on fire RIGHT NOW".
 */

interface CardData {
  summary: AnalyticsSummaryResponse | null;
  forecast: CostForecastResponse | null;
  savings: SavingsSummaryResponse | null;
  risk: CostAnomalyRiskResponse | null;
}

export function CostKpiStrip({ windowDays }: { windowDays: number }) {
  const [data, setData] = useState<CardData>({
    summary: null,
    forecast: null,
    savings: null,
    risk: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    async function load() {
      const [summary, forecast, savings, risk] = await Promise.allSettled([
        getAnalyticsSummary(1, controller.signal),
        getCostForecast(Math.min(24, windowDays * 24), controller.signal),
        getSavingsSummary(windowDays, controller.signal),
        getCostAnomalyRisk(controller.signal),
      ]);
      if (cancelled) return;
      setData({
        summary: summary.status === "fulfilled" ? summary.value : null,
        forecast: forecast.status === "fulfilled" ? forecast.value : null,
        savings: savings.status === "fulfilled" ? savings.value : null,
        risk: risk.status === "fulfilled" ? risk.value : null,
      });
    }

    void load();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [windowDays]);

  const todaySpend = data.summary?.cost_today_usd ?? 0;
  const yesterdaySpend = data.summary?.cost_yesterday_usd ?? 0;
  const todayDelta = yesterdaySpend > 0 ? (todaySpend - yesterdaySpend) / yesterdaySpend : 0;
  const todayDirection = todaySpend > yesterdaySpend ? "up" : todaySpend < yesterdaySpend ? "down" : "flat";

  // Sum forecast points for a "next window" total
  const forecastTotal = data.forecast?.points.reduce(
    (acc, p) => acc + p.predicted_cost_usd,
    0,
  ) ?? 0;
  const forecastConfidence = data.forecast?.confidence ?? 0;
  const forecastTrend = data.forecast?.trend ?? "stable";

  const wasted = data.savings?.cumulative_wasted_usd ?? 0;
  const totalSpendForWindow = (data.savings?.cumulative_wasted_usd ?? 0)
    + (data.savings?.cumulative_resolved_blast_usd ?? 0)
    + Math.max(0, todaySpend * windowDays); // rough — replaced by hero chart's real number
  const wastedPct = totalSpendForWindow > 0 ? wasted / totalSpendForWindow : 0;

  const riskStatus = data.risk?.status ?? "ok";
  const riskLabel = data.risk?.risk_label ?? "Stable";
  const riskScore = data.risk?.risk_score ?? 0;

  return (
    <section className="cost-kpi-strip" aria-label="Cost key indicators">
      <article className="cost-kpi-card">
        <header>Spent today</header>
        <strong className="cost-kpi-value mono">{formatUsd(todaySpend)}</strong>
        <div className={`cost-kpi-delta cost-kpi-delta-${todayDirection}`}>
          {todayDirection === "up" ? "▲" : todayDirection === "down" ? "▼" : "—"}{" "}
          {formatPercent(Math.abs(todayDelta) * 100)} vs yesterday
        </div>
      </article>

      <article className="cost-kpi-card">
        <header>Forecast (next {data.forecast?.hours_ahead ?? "—"}h)</header>
        <strong className="cost-kpi-value mono">{formatUsd(forecastTotal)}</strong>
        <div className="cost-kpi-meta">
          <span className={`cost-kpi-trend cost-kpi-trend-${forecastTrend}`}>
            {forecastTrend === "rising" ? "↑ rising" : forecastTrend === "falling" ? "↓ falling" : "→ stable"}
          </span>
          <span className="cost-kpi-confidence">
            {Math.round(forecastConfidence * 100)}% confidence
          </span>
        </div>
      </article>

      <article className={`cost-kpi-card ${wastedPct >= 0.10 ? "cost-kpi-warn" : ""}`}>
        <header>Wasted on open issues</header>
        <strong className="cost-kpi-value mono">{formatUsd(wasted)}</strong>
        <div className="cost-kpi-meta">
          <span className={`cost-kpi-waste-pct ${wastedPct >= 0.10 ? "high" : "low"}`}>
            {formatPercent(wastedPct * 100)} of spend
          </span>
          <span className="cost-kpi-confidence">
            {data.savings?.total_caught_count ?? 0} open issues
          </span>
        </div>
      </article>

      <article className={`cost-kpi-card cost-kpi-risk-${riskStatus}`}>
        <header>Anomaly risk</header>
        <strong className="cost-kpi-value">{riskLabel}</strong>
        <div className="cost-kpi-meta">
          <span className="cost-kpi-risk-score mono">
            score {riskScore.toFixed(2)}
          </span>
          {data.risk?.contributing_factors && data.risk.contributing_factors.length > 0 ? (
            <span
              className="cost-kpi-risk-factors"
              title={data.risk.contributing_factors.join("\n")}
            >
              {data.risk.contributing_factors.length} factor
              {data.risk.contributing_factors.length === 1 ? "" : "s"}
            </span>
          ) : null}
        </div>
      </article>
    </section>
  );
}
