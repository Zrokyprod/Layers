"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import type { CSSProperties } from "react";
import { useMemo, useState } from "react";
import { ArrowLeft, Copy, Download, ExternalLink, Play, RefreshCw, ShieldCheck } from "lucide-react";

import type { ReplayMode } from "@/lib/api";
import { formatCount, formatDateTime, formatUsd } from "@/lib/format";
import {
  useCallDetail,
  useCallTraceTree,
  useCreateReplayRunFromCall,
  useRecentTraces,
  useTraceById,
} from "@/lib/hooks";
import { DEFAULT_VERIFICATION_REPLAY_MODE } from "@/lib/replay-mode";
import type { JsonMap, TraceListItem, TraceTreeNode } from "@/lib/types";

const DASH = "—";
const TRACE_LIMIT = 100;
type ActionState = { kind: "success" | "error"; message: string } | null;

function asObject(value: unknown): JsonMap {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonMap : {};
}

function stringifyValue(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === "string") return value.trim() || null;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return null;
  }
}

function readPath(payload: JsonMap, path: string[]): unknown {
  let current: unknown = payload;
  for (const segment of path) {
    if (!current || typeof current !== "object" || Array.isArray(current) || !(segment in current)) return undefined;
    current = (current as JsonMap)[segment];
  }
  return current;
}

function firstPresent(payload: JsonMap, paths: string[][]): string | null {
  for (const path of paths) {
    const value = stringifyValue(readPath(payload, path));
    if (value) return value;
  }
  return null;
}

function extractPromptText(payload: JsonMap): string | null {
  return firstPresent(payload, [
    ["prompt"],
    ["input"],
    ["user_input"],
    ["request", "prompt"],
    ["request", "input"],
    ["request", "messages"],
    ["messages"],
    ["payload", "prompt"],
    ["payload", "input"],
  ]);
}

function extractResponseText(payload: JsonMap): string | null {
  return firstPresent(payload, [
    ["response"],
    ["output"],
    ["completion"],
    ["final_response"],
    ["result"],
    ["response_text"],
    ["payload", "response"],
    ["payload", "output"],
  ]);
}

function extractArray(payload: JsonMap, paths: string[][]): unknown[] {
  for (const path of paths) {
    const value = readPath(payload, path);
    if (Array.isArray(value)) return value;
  }
  return [];
}

function flattenTree(root: TraceTreeNode | null): Array<{ node: TraceTreeNode; depth: number; index: number }> {
  const rows: Array<{ node: TraceTreeNode; depth: number; index: number }> = [];
  function visit(node: TraceTreeNode, depth: number) {
    rows.push({ node, depth, index: rows.length + 1 });
    for (const child of node.children) visit(child, depth + 1);
  }
  if (root) visit(root, 0);
  return rows;
}

function latencyLabel(value: number | null | undefined): string {
  if (value == null) return DASH;
  return value < 1000 ? `${value}ms` : `${(value / 1000).toFixed(2)}s`;
}

function traceDateLabel(value: string | null | undefined): string {
  return formatDateTime(value?.replace(/\+00:00Z$/, "Z"));
}

function statusLabel(trace: TraceListItem): string {
  return trace.has_failure ? "Failed" : "Success";
}

function statusClass(trace: TraceListItem): string {
  return trace.has_failure ? "trace-status-failed" : "trace-status-success";
}

function replayReadiness(trace: TraceListItem): string {
  return trace.root_call_id ? "Replay ready" : "Not replayable";
}

function modelLabel(trace: TraceListItem, root: TraceTreeNode | null): string {
  return root?.model || trace.providers[0] || DASH;
}

function agentLabel(trace: TraceListItem, root: TraceTreeNode | null): string {
  return trace.agents[0] || root?.agent_name || DASH;
}

function stepTypeLabel(node: TraceTreeNode, depth: number): string {
  if (depth === 0) return "Root call";
  if (node.provider?.toLowerCase() === "tool" || node.error_code) return "Tool call";
  if (node.model || node.provider) return "LLM call";
  return "Agent step";
}

function nodeTitle(node: TraceTreeNode, depth: number): string {
  if (depth === 0) return "Root call";
  if (node.error_code) return `Tool or agent step: ${node.error_code}`;
  return node.agent_name || node.call_id;
}

