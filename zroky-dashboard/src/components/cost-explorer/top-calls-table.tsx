"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getCostTopCalls } from "@/lib/api";
import { formatUsd } from "@/lib/format";
import type { CostTopCallItem, CostTopCallsResponse } from "@/lib/types";

/**
 * CostTopCallsTable — "where is my money actually going?"
 *
 * The Pareto breakdown shows cost by model/user/agent aggregates. This table
 * shows the individual calls that drove the highest spend in the window —
 * useful for debugging runaway agents, unexpectedly expensive prompts, or
 * pinpointing which failed calls wasted the most money.
 *
 * Backend: GET /v1/analytics/cost/top-calls?limit=10&hours={windowDays*24}
 */

function statusColor(status: string): string {
  if (status === "success") return "var(--color-green)";
  if (status === "error" || status === "failed") return "var(--color-red)";
  return "var(--color-muted)";
}

export function CostTopCallsTable({ windowDays }: { windowDays: number }) {
  const [data, setData] = useState<CostTopCallsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError(null);

    getCostTopCalls(10, windowDays * 24, controller.signal)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e: unknown) => {
        if ((e as { name?: string }).name === "AbortError") return;
        if (!cancelled) setError((e as { message?: string }).message ?? "Failed to load.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [windowDays]);

  return (
    <section className="panel" aria-label="Top calls by cost">
      <header className="panel-header">
        <div>
          <h3>Top Calls by Cost</h3>
          <p>Most expensive individual calls in the last {windowDays}d window.</p>
        </div>
      </header>

      {loading && <div className="loading" />}

      {error && (
        <p className="notif-error" style={{ padding: "0.75rem" }}>
          {error}
        </p>
      )}

      {!loading && !error && (!data || data.items.length === 0) && (
        <div className="empty">No calls recorded in this window.</div>
      )}

      {!loading && !error && data && data.items.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table className="data-table" style={{ width: "100%", fontSize: "0.85rem" }}>
            <thead>
              <tr>
                <th>Model</th>
                <th>Agent</th>
                <th>Status</th>
                <th>Error</th>
                <th style={{ textAlign: "right" }}>Cost</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((item: CostTopCallItem) => (
                <tr key={item.call_id}>
                  <td className="mono" style={{ fontSize: "0.78rem" }}>
                    {item.model ?? item.provider ?? "—"}
                  </td>
                  <td style={{ maxWidth: "140px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {item.agent_name ?? "—"}
                  </td>
                  <td>
                    <span style={{ color: statusColor(item.status), fontWeight: 500 }}>
                      {item.status}
                    </span>
                  </td>
                  <td className="mono" style={{ fontSize: "0.75rem", color: "var(--color-red)" }}>
                    {item.error_code ?? "—"}
                  </td>
                  <td className="mono" style={{ textAlign: "right", fontWeight: 600 }}>
                    {formatUsd(item.cost_usd)}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <Link
                      href="/evidence"
                      className="btn btn-soft btn-sm"
                      style={{ whiteSpace: "nowrap" }}
                    >
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
