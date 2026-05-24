"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRecentTraces } from "@/lib/hooks";
import { formatUsd, formatDateTime, formatCount } from "@/lib/format";
import type { TraceListItem } from "@/lib/types";

const PROVIDER_COLORS: Record<string, string> = {
  openai: "#10a37f",
  anthropic: "#c9855e",
  google: "#4285f4",
  gemini: "#4285f4",
  cohere: "#db4437",
  mistral: "#7b5ea7",
};
function providerColor(p: string): string {
  return PROVIDER_COLORS[p.toLowerCase()] ?? "#6b7280";
}

function TraceRow({ item }: { item: TraceListItem }) {
  function downloadBlob(filename: string, contents: string, type = "text/plain") {
    const blob = new Blob([contents], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function exportTraceJson() {
    try {
      const json = JSON.stringify(item, null, 2);
      downloadBlob(`trace-${item.trace_id}.json`, json, "application/json");
    } catch {
      // ignore
    }
  }

  async function copyTrace() {
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard) {
        await navigator.clipboard.writeText(JSON.stringify(item, null, 2));
      }
    } catch {
      // ignore
    }
  }

  return (
    <div className={`trace-row${item.has_failure ? " trace-row-failed" : " trace-row-ok"}`}>
      <div className="trace-row-main">
        <div className="trace-row-title">
          <strong>{item.agents.length > 0 ? item.agents.join(" → ") : "Unnamed Trace"}</strong>
          {item.agent_count > 1 && (
            <span className="trace-badge trace-badge-multi">{item.agent_count} agents</span>
          )}
          {item.has_failure && (
            <span className="trace-badge trace-badge-failed">
              {item.root_failure_category ?? "FAILED"}
            </span>
          )}
        </div>

        <div className="trace-row-meta">
          {item.providers.map((p) => (
            <span
              key={p}
              className="trace-provider-tag"
              style={{ background: providerColor(p) + "22", color: providerColor(p), borderColor: providerColor(p) + "44" }}
            >
              {p}
            </span>
          ))}
          <span className="trace-meta-item">{formatCount(item.call_count)} call{item.call_count !== 1 ? "s" : ""}</span>
          {item.total_cost_usd > 0 && (
            <span className="trace-meta-item mono">{formatUsd(item.total_cost_usd)}</span>
          )}
          <span className="trace-meta-item">{formatDateTime(item.started_at)}</span>
          {item.last_seen_at !== item.started_at && (
            <span className="trace-meta-item">last seen {formatDateTime(item.last_seen_at)}</span>
          )}
        </div>
      </div>

      <div className="trace-row-actions">
        <Link href={`/calls/${item.root_call_id}`} className="btn btn-soft btn-sm">
          Root Call
        </Link>
        <button className="btn btn-soft btn-sm" type="button" onClick={exportTraceJson}>Export JSON</button>
        <button className="btn btn-soft btn-sm" type="button" onClick={copyTrace}>Copy</button>
      </div>
    </div>
  );
}

type FilterMode = "all" | "multi" | "failed";