function nodeSummary(node: TraceTreeNode): string {
  const model = [node.provider, node.model].filter(Boolean).join(" · ");
  const cost = node.wasted_cost_usd > 0 ? ` · ${formatUsd(node.wasted_cost_usd)}` : "";
  const error = node.error_code ? ` · ${node.error_code}` : "";
  return `${model || "Captured step"} · ${latencyLabel(node.latency_ms)}${cost}${error}`;
}

function toolRows(payload: JsonMap, nodes: Array<{ node: TraceTreeNode; depth: number; index: number }>) {
  const explicit = extractArray(payload, [
    ["tool_calls"],
    ["tools"],
    ["payload", "tool_calls"],
    ["request", "tool_calls"],
    ["events", "tool_calls"],
  ]).map((item, index) => {
    const object = asObject(item);
    return {
      id: `tool-${index}`,
      name: firstPresent(object, [["name"], ["tool_name"], ["function", "name"], ["tool"]]) ?? `Tool call ${index + 1}`,
      status: firstPresent(object, [["status"], ["result", "status"], ["error"]]) ?? "captured",
      summary: firstPresent(object, [["summary"], ["arguments"], ["input"], ["result"], ["output"], ["error"]]) ?? "Tool call captured.",
      failed: Boolean(firstPresent(object, [["error"]])) || /fail|error|timeout/i.test(String(firstPresent(object, [["status"]]) ?? "")),
    };
  });
  if (explicit.length > 0) return explicit;
  return nodes
    .filter(({ node }) => node.error_code || /tool|timeout|error|fail/i.test(`${node.status} ${node.error_code ?? ""}`))
    .map(({ node, index }) => ({
      id: node.call_id,
      name: node.agent_name || `Step ${index}`,
      status: node.status,
      summary: node.error_code ? `${node.error_code} on ${node.provider ?? "captured provider"}.` : nodeSummary(node),
      failed: Boolean(node.error_code) || /fail|error|timeout/i.test(node.status),
    }));
}

function listTextValues(payload: JsonMap, paths: string[][]): string[] {
  const values = extractArray(payload, paths);
  return values.map((value, index) => {
    const object = asObject(value);
    return firstPresent(object, [["title"], ["name"], ["id"], ["text"], ["content"], ["summary"]]) ?? stringifyValue(value) ?? `Item ${index + 1}`;
  });
}

