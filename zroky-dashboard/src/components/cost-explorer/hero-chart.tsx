"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getCostDailyTrend,
  getCostForecast,
  listAlerts,
} from "@/lib/api";
import { formatUsd } from "@/lib/format";
import type {
  AlertItemResponse,
  CostDailyTrendResponse,
  CostForecastResponse,
} from "@/lib/types";

/**
 * CostHeroChart — the differentiated cost visualization.
 *
 * Three layers on a single SVG canvas:
 *   1. Stacked bars per day: legitimate spend (green) + failed-call spend (red)
 *      — `failed_cost_usd` is already in CostDailyTrendPoint, no new backend.
 *   2. Forecast line (dashed) projecting future cost from /ai/cost/forecast.
 *      Sums forecast hours into a single "tomorrow" data point so it lines up
 *      with the historical daily bars.
 *   3. Issue markers — vertical red bands at the dates COST_SPIKE alerts
 *      fired. Connects detection → visualization, the gap nobody else covers.
 *
 * Hover tooltip shows full breakdown per day including which alerts hit.
 */

interface Point {
  day: string;        // YYYY-MM-DD
  total: number;
  failed: number;     // subset of total, drawn as red overlay
  legitimate: number; // total - failed
  callCount: number;
  failedCount: number;
  isForecast?: boolean;
  forecastLower?: number;
  forecastUpper?: number;
  spikeAlerts?: AlertItemResponse[];
}

const CHART_HEIGHT = 280;
const CHART_PAD = { top: 24, right: 24, bottom: 36, left: 56 };

function parseDayKey(day: string): number {
  // YYYY-MM-DD → epoch ms (UTC midnight) for sorting/comparison
  const t = Date.parse(`${day}T00:00:00Z`);
  return Number.isFinite(t) ? t : 0;
}

