"use client";

import { useMemo } from "react";

/**
 * AI Advisory Scorecard - renders model-authored diagnostic scores in a compact,
 * visual format with bars, labels, and reasons. These scores are context for
 * review, not policy authority or proof.
 *
 * Pulls from two shapes the backend may produce:
 *
 *   1) Layer 3 evidence dicts emitted by `hallucination_risk.py` and
 *      `accuracy_regression.py` detectors:
 *
 *      {
 *        "judge_model": "anthropic/claude-haiku-4",
 *        "judge_verdict": "fail",
 *        "judge_confidence": 0.88,
 *        "groundedness_score": 0.15,
 *        "groundedness_floor": 0.35,
 *        "groundedness_reason": "...",
 *        "accuracy_score": 0.25,
 *        "accuracy_reason": "...",
 *        "other_dimensions": {"relevance": 0.80, "coherence": 0.75, ...},
 *        "judge_overall_score": 0.575
 *      }
 *
 *   2) Raw `judge_scores_json` payloads from replay traces (parsed object):
 *
 *      {
 *        "model": "anthropic/claude-haiku-4",
 *        "verdict": "fail",
 *        "confidence": 0.88,
 *        "overall_score": 0.575,
 *        "dimensions": {
 *          "groundedness": {"score": 0.15, "reason": "..."},
 *          "accuracy":     {"score": 0.25, "reason": "..."},
 *          ...
 *        }
 *      }
 *
 * This is advisory context only. It must not be treated as the policy decision
 * or system-of-record proof for a protected action.
 *
 * Returns null if no judge data is present — safe to drop into pages that
 * may or may not have Layer 3 signals.
 */

interface JudgeScorecardProps {
  source: Record<string, unknown> | null | undefined;
  title?: string;
}

interface DimensionEntry {
  name: string;
  score: number;
  reason: string | null;
  floor: number | null; // optional threshold for the score (e.g. groundedness floor)
  breached: boolean;
}

const DIMENSION_ORDER = [
  "accuracy",
  "faithfulness",
  "groundedness",
  "relevance",
  "coherence",
  "completeness",
] as const;

const DIMENSION_HINTS: Record<string, string> = {
  accuracy: "Semantic match against expected output.",
  faithfulness: "Stays faithful to the input prompt + tool context.",
  groundedness: "Every factual claim has source support.",
  relevance: "Addresses what the user actually asked.",
  coherence: "Reads cleanly without contradictions or rambling.",
  completeness: "Covers the full ask, not just part of it.",
};

function asNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function asString(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

function extractDimensions(
  source: Record<string, unknown>,
): DimensionEntry[] {
  const entries: DimensionEntry[] = [];

  // Shape 2: `dimensions` map present (replay-trace shape)
  const dimsBlock = source.dimensions;
  if (dimsBlock && typeof dimsBlock === "object" && !Array.isArray(dimsBlock)) {
    for (const [name, raw] of Object.entries(dimsBlock as Record<string, unknown>)) {
      if (raw && typeof raw === "object" && !Array.isArray(raw)) {
        const score = asNumber((raw as Record<string, unknown>).score);
        const reason = asString((raw as Record<string, unknown>).reason);
        if (score !== null) {
          entries.push({
            name,
            score,
            reason,
            floor: null,
            breached: false, // shape 2 doesn't carry per-dim breach floors
          });
        }
      } else {
        const flat = asNumber(raw);
        if (flat !== null) {
          entries.push({ name, score: flat, reason: null, floor: null, breached: false });
        }
      }
    }
  }

  // Shape 1: flattened evidence keys (e.g. groundedness_score, accuracy_score, other_dimensions)
  const groundedness = asNumber(source.groundedness_score);
  const groundednessFloor = asNumber(source.groundedness_floor);
  const groundednessReason = asString(source.groundedness_reason);
  if (groundedness !== null && !entries.some((e) => e.name === "groundedness")) {
    entries.push({
      name: "groundedness",
      score: groundedness,
      reason: groundednessReason,
      floor: groundednessFloor,
      breached: groundednessFloor !== null && groundedness < groundednessFloor,
    });
  }

  const accuracy = asNumber(source.accuracy_score);
  const accuracyFloor = asNumber(source.absolute_floor);
  const accuracyReason = asString(source.accuracy_reason);
  if (accuracy !== null && !entries.some((e) => e.name === "accuracy")) {
    entries.push({
      name: "accuracy",
      score: accuracy,
      reason: accuracyReason,
      floor: accuracyFloor,
      breached: accuracyFloor !== null && accuracy < accuracyFloor,
    });
  }

  const other = source.other_dimensions;
  if (other && typeof other === "object" && !Array.isArray(other)) {
    for (const [name, raw] of Object.entries(other as Record<string, unknown>)) {
      const score = asNumber(raw);
      if (score !== null && !entries.some((e) => e.name === name)) {
        entries.push({ name, score, reason: null, floor: null, breached: false });
      }
    }
  }

  // Stable ordering: known dims first in canonical order, then any extras alphabetically.
  const order = new Map<string, number>();
  DIMENSION_ORDER.forEach((n, i) => order.set(n, i));
  return entries.sort((a, b) => {
    const ai = order.get(a.name) ?? 999;
    const bi = order.get(b.name) ?? 999;
    if (ai !== bi) return ai - bi;
    return a.name.localeCompare(b.name);
  });
}

function colorForScore(score: number, floor: number | null): string {
  // Below explicit floor → red. Otherwise score-band coloring.
  if (floor !== null && score < floor) return "judge-bar-red";
  if (score < 0.4) return "judge-bar-red";
  if (score < 0.6) return "judge-bar-accent";
  if (score < 0.8) return "judge-bar-yellow";
  return "judge-bar-green";
}

export function JudgeScorecard({ source, title = "AI advisory scorecard" }: JudgeScorecardProps) {
  const dims = useMemo(
    () => (source ? extractDimensions(source as Record<string, unknown>) : []),
    [source],
  );

  if (!source) return null;
  if (dims.length === 0) return null;

  const model =
    asString((source as Record<string, unknown>).judge_model) ??
    asString((source as Record<string, unknown>).model);
  const verdict =
    asString((source as Record<string, unknown>).judge_verdict) ??
    asString((source as Record<string, unknown>).verdict);
  const confidence =
    asNumber((source as Record<string, unknown>).judge_confidence) ??
    asNumber((source as Record<string, unknown>).confidence);
  const overall =
    asNumber((source as Record<string, unknown>).judge_overall_score) ??
    asNumber((source as Record<string, unknown>).overall_score);

  return (
    <article className="judge-scorecard">
      <header className="judge-scorecard-header">
        <div>
          <h4>{title}</h4>
          <p>
            {model ? (
              <span className="mono">{model}</span>
            ) : (
              <span className="judge-scorecard-muted">judge model unknown</span>
            )}
            {verdict ? (
              <span className={`judge-scorecard-verdict judge-scorecard-verdict-${verdict}`}>
                Advisory: {verdict}
              </span>
            ) : null}
            {confidence !== null ? (
              <span className="judge-scorecard-muted">
                confidence {(confidence * 100).toFixed(0)}%
              </span>
            ) : null}
            <span className="judge-scorecard-muted">advisory only</span>
          </p>
        </div>
        {overall !== null ? (
          <div className="judge-scorecard-overall">
            <span className="judge-scorecard-overall-label">overall</span>
            <strong className="mono">{overall.toFixed(2)}</strong>
          </div>
        ) : null}
      </header>

      <div className="judge-scorecard-rows">
        {dims.map((dim) => {
          const pct = Math.max(0, Math.min(100, dim.score * 100));
          const colorClass = colorForScore(dim.score, dim.floor);
          return (
            <div
              key={dim.name}
              className={`judge-scorecard-row${dim.breached ? " judge-scorecard-row-breached" : ""}`}
              title={DIMENSION_HINTS[dim.name] ?? ""}
            >
              <div className="judge-scorecard-row-head">
                <strong className="judge-scorecard-dim-name">{dim.name}</strong>
                <span className="judge-scorecard-dim-score mono">
                  {dim.score.toFixed(2)}
                  {dim.floor !== null ? (
                    <span className="judge-scorecard-floor"> / floor {dim.floor.toFixed(2)}</span>
                  ) : null}
                </span>
              </div>
              <div className="judge-scorecard-bar-track">
                <div className={`judge-scorecard-bar ${colorClass}`} style={{ width: `${pct}%` }} />
                {dim.floor !== null ? (
                  <div
                    className="judge-scorecard-floor-marker"
                    style={{ left: `${Math.max(0, Math.min(100, dim.floor * 100))}%` }}
                    aria-hidden="true"
                  />
                ) : null}
              </div>
              {dim.reason ? (
                <p className="judge-scorecard-reason">
                  <em>Judge said:</em> {dim.reason}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
    </article>
  );
}
