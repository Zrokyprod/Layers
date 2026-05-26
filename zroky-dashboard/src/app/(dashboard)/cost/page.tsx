"use client";

/**
 * /cost — unified Cost Explorer.
 *
 * Single page that consolidates every cost view: trend with forecast + issue
 * markers + waste attribution, cost-per-outcome KPIs, what-if model swap
 * calculator, and Pareto breakdowns by model/user/agent.
 *
 * This is the "best & most advanced" cost surface in the product. Every other
 * cost widget (home page summary, top-bar Saved-You badge, call-detail
 * counterfactual) is a teaser pointing here.
 */

import { CircleDollarSign } from "lucide-react";
import { useState } from "react";
import { CostKpiStrip } from "@/components/cost-explorer/kpi-strip";
import { CostHeroChart } from "@/components/cost-explorer/hero-chart";
import { CostPerOutcome } from "@/components/cost-explorer/per-outcome";
import { CostWhatIfCalculator } from "@/components/cost-explorer/what-if-calculator";
import { CostParetoBreakdown } from "@/components/cost-explorer/pareto-breakdown";
import { CostTopCallsTable } from "@/components/cost-explorer/top-calls-table";

type WindowDays = 1 | 7 | 14 | 30;

const WINDOW_OPTIONS: { value: WindowDays; label: string }[] = [
  { value: 1, label: "24h" },
  { value: 7, label: "7d" },
  { value: 14, label: "14d" },
  { value: 30, label: "30d" },
];

export default function CostExplorerPage() {
  const [windowDays, setWindowDays] = useState<WindowDays>(14);

  return (
    <div className="cost-explorer">
      <section className="module-hero cost-explorer-hero">
        <div className="module-hero-header">
          <div>
            <span className="module-eyebrow">
              <CircleDollarSign aria-hidden="true" />
              Cost leak detection
            </span>
            <h1>Cost</h1>
            <p>
              Find where money is leaking across spend trend, waste attribution,
              outcome cost, model swaps, Pareto breakdowns, and expensive calls.
            </p>
          </div>
          <div className="cost-explorer-window" role="tablist" aria-label="Time window">
            {WINDOW_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                role="tab"
                aria-selected={windowDays === opt.value}
                className={`cost-window-btn ${windowDays === opt.value ? "active" : ""}`}
                onClick={() => setWindowDays(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      <CostKpiStrip windowDays={windowDays} />

      <CostHeroChart windowDays={windowDays} />

      <div className="cost-explorer-grid-2">
        <CostPerOutcome windowDays={windowDays} />
        <CostWhatIfCalculator windowDays={windowDays} />
      </div>

      <CostParetoBreakdown windowDays={windowDays} />

      <CostTopCallsTable windowDays={windowDays} />
    </div>
  );
}