function formatShortDay(day: string): string {
  const d = new Date(`${day}T00:00:00Z`);
  if (!Number.isFinite(d.getTime())) return day;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function CostHeroChart({ windowDays }: { windowDays: number }) {
  const [trend, setTrend] = useState<CostDailyTrendResponse | null>(null);
  const [forecast, setForecast] = useState<CostForecastResponse | null>(null);
  const [alerts, setAlerts] = useState<AlertItemResponse[]>([]);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    async function load() {
      const [trendRes, forecastRes, alertsRes] = await Promise.allSettled([
        getCostDailyTrend(windowDays, controller.signal),
        getCostForecast(Math.min(24, windowDays * 24), controller.signal),
        // Pull recent COST_SPIKE alerts to mark on the chart
        listAlerts({ category: "COST_SPIKE", limit: 100 }),
      ]);
      if (cancelled) return;
      setTrend(trendRes.status === "fulfilled" ? trendRes.value : null);
      setForecast(forecastRes.status === "fulfilled" ? forecastRes.value : null);
      setAlerts(
        alertsRes.status === "fulfilled" ? (alertsRes.value.items ?? []) : [],
      );
    }

    void load();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [windowDays]);

  const points: Point[] = useMemo(() => {
    const base: Point[] = (trend?.points ?? []).map((p) => ({
      day: p.day,
      total: p.total_cost_usd,
      failed: p.failed_cost_usd,
      legitimate: Math.max(0, p.total_cost_usd - p.failed_cost_usd),
      callCount: p.call_count,
      failedCount: p.failed_call_count,
    }));

    // Attach issue markers — group alerts by day
    if (alerts.length > 0) {
      const byDay = new Map<string, AlertItemResponse[]>();
      for (const a of alerts) {
        const d = a.created_at?.slice(0, 10);
        if (!d) continue;
        const arr = byDay.get(d) ?? [];
        arr.push(a);
        byDay.set(d, arr);
      }
      for (const p of base) {
        const hits = byDay.get(p.day);
        if (hits && hits.length > 0) p.spikeAlerts = hits;
      }
    }

    // Append forecast points as a single tomorrow-summary (or per-day if longer)
    if (forecast && forecast.status === "ok" && forecast.points.length > 0) {
      const lastDay = base.length > 0 ? base[base.length - 1].day : null;
      const lastEpoch = lastDay ? parseDayKey(lastDay) : Date.now();
      // Sum forecast hours into daily buckets keyed by date
      const fbuckets = new Map<string, { sum: number; lower: number; upper: number }>();
      for (const fp of forecast.points) {
        const day = fp.hour.slice(0, 10);
        const existing = fbuckets.get(day) ?? { sum: 0, lower: 0, upper: 0 };
        existing.sum += fp.predicted_cost_usd;
        existing.lower += fp.lower_bound_usd;
        existing.upper += fp.upper_bound_usd;
        fbuckets.set(day, existing);
      }
      const sortedDays = Array.from(fbuckets.keys()).sort();
      for (const day of sortedDays) {
        if (parseDayKey(day) <= lastEpoch) continue; // skip past
        const f = fbuckets.get(day)!;
        base.push({
          day,
          total: f.sum,
          failed: 0,
          legitimate: f.sum,
          callCount: 0,
          failedCount: 0,
          isForecast: true,
          forecastLower: f.lower,
          forecastUpper: f.upper,
        });
      }
    }

    return base;
  }, [trend, forecast, alerts]);

  if (!trend) {
    return (
      <section className="cost-hero-chart panel">
        <header className="panel-header">
          <div>
            <h2>Cost trend</h2>
            <p>Loading spend, forecast, and issue markers...</p>
          </div>
        </header>
        <div className="cost-hero-skeleton" style={{ height: CHART_HEIGHT }} />
      </section>
    );
  }

  if (points.length === 0) {
    return (
      <section className="cost-hero-chart panel">
        <header className="panel-header">
          <div>
            <h2>Cost trend</h2>
            <p>No spend recorded in this window.</p>
          </div>
        </header>
      </section>
    );
  }

  const chartWidth = Math.max(600, points.length * 48);
  const innerW = chartWidth - CHART_PAD.left - CHART_PAD.right;
  const innerH = CHART_HEIGHT - CHART_PAD.top - CHART_PAD.bottom;

  const maxValue = Math.max(
    ...points.map((p) => Math.max(p.total, p.forecastUpper ?? p.total)),
    1,
  );
  const yScale = (v: number): number => CHART_PAD.top + innerH - (v / maxValue) * innerH;
  const barWidth = Math.max(8, innerW / points.length - 8);
  const xCenter = (i: number): number =>
    CHART_PAD.left + (i + 0.5) * (innerW / points.length);

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * maxValue);

  // Build forecast line path (dashed) — connects last historical → forecast pts
  const lastHistoricalIdx = points.findIndex((p) => p.isForecast) - 1;
  const forecastStartIdx = points.findIndex((p) => p.isForecast);
  const forecastLinePath =
    forecastStartIdx >= 0 && lastHistoricalIdx >= 0
      ? points
          .slice(lastHistoricalIdx, points.length)
          .map((p, i) => {
            const realIdx = lastHistoricalIdx + i;
            const x = xCenter(realIdx);
            const y = yScale(p.total);
            return `${i === 0 ? "M" : "L"} ${x} ${y}`;
          })
          .join(" ")
      : "";

  const hoverPoint = hoverIdx !== null ? points[hoverIdx] : null;

  return (
    <section className="cost-hero-chart panel">
      <header className="panel-header">
        <div>
          <h2>Cost trend</h2>
          <p>
            Legitimate spend, wasted spend, forecast, and detected issues in
            one view.
          </p>
        </div>
        <div className="cost-hero-legend" aria-label="Chart legend">
          <span className="legend-item">
            <span className="legend-swatch swatch-legit" /> Legitimate
          </span>
          <span className="legend-item">
            <span className="legend-swatch swatch-failed" /> Wasted (failed)
          </span>
          <span className="legend-item">
            <span className="legend-swatch swatch-forecast" /> Forecast
          </span>
          <span className="legend-item">
            <span className="legend-swatch swatch-anomaly" /> COST_SPIKE
          </span>
        </div>
      </header>

      <div className="cost-hero-scroll">
        <svg
          width={chartWidth}
          height={CHART_HEIGHT}
          role="img"
          aria-label="Cost trend chart with forecast and issue markers"
        >
          {/* Y-axis grid lines + labels */}
          {yTicks.map((t, i) => {
            const y = yScale(t);
            return (
              <g key={i}>
                <line
                  x1={CHART_PAD.left}
                  x2={chartWidth - CHART_PAD.right}
                  y1={y}
                  y2={y}
                  stroke="rgba(0,0,0,0.06)"
                  strokeDasharray={i === 0 ? "" : "2 4"}
                />
                <text
                  x={CHART_PAD.left - 8}
                  y={y + 4}
                  textAnchor="end"
                  fontSize="10"
                  fill="var(--text-secondary)"
                  className="mono"
                >
                  ${t.toFixed(t < 10 ? 2 : 0)}
                </text>
              </g>
            );
          })}

          {/* Issue bands (drawn behind bars) */}
          {points.map((p, i) =>
            p.spikeAlerts && p.spikeAlerts.length > 0 ? (
              <rect
                key={`anom-${i}`}
                x={xCenter(i) - barWidth / 2 - 2}
                y={CHART_PAD.top}
                width={barWidth + 4}
                height={innerH}
                fill="rgba(239, 68, 68, 0.10)"
                stroke="rgba(239, 68, 68, 0.35)"
                strokeWidth={1}
                strokeDasharray="3 3"
              />
            ) : null,
          )}

          {/* Forecast uncertainty band */}
          {points.map((p, i) =>
            p.isForecast && p.forecastUpper !== undefined && p.forecastLower !== undefined ? (
              <rect
                key={`fband-${i}`}
                x={xCenter(i) - barWidth / 2}
                y={yScale(p.forecastUpper)}
                width={barWidth}
                height={Math.max(0, yScale(p.forecastLower) - yScale(p.forecastUpper))}
                fill="rgba(99, 102, 241, 0.12)"
              />
            ) : null,
          )}

          {/* Stacked bars: legitimate (green) bottom, failed (red) on top */}
          {points.map((p, i) => {
            if (p.isForecast) {
              // Forecast: hollow bar so it visually reads as projection
              return (
                <rect
                  key={`fbar-${i}`}
                  x={xCenter(i) - barWidth / 2}
                  y={yScale(p.total)}
                  width={barWidth}
                  height={Math.max(0, innerH + CHART_PAD.top - yScale(p.total))}
                  fill="rgba(99, 102, 241, 0.10)"
                  stroke="rgba(99, 102, 241, 0.55)"
                  strokeWidth={1}
                  strokeDasharray="4 3"
                  onMouseEnter={() => setHoverIdx(i)}
                  onMouseLeave={() => setHoverIdx((curr) => (curr === i ? null : curr))}
                />
              );
            }
            const legitH = (p.legitimate / maxValue) * innerH;
            const failedH = (p.failed / maxValue) * innerH;
            const legitY = CHART_PAD.top + innerH - legitH;
            const failedY = legitY - failedH;
            return (
              <g
                key={`bar-${i}`}
                onMouseEnter={() => setHoverIdx(i)}
                onMouseLeave={() => setHoverIdx((curr) => (curr === i ? null : curr))}
              >
                {legitH > 0 ? (
                  <rect
                    x={xCenter(i) - barWidth / 2}
                    y={legitY}
                    width={barWidth}
                    height={legitH}
                    fill="#22c55e"
                    rx={2}
                  />
                ) : null}
                {failedH > 0 ? (
                  <rect
                    x={xCenter(i) - barWidth / 2}
                    y={failedY}
                    width={barWidth}
                    height={failedH}
                    fill="#ef4444"
                    rx={2}
                  />
                ) : null}
              </g>
            );
          })}

          {/* Forecast line connecting last historical → projection */}
          {forecastLinePath ? (
            <path
              d={forecastLinePath}
              fill="none"
              stroke="#6366f1"
              strokeWidth={2}
              strokeDasharray="5 4"
            />
          ) : null}

          {/* Issue marker triangles at top of each spike day */}
          {points.map((p, i) =>
            p.spikeAlerts && p.spikeAlerts.length > 0 ? (
              <g key={`amark-${i}`}>
                <polygon
                  points={`${xCenter(i)},${CHART_PAD.top - 4} ${xCenter(i) - 6},${CHART_PAD.top - 14} ${xCenter(i) + 6},${CHART_PAD.top - 14}`}
                  fill="#ef4444"
                />
                <text
                  x={xCenter(i)}
                  y={CHART_PAD.top - 6}
                  textAnchor="middle"
                  fontSize="8"
                  fill="#fff"
                  fontWeight="700"
                >
                  {p.spikeAlerts.length}
                </text>
              </g>
            ) : null,
          )}

          {/* X-axis day labels */}
          {points.map((p, i) => {
            // Skip labels if too crowded
            const shouldDraw = points.length <= 14 || i % Math.ceil(points.length / 10) === 0;
            if (!shouldDraw) return null;
            return (
              <text
                key={`xlabel-${i}`}
                x={xCenter(i)}
                y={CHART_HEIGHT - CHART_PAD.bottom + 16}
                textAnchor="middle"
                fontSize="10"
                fill={p.isForecast ? "#6366f1" : "var(--text-secondary)"}
                fontWeight={p.isForecast ? 600 : 400}
              >
                {formatShortDay(p.day)}
              </text>
            );
          })}

          {/* X-axis baseline */}
          <line
            x1={CHART_PAD.left}
            x2={chartWidth - CHART_PAD.right}
            y1={CHART_PAD.top + innerH}
            y2={CHART_PAD.top + innerH}
            stroke="rgba(0,0,0,0.15)"
          />
        </svg>
      </div>

      {/* Tooltip / inline breakdown for the hovered day */}
      <div className="cost-hero-tooltip" aria-live="polite">
        {hoverPoint ? (
          <>
            <div className="cost-hero-tooltip-head">
              <strong>{formatShortDay(hoverPoint.day)}</strong>
              {hoverPoint.isForecast ? (
                <span className="cost-hero-tooltip-tag forecast">forecast</span>
              ) : null}
              {hoverPoint.spikeAlerts && hoverPoint.spikeAlerts.length > 0 ? (
                <span className="cost-hero-tooltip-tag anomaly">
                  {hoverPoint.spikeAlerts.length} cost-spike
                  {hoverPoint.spikeAlerts.length === 1 ? "" : "s"}
                </span>
              ) : null}
            </div>
            <dl className="cost-hero-tooltip-grid">
              <div>
                <dt>Total</dt>
                <dd className="mono">{formatUsd(hoverPoint.total)}</dd>
              </div>
              {!hoverPoint.isForecast ? (
                <>
                  <div>
                    <dt>Legitimate</dt>
                    <dd className="mono">{formatUsd(hoverPoint.legitimate)}</dd>
                  </div>
                  <div>
                    <dt>Wasted (failed)</dt>
                    <dd className="mono">{formatUsd(hoverPoint.failed)}</dd>
                  </div>
                  <div>
                    <dt>Calls</dt>
                    <dd className="mono">
                      {hoverPoint.callCount.toLocaleString()}
                      {hoverPoint.failedCount > 0 ? (
                        <span className="cost-hero-tooltip-fail">
                          {" "}
                          ({hoverPoint.failedCount} failed)
                        </span>
                      ) : null}
                    </dd>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <dt>Lower</dt>
                    <dd className="mono">{formatUsd(hoverPoint.forecastLower ?? 0)}</dd>
                  </div>
                  <div>
                    <dt>Upper</dt>
                    <dd className="mono">{formatUsd(hoverPoint.forecastUpper ?? 0)}</dd>
                  </div>
                </>
              )}
            </dl>
          </>
        ) : (
          <p className="cost-hero-tooltip-hint">
            Hover a bar to see day-level breakdown.
          </p>
        )}
      </div>
    </section>
  );
}
