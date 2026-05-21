"use client";

import { useEffect, useMemo, useState } from "react";
import { getCostByModel, getCostDailyTrend } from "@/lib/api";
import { formatUsd } from "@/lib/format";
import type { CostBreakdownResponse, CostDailyTrendResponse } from "@/lib/types";

/**
 * CostWhatIfCalculator — "if I switched model X to model Y, I'd save $Z"
 *
 * Uses the actual 14/30d traffic mix per model and known per-token pricing
 * to project savings (or added cost) of a model swap.
 *
 * Pricing catalog is embedded here (kept in sync with /pricing_config.json
 * + commonly-quoted alternatives). When the backend's `pricing_catalog`
 * endpoint ships, swap to that. For now this is a defensible static map
 * — the user reviews the swap before acting on it.
 *
 * This is the "demo wow" feature — competitors don't show this at all.
 */

/**
 * Approximate per-1M-token blended price for output-heavy chat workloads.
 * Calculated as input_per_1m * 0.4 + output_per_1m * 0.6 — matches what
 * most users actually experience for chat/agent traffic where output is
 * the dominant share. Kept conservative; final savings always show a
 * range, not a single number.
 */
const MODEL_BLENDED_PRICE: Record<string, { provider: string; blendedPer1M: number }> = {
  // OpenAI
  "gpt-4o": { provider: "openai", blendedPer1M: 11.0 },
  "gpt-4o-mini": { provider: "openai", blendedPer1M: 0.39 },
  "gpt-4-turbo": { provider: "openai", blendedPer1M: 22.0 },
  "gpt-4": { provider: "openai", blendedPer1M: 42.0 },
  "gpt-3.5-turbo": { provider: "openai", blendedPer1M: 1.1 },
  "o3": { provider: "openai", blendedPer1M: 33.0 }, // reasoning blended
  "o3-mini": { provider: "openai", blendedPer1M: 3.5 },

  // Anthropic
  "claude-3-7-sonnet": { provider: "anthropic", blendedPer1M: 10.2 },
  "claude-3-5-sonnet": { provider: "anthropic", blendedPer1M: 9.0 },
  "claude-3-5-haiku": { provider: "anthropic", blendedPer1M: 1.6 },
  "claude-3-opus": { provider: "anthropic", blendedPer1M: 45.0 },
  "claude-3-haiku": { provider: "anthropic", blendedPer1M: 0.6 },

  // Google
  "gemini-2.5-pro": { provider: "google", blendedPer1M: 7.7 },
  "gemini-1.5-pro": { provider: "google", blendedPer1M: 5.0 },
  "gemini-1.5-flash": { provider: "google", blendedPer1M: 0.3 },
};

function normalizeModelKey(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const trimmed = raw.toLowerCase().trim();
  // Direct match
  if (MODEL_BLENDED_PRICE[trimmed]) return trimmed;
  // Try removing common version suffixes (e.g. gpt-4o-2024-08-06 → gpt-4o)
  for (const known of Object.keys(MODEL_BLENDED_PRICE)) {
    if (trimmed.startsWith(known)) return known;
  }
  return null;
}

