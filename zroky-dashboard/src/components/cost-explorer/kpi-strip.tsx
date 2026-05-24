"use client";

import { useEffect, useState } from "react";
import {
  getAnalyticsSummary,
  getCostDailyTrend,
  getSavingsSummary,
} from "@/lib/api";
import { formatUsd, formatPercent } from "@/lib/format";
import type {
  AnalyticsSummaryResponse,
  CostDailyTrendResponse,
  SavingsSummaryResponse,
} from "@/lib/types";

/**
 * CostKpiStrip — 4 hero KPIs at the top of the Cost Explorer.
 *
 *   1. Spent today      — cost_today_usd vs cost_yesterday_usd (Δ%)
 *   2. Est. tomorrow    — average of last 3 daily-trend points (deterministic)
 *   3. Wasted on issues — cumulative_wasted_usd / total spend
 *   4. Anomaly risk     — z-score of today vs window mean±std (deterministic)
 *
 * Cards 2 and 4 were previously calling /ai/cost/forecast and
 * /ai/cost/anomaly-risk — routes that don't exist in the backend.
 * They now derive the same signal from the daily-trend data already
 * fetched by CostHeroChart. No extra network call, no silent 404.
 */

interface CardData {
  summary: AnalyticsSummaryResponse | null;
  trend: CostDailyTrendResponse | null;
  savings: SavingsSummaryResponse | null;
}

// ── Deterministic forecast: average of last 3 daily points ──────────────────

function computeForecast(trend: CostDailyTrendResponse | null): {
  avgPerDay: number;
  direction: "rising" | "falling" | "stable";
} {
  const pts = trend?.points ?? [];
  const last3 = pts.slice(-3).map((p) => p.total_cost_usd);
  if (last3.length === 0) return { avgPerDay: 0, direction: "stable" };
  const avg = last3.reduce((a, b) => a + b, 0) / last3.length;
  const first = last3[0];
  const last = last3[last3.length - 1];
  const direction: "rising" | "falling" | "stable" =
    last > first * 1.05 ? "rising" : last < first * 0.95 ? "falling" : "stable";
  return { avgPerDay: avg, direction };
}

// ── Deterministic anomaly: z-score of latest day vs window mean±std ──────────

function computeAnomalyRisk(trend: CostDailyTrendResponse | null): {
  status: "ok" | "elevated" | "high";
  label: string;
  zScore: number;
} {
  const costs = (trend?.points ?? []).map((p) => p.total_cost_usd);
  if (costs.length < 3) return { status: "ok", label: "Normal", zScore: 0 };
  const mean = costs.reduce((a, b) => a + b, 0) / costs.length;
  const variance = costs.reduce((a, b) => a + (b - mean) ** 2, 0) / costs.length;
  const std = Math.sqrt(variance);
  const latest = costs[costs.length - 1] ?? 0;
  const z = std > 0 ? (latest - mean) / std : 0;
  if (z > 2.5) return { status: "high", label: "High", zScore: z };
  if (z > 1.5) return { status: "elevated", label: "Elevated", zScore: z };
  return { status: "ok", label: "Normal", zScore: z };
}

export function CostKpiStrip({ windowDays }: { windowDays: number }) {
  const [data, setData] = useState<CardData>({
    summary: null,
    trend: null,
    savings: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    async function load() {
      const [summary, trend, savings] = await Promise.allSettled([
        getAnalyticsSummary(1, controller.signal),
        getCostDailyTrend(windowDays, controller.signal),
        getSavingsSummary(windowDays, controller.signal),
      ]);
      if (cancelled) return;
      setData({
        summary: summary.status === "fulfilled" ? summary.value : null,
        trend: trend.status === "fulfilled" ? trend.value : null,
        savings: savings.status === "fulfilled" ? savings.value : null,
      });
    }

    void load();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [windowDays]);

  // Card 1: Spent today
  const todaySpend = data.summary?.cost_today_usd ?? 0;
  const yesterdaySpend = data.summary?.cost_yesterday_usd ?? 0;
  const todayDelta = yesterdaySpend > 0 ? (todaySpend - yesterdaySpend) / yesterdaySpend : 0;
  const todayDirection = todaySpend > yesterdaySpend ? "up" : todaySpend < yesterdaySpend ? "down" : "flat";

  // Card 2: Est. tomorrow
  const { avgPerDay, direction: forecastDir } = computeForecast(data.trend);

  // Card 3: Wasted on open issues
  const wasted = data.savings?.cumulative_wasted_usd ?? 0;
  const totalSpendForWindow =
    (data.savings?.cumulative_wasted_usd ?? 0) +
    (data.savings?.cumulative_resolved_blast_usd ?? 0) +
    Math.max(0, todaySpend * windowDays);
  const wastedPct = totalSpendForWindow > 0 ? wasted / totalSpendForWindow : 0;

  // Card 4: Anomaly risk
  const { status: riskStatus, label: riskLabel, zScore } = computeAnomalyRisk(data.trend);

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
        <header>Est. tomorrow</header>
        <strong className="cost-kpi-value mono">
          {data.trend ? formatUsd(avgPerDay) : "—"}
        </strong>
        <div className="cost-kpi-meta">
          <span className={`cost-kpi-trend cost-kpi-trend-${forecastDir}`}>
            {forecastDir === "rising" ? "↑ rising" : forecastDir === "falling" ? "↓ falling" : "→ stable"}
          </span>
          <span className="cost-kpi-confidence">
            avg last {Math.min(3, data.trend?.points.length ?? 0)}d
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
            z={zScore.toFixed(2)}
          </span>
          <span className="cost-kpi-confidence">
            {(data.trend?.points.length ?? 0)}d sample
          </span>
        </div>
      </article>
    </section>
  );
}
