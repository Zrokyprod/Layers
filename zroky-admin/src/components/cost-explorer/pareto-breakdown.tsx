"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getCostByAgent,
  getCostByModel,
  getCostByUser,
} from "@/lib/api";
import { formatUsd } from "@/lib/format";
import type { CostBreakdownResponse } from "@/lib/types";

/**
 * CostParetoBreakdown — "80% of cost comes from 5% of [models|users|agents]".
 *
 * Horizontal bar chart sorted descending. Each row shows its share of
 * total spend, AND a cumulative-percentage marker for the running total.
 * Highlights the rows that collectively cross 80% — the classic Pareto
 * cutoff — so users immediately see "these are the items to target".
 *
 * Three tabs: by model / user / agent. All powered by existing routes.
 */

type Dim = "model" | "user" | "agent";

const TABS: { key: Dim; label: string }[] = [
  { key: "model", label: "By model" },
  { key: "user", label: "By user" },
  { key: "agent", label: "By agent" },
];

const PARETO_THRESHOLD = 0.80;

export function CostParetoBreakdown({ windowDays }: { windowDays: number }) {
  const [tab, setTab] = useState<Dim>("model");
  const [data, setData] = useState<Record<Dim, CostBreakdownResponse | null>>({
    model: null,
    user: null,
    agent: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    async function load() {
      const [m, u, a] = await Promise.allSettled([
        getCostByModel(windowDays, controller.signal),
        getCostByUser(windowDays, controller.signal),
        getCostByAgent(windowDays, controller.signal),
      ]);
      if (cancelled) return;
      setData({
        model: m.status === "fulfilled" ? m.value : null,
        user: u.status === "fulfilled" ? u.value : null,
        agent: a.status === "fulfilled" ? a.value : null,
      });
    }

    void load();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [windowDays]);

  const current = data[tab];

  const rows = useMemo(() => {
    if (!current || current.items.length === 0) return [];
    const sorted = [...current.items].sort((a, b) => b.total_cost_usd - a.total_cost_usd);
    const total = sorted.reduce((s, it) => s + it.total_cost_usd, 0);
    if (total <= 0) return [];

    let running = 0;
    let crossedAt: number | null = null;
    return sorted.map((it, idx) => {
      const share = it.total_cost_usd / total;
      running += share;
      const isPareto = crossedAt === null && running >= PARETO_THRESHOLD;
      if (isPareto) crossedAt = idx;
      return {
        key: it.key || "—",
        cost: it.total_cost_usd,
        failedCost: it.failed_cost_usd,
        callCount: it.call_count,
        failedCount: it.failed_call_count,
        share,
        cumulativeShare: running,
        isPareto,
        isWithinPareto: crossedAt === null || idx <= crossedAt,
      };
    });
  }, [current]);

  const paretoCount = rows.filter((r) => r.isWithinPareto).length;
  const totalCount = rows.length;
  const paretoPercent = totalCount > 0 ? (paretoCount / totalCount) * 100 : 0;

  return (
    <section className="cost-pareto panel">
      <header className="panel-header">
        <div>
          <h3>Where the money goes</h3>
          <p>
            Sorted by spend with cumulative-percentage marker.
            {totalCount > 0 ? (
              <>
                {" "}<strong>{paretoCount}</strong> of {totalCount}{" "}
                {tab}
                {paretoCount === 1 ? "" : "s"}
                {" "}
                ({paretoPercent.toFixed(0)}%) drive 80% of spend.
              </>
            ) : null}
          </p>
        </div>
        <div className="cost-pareto-tabs" role="tablist" aria-label="Breakdown dimension">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              className={`cost-pareto-tab ${tab === t.key ? "active" : ""}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>

      {rows.length === 0 ? (
        <p className="cost-pareto-empty">
          {current ? "No data in this window." : "Loading…"}
        </p>
      ) : (
        <div className="cost-pareto-rows">
          {rows.map((r, idx) => (
            <div
              key={`${r.key}-${idx}`}
              className={`cost-pareto-row ${r.isWithinPareto ? "in-pareto" : ""} ${r.isPareto ? "is-pareto-line" : ""}`}
            >
              <div className="cost-pareto-row-head">
                <span className="cost-pareto-rank mono">#{idx + 1}</span>
                <span className="cost-pareto-key mono">{r.key}</span>
                <span className="cost-pareto-cost mono">{formatUsd(r.cost)}</span>
              </div>
              <div className="cost-pareto-bar-wrap" aria-hidden="true">
                <div className="cost-pareto-bar-track">
                  <div
                    className="cost-pareto-bar-fill"
                    style={{ width: `${r.share * 100}%` }}
                  />
                  {/* Cumulative line */}
                  <div
                    className="cost-pareto-cum-marker"
                    style={{ left: `${Math.min(100, r.cumulativeShare * 100)}%` }}
                    title={`Cumulative: ${(r.cumulativeShare * 100).toFixed(1)}%`}
                  />
                </div>
                <div className="cost-pareto-row-meta">
                  <span>{(r.share * 100).toFixed(1)}% share</span>
                  <span className="cost-pareto-cum mono">
                    cum {(r.cumulativeShare * 100).toFixed(0)}%
                  </span>
                  {r.failedCount > 0 ? (
                    <span className="cost-pareto-failed">
                      {r.failedCount.toLocaleString()} failed ·{" "}
                      {formatUsd(r.failedCost)} wasted
                    </span>
                  ) : null}
                  <span>{r.callCount.toLocaleString()} calls</span>
                </div>
              </div>
            </div>
          ))}

          {/* Pareto line callout */}
          <div className="cost-pareto-legend">
            <span className="cost-pareto-legend-band" /> Within 80%
            <span className="cost-pareto-legend-dot" /> Cumulative %
          </div>
        </div>
      )}
    </section>
  );
}