function diagnosisSummary(payload: JsonMap | null): { code: string; rootCause: string; confidence: string } | null {
  if (!payload) return null;
  const firstDiagnosis = Array.isArray(payload.diagnoses) ? asObject(payload.diagnoses[0]) : payload;
  const code = firstPresent(firstDiagnosis, [["failure_code"], ["category"], ["code"], ["diagnosis"]]) ?? DASH;
  const rootCause = firstPresent(firstDiagnosis, [["root_cause"], ["reason"], ["summary"], ["evidence", "summary"]]) ?? "No diagnosis generated yet.";
  const confidence = firstPresent(firstDiagnosis, [["confidence"], ["confidence_score"]]) ?? DASH;
  if (code === DASH && rootCause === "No diagnosis generated yet." && confidence === DASH) return null;
  return { code, rootCause, confidence };
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

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="trace-detail-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

export default function TraceDetailPage() {
  const params = useParams() as { id?: string };
  const router = useRouter();
  const traceId = params?.id ?? "";
  const [copied, setCopied] = useState(false);
  const [actionState, setActionState] = useState<ActionState>(null);

  const tracesQuery = useRecentTraces(30, TRACE_LIMIT);
  const traceByIdQuery = useTraceById(traceId, 30);
  const traceItem = useMemo(() => {
    const fromRecent = (tracesQuery.data?.items ?? []).find((trace) => trace.trace_id === traceId) ?? null;
    return fromRecent ?? traceByIdQuery.data ?? null;
  }, [traceByIdQuery.data, traceId, tracesQuery.data?.items]);

  const rootCallId = traceItem?.root_call_id ?? "";
  const traceTreeQuery = useCallTraceTree(rootCallId);
  const callDetailQuery = useCallDetail(rootCallId);
  const replayMutation = useCreateReplayRunFromCall({
    onSuccess: (run) => router.push(`/replay/${run.id}`),
  });

  const tree = traceTreeQuery.data ?? null;
  const rootNode = tree?.root_node ?? null;
  const detail = callDetailQuery.data ?? null;
  const payload = useMemo(() => detail?.payload ?? {}, [detail?.payload]);
  const timelineRows = useMemo(() => flattenTree(rootNode), [rootNode]);
  const promptText = useMemo(() => extractPromptText(payload), [payload]);
  const responseText = useMemo(() => extractResponseText(payload), [payload]);
  const tools = useMemo(() => toolRows(payload, timelineRows), [payload, timelineRows]);
  const retrievalItems = useMemo(() => listTextValues(payload, [["retrieval"], ["retrieval_context"], ["documents"], ["payload", "retrieval"]]), [payload]);
  const memoryItems = useMemo(() => listTextValues(payload, [["memory"], ["memory_events"], ["payload", "memory"]]), [payload]);
  const diagnosis = useMemo(() => diagnosisSummary(detail?.diagnosis_result ?? null), [detail?.diagnosis_result]);

  function runReplay() {
    if (!rootCallId) return;
    replayMutation.mutate({
      callId: rootCallId,
      payload: { replay_mode: DEFAULT_VERIFICATION_REPLAY_MODE as ReplayMode },
    });
  }

  function showAction(kind: "success" | "error", message: string) {
    setActionState({ kind, message });
  }

  async function refreshTraceDetail() {
    setActionState(null);
    try {
      await Promise.all([
        tracesQuery.refetch(),
        traceByIdQuery.refetch(),
        traceTreeQuery.refetch(),
        callDetailQuery.refetch(),
      ]);
      showAction("success", "Trace detail refreshed.");
    } catch {
      showAction("error", "Refresh failed. Try again.");
    }
  }

  async function copyValue(value: string, successMessage: string) {
    if (!value) {
      showAction("error", "Nothing to copy.");
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      showAction("success", successMessage);
    } catch {
      showAction("error", "Clipboard copy failed.");
    }
  }

  async function copyTraceId() {
    try {
      await navigator.clipboard.writeText(traceId);
      setCopied(true);
      showAction("success", "Trace ID copied.");
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
      showAction("error", "Clipboard copy failed.");
    }
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

  const latency = rootNode?.latency_ms ?? detail?.call.latency_ms ?? null;
  const cost = traceItem.total_cost_usd > 0 ? traceItem.total_cost_usd : tree?.total_wasted_cost_usd ?? 0;
  const spans = traceItem.call_count || (tree ? tree.total_downstream_calls + 1 : 0);
  const rawPayload = {
    trace: traceItem,
    root_call: detail?.call ?? null,
    payload,
    trace_tree: tree,
  };
  const rawPayloadJson = JSON.stringify(rawPayload, null, 2);

  async function copyRawPayload() {
    await copyValue(rawPayloadJson, "Raw trace JSON copied.");
  }

  function exportRawPayload() {
    downloadJson(`zroky-trace-${traceId}.json`, rawPayload);
    showAction("success", "Raw trace JSON exported.");
  }

  return (
    <div className="trace-detail-mvp">
      <Link href="/trace" className="trace-detail-back">
        <ArrowLeft aria-hidden="true" />
        Back to Traces
      </Link>

      <section className="trace-detail-hero">
        <div>
          <div className="trace-detail-badges">
            <span className={`trace-mvp-status ${statusClass(traceItem)}`}>{statusLabel(traceItem)}</span>
            <span className="trace-mvp-status trace-status-neutral">{replayReadiness(traceItem)}</span>
            {traceItem.root_failure_category ? <span className="trace-mvp-status trace-status-failed">{traceItem.root_failure_category}</span> : null}
          </div>
          <h1>{agentLabel(traceItem, rootNode)} trace</h1>
          <p>{statusLabel(traceItem)} · {agentLabel(traceItem, rootNode)} · {traceItem.providers[0] ?? "Production"}</p>
        </div>
        <div className="trace-detail-hero-actions">
          <button type="button" className="btn btn-soft" onClick={() => void refreshTraceDetail()} disabled={tracesQuery.isFetching || traceByIdQuery.isFetching || traceTreeQuery.isFetching || callDetailQuery.isFetching}>
            <RefreshCw aria-hidden="true" />
            {tracesQuery.isFetching || traceByIdQuery.isFetching || traceTreeQuery.isFetching || callDetailQuery.isFetching ? "Refreshing..." : "Refresh"}
          </button>
          <button type="button" className="btn btn-soft" onClick={() => void copyTraceId()}>
            <Copy aria-hidden="true" />
            {copied ? "Copied" : "Copy trace ID"}
          </button>
          <button type="button" className="btn btn-primary" onClick={runReplay} disabled={!rootCallId || replayMutation.isPending}>
            <Play aria-hidden="true" />
            {replayMutation.isPending ? "Running..." : "Run replay"}
          </button>
        </div>
      </section>

      {actionState ? (
        <div className={`trace-mvp-action-message ${actionState.kind === "error" ? "is-error" : ""}`} role="status">
          {actionState.message}
        </div>
      ) : null}

      <section className="trace-detail-metrics" aria-label="Trace metadata">
        <MetricCard label="Latency" value={latencyLabel(latency)} />
        <MetricCard label="Cost" value={cost > 0 ? formatUsd(cost) : DASH} />
        <MetricCard label="Model" value={modelLabel(traceItem, rootNode)} />
        <MetricCard label="Spans / steps" value={formatCount(spans)} />
        <MetricCard label="Created" value={traceDateLabel(traceItem.started_at)} />
      </section>

      <section className="trace-detail-layout" aria-label="Trace investigation">
        <main className="trace-detail-main">
          <article className="trace-detail-card">
            <header>
              <h2>Trace timeline</h2>
              <p>Ordered execution evidence from root call through child steps.</p>
            </header>
            {traceTreeQuery.isLoading ? <div className="trace-detail-empty">Loading trace timeline...</div> : null}
            {traceTreeQuery.error ? <div className="trace-detail-empty">Trace tree unavailable.</div> : null}
            {!traceTreeQuery.isLoading && timelineRows.length === 0 ? <div className="trace-detail-empty">No structured trace steps captured yet.</div> : null}
            {timelineRows.length > 0 ? (
              <div className="trace-detail-timeline">
                {timelineRows.map(({ node, depth, index }) => (
                  <div key={node.call_id} className={`trace-detail-step ${node.error_code ? "is-failed" : ""}`} style={{ "--trace-depth": depth } as CSSProperties}>
                    <span className="trace-detail-step-index">{index}</span>
                    <div>
                      <span className="trace-detail-step-type">{stepTypeLabel(node, depth)}</span>
                      <strong>{nodeTitle(node, depth)}</strong>
                      <p>{nodeSummary(node)}</p>
                      <div className="trace-detail-step-actions">
                        <Link href={`/calls/${node.call_id}`} className="btn btn-soft btn-sm">
                          <ExternalLink aria-hidden="true" />
                          View call
                        </Link>
                        <button type="button" className="btn btn-soft btn-sm" onClick={() => void copyValue(node.call_id, "Call ID copied.")}>
                          <Copy aria-hidden="true" />
                          Copy call ID
                        </button>
                      </div>
                    </div>
                    <span className={`trace-mvp-status ${/fail|error|timeout/i.test(node.status) ? "trace-status-failed" : "trace-status-success"}`}>{node.status}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </article>

          <article className="trace-detail-card">
            <header>
              <h2>Input / Output</h2>
              <p>Captured prompt and final response for the root call.</p>
            </header>
            <div className="trace-detail-io-grid">
              <div>
                <span>Input</span>
                <p>{promptText ?? "No input captured."}</p>
              </div>
              <div>
                <span>Output</span>
                <p>{responseText ?? "No output captured."}</p>
              </div>
            </div>
          </article>

          <article className="trace-detail-card">
            <header>
              <h2>Tool behavior</h2>
              <p>Tool calls and failed execution steps extracted from captured evidence.</p>
            </header>
            {tools.length === 0 ? <div className="trace-detail-empty">No tool calls captured.</div> : (
              <div className="trace-detail-list">
                {tools.map((tool) => (
                  <div key={tool.id} className={`trace-detail-list-row ${tool.failed ? "is-failed" : ""}`}>
                    <div>
                      <strong>{tool.name}</strong>
                      <span>{tool.summary}</span>
                    </div>
                    <span className={`trace-mvp-status ${tool.failed ? "trace-status-failed" : "trace-status-neutral"}`}>{tool.status}</span>
                  </div>
                ))}
              </div>
            )}
          </article>

          <article className="trace-detail-card">
            <header>
              <h2>Retrieval / Memory</h2>
              <p>Context attached to this trace when captured by the SDK.</p>
            </header>
            <div className="trace-detail-context-grid">
              <div>
                <strong>Retrieval context</strong>
                {retrievalItems.length > 0 ? retrievalItems.map((item) => <span key={item}>{item}</span>) : <span>No retrieval context captured.</span>}
              </div>
              <div>
                <strong>Memory</strong>
                {memoryItems.length > 0 ? memoryItems.map((item) => <span key={item}>{item}</span>) : <span>No memory events captured.</span>}
              </div>
            </div>
          </article>

          <article className="trace-detail-card">
            <header>
              <h2>Diagnosis result</h2>
              <p>Failure classification and root-cause evidence when available.</p>
            </header>
            {diagnosis ? (
              <div className="trace-detail-diagnosis">
                <div><span>Failure code</span><strong>{diagnosis.code}</strong></div>
                <div><span>Root cause</span><strong>{diagnosis.rootCause}</strong></div>
                <div><span>Confidence</span><strong>{diagnosis.confidence}</strong></div>
              </div>
            ) : (
              <div className="trace-detail-empty">No diagnosis generated yet.</div>
            )}
          </article>

          <article className="trace-detail-card">
            <header>
              <div>
                <h2>Raw evidence</h2>
                <p>Original trace, root call, payload, and tree response for debugging.</p>
              </div>
              <div className="trace-detail-raw-actions">
                <button type="button" className="btn btn-soft btn-sm" onClick={() => void copyRawPayload()}>
                  <Copy aria-hidden="true" />
                  Copy JSON
                </button>
                <button type="button" className="btn btn-soft btn-sm" onClick={exportRawPayload}>
                  <Download aria-hidden="true" />
                  Download
                </button>
              </div>
            </header>
            <details className="trace-raw-disclosure">
              <summary>View raw payload JSON</summary>
              <pre>{rawPayloadJson}</pre>
            </details>
          </article>
        </main>

        <aside className="trace-detail-panel" aria-label="Trace action panel">
          <div className="trace-detail-panel-card">
            <span>Replay readiness</span>
            <strong>{replayReadiness(traceItem)}</strong>
            <p>{rootCallId ? "Root call evidence is available for trusted replay." : "This trace is missing a root call id."}</p>
          </div>
          <div className="trace-detail-panel-card">
            <span>Related evidence</span>
            <strong>{rootCallId || DASH}</strong>
            <div className="trace-detail-panel-actions">
              {rootCallId ? <Link href={`/calls/${rootCallId}`} className="btn btn-soft btn-sm">View source call</Link> : null}
              {rootCallId ? (
                <button type="button" className="btn btn-soft btn-sm" onClick={() => void copyValue(rootCallId, "Root call ID copied.")}>
                  <Copy aria-hidden="true" />
                  Copy root ID
                </button>
              ) : null}
            </div>
          </div>
          <div className="trace-detail-actions">
            <button type="button" className="btn btn-primary" onClick={runReplay} disabled={!rootCallId || replayMutation.isPending}>
              <Play aria-hidden="true" />
              {replayMutation.isPending ? "Running..." : "Run replay"}
            </button>
            <button type="button" className="btn btn-soft" onClick={() => void copyTraceId()}>
              <Copy aria-hidden="true" />
              {copied ? "Copied" : "Copy trace ID"}
            </button>
            <button type="button" className="btn btn-soft" onClick={exportRawPayload}>
              <Download aria-hidden="true" />
              Export raw JSON
            </button>
          </div>
          <div className="trace-detail-panel-card">
            <span>Golden eligibility</span>
            <strong>Not eligible from raw trace</strong>
            <p>Run trusted replay before creating a Golden.</p>
          </div>
          <div className="trace-detail-panel-card">
            <span>Trust rule</span>
            <strong><ShieldCheck aria-hidden="true" /> Raw trace is evidence only</strong>
            <p>Create Golden must come from verified replay proof, not raw trace data.</p>
          </div>
        </aside>
      </section>
    </div>
  );
}
