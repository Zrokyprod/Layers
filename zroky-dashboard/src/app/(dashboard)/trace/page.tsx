"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Copy, Download, GitBranch, Play, RefreshCw, Search, SlidersHorizontal, XCircle } from "lucide-react";

import type { ReplayMode } from "@/lib/api";
import { formatCount, formatDateTime, formatUsd } from "@/lib/format";
import { useCreateReplayRunFromCall, useListCalls, useRecentTraces } from "@/lib/hooks";
import { DEFAULT_VERIFICATION_REPLAY_MODE } from "@/lib/replay-mode";
import type { CallListItem, TraceListItem } from "@/lib/types";

const DASH = "—";
const TRACE_LIMIT = 100;
const SLOW_TRACE_LATENCY_MS = 1000;

type StatusFilter = "all" | "failed" | "success";
type ReplayFilter = "all" | "ready" | "missing";
type LatencyFilter = "all" | "slow";
type WindowDays = 7 | 14 | 30;
type ActionState = { kind: "success" | "error"; message: string } | null;

function statusLabel(item: TraceListItem): string {
  return item.has_failure ? "Failed" : "Success";
}

function statusClass(item: TraceListItem): string {
  return item.has_failure ? "trace-status-failed" : "trace-status-success";
}

function latencyLabel(value: number | null | undefined): string {
  if (value == null) return DASH;
  return value < 1000 ? `${value}ms` : `${(value / 1000).toFixed(2)}s`;
}

function traceDateLabel(value: string | null | undefined): string {
  return formatDateTime(value?.replace(/\+00:00Z$/, "Z"));
}

function avgLatencyLabel(values: Array<number | null | undefined>): string {
  const valid = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (valid.length === 0) return DASH;
  const avg = valid.reduce((sum, value) => sum + value, 0) / valid.length;
  return latencyLabel(avg);
}

function traceTitle(item: TraceListItem): string {
  if (item.agents.length > 0) return item.agents.join(" -> ");
  return item.root_call_id ? `Call ${item.root_call_id.slice(0, 12)}` : `Trace ${item.trace_id.slice(0, 12)}`;
}

function traceMeta(item: TraceListItem): string {
  return `${item.trace_id} · ${formatCount(item.call_count)} span${item.call_count === 1 ? "" : "s"}`;
}

function callTypeLabel(call: CallListItem | undefined): string {
  return call?.call_type?.trim() || "trace";
}

function modelLabel(item: TraceListItem, call: CallListItem | undefined): string {
  return call?.model?.trim() || item.providers[0] || DASH;
}

function agentLabel(item: TraceListItem, call: CallListItem | undefined): string {
  return item.agents[0] || call?.agent_name || DASH;
}

function traceMatchesSearch(item: TraceListItem, call: CallListItem | undefined, search: string): boolean {
  const needle = search.trim().toLowerCase();
  if (!needle) return true;
  return [
    item.trace_id,
    item.root_call_id,
    ...item.agents,
    ...item.providers,
    item.root_failure_category ?? "",
    call?.agent_name ?? "",
    call?.model ?? "",
    call?.call_type ?? "",
    call?.status ?? "",
  ].some((value) => value.toLowerCase().includes(needle));
}

function traceErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) return "Failed to load traces.";
  if (/422|less_than_equal|limit/i.test(error.message)) {
    return "Trace query exceeded the backend window. Refresh with the safe 100 trace limit.";
  }
  return error.message || "Failed to load traces.";
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function TraceMetric({
  label,
  value,
  helper,
  active,
  onClick,
}: {
  label: string;
  value: string;
  helper: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`trace-mvp-kpi trace-mvp-kpi-button${active ? " is-active" : ""}`}
      onClick={onClick}
    >
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{helper}</p>
    </button>
  );
}

