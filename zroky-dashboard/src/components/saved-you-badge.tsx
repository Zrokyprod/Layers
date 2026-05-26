"use client";

import { useEffect, useMemo, useState } from "react";
import { ShieldCheck } from "lucide-react";

import { getSavingsSummary } from "@/lib/api";
import type { SavingsSummaryResponse } from "@/lib/types";

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
        // Decorative ROI badge; never break the top bar.
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
    const saved = data.cumulative_resolved_blast_usd + data.projected_averted_usd;
    return saved > 0 ? saved : null;
  }, [data]);

  if (headline === null || !data) return null;

  const tooltip =
    `Last ${data.window_days}d:\n` +
    `- ${data.total_resolved_count} issues resolved\n` +
    `- ${formatUsdCompact(data.cumulative_resolved_blast_usd)} caught and resolved\n` +
    `- +${formatUsdCompact(data.projected_averted_usd)} projected 6h savings\n` +
    (data.cumulative_wasted_usd > 0
      ? `- ${formatUsdCompact(data.cumulative_wasted_usd)} still open (${data.total_caught_count - data.total_resolved_count} issues)`
      : "");

  return (
    <span
      className="saved-you-badge"
      title={tooltip}
      aria-label={`Saved by Zroky in last ${data.window_days} days: ${formatUsdCompact(headline)}`}
    >
      <ShieldCheck className="saved-you-icon" aria-hidden="true" />
      <span className="saved-you-label">Saved</span>
      <strong className="saved-you-value mono">{formatUsdCompact(headline)}</strong>
    </span>
  );
}
