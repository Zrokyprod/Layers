"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useAlerts } from "@/lib/hooks";
import { getDetectorMeta } from "@/lib/detector-meta";
import type { AlertItemResponse } from "@/lib/types";

/**
 * PriorityQueue — "what should I look at right now?" widget for the home page.
 *
 * Ranks OPEN alerts by a single composite score so the engineer doesn't have
 * to triage 200 rows by hand. Score = severity_weight × log(occurrence+1) ×
 * blast_radius_weight × recency_decay.
 *
 *   - severity_weight: critical=10, high=5, medium=2, low=1
 *   - occurrence:      from evidence.occurrence_count (logged so a 1000-occ
 *                      issue doesn't completely dominate a 5-occ critical one)
 *   - blast_radius:    USD impact normalized log-scale
 *   - recency_decay:   half-life of 12h — fresh alerts rank above stale ones
 *
 * This is intentionally a pure client-side ranking on top of the existing
 * /v1/alerts route — no new backend work. The formula constants are tuned
 * to surface the "screams loudest" alert first while still letting a wave
 * of medium-severity alerts beat a single stale critical.
 *
 * Cap at 5 items. The whole point of a Priority Queue is that it's NOT a
 * second alerts list — it's the "open dashboard, do these 5 things" pull.
 */

const SEVERITY_WEIGHT: Record<string, number> = {
  critical: 10,
  high: 5,
  medium: 2,
  low: 1,
};

const RECENCY_HALF_LIFE_HOURS = 12;
const MAX_ITEMS = 5;

interface RankedAlert {
  alert: AlertItemResponse;
  score: number;
  /** What drove the score, in order. Used for the "why this one" tooltip. */
  factors: string[];
}

function asNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function formatUsdCompact(n: number): string {
  if (n < 1) return `$${n.toFixed(2)}`;
  if (n < 100) return `$${n.toFixed(2)}`;
  if (n < 1000) return `$${Math.round(n)}`;
  if (n < 1_000_000) return `$${(n / 1000).toFixed(1)}k`;
  return `$${(n / 1_000_000).toFixed(1)}M`;
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return "—";
  const deltaMs = Date.now() - then;
  const mins = Math.floor(deltaMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function rank(items: readonly AlertItemResponse[]): RankedAlert[] {
  const now = Date.now();
  const ranked: RankedAlert[] = items.map((alert) => {
    const sevKey = (alert.severity || "low").toLowerCase();
    const sevWeight = SEVERITY_WEIGHT[sevKey] ?? 1;

    const ev = (alert.evidence ?? {}) as Record<string, unknown>;
    const occurrences = Math.max(1, asNumber(ev.occurrence_count) ?? 1);
    const occFactor = Math.log10(occurrences + 1) + 1; // ≥1

    const blastUsd = asNumber(ev.blast_radius_usd) ?? asNumber(ev.cost_impact_usd) ?? 0;
    // 1 + log10(blast+1) so $0 alerts still score on severity alone.
    const blastFactor = 1 + Math.log10(Math.max(0, blastUsd) + 1);

    const createdMs = new Date(alert.created_at).getTime();
    const ageHours = Number.isFinite(createdMs)
      ? Math.max(0, (now - createdMs) / (1000 * 60 * 60))
      : 0;
    const recencyDecay = Math.pow(0.5, ageHours / RECENCY_HALF_LIFE_HOURS); // (0,1]

    const score = sevWeight * occFactor * blastFactor * recencyDecay;

    const factors: string[] = [`${sevKey} severity`];
    if (occurrences > 1) factors.push(`${Math.round(occurrences)} occurrences`);
    if (blastUsd > 0) factors.push(`${formatUsdCompact(blastUsd)} impact`);
    factors.push(formatRelative(alert.created_at));

    return { alert, score, factors };
  });

  ranked.sort((a, b) => b.score - a.score);
  return ranked.slice(0, MAX_ITEMS);
}

export function PriorityQueue() {
  const alertsQuery = useAlerts({ status: "OPEN", limit: 50 });

  const ranked = useMemo<RankedAlert[]>(() => {
    const items = alertsQuery.data?.items ?? [];
    return rank(items);
  }, [alertsQuery.data]);

  if (alertsQuery.isLoading) {
    return (
      <article className="priority-queue panel" aria-label="Today's Priority queue">
        <header className="panel-header">
          <div>
            <h3>Today’s Priority</h3>
            <p>The five issues most worth your attention right now.</p>
          </div>
        </header>
        <p className="priority-queue-empty">Loading priorities…</p>
      </article>
    );
  }

  if (ranked.length === 0) {
    return (
      <article className="priority-queue panel" aria-label="Today's Priority queue">
        <header className="panel-header">
          <div>
            <h3>Today’s Priority</h3>
            <p>The five issues most worth your attention right now.</p>
          </div>
        </header>
        <p className="priority-queue-empty">
          <span aria-hidden="true">✓</span> Inbox zero — nothing open right now.
        </p>
      </article>
    );
  }

  return (
    <article className="priority-queue panel" aria-label="Today's Priority queue">
      <header className="panel-header">
        <div>
          <h3>Today’s Priority</h3>
          <p>Top {ranked.length} ranked by severity × occurrence × blast × recency.</p>
        </div>
        <Link href="/alerts?status=OPEN" className="priority-queue-see-all">
          See all open →
        </Link>
      </header>

      <ol className="priority-queue-list">
        {ranked.map(({ alert, factors }, idx) => {
          const meta = getDetectorMeta(alert.category);
          return (
            <li key={alert.alert_id} className="priority-queue-item">
              <Link
                href={`/alerts/${alert.alert_id}`}
                className="priority-queue-link"
              >
                <span className="priority-queue-rank mono" aria-hidden="true">
                  #{idx + 1}
                </span>
                <div className="priority-queue-body">
                  <div className="priority-queue-title-row">
                    <span
                      className={`priority-queue-badge badge-${meta.badgeColor}`}
                      title={meta.description}
                    >
                      <span aria-hidden="true">{meta.icon}</span> {meta.label}
                    </span>
                    <span
                      className={`priority-queue-severity sev-${(alert.severity || "low").toLowerCase()}`}
                    >
                      {alert.severity || "low"}
                    </span>
                  </div>
                  <p className="priority-queue-headline">{alert.title}</p>
                  <p className="priority-queue-factors">{factors.join(" · ")}</p>
                </div>
                <span className="priority-queue-cta" aria-hidden="true">
                  →
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </article>
  );
}