function TraceRow({
  item,
  rootCall,
  onReplay,
  onCopyTraceId,
  replaying,
}: {
  item: TraceListItem;
  rootCall: CallListItem | undefined;
  onReplay: (callId: string) => void;
  onCopyTraceId: (traceId: string) => void;
  replaying: boolean;
}) {
  return (
    <tr>
      <td data-label="Trace / Call">
        <div className="trace-mvp-primary-cell">
          <Link href={`/trace/${encodeURIComponent(item.trace_id)}`}>{traceTitle(item)}</Link>
          <span>{traceMeta(item)}</span>
        </div>
      </td>
      <td data-label="Status"><span className={`trace-mvp-status ${statusClass(item)}`}>{statusLabel(item)}</span></td>
      <td data-label="Agent">{agentLabel(item, rootCall)}</td>
      <td data-label="Type">{callTypeLabel(rootCall)}</td>
      <td data-label="Model">{modelLabel(item, rootCall)}</td>
      <td data-label="Cost">{item.total_cost_usd > 0 ? formatUsd(item.total_cost_usd) : DASH}</td>
      <td data-label="Latency">{latencyLabel(rootCall?.latency_ms)}</td>
      <td data-label="Created">{traceDateLabel(item.started_at)}</td>
      <td data-label="Action">
        <div className="trace-mvp-row-actions">
          <Link href={`/trace/${encodeURIComponent(item.trace_id)}`} className="btn btn-soft btn-sm">View trace</Link>
          {item.root_call_id ? (
            <Link href={`/calls/${item.root_call_id}`} className="btn btn-soft btn-sm">Source call</Link>
          ) : null}
          <button
            type="button"
            className="btn btn-soft btn-sm"
            onClick={() => onCopyTraceId(item.trace_id)}
          >
            <Copy aria-hidden="true" />
            Copy ID
          </button>
          {item.root_call_id ? (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => onReplay(item.root_call_id)}
              disabled={replaying}
            >
              <Play aria-hidden="true" />
              Replay
            </button>
          ) : null}
        </div>
      </td>
    </tr>
  );
}

