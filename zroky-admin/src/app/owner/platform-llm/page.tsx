"use client";

import { useCallback, useEffect, useState } from "react";
import { Cpu, RotateCcw } from "lucide-react";
import { getPlatformLlmUsageSummary } from "@/lib/api";
import type { PlatformLlmUsageSummaryResponse } from "@/lib/types";

export default function PlatformLlmUsagePage() {
  const [data, setData] = useState<PlatformLlmUsageSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getPlatformLlmUsageSummary();
      setData(res);
    } catch (e: unknown) {
      const msg =
        typeof e === "object" && e && "message" in e
          ? (e as { message?: string }).message
          : undefined;
      setError(msg || "Failed to load platform LLM usage.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="owner-page">
      <div className="owner-page-header">
        <div className="owner-topbar-brand">
          <Cpu size={18} style={{ color: "var(--text-secondary)" }} />
          <h2 className="owner-page-title">Platform LLM Usage</h2>
        </div>
        <button type="button" className="btn btn-soft" onClick={load} disabled={loading}>
          <RotateCcw size={14} style={{ marginRight: 6 }} />
          Refresh
        </button>
      </div>

      {error && <div className="alert-strip alert-strip-error">{error}</div>}

      {loading && !data && <p className="hint">Loading usage data…</p>}

      {data && (
        <>
          <div className="owner-stat-grid">
            <MetricCard label="Total Calls" value={data.total_calls.toLocaleString()} />
            <MetricCard
              label="Total Cost"
              value={`$${data.total_cost_usd.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 6 })}`}
            />
            <MetricCard label="Total Tokens" value={data.total_tokens.toLocaleString()} />
            <MetricCard
              label="Avg Latency"
              value={`${data.avg_latency_ms.toLocaleString(undefined, { maximumFractionDigits: 0 })} ms`}
            />
          </div>

          <div className="owner-llm-panels">
            <div className="panel">
              <div className="panel-header">By Purpose</div>
              <div className="owner-llm-list">
                {Object.entries(data.by_purpose).length === 0 && (
                  <p className="hint">No usage by purpose yet.</p>
                )}
                {Object.entries(data.by_purpose).map(([purpose, stats]) => (
                  <div key={purpose} className="owner-llm-row">
                    <span style={{ textTransform: "capitalize" }}>{purpose.replace(/_/g, " ")}</span>
                    <div className="owner-llm-stats">
                      <p>{stats.calls.toLocaleString()} calls</p>
                      <p>{stats.tokens.toLocaleString()} tokens</p>
                      <p>${stats.cost_usd.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 6 })}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="panel">
              <div className="panel-header">By Model</div>
              <div className="owner-llm-list">
                {Object.entries(data.by_model).length === 0 && (
                  <p className="hint">No usage by model yet.</p>
                )}
                {Object.entries(data.by_model).map(([model, stats]) => (
                  <div key={model} className="owner-llm-row">
                    <span>{model}</span>
                    <div className="owner-llm-stats">
                      <p>{stats.calls.toLocaleString()} calls</p>
                      <p>{stats.tokens.toLocaleString()} tokens</p>
                      <p>${stats.cost_usd.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 6 })}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">Recent Calls</div>
            {data.recent.length === 0 && <p className="hint">No recent calls recorded.</p>}
            <div className="owner-llm-list">
              {data.recent.map((r) => (
                <div key={r.id} className="owner-llm-recent-row">
                  <span className="owner-action-code">{r.purpose}</span>
                  <span className="owner-llm-model">{r.model}</span>
                  <span className="hint">{r.total_tokens.toLocaleString()} tokens</span>
                  <span className="hint">${r.cost_usd.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 6 })}</span>
                  <span className="hint">{r.latency_ms != null ? `${Math.round(r.latency_ms)} ms` : "—"}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="owner-stat-card">
      <span className="owner-stat-label">{label}</span>
      <span className="owner-stat-value">{value}</span>
    </div>
  );
}