export function CostWhatIfCalculator({ windowDays }: { windowDays: number }) {
  const [byModel, setByModel] = useState<CostBreakdownResponse | null>(null);
  const [trend, setTrend] = useState<CostDailyTrendResponse | null>(null);
  const [fromModel, setFromModel] = useState<string>("");
  const [toModel, setToModel] = useState<string>("gpt-4o-mini");

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    async function load() {
      const [byModelRes, trendRes] = await Promise.allSettled([
        getCostByModel(windowDays, controller.signal),
        getCostDailyTrend(windowDays, controller.signal),
      ]);
      if (cancelled) return;
      setByModel(byModelRes.status === "fulfilled" ? byModelRes.value : null);
      setTrend(trendRes.status === "fulfilled" ? trendRes.value : null);
    }

    void load();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [windowDays]);

  // Auto-pick the most expensive model as the default "from" once data lands
  useEffect(() => {
    if (!byModel?.items.length || fromModel) return;
    const sorted = [...byModel.items].sort((a, b) => b.total_cost_usd - a.total_cost_usd);
    const topKnown = sorted.find((it) => normalizeModelKey(it.key) !== null);
    if (topKnown) setFromModel(topKnown.key);
  }, [byModel, fromModel]);

  const knownModels = useMemo(
    () => Object.keys(MODEL_BLENDED_PRICE).sort(),
    [],
  );

  // Build the list of selectable "from" models from observed usage
  const observedModels = useMemo(() => {
    return (byModel?.items ?? [])
      .filter((it) => normalizeModelKey(it.key) !== null)
      .sort((a, b) => b.total_cost_usd - a.total_cost_usd);
  }, [byModel]);

  const projection = useMemo(() => {
    if (!fromModel || !toModel) return null;
    const fromKey = normalizeModelKey(fromModel);
    const toKey = normalizeModelKey(toModel);
    if (!fromKey || !toKey) return null;
    const fromPrice = MODEL_BLENDED_PRICE[fromKey].blendedPer1M;
    const toPrice = MODEL_BLENDED_PRICE[toKey].blendedPer1M;

    const fromItem = byModel?.items.find(
      (it) => normalizeModelKey(it.key) === fromKey,
    );
    if (!fromItem) return null;

    const observedSpend = fromItem.total_cost_usd;
    // Implied savings ratio (price drop)
    const ratio = fromPrice > 0 ? toPrice / fromPrice : 1;
    const projectedSpend = observedSpend * ratio;
    const savingsUsd = observedSpend - projectedSpend;
    const savingsPct = observedSpend > 0 ? savingsUsd / observedSpend : 0;

    // Project to annualized as well — the "wow factor" number
    const annualMultiplier = 365 / Math.max(1, windowDays);
    const annualSavings = savingsUsd * annualMultiplier;

    // Confidence is naive — we just attach a wide ±25% band acknowledging
    // that the actual blend (token-level) may differ from our heuristic.
    const lowerSavings = savingsUsd * 0.75;
    const upperSavings = savingsUsd * 1.25;

    return {
      observedSpend,
      projectedSpend,
      savingsUsd,
      savingsPct,
      annualSavings,
      lowerSavings,
      upperSavings,
      callCount: fromItem.call_count,
      direction: savingsUsd >= 0 ? "save" : "cost",
    };
  }, [fromModel, toModel, byModel, windowDays]);

  const totalWindowSpend = trend?.points.reduce(
    (s, p) => s + p.total_cost_usd,
    0,
  ) ?? 0;

  return (
    <section className="cost-whatif panel">
      <header className="panel-header">
        <div>
          <h3>What if you switched models?</h3>
          <p>
            Project savings against your actual {windowDays}-day mix.
            Conservative ±25% band.
          </p>
        </div>
      </header>

      {observedModels.length === 0 ? (
        <p className="cost-whatif-empty">
          No recognized models in observed traffic yet. Send some calls and
          come back.
        </p>
      ) : (
        <>
          <div className="cost-whatif-controls">
            <label className="cost-whatif-field">
              <span>Switch from</span>
              <select
                value={fromModel}
                onChange={(e) => setFromModel(e.target.value)}
                className="mono"
              >
                {observedModels.map((it) => (
                  <option key={it.key} value={it.key}>
                    {it.key} ({formatUsd(it.total_cost_usd)})
                  </option>
                ))}
              </select>
            </label>
            <span className="cost-whatif-arrow" aria-hidden="true">→</span>
            <label className="cost-whatif-field">
              <span>To</span>
              <select
                value={toModel}
                onChange={(e) => setToModel(e.target.value)}
                className="mono"
              >
                {knownModels.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {projection ? (
            <div
              className={`cost-whatif-result cost-whatif-result-${projection.direction}`}
              role="status"
            >
              <div className="cost-whatif-headline">
                <strong className="cost-whatif-headline-amount mono">
                  {projection.direction === "save" ? "Save" : "Adds"}{" "}
                  {formatUsd(Math.abs(projection.savingsUsd))}
                </strong>
                <span className="cost-whatif-headline-window">
                  over last {windowDays}d
                </span>
              </div>
              <div className="cost-whatif-bands">
                <span>
                  Range: <span className="mono">
                    {formatUsd(Math.abs(projection.lowerSavings))} – {formatUsd(Math.abs(projection.upperSavings))}
                  </span>
                </span>
                <span>
                  Annualized: <strong className="mono">
                    {formatUsd(Math.abs(projection.annualSavings))}/yr
                  </strong>
                </span>
              </div>
              <dl className="cost-whatif-detail-grid">
                <div>
                  <dt>Current spend on {fromModel}</dt>
                  <dd className="mono">{formatUsd(projection.observedSpend)}</dd>
                </div>
                <div>
                  <dt>Projected on {toModel}</dt>
                  <dd className="mono">{formatUsd(projection.projectedSpend)}</dd>
                </div>
                <div>
                  <dt>% of window spend affected</dt>
                  <dd className="mono">
                    {totalWindowSpend > 0
                      ? `${((projection.observedSpend / totalWindowSpend) * 100).toFixed(1)}%`
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Calls in scope</dt>
                  <dd className="mono">{projection.callCount.toLocaleString()}</dd>
                </div>
              </dl>
              <footer className="cost-whatif-caveat">
                Estimate uses blended per-1M-token pricing (40% input / 60%
                output mix). Verify quality on your goldens before switching
                — savings only count if accuracy holds.
              </footer>
            </div>
          ) : (
            <p className="cost-whatif-empty">Pick two models to compare.</p>
          )}
        </>
      )}
    </section>
  );
}
