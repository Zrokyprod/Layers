"use client";

import { useMemo } from "react";

/**
 * CounterfactualImpact — "what Zroky just prevented".
 *
 * Renders an emotional ROI callout: projects the impact of THIS specific
 * issue forward in time as if it hadn't been caught, and frames it as
 * "saved by Zroky" with concrete numbers.
 *
 * Pulls signals defensively from the diagnosis envelope:
 *   - `blast_radius_usd` — cumulative cost-so-far (already wasted)
 *   - `occurrence_count` — number of times this fingerprint fired
 *   - `evidence.cost_impact_usd` / `evidence.wasted_cost_usd`
 *   - `evidence.current_15m_spend_usd` + `evidence.baseline_15m_spend_usd`
 *   - `evidence.tokens_wasted` / `evidence.iterations`
 *   - `comparison_multiplier` / `anomaly_multiplier`
 *
 * If we can't ground a counterfactual in real numbers, we render nothing —
 * we never make up figures. Better silent than fictional.
 *
 * The projection window is fixed at 6h (a reasonable response-time floor
 * before a human would have caught a runaway agent without monitoring).
 * Multipliers below derive from the "if not caught, how much longer would
 * it have burned" assumption and are tunable via the constants block.
 */

const PROJECTION_HOURS = 6;

interface CounterfactualImpactProps {
  /** Full diagnosis object (typically `detail.diagnosis_result.diagnoses[0]`). */
  diagnosis: Record<string, unknown> | null | undefined;
  /** Evidence sub-object (defaults to `diagnosis.evidence`). */
  evidence?: Record<string, unknown> | null;
}

interface Projection {
  alreadyWastedUsd: number | null;
  projectedAdditionalUsd: number | null;
  affectedCalls: number | null;
  rationale: string;
  /** Display sub-heading describing how the figure was computed. */
  basis: string;
}

function asNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function formatUsd(n: number): string {
  if (n === 0) return "$0";
  if (n < 0.01) return "<$0.01";
  if (n < 1) return `$${n.toFixed(2)}`;
  if (n < 100) return `$${n.toFixed(2)}`;
  return `$${Math.round(n).toLocaleString()}`;
}

function formatCount(n: number): string {
  if (n < 1000) return `${Math.round(n)}`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

function buildProjection(
  diagnosis: Record<string, unknown>,
  evidence: Record<string, unknown>,
): Projection | null {
  const alreadyWastedUsd =
    asNumber(diagnosis.blast_radius_usd) ??
    asNumber(evidence.cost_impact_usd) ??
    asNumber(evidence.wasted_cost_usd) ??
    null;

  const occurrenceCount = asNumber(diagnosis.occurrence_count);

  // Path A: explicit per-15m spend rate (cost-spike evidence)
  const current15m = asNumber(evidence.current_15m_spend_usd);
  const baseline15m = asNumber(evidence.baseline_15m_spend_usd);
  if (current15m !== null && current15m > 0 && baseline15m !== null) {
    const excessPer15m = Math.max(0, current15m - baseline15m);
    if (excessPer15m > 0) {
      const projectedAdditionalUsd = excessPer15m * (PROJECTION_HOURS * 4); // 4 fifteen-minute slices per hour
      return {
        alreadyWastedUsd,
        projectedAdditionalUsd,
        affectedCalls: occurrenceCount,
        rationale: `If this cost-spike continued at current burn, the next ${PROJECTION_HOURS}h would add roughly ${formatUsd(projectedAdditionalUsd)} on top of baseline.`,
        basis: `current ${formatUsd(current15m)} vs baseline ${formatUsd(baseline15m)} per 15m`,
      };
    }
  }

  // Path B: extrapolate from cumulative blast radius assuming same incident rate
  if (alreadyWastedUsd !== null && alreadyWastedUsd > 0 && occurrenceCount !== null && occurrenceCount > 0) {
    // Crude assumption: incidents continue at the same rate; one incident-cost worth
    // of waste per hour absent monitoring. Conservative — clearly framed as a
    // projection, never as an exact prediction.
    const perIncidentUsd = alreadyWastedUsd / occurrenceCount;
    const projectedAdditionalUsd = perIncidentUsd * PROJECTION_HOURS;
    return {
      alreadyWastedUsd,
      projectedAdditionalUsd,
      affectedCalls: occurrenceCount * PROJECTION_HOURS,
      rationale: `If this issue continued unattended for ${PROJECTION_HOURS}h, it would have added roughly ${formatUsd(projectedAdditionalUsd)} and impacted ~${formatCount(
        occurrenceCount * PROJECTION_HOURS,
      )} calls.`,
      basis: `extrapolated from ${formatCount(occurrenceCount)} occurrences and ${formatUsd(alreadyWastedUsd)} wasted so far`,
    };
  }

  // Path C: minimal — only the already-wasted figure, no projection
  if (alreadyWastedUsd !== null && alreadyWastedUsd > 0) {
    return {
      alreadyWastedUsd,
      projectedAdditionalUsd: null,
      affectedCalls: occurrenceCount,
      rationale: `Zroky caught this incident after ${formatUsd(alreadyWastedUsd)} of waste — projection unavailable without a baseline reference.`,
      basis: "no baseline reference available",
    };
  }

  return null;
}

export function CounterfactualImpact({
  diagnosis,
  evidence,
}: CounterfactualImpactProps) {
  const projection = useMemo(() => {
    if (!diagnosis) return null;
    const ev = (evidence ??
      (diagnosis as Record<string, unknown>).evidence ??
      {}) as Record<string, unknown>;
    return buildProjection(diagnosis as Record<string, unknown>, ev);
  }, [diagnosis, evidence]);

  if (!projection) return null;

  const total =
    (projection.alreadyWastedUsd ?? 0) +
    (projection.projectedAdditionalUsd ?? 0);

  return (
    <article className="counterfactual-card" aria-label="Counterfactual impact">
      <header className="counterfactual-header">
        <div className="counterfactual-eyebrow">
          <span aria-hidden="true">🛡</span> Saved by Zroky
        </div>
        {total > 0 ? (
          <div className="counterfactual-total">
            <span className="counterfactual-total-label">total averted</span>
            <strong className="mono counterfactual-total-value">
              {formatUsd(total)}
            </strong>
          </div>
        ) : null}
      </header>

      <p className="counterfactual-rationale">{projection.rationale}</p>

      <div className="counterfactual-stats">
        {projection.alreadyWastedUsd !== null && projection.alreadyWastedUsd > 0 ? (
          <div className="counterfactual-stat">
            <span className="counterfactual-stat-label">Wasted so far</span>
            <strong className="mono">{formatUsd(projection.alreadyWastedUsd)}</strong>
          </div>
        ) : null}
        {projection.projectedAdditionalUsd !== null ? (
          <div className="counterfactual-stat counterfactual-stat-projection">
            <span className="counterfactual-stat-label">
              Projected over next {PROJECTION_HOURS}h
            </span>
            <strong className="mono">
              +{formatUsd(projection.projectedAdditionalUsd)}
            </strong>
          </div>
        ) : null}
        {projection.affectedCalls !== null && projection.affectedCalls > 0 ? (
          <div className="counterfactual-stat">
            <span className="counterfactual-stat-label">Affected calls (proj.)</span>
            <strong className="mono">{formatCount(projection.affectedCalls)}</strong>
          </div>
        ) : null}
      </div>

      <footer className="counterfactual-footer">{projection.basis}</footer>
    </article>
  );
}
