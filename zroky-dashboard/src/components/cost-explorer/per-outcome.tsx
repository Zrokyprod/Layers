"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getCostByUser,
  getCostDailyTrend,
  getSavingsSummary,
} from "@/lib/api";
import { formatUsd } from "@/lib/format";
import type {
  CostBreakdownResponse,
  CostDailyTrendResponse,
  SavingsSummaryResponse,
} from "@/lib/types";

/**
 * CostPerOutcome — the "ROI" framing that finance buyers ask for.
 *
 * Three ratios that turn raw cost into business signal:
 *
 *   $/successful call → cost efficiency
 *      total_cost / (calls - failed_calls)
 *
 *   $/active user      → unit economics
 *      total_cost / distinct_user_count (from /cost/by-user)
 *
 *   $/issue resolved   → value delivered
 *      cumulative_resolved_blast / total_resolved_count
 *
 * Engineering-only products show raw cost. Finance-friendly products show
 * cost per outcome. This is the metric that gets the CFO to say yes.
 */

export function CostPerOutcome({ windowDays }: { windowDays: number }) {
  const [trend, setTrend] = useState<CostDailyTrendResponse | null>(null);
  const [byUser, setByUser] = useState<CostBreakdownResponse | null>(null);
  const [savings, setSavings] = useState<SavingsSummaryResponse | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    async function load() {
      const [trendRes, byUserRes, savingsRes] = await Promise.allSettled([
        getCostDailyTrend(windowDays, controller.signal),
        getCostByUser(windowDays, controller.signal),
        getSavingsSummary(windowDays, controller.signal),
      ]);
      if (cancelled) return;
      setTrend(trendRes.status === "fulfilled" ? trendRes.value : null);
      setByUser(byUserRes.status === "fulfilled" ? byUserRes.value : null);
      setSavings(savingsRes.status === "fulfilled" ? savingsRes.value : null);
    }

    void load();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [windowDays]);

  const metrics = useMemo(() => {
    const totalCost = (trend?.points ?? []).reduce(
      (s, p) => s + p.total_cost_usd,
      0,
    );
    const totalCalls = (trend?.points ?? []).reduce(
      (s, p) => s + p.call_count,
      0,
    );
    const failedCalls = (trend?.points ?? []).reduce(
      (s, p) => s + p.failed_call_count,
      0,
    );
    const successfulCalls = Math.max(0, totalCalls - failedCalls);

    const userCount = byUser?.items.length ?? 0;
    const resolvedBlast = savings?.cumulative_resolved_blast_usd ?? 0;
    const resolvedCount = savings?.total_resolved_count ?? 0;

    return {
      totalCost,
      successfulCalls,
      totalCalls,
      failedCalls,
      userCount,
      resolvedBlast,
      resolvedCount,
      perSuccess: successfulCalls > 0 ? totalCost / successfulCalls : null,
      perUser: userCount > 0 ? totalCost / userCount : null,
      perResolved: resolvedCount > 0 ? resolvedBlast / resolvedCount : null,
    };
  }, [trend, byUser, savings]);

  return (
    <section className="cost-outcome panel">
      <header className="panel-header">
        <div>
          <h3>Cost per outcome</h3>
          <p>Unit economics — the metrics finance asks for.</p>
        </div>
      </header>

      <div className="cost-outcome-grid">
        <article className="cost-outcome-card">
          <header>Per successful call</header>
          <strong className="cost-outcome-value mono">
            {metrics.perSuccess !== null ? formatUsd(metrics.perSuccess) : "—"}
          </strong>
          <p className="cost-outcome-denominator">
            {metrics.successfulCalls.toLocaleString()} successful calls
            {metrics.failedCalls > 0 ? (
              <span className="cost-outcome-fail-note">
                {" "}
                · {metrics.failedCalls.toLocaleString()} failed excluded
              </span>
            ) : null}
          </p>
        </article>

        <article className="cost-outcome-card">
          <header>Per active user</header>
          <strong className="cost-outcome-value mono">
            {metrics.perUser !== null ? formatUsd(metrics.perUser) : "—"}
          </strong>
          <p className="cost-outcome-denominator">
            {metrics.userCount.toLocaleString()} active user
            {metrics.userCount === 1 ? "" : "s"} in window
          </p>
        </article>

        <article className="cost-outcome-card cost-outcome-value-saved">
          <header>Per issue resolved</header>
          <strong className="cost-outcome-value mono">
            {metrics.perResolved !== null ? formatUsd(metrics.perResolved) : "—"}
          </strong>
          <p className="cost-outcome-denominator">
            avg savings · {metrics.resolvedCount.toLocaleString()} resolved
          </p>
        </article>
      </div>

      <footer className="cost-outcome-footer">
        Window total: <strong className="mono">{formatUsd(metrics.totalCost)}</strong>
        {" "}across {metrics.totalCalls.toLocaleString()} calls.
      </footer>
    </section>
  );
}
