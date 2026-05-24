"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useRecentTraces, useCallTraceTree, useTraceById, useCreateReplayRunFromCall } from "@/lib/hooks";
import { formatUsd, formatDateTime, formatCount } from "@/lib/format";
import { StatusPill } from "@/components/status-pill";
import type { ReplayMode } from "@/lib/api";
import { REPLAY_MODE_OPTIONS, replayModeProof } from "@/lib/replay-mode";
import type { TraceTreeNode } from "@/lib/types";

const PROVIDER_COLORS: Record<string, string> = {
  openai: "#10a37f",
  anthropic: "#c9855e",
  google: "#4285f4",
  gemini: "#4285f4",
  cohere: "#db4437",
  mistral: "#7b5ea7",
};
function providerColor(p: string | null): string {
  return PROVIDER_COLORS[(p ?? "").toLowerCase()] ?? "#6b7280";
}

const FAILED_STATUS_SET = new Set(["failed", "error", "timeout", "auth_failure", "loop_detected"]);

function TraceTreeView({ node, depth = 0 }: { node: TraceTreeNode; depth?: number }) {
  const hasChildren = node.children.length > 0;
  const [expanded, setExpanded] = useState(depth < 3);
  const isFailed = FAILED_STATUS_SET.has(node.status.toLowerCase());
  const agentLabel = node.agent_name ?? node.call_id.slice(0, 8);

  const borderColor = isFailed ? "#ef4444" : node.status === "success" ? "#22c55e" : "#f59e0b";
  const bgColor = isFailed ? "rgba(239,68,68,0.06)" : "transparent";

  return (
    <li style={{ listStyle: "none", paddingLeft: depth === 0 ? 0 : 20 }}>
      <div
        style={{
          borderLeft: `3px solid ${borderColor}`,
          background: bgColor,
          borderRadius: 8,
          padding: "8px 12px",
          marginBottom: 4,
          display: "flex",
          alignItems: "flex-start",
          gap: 8,
        }}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={() => setExpanded((c) => !c)}
            aria-label={expanded ? "Collapse" : "Expand"}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: 12,
              color: "var(--muted)",
              paddingTop: 2,
              flexShrink: 0,
            }}
          >
            {expanded ? "▼" : "▶"}
          </button>
        ) : (
          <span style={{ width: 16, flexShrink: 0 }} />
        )}

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <strong style={{ fontSize: 14 }}>{agentLabel}</strong>

            {node.wasted_cost_usd > 0 && (
              <span
                style={{
                  background: "#ef4444",
                  color: "#fff",
                  borderRadius: 4,
                  padding: "1px 6px",
                  fontSize: 11,
                  fontWeight: 600,
                }}
              >
                wasted {formatUsd(node.wasted_cost_usd)}
              </span>
            )}

            {node.error_code && (
              <span
                style={{
                  background: "rgba(239,68,68,0.12)",
                  color: "#ef4444",
                  borderRadius: 4,
                  padding: "1px 6px",
                  fontSize: 11,
                }}
              >
                {node.error_code}
              </span>
            )}
          </div>

          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
            {node.provider && (
              <span
                style={{
                  background: providerColor(node.provider) + "22",
                  color: providerColor(node.provider),
                  border: `1px solid ${providerColor(node.provider)}44`,
                  borderRadius: 4,
                  padding: "1px 6px",
                  fontSize: 11,
                  fontWeight: 500,
                }}
              >
                {node.provider}
              </span>
            )}
            {node.model && (
              <span
                style={{
                  background: "var(--surface-muted)",
                  borderRadius: 4,
                  padding: "1px 6px",
                  fontSize: 11,
                  color: "var(--muted)",
                }}
              >
                {node.model}
              </span>
            )}
            {node.latency_ms != null && (
              <span style={{ fontSize: 11, color: "var(--muted)" }}>
                {node.latency_ms < 1000 ? `${node.latency_ms}ms` : `${(node.latency_ms / 1000).toFixed(1)}s`}
              </span>
            )}
            <StatusPill value={node.status} />
          </div>
        </div>
      </div>

      {hasChildren && expanded && (
        <ul style={{ margin: 0, padding: 0 }}>
          {node.children.map((child) => (
            <TraceTreeView key={child.call_id} node={child} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

export default function TraceDetailPage() {
  const params = useParams() as { id?: string };
  const router = useRouter();
  const traceId = params?.id ?? "";
  const [replayMode, setReplayMode] = useState<ReplayMode>("stub");

  // try to discover the trace entry via recent traces, falling back to trace-by-id lookup
  const tracesQuery = useRecentTraces(30, 500);
  const traceByIdQuery = useTraceById(traceId, 30);
  const traceItem = useMemo(() => {
    const fromRecent = (tracesQuery.data?.items ?? []).find((t) => t.trace_id === traceId) ?? null;
    return fromRecent ?? traceByIdQuery.data ?? null;
  }, [tracesQuery.data, traceByIdQuery.data, traceId]);

  const rootCallId = traceItem?.root_call_id ?? null;
  const traceTreeQuery = useCallTraceTree(rootCallId ?? "");
  const createReplayMutation = useCreateReplayRunFromCall({
    onSuccess: (run) => router.push(`/replay/${run.id}`),
  });

  useEffect(() => {
    // no-op: hook usage ensures refetches
  }, [traceId]);

  function createReplay() {
    if (!rootCallId) return;
    createReplayMutation.mutate({
      callId: rootCallId,
      payload: { replay_mode: replayMode },
    });
  }

  if (!traceId) {
    return <section className="panel"><p>Trace id missing.</p></section>;
  }

  if (!traceItem) {
    return (
      <section className="panel">
        <h3>Trace not found</h3>
        <p>The requested trace id was not found in the recent window. Try widening the window on the <Link href="/trace">Traces list</Link>.</p>
      </section>
    );
  }

  const tree = traceTreeQuery.data ?? null;

  return (
    <section>
      <header className="panel-header">
        <div>
          <h3>Trace {traceItem.trace_id}</h3>
          <p className="mono">{traceItem.agents.join(' → ')} · {traceItem.providers.join(', ')}</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <select
            value={replayMode}
            onChange={(event) => setReplayMode(event.target.value as ReplayMode)}
            className="input"
            style={{ maxWidth: 170 }}
            disabled={!rootCallId || createReplayMutation.isPending}
          >
            {REPLAY_MODE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <span className="alert-cat-badge badge-gray" title={replayMode === "stub" ? "Stub replay is a sanity check, not a verified fix." : undefined}>
            {replayModeProof(replayMode)}
          </span>
          <button
            type="button"
            className="btn btn-primary"
            onClick={createReplay}
            disabled={!rootCallId || createReplayMutation.isPending}
          >
            {createReplayMutation.isPending ? "Creating..." : "Create Replay"}
          </button>
          <Link href={`/calls/${traceItem.root_call_id}`} className="btn btn-soft">Open Root Call</Link>
          <button className="btn btn-soft" onClick={() => { const blob = new Blob([JSON.stringify(traceItem, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `trace-${traceItem.trace_id}.json`; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url); }}>Export JSON</button>
        </div>
      </header>

      <section className="panel">
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <div className="kpi-card"><strong>{formatCount(traceItem.call_count)}</strong><span>Calls</span></div>
          <div className="kpi-card"><strong className="mono">{formatUsd(traceItem.total_cost_usd)}</strong><span>Wasted cost</span></div>
          <div className="kpi-card"><strong>{traceItem.agent_count}</strong><span>Agents</span></div>
          <div className="kpi-card"><strong>{traceItem.has_failure ? 'Failed' : 'OK'}</strong><span>Status</span></div>
          <div className="kpi-card"><strong className="mono">{formatDateTime(traceItem.started_at)}</strong><span>Started</span></div>
        </div>
      </section>

      <section className="panel">
        <header className="panel-header"><div><h3>Trace Tree</h3><p>Expanded call tree for this trace.</p></div></header>
        {traceTreeQuery.isLoading ? <div className="loading" /> : null}
        {traceTreeQuery.error ? <p className="hint">{traceTreeQuery.error instanceof Error ? traceTreeQuery.error.message : 'Failed to load trace tree.'}</p> : null}
        {tree ? (
          <ul style={{ margin: 0, padding: 0 }}>
            <TraceTreeView node={tree.root_node} />
          </ul>
        ) : (
          <div className="empty">Trace tree unavailable.</div>
        )}
      </section>
    </section>
  );
}
