"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowLeft, Download, FileJson, Play } from "lucide-react";

import { useRecentTraces, useCallTraceTree, useTraceById, useCreateReplayRunFromCall } from "@/lib/hooks";
import { formatUsd, formatDateTime, formatCount } from "@/lib/format";
import type { ReplayMode } from "@/lib/api";
import { DEFAULT_VERIFICATION_REPLAY_MODE, REPLAY_MODE_OPTIONS, STUB_REPLAY_MODE, replayModeProof } from "@/lib/replay-mode";
import { TraceTreeView } from "@/components/trace-tree-view";

export default function TraceDetailPage() {
  const params = useParams() as { id?: string };
  const router = useRouter();
  const traceId = params?.id ?? "";
  const [replayMode, setReplayMode] = useState<ReplayMode>(DEFAULT_VERIFICATION_REPLAY_MODE);

  const tracesQuery = useRecentTraces(30, 500);
  const traceByIdQuery = useTraceById(traceId, 30);
  const traceItem = useMemo(() => {
    const fromRecent = (tracesQuery.data?.items ?? []).find((trace) => trace.trace_id === traceId) ?? null;
    return fromRecent ?? traceByIdQuery.data ?? null;
  }, [tracesQuery.data, traceByIdQuery.data, traceId]);

  const rootCallId = traceItem?.root_call_id ?? null;
  const traceTreeQuery = useCallTraceTree(rootCallId ?? "");
  const createReplayMutation = useCreateReplayRunFromCall({
    onSuccess: (run) => router.push(`/replay/${run.id}`),
  });

  function createReplay() {
    if (!rootCallId) return;
    createReplayMutation.mutate({
      callId: rootCallId,
      payload: { replay_mode: replayMode },
    });
  }

  function exportJson() {
    if (!traceItem) return;
    const blob = new Blob([JSON.stringify(traceItem, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `trace-${traceItem.trace_id}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  if (!traceId) {
    return <section className="panel"><p>Trace id missing.</p></section>;
  }

  if (!traceItem) {
    return (
      <section className="panel detail-page">
        <h3>Trace not found</h3>
        <p>The requested trace id was not found in the recent window. Try widening the window on the <Link href="/trace">Traces list</Link>.</p>
      </section>
    );
  }

  const tree = traceTreeQuery.data ?? null;

  return (
    <div className="trace-detail-page">
      <Link href="/trace" className="detail-back-link">
        <ArrowLeft aria-hidden="true" />
        Back to traces
      </Link>

      <section className="panel detail-hero">
        <div className="detail-hero-main">
          <div className="detail-badge-row">
            <span className={`alert-cat-badge ${traceItem.has_failure ? "badge-red" : "badge-green"}`}>
              {traceItem.has_failure ? "Failure" : "Healthy"}
            </span>
            {traceItem.agent_count > 1 && <span className="alert-cat-badge badge-gray">{traceItem.agent_count} agents</span>}
            {traceItem.root_failure_category && <span className="alert-cat-badge badge-red">{traceItem.root_failure_category}</span>}
          </div>
          <h1>Trace {traceItem.trace_id}</h1>
          <div className="detail-meta-row">
            <span className="mono">{traceItem.agents.length ? traceItem.agents.join(" -> ") : "No agent name captured"}</span>
            <span>{traceItem.providers.length ? traceItem.providers.join(", ") : "No provider captured"}</span>
            <span>{formatDateTime(traceItem.started_at)}</span>
          </div>
        </div>
        <aside className="detail-hero-side">
          <div className={`detail-impact-value${traceItem.has_failure ? " is-danger" : ""}`}>
            {formatCount(traceItem.call_count)}
          </div>
          <span className="notif-meta">calls in trace</span>
        </aside>
      </section>

      <section className="detail-action-bar">
        <div className="detail-action-group">
          <select
            value={replayMode}
            onChange={(event) => setReplayMode(event.target.value as ReplayMode)}
            className="input detail-mode-select"
            disabled={!rootCallId || createReplayMutation.isPending}
          >
            {REPLAY_MODE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <span
            className="alert-cat-badge badge-gray"
            title={replayMode === STUB_REPLAY_MODE ? "Stub replay is a sanity check, not a verified fix." : undefined}
          >
            {replayModeProof(replayMode)}
          </span>
          <button
            type="button"
            className="btn btn-primary"
            onClick={createReplay}
            disabled={!rootCallId || createReplayMutation.isPending}
          >
            <Play aria-hidden="true" />
            {createReplayMutation.isPending ? "Creating..." : "Create replay"}
          </button>
        </div>
        <div className="detail-action-group detail-action-split">
          <Link href={`/calls/${traceItem.root_call_id}`} className="btn btn-soft">
            Open root call
          </Link>
          <button className="btn btn-soft" type="button" onClick={exportJson}>
            <FileJson aria-hidden="true" />
            Export JSON
          </button>
        </div>
      </section>

      <section className="detail-section-grid">
        <MetricCard label="Calls" value={formatCount(traceItem.call_count)} />
        <MetricCard label="Wasted cost" value={formatUsd(traceItem.total_cost_usd)} />
        <MetricCard label="Agents" value={formatCount(traceItem.agent_count)} />
        <MetricCard label="Status" value={traceItem.has_failure ? "Failed" : "OK"} tone={traceItem.has_failure ? "warn" : "good"} />
        <MetricCard label="Started" value={formatDateTime(traceItem.started_at)} />
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Trace tree</h3>
            <p>Expanded call tree for this trace, grouped by agent, provider, status, latency, and wasted cost.</p>
          </div>
          <button className="btn btn-soft" type="button" onClick={exportJson}>
            <Download aria-hidden="true" />
            Export
          </button>
        </header>
        {traceTreeQuery.isLoading ? <div className="loading" /> : null}
        {traceTreeQuery.error ? <p className="hint">{traceTreeQuery.error instanceof Error ? traceTreeQuery.error.message : "Failed to load trace tree."}</p> : null}
        {tree ? (
          <ul className="trace-tree-list">
            <TraceTreeView node={tree.root_node} />
          </ul>
        ) : (
          <div className="empty">Trace tree unavailable.</div>
        )}
      </section>
    </div>
  );
}

function MetricCard({ label, value, tone }: { label: string; value: string; tone?: "good" | "warn" }) {
  return (
    <article className={`detail-proof-card${tone === "good" ? " is-good" : tone === "warn" ? " is-warn" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