export default function TracePage() {
  const router = useRouter();
  const [windowDays, setWindowDays] = useState<WindowDays>(7);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [agentFilter, setAgentFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [modelFilter, setModelFilter] = useState("");
  const [replayFilter, setReplayFilter] = useState<ReplayFilter>("all");
  const [latencyFilter, setLatencyFilter] = useState<LatencyFilter>("all");
  const [search, setSearch] = useState("");
  const [actionState, setActionState] = useState<ActionState>(null);

  const tracesQuery = useRecentTraces(windowDays, TRACE_LIMIT);
  const callsQuery = useListCalls({ limit: 200, sort_by: "created_at", sort_order: "desc" });
  const replayMutation = useCreateReplayRunFromCall({
    onSuccess: (run) => router.push(`/replay/${run.id}`),
  });

  const traces = useMemo(() => tracesQuery.data?.items ?? [], [tracesQuery.data?.items]);
  const callsById = useMemo(() => {
    const map = new Map<string, CallListItem>();
    for (const call of callsQuery.data?.items ?? []) {
      map.set(call.call_id, call);
    }
    return map;
  }, [callsQuery.data?.items]);

  const agentOptions = useMemo(() => {
    const values = new Set<string>();
    for (const item of traces) {
      for (const agent of item.agents) values.add(agent);
      const root = callsById.get(item.root_call_id);
      if (root?.agent_name) values.add(root.agent_name);
    }
    return Array.from(values).sort();
  }, [callsById, traces]);

  const typeOptions = useMemo(() => {
    const values = new Set<string>();
    for (const item of traces) {
      const root = callsById.get(item.root_call_id);
      if (root?.call_type) values.add(root.call_type);
    }
    return Array.from(values).sort();
  }, [callsById, traces]);

  const modelOptions = useMemo(() => {
    const values = new Set<string>();
    for (const item of traces) {
      for (const provider of item.providers) values.add(provider);
      const root = callsById.get(item.root_call_id);
      if (root?.model) values.add(root.model);
    }
    return Array.from(values).sort();
  }, [callsById, traces]);

  const displayRows = useMemo(() => {
    return traces.filter((item) => {
      const root = callsById.get(item.root_call_id);
      if (statusFilter === "failed" && !item.has_failure) return false;
      if (statusFilter === "success" && item.has_failure) return false;
      if (agentFilter && agentLabel(item, root) !== agentFilter && !item.agents.includes(agentFilter)) return false;
      if (typeFilter && callTypeLabel(root) !== typeFilter) return false;
      if (modelFilter && modelLabel(item, root) !== modelFilter && !item.providers.includes(modelFilter)) return false;
      if (replayFilter === "ready" && !item.root_call_id) return false;
      if (replayFilter === "missing" && item.root_call_id) return false;
      if (latencyFilter === "slow" && ((root?.latency_ms ?? 0) < SLOW_TRACE_LATENCY_MS)) return false;
      return traceMatchesSearch(item, root, search);
    });
  }, [agentFilter, callsById, latencyFilter, modelFilter, replayFilter, search, statusFilter, traces, typeFilter]);

  const rootCalls = traces.map((item) => callsById.get(item.root_call_id));
  const replayReadyCount = traces.filter((item) => Boolean(item.root_call_id)).length;
  const slowTraceCount = traces.filter((item) => (callsById.get(item.root_call_id)?.latency_ms ?? 0) >= SLOW_TRACE_LATENCY_MS).length;

  function clearFilters() {
    setStatusFilter("all");
    setAgentFilter("");
    setTypeFilter("");
    setModelFilter("");
    setReplayFilter("all");
    setLatencyFilter("all");
    setSearch("");
  }

  function showAction(kind: "success" | "error", message: string) {
    setActionState({ kind, message });
  }

  function runReplay(callId: string) {
    replayMutation.mutate({
      callId,
      payload: { replay_mode: DEFAULT_VERIFICATION_REPLAY_MODE as ReplayMode },
    });
  }

  async function refreshTraces() {
    setActionState(null);
    try {
      await Promise.all([tracesQuery.refetch(), callsQuery.refetch()]);
      showAction("success", "Trace data refreshed.");
    } catch {
      showAction("error", "Refresh failed. Try again.");
    }
  }

  async function copyVisibleTraceIds() {
    const traceIds = displayRows.map((item) => item.trace_id);
    if (traceIds.length === 0) {
      showAction("error", "No visible trace IDs to copy.");
      return;
    }
    try {
      await navigator.clipboard.writeText(traceIds.join("\n"));
      showAction("success", `Copied ${formatCount(traceIds.length)} trace IDs.`);
    } catch {
      showAction("error", "Clipboard copy failed.");
    }
  }

  async function copyTraceId(traceId: string) {
    try {
      await navigator.clipboard.writeText(traceId);
      showAction("success", "Trace ID copied.");
    } catch {
      showAction("error", "Clipboard copy failed.");
    }
  }

  function exportVisibleRows() {
    if (displayRows.length === 0) {
      showAction("error", "No visible traces to export.");
      return;
    }
    const payload = displayRows.map((item) => ({
      trace: item,
      root_call: callsById.get(item.root_call_id) ?? null,
    }));
    downloadJson(`zroky-traces-${windowDays}d-visible.json`, payload);
    showAction("success", `Exported ${formatCount(displayRows.length)} visible traces.`);
  }

  return (
    <div className="traces-mvp">
      <section className="trace-mvp-hero">
        <div>
          <div className="trace-mvp-eyebrow">
            <GitBranch aria-hidden="true" />
            Evidence browser
          </div>
          <h1>Trace Graphs</h1>
          <p>Captured agent calls, tool steps, retrieval events, and replay-ready evidence.</p>
        </div>
        <div className="trace-mvp-hero-actions">
          <button type="button" className="btn btn-soft" onClick={() => void refreshTraces()} disabled={tracesQuery.isFetching || callsQuery.isFetching}>
            <RefreshCw aria-hidden="true" />
            {tracesQuery.isFetching || callsQuery.isFetching ? "Refreshing..." : "Refresh"}
          </button>
          <button type="button" className="btn btn-soft" onClick={() => void copyVisibleTraceIds()}>
            <Copy aria-hidden="true" />
            Copy IDs
          </button>
          <button type="button" className="btn btn-primary" onClick={exportVisibleRows}>
            <Download aria-hidden="true" />
            Export JSON
          </button>
        </div>
      </section>

      {actionState ? (
        <div className={`trace-mvp-action-message ${actionState.kind === "error" ? "is-error" : ""}`} role="status">
          {actionState.message}
        </div>
      ) : null}

      <section className="trace-mvp-kpis" aria-label="Trace overview">
        <TraceMetric
          label="Captured traces"
          value={tracesQuery.data ? formatCount(tracesQuery.data.total) : DASH}
          helper="Reset to every loaded trace."
          active={statusFilter === "all" && replayFilter === "all" && latencyFilter === "all" && !agentFilter && !typeFilter && !modelFilter && !search}
          onClick={clearFilters}
        />
        <TraceMetric
          label="Failed calls"
          value={tracesQuery.data ? formatCount(tracesQuery.data.failed_count) : DASH}
          helper="Filter failed trace groups."
          active={statusFilter === "failed"}
          onClick={() => {
            setStatusFilter("failed");
            setReplayFilter("all");
            setLatencyFilter("all");
          }}
        />
        <TraceMetric
          label="Replay-ready"
          value={tracesQuery.data ? formatCount(replayReadyCount) : DASH}
          helper="Filter root-call evidence."
          active={replayFilter === "ready"}
          onClick={() => {
            setReplayFilter("ready");
            setLatencyFilter("all");
          }}
        />
        <TraceMetric
          label="Avg latency"
          value={avgLatencyLabel(rootCalls.map((call) => call?.latency_ms))}
          helper={`${formatCount(slowTraceCount)} loaded over 1s.`}
          active={latencyFilter === "slow"}
          onClick={() => {
            setLatencyFilter("slow");
            setReplayFilter("all");
          }}
        />
      </section>

      <section className="trace-mvp-filter-panel" aria-label="Trace filters">
        <header>
          <div>
            <h2>Trace filters</h2>
            <p>{formatCount(displayRows.length)} loaded evidence rows.</p>
          </div>
          <SlidersHorizontal aria-hidden="true" />
        </header>
        <div className="trace-mvp-toolbar">
          <label>
            <span>Window</span>
            <select value={windowDays} onChange={(event) => setWindowDays(Number(event.target.value) as WindowDays)}>
              <option value={7}>Last 7 days</option>
              <option value={14}>Last 14 days</option>
              <option value={30}>Last 30 days</option>
            </select>
          </label>
          <button type="button" className="btn btn-soft btn-sm" onClick={clearFilters}>
            <XCircle aria-hidden="true" />
            Clear filters
          </button>
        </div>
        <div className="trace-mvp-filters">
          <label>
            <span>Status</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}>
              <option value="all">All</option>
              <option value="failed">Failed</option>
              <option value="success">Success</option>
            </select>
          </label>
          <label>
            <span>Agent</span>
            <select value={agentFilter} onChange={(event) => setAgentFilter(event.target.value)}>
              <option value="">Any</option>
              {agentOptions.map((agent) => <option key={agent} value={agent}>{agent}</option>)}
            </select>
          </label>
          <label>
            <span>Call type</span>
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              <option value="">Any</option>
              {typeOptions.map((type) => <option key={type} value={type}>{type}</option>)}
            </select>
          </label>
          <label>
            <span>Provider/model</span>
            <select value={modelFilter} onChange={(event) => setModelFilter(event.target.value)}>
              <option value="">Any</option>
              {modelOptions.map((model) => <option key={model} value={model}>{model}</option>)}
            </select>
          </label>
          <label>
            <span>Replay-ready</span>
            <select value={replayFilter} onChange={(event) => setReplayFilter(event.target.value as ReplayFilter)}>
              <option value="all">All</option>
              <option value="ready">Replay-ready</option>
              <option value="missing">Missing root call</option>
            </select>
          </label>
          <label>
            <span>Latency</span>
            <select value={latencyFilter} onChange={(event) => setLatencyFilter(event.target.value as LatencyFilter)}>
              <option value="all">All</option>
              <option value="slow">Over 1s</option>
            </select>
          </label>
          <label className="trace-mvp-search">
            <span>Search</span>
            <div>
              <Search aria-hidden="true" />
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search trace, call, agent..." />
            </div>
          </label>
        </div>
      </section>

      <section className="trace-mvp-table-section">
        <header>
          <div>
            <h2>Trace evidence</h2>
            <p>Captured calls and trace trees ready for investigation.</p>
          </div>
          {callsQuery.error && traces.length > 0 ? (
            <span className="trace-mvp-warning">Call enrichment unavailable. Trace rows are still shown.</span>
          ) : null}
        </header>

        {tracesQuery.isLoading ? <div className="trace-mvp-empty">Loading captured traces...</div> : null}
        {tracesQuery.error ? <div className="trace-mvp-error">{traceErrorMessage(tracesQuery.error)}</div> : null}
        {!tracesQuery.isLoading && !tracesQuery.error && displayRows.length === 0 ? (
          <div className="trace-mvp-empty">
            <strong>No traces captured yet</strong>
            <p>
              Run one SDK or Gateway call with your project key, then refresh here. Your first captured trace appears in
              this table when capture is working.
            </p>
            <div className="trace-mvp-empty-actions">
              <button type="button" className="btn btn-primary btn-sm" onClick={() => void refreshTraces()}>
                <RefreshCw aria-hidden="true" />
                Refresh traces
              </button>
              <Link href="/settings/keys" className="btn btn-soft btn-sm">Back to project key setup</Link>
            </div>
          </div>
        ) : null}
        {displayRows.length > 0 ? (
          <div className="trace-mvp-table-wrap">
            <table className="trace-mvp-table">
              <thead>
                <tr>
                  <th>Trace / Call</th>
                  <th>Status</th>
                  <th>Agent</th>
                  <th>Type</th>
                  <th>Model</th>
                  <th>Cost</th>
                  <th>Latency</th>
                  <th>Created</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {displayRows.map((item) => (
                  <TraceRow
                    key={item.trace_id}
                    item={item}
                    rootCall={callsById.get(item.root_call_id)}
                    onReplay={runReplay}
                    onCopyTraceId={(traceId) => void copyTraceId(traceId)}
                    replaying={replayMutation.isPending}
                  />
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
