"use client";

import { useEffect, useState, useMemo } from "react";
import { getSavingsSummary } from "@/lib/api";
import type { SavingsSummaryResponse } from "@/lib/types";

/**
 * SavedYouBadge — persistent top-bar ROI counter.
 *
 * Polls /v1/analytics/savings every 60s. Shows the dominant figure
 * (resolved-blast + projected-averted) as a compact "Saved $X" pill.
 * Tooltip on hover exposes the breakdown.
 *
 * Renders nothing while loading or when the totals are zero — we never
 * show a "$0 saved" badge because that's worse than no badge.
 *
 * Why a separate widget (not on the home page only): this is the
 * persistent emotional anchor — every page-load reinforces value. The
 * counter is intentionally always-visible.
 */

const POLL_INTERVAL_MS = 60_000;
const SAVINGS_WINDOW_DAYS = 30;

function formatUsdCompact(n: number): string {
  if (n < 1) return `$${n.toFixed(2)}`;
  if (n < 1000) return `$${Math.round(n)}`;
  if (n < 10_000) return `$${(n / 1000).toFixed(1)}k`;
  if (n < 1_000_000) return `$${Math.round(n / 1000)}k`;
  return `$${(n / 1_000_000).toFixed(1)}M`;
}

export function SavedYouBadge() {
  const [data, setData] = useState<SavingsSummaryResponse | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    async function fetchOnce() {
      try {
        const res = await getSavingsSummary(SAVINGS_WINDOW_DAYS, controller.signal);
        if (!cancelled) setData(res);
      } catch {
        // Silent — savings widget is decorative; never break the topbar.
      }
    }

    void fetchOnce();
    const interval = window.setInterval(() => void fetchOnce(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(interval);
    };
  }, []);

  const headline = useMemo(() => {
    if (!data) return null;
    // Headline = "what would have been lost" — resolved + projected.
    // Open-but-still-bleeding is shown in the tooltip only; the badge
    // should celebrate saves, not surface noise.
    const saved = data.cumulative_resolved_blast_usd + data.projected_averted_usd;
    return saved > 0 ? saved : null;
  }, [data]);

  if (headline === null || !data) return null;

  const tooltip =
    `Last ${data.window_days}d:\n` +
    `• ${data.total_resolved_count} issues resolved\n` +
    `• ${formatUsdCompact(data.cumulative_resolved_blast_usd)} caught & resolved\n` +
    `• +${formatUsdCompact(data.projected_averted_usd)} projected 6h savings\n` +
    (data.cumulative_wasted_usd > 0
      ? `• ${formatUsdCompact(data.cumulative_wasted_usd)} still bleeding (${data.total_caught_count - data.total_resolved_count} open)`
      : "");

  return (
    <span
      className="saved-you-badge"
      title={tooltip}
      aria-label={`Saved by Zroky in last ${data.window_days} days: ${formatUsdCompact(headline)}`}
    >
      <span className="saved-you-icon" aria-hidden="true">🛡</span>
      <span className="saved-you-label">Saved</span>
      <strong className="saved-you-value mono">{formatUsdCompact(headline)}</strong>
    </span>
  );
}
