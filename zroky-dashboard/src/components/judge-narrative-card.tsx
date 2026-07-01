"use client";

import { useMemo, useState } from "react";

/**
 * AI Advisory Narrative Card - surfaces model-authored diagnostic reasoning as
 * non-authoritative context. It is useful for triage, not for policy authority
 * or proof.
 *
 * Distinct from `JudgeScorecard`:
 *   - Scorecard:  per-dimension bars + scores + small reason text.
 *   - Narrative:  ONE prominent quote - the lowest-scored dimension's reason,
 *                 attributed to the advisory model, with a copy-to-clipboard CTA.
 *
 * This narrative is advisory context only. It must not be treated as the
 * policy decision or system-of-record proof for a protected action.
 *
 * Renders only when the diagnosis evidence carries a Layer 3 detector's
 * reasoning text (groundedness_reason / accuracy_reason). Silent otherwise
 * so it's safe to drop into pages that may not have Layer 3 signals.
 */

interface JudgeNarrativeCardProps {
  /**
   * Source object — typically the diagnosis `evidence` dict written by the
   * `hallucination_risk` / `accuracy_regression` detectors.
   */
  source: Record<string, unknown> | null | undefined;
  /**
   * Detector category (e.g. "HALLUCINATION_RISK"). Used purely for the
   * hero subtitle. Falls back to a generic label when omitted.
   */
  category?: string | null;
}

interface Narrative {
  dimension: string;
  score: number | null;
  reason: string;
  /** Severity hint — drives the accent color. */
  severity: "critical" | "high" | "medium";
}

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

function extractStrongestNarrative(src: Record<string, unknown>): Narrative | null {
  // Layer 3 detector shape (evidence dict).
  const groundednessReason = asString(src.groundedness_reason);
  const groundednessScore = asNumber(src.groundedness_score);
  const groundednessFloor = asNumber(src.groundedness_floor);

  const accuracyReason = asString(src.accuracy_reason);
  const accuracyScore = asNumber(src.accuracy_score);
  const accuracyFloor = asNumber(src.absolute_floor);

  const candidates: Narrative[] = [];

  if (groundednessReason) {
    const breached =
      groundednessFloor !== null &&
      groundednessScore !== null &&
      groundednessScore < groundednessFloor;
    candidates.push({
      dimension: "groundedness",
      score: groundednessScore,
      reason: groundednessReason,
      severity: breached ? "critical" : "medium",
    });
  }
  if (accuracyReason) {
    const breached =
      accuracyFloor !== null &&
      accuracyScore !== null &&
      accuracyScore < accuracyFloor;
    candidates.push({
      dimension: "accuracy",
      score: accuracyScore,
      reason: accuracyReason,
      severity: breached ? "critical" : "medium",
    });
  }

  // Replay-trace shape: dimensions.{name}.reason
  const dimsBlock = src.dimensions;
  if (dimsBlock && typeof dimsBlock === "object" && !Array.isArray(dimsBlock)) {
    for (const [name, raw] of Object.entries(dimsBlock as Record<string, unknown>)) {
      if (raw && typeof raw === "object" && !Array.isArray(raw)) {
        const reason = asString((raw as Record<string, unknown>).reason);
        const score = asNumber((raw as Record<string, unknown>).score);
        if (reason) {
          const severity: Narrative["severity"] =
            score !== null && score < 0.4 ? "critical" : score !== null && score < 0.6 ? "high" : "medium";
          candidates.push({ dimension: name, score, reason, severity });
        }
      }
    }
  }

  if (candidates.length === 0) return null;

  // Pick the lowest-scored / most-severe narrative.
  candidates.sort((a, b) => {
    const sev = { critical: 0, high: 1, medium: 2 } as const;
    if (sev[a.severity] !== sev[b.severity]) return sev[a.severity] - sev[b.severity];
    const ascore = a.score ?? 1;
    const bscore = b.score ?? 1;
    return ascore - bscore;
  });
  return candidates[0];
}

export function JudgeNarrativeCard({ source, category }: JudgeNarrativeCardProps) {
  const [copied, setCopied] = useState(false);

  const narrative = useMemo(
    () => (source ? extractStrongestNarrative(source as Record<string, unknown>) : null),
    [source],
  );
  const model = source ? asString((source as Record<string, unknown>).judge_model) : null;
  const verdict = source ? asString((source as Record<string, unknown>).judge_verdict) : null;
  const confidence = source ? asNumber((source as Record<string, unknown>).judge_confidence) : null;

  if (!narrative) return null;

  // Capture into a const so the inner closures keep the non-null narrowing
  // — TypeScript doesn't propagate the `if (!narrative) return null` guard
  // into nested function declarations.
  const n: Narrative = narrative;
  const heroCategory = category && category.trim() ? category : "AI advisory";
  const accent = n.severity; // critical | high | medium → CSS class

  function buildShareText(): string {
    const parts: string[] = [];
    parts.push(`AI advisory on ${n.dimension}:`);
    parts.push(`"${n.reason}"`);
    const meta: string[] = [];
    if (model) meta.push(`model: ${model}`);
    if (verdict) meta.push(`advisory verdict: ${verdict}`);
    if (n.score !== null) meta.push(`score: ${n.score.toFixed(2)}`);
    if (confidence !== null) meta.push(`confidence: ${(confidence * 100).toFixed(0)}%`);
    if (meta.length > 0) parts.push(`- ${meta.join(", ")}`);
    parts.push("Advisory only. Policy decisions and system-of-record proof remain authoritative.");
    return parts.join("\n");
  }

  async function copyShareText() {
    try {
      await navigator.clipboard.writeText(buildShareText());
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard write can fail in non-secure contexts. Silent — the button
      // resets to "Copy" and the user can select the text manually.
    }
  }

  return (
    <article className={`judge-narrative judge-narrative-${accent}`} aria-label="AI advisory narrative">
      <header className="judge-narrative-header">
        <div className="judge-narrative-eyebrow">
          <span aria-hidden="true">AI</span> {heroCategory}
          {narrative.dimension ? (
            <span className="judge-narrative-eyebrow-sub">· {narrative.dimension}</span>
          ) : null}
        </div>
        <button
          type="button"
          className="judge-narrative-copy-btn"
          onClick={() => void copyShareText()}
          aria-label="Copy advisory text to clipboard"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </header>

      <blockquote className="judge-narrative-quote">
        <p>&ldquo;{narrative.reason}&rdquo;</p>
      </blockquote>

      <footer className="judge-narrative-footer">
        {model ? <span className="mono judge-narrative-model">{model}</span> : null}
        {verdict ? (
          <span className={`judge-narrative-verdict judge-narrative-verdict-${verdict}`}>
            Advisory: {verdict}
          </span>
        ) : null}
        {narrative.score !== null ? (
          <span className="judge-narrative-score">
            <strong>{narrative.dimension}</strong>:{" "}
            <span className="mono">{narrative.score.toFixed(2)}</span>
          </span>
        ) : null}
        {confidence !== null ? (
          <span className="judge-narrative-confidence">
            confidence <span className="mono">{(confidence * 100).toFixed(0)}%</span>
          </span>
        ) : null}
        <span className="judge-narrative-confidence">advisory only</span>
      </footer>
    </article>
  );
}