export default function TracePage() {
  const [days, setDays] = useState(7);
  const { data, isLoading, error } = useRecentTraces(days, 200);
  const [filter, setFilter] = useState<FilterMode>("all");
  const [providerFilter, setProviderFilter] = useState<string | null>(null);
  const [agentFilter, setAgentFilter] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<'ANY' | 'FAILED' | 'OK'>('ANY');
  const [searchId, setSearchId] = useState<string>("");
  const [startDate, setStartDate] = useState<string | null>(null);
  const [endDate, setEndDate] = useState<string | null>(null);

  const allItems = useMemo(() => data?.items ?? [], [data?.items]);
  const multiAgentItems = useMemo(() => allItems.filter((i) => i.agent_count > 1), [allItems]);
  const failedItems = useMemo(() => allItems.filter((i) => i.has_failure), [allItems]);
  const totalCost = useMemo(() => allItems.reduce((s, i) => s + i.total_cost_usd, 0), [allItems]);

  let displayItems =
    filter === "multi" ? multiAgentItems
    : filter === "failed" ? failedItems
    : allItems;
  if (providerFilter) displayItems = displayItems.filter((i) => (i.providers ?? []).includes(providerFilter));
  if (agentFilter) displayItems = displayItems.filter((i) => (i.agents ?? []).includes(agentFilter));
  if (statusFilter === 'FAILED') displayItems = displayItems.filter((i) => i.has_failure);
  if (statusFilter === 'OK') displayItems = displayItems.filter((i) => !i.has_failure);
  if (searchId && searchId.trim()) displayItems = displayItems.filter((i) => i.trace_id.toLowerCase().includes(searchId.trim().toLowerCase()));
  if (startDate) {
    const from = new Date(startDate).getTime();
    displayItems = displayItems.filter((i) => new Date(i.started_at).getTime() >= from);
  }
  if (endDate) {
    const to = new Date(endDate).getTime();
    displayItems = displayItems.filter((i) => new Date(i.started_at).getTime() <= to);
  }

  const providerNames = useMemo(() => {
    const s = new Set<string>();
    for (const i of allItems) for (const p of i.providers ?? []) s.add(p);
    return Array.from(s).sort();
  }, [allItems]);

  const agentNames = useMemo(() => {
    const s = new Set<string>();
    for (const i of allItems) for (const a of i.agents ?? []) s.add(a);
    return Array.from(s).sort();
  }, [allItems]);

  function downloadBlob(filename: string, contents: string, type = "text/plain") {
    const blob = new Blob([contents], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function exportTracesJson(items: typeof displayItems) {
    try {
      const json = JSON.stringify(items, null, 2);
      downloadBlob(`traces-${Date.now()}.json`, json, "application/json");
    } catch {
      // ignore
    }
  }

  function exportTracesCsv(items: typeof displayItems) {
    const header = ["trace_id", "agents", "agent_count", "providers", "call_count", "total_cost_usd", "started_at", "last_seen_at", "has_failure", "root_failure_category", "root_call_id"];
    const rows = items.map((i) => {
      const cols = [
        i.trace_id,
        (i.agents ?? []).join(" |") ,
        String(i.agent_count ?? 0),
        (i.providers ?? []).join(" |") ,
        String(i.call_count ?? 0),
        String(i.total_cost_usd ?? 0),
        i.started_at,
        i.last_seen_at,
        String(Boolean(i.has_failure)),
        i.root_failure_category ?? "",
        i.root_call_id ?? "",
      ];
      return cols.map((c) => JSON.stringify(c ?? "")).join(",");
    });
    const csv = [header.join(","), ...rows].join("\n");
    downloadBlob(`traces-${Date.now()}.csv`, csv, "text/csv;charset=utf-8");
  }

  return (
    <>
      {/* ── KPI strip ── */}
      {data && (
        <div className="kpi-grid trace-kpi-grid">
          <article className="kpi-card">
            <span className="kpi-label">Total Traces</span>
            <strong className="kpi-value">{data.total}</strong>
          </article>
          <article className="kpi-card">
            <span className="kpi-label">Multi-Agent</span>
            <strong className="kpi-value">{data.multi_agent_count}</strong>
          </article>
          <article className={`kpi-card${data.failed_count > 0 ? " kpi-card-danger" : ""}`}>
            <span className="kpi-label">With Failures</span>
            <strong className={`kpi-value${data.failed_count > 0 ? " kpi-value-danger" : ""}`}>
              {data.failed_count}
            </strong>
          </article>
          <article className="kpi-card">
            <span className="kpi-label">Total Cost</span>
            <strong className="kpi-value mono">{formatUsd(totalCost)}</strong>
          </article>
        </div>
      )}

      <section className="panel" id="trace-summary">
        <header className="panel-header">
          <div>
            <h3>Multi-Agent Trace Explorer</h3>
            <p>Provider-agnostic trace tree — see which agent did what, in order, with costs and failures highlighted.</p>
          </div>
          <div className="trace-window-btns">
            <button className="btn btn-soft btn-sm" type="button" onClick={() => exportTracesJson(displayItems)}>
              Export JSON
            </button>
            <button className="btn btn-soft btn-sm" type="button" onClick={() => exportTracesCsv(displayItems)}>
              Export CSV
            </button>
            {[1, 7, 14, 30].map((d) => (
              <button
                key={d}
                type="button"
                className={`cost-window-btn${days === d ? " active" : ""}`}
                onClick={() => setDays(d)}
              >
                {d}d
              </button>
            ))}
          </div>
        </header>

        <div className="trace-filter-row">
          {(
            [
              { mode: "all" as FilterMode, label: `All (${allItems.length})` },
              { mode: "multi" as FilterMode, label: `Multi-agent (${multiAgentItems.length})` },
              { mode: "failed" as FilterMode, label: `Failed (${failedItems.length})`, danger: true },
            ] as { mode: FilterMode; label: string; danger?: boolean }[]
          ).map(({ mode, label, danger }) => (
            <button
              key={mode}
              type="button"
              className={`btn trace-filter-btn${filter === mode ? (danger ? " btn-danger" : " btn-primary") : " btn-soft"}`}
              onClick={() => setFilter(mode)}
            >
              {label}
            </button>
          ))}
          <div style={{ marginLeft: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
            <input placeholder="Search trace id" value={searchId} onChange={(e) => setSearchId(e.target.value)} style={{ minWidth: 200 }} />
            <select value={providerFilter ?? ""} onChange={(e) => setProviderFilter(e.target.value || null)}>
              <option value="">All providers</option>
              {providerNames.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <select value={agentFilter ?? ""} onChange={(e) => setAgentFilter(e.target.value || null)}>
              <option value="">All agents</option>
              {agentNames.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as "ANY" | "FAILED" | "OK")}>
              <option value="ANY">Any status</option>
              <option value="FAILED">Failed only</option>
              <option value="OK">Successful only</option>
            </select>
            <label style={{ fontSize: 12 }}>From</label>
            <input type="date" value={startDate ?? ""} onChange={(e) => setStartDate(e.target.value || null)} />
            <label style={{ fontSize: 12 }}>To</label>
            <input type="date" value={endDate ?? ""} onChange={(e) => setEndDate(e.target.value || null)} />
            <button className="btn btn-soft" onClick={() => { setSearchId(""); setProviderFilter(null); setAgentFilter(null); setStatusFilter('ANY'); setStartDate(null); setEndDate(null); }}>Clear</button>
          </div>
        </div>
      </section>

      <section className="panel">
        {isLoading && <div className="loading" />}
        {error && <p className="hint">{error instanceof Error ? error.message : "Failed to load traces."}</p>}
        {!isLoading && !error && displayItems.length === 0 && (
          <div className="empty">
            {filter === "failed"
              ? `No failed traces in the last ${days} day${days !== 1 ? "s" : ""}.`
              : filter === "multi"
              ? `No multi-agent traces in the last ${days} day${days !== 1 ? "s" : ""}.`
              : `No traces found in the last ${days}d. Traces appear once calls with a shared trace_id are ingested.`}
          </div>
        )}
        {!isLoading && displayItems.length > 0 && (
          <div className="trace-list">
            {displayItems.map((item) => (
              <TraceRow key={item.trace_id} item={item} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}
