"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { formatCount, formatDateTime, formatUsd, numberFromUnknown, safeString } from "@/lib/format";
import {
  useCallDetail,
  useListCalls,
  useCallTraceTree,
  useDiagnosisFixWatch,
  useDiagnosisPrLinks,
  useSubmitDiagnosisFeedback,
  useResolveDiagnosis,
  useCreateShareLink,
  useGenerateDiagnosisPr,
  useMarkDiagnosisFixCopied,
} from "@/lib/hooks";
import { prGenerationSchema, type PrGenerationFormData } from "@/lib/schemas";
import type { JsonMap, TraceTreeNode } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";
import { JudgeScorecard } from "@/components/judge-scorecard";
import { JudgeNarrativeCard } from "@/components/judge-narrative-card";
import { CounterfactualImpact } from "@/components/counterfactual-impact";

function asObject(value: unknown): JsonMap {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as JsonMap;
  }
  return {};
}

function readPath(payload: JsonMap, path: string[]): unknown {
  let current: unknown = payload;
  for (const segment of path) {
    if (!current || typeof current !== "object" || Array.isArray(current) || !(segment in current)) {
      return undefined;
    }
    current = (current as JsonMap)[segment];
  }
  return current;
}

function stringifyValue(value: unknown): string | null {
  if (value == null) {
    return null;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value) || typeof value === "object") {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return null;
    }
  }
  return null;
}

function firstPresent(payload: JsonMap, paths: string[][]): string | null {
  for (const path of paths) {
    const value = stringifyValue(readPath(payload, path));
    if (value) {
      return value;
    }
  }
  return null;
}

function extractPromptText(payload: JsonMap): string | null {
  return firstPresent(payload, [
    ["prompt"],
    ["input"],
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
    ["result"],
    ["response_text"],
    ["request", "response"],
    ["payload", "response"],
    ["payload", "output"],
  ]);
}

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch { /* noop */ }
  };
  return (
    <button type="button" className="copy-btn" onClick={() => void copy()} title={`Copy ${label}`}>
      {copied ? "✓" : "⎘"}
    </button>
  );
}

function ConfidenceBadge({ confidence, version, ageDays }: {
  confidence: string | null;
  version: string | null;
  ageDays: number | null;
}) {
  if (!confidence) return null;
  const low = confidence.toLowerCase() === "low";
  return (
    <span className={`conf-badge ${low ? "conf-badge-low" : "conf-badge-ok"}`} title={`Pricing v${version ?? "?"} · ${ageDays != null ? `${ageDays}d old` : "age unknown"}`}>
      {low ? "⚠ Low confidence" : "✓ Pricing verified"} {version ? `v${version}` : ""}
    </span>
  );
}

function StructuredObject({ data, emptyLabel = "No data" }: { data: JsonMap; emptyLabel?: string }) {
  const entries = Object.entries(data);
  if (entries.length === 0) return <p className="empty-inline">{emptyLabel}</p>;
  return (
    <dl className="struct-list">
      {entries.map(([k, v]) => (
        <div key={k} className="struct-row">
          <dt className="struct-key">{k}</dt>
          <dd className="struct-val">
            {typeof v === "object" && v !== null
              ? <pre className="struct-pre">{JSON.stringify(v, null, 2)}</pre>
              : String(v ?? "—")}
          </dd>
        </div>
      ))}
    </dl>
  );
}


const FAILED_STATUS_SET = new Set(["failed", "error", "timeout", "auth_failure", "loop_detected"]);
const PROVIDER_COLORS: Record<string, string> = {
  openai: "#3a9663",
  anthropic: "#f8fafc",
  google: "#5088b7",
  gemini: "#5088b7",
  cohere: "#c94b5f",
  mistral: "#9098a8",
};
function providerColor(p: string | null): string {
  return PROVIDER_COLORS[(p ?? "").toLowerCase()] ?? "#6b7280";
}

function collectAgentStats(node: TraceTreeNode, acc: Map<string, { calls: number; cost: number; failed: boolean }>) {
  const key = node.agent_name ?? "unknown-agent";
  const prev = acc.get(key) ?? { calls: 0, cost: 0, failed: false };
  acc.set(key, {
    calls: prev.calls + 1,
    cost: prev.cost + node.wasted_cost_usd,
    failed: prev.failed || FAILED_STATUS_SET.has(node.status.toLowerCase()),
  });
  for (const child of node.children) {
    collectAgentStats(child, acc);
  }
}

function TraceTreeView({ node, depth = 0 }: { node: TraceTreeNode; depth?: number }) {
  const hasChildren = node.children.length > 0;
  const [expanded, setExpanded] = useState(depth < 3);
  const isFailed = FAILED_STATUS_SET.has(node.status.toLowerCase());
  const agentLabel = node.agent_name ?? node.call_id.slice(0, 8);

  const borderColor = isFailed ? "var(--dashboard-danger)" : node.status === "success" ? "var(--dashboard-success)" : "var(--dashboard-warning)";
  const bgColor = isFailed ? "var(--dashboard-danger-soft)" : "transparent";

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

export default function CallDetailPage() {
  const params = useParams<{ id: string }>();
  const callId = typeof params.id === "string" ? params.id : "";

  const detailQuery = useCallDetail(callId);
  const prevCallQuery = useListCalls({
    date_from: detailQuery.data?.call.created_at ?? "",
    sort_by: "created_at",
    sort_order: "asc",
    limit: 3,
    offset: 0,
  });
  const nextCallQuery = useListCalls({
    date_to: detailQuery.data?.call.created_at ?? "",
    sort_by: "created_at",
    sort_order: "desc",
    limit: 3,
    offset: 0,
  });
  const traceTreeQuery = useCallTraceTree(callId);
  const fixWatchQuery = useDiagnosisFixWatch(callId);
  const prLinksQuery = useDiagnosisPrLinks(callId);

  const feedbackMutation = useSubmitDiagnosisFeedback();
  const resolveMutation = useResolveDiagnosis();
  const shareMutation = useCreateShareLink();
  const generatePrMutation = useGenerateDiagnosisPr();
  const markFixCopiedMutation = useMarkDiagnosisFixCopied();

  const [share, setShare] = useState<Awaited<ReturnType<ReturnType<typeof useCreateShareLink>["mutateAsync"]>> | null>(null);
  const [prResult, setPrResult] = useState<Awaited<ReturnType<ReturnType<typeof useGenerateDiagnosisPr>["mutateAsync"]>> | null>(null);
  const [actionNote, setActionNote] = useState<string>("");

  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<PrGenerationFormData>({
    resolver: zodResolver(prGenerationSchema),
    defaultValues: {
      repositoryOwner: "",
      repositoryName: "",
      baseBranch: "main",
    },
  });

  const detail = detailQuery.data ?? null;
  const traceTree = traceTreeQuery.isError ? null : traceTreeQuery.data ?? null;
  const fixWatch = fixWatchQuery.isError ? null : fixWatchQuery.data ?? null;
  const prLinks = prLinksQuery.isError ? [] : prLinksQuery.data ?? [];
  const loading = detailQuery.isLoading;
  const error = detailQuery.error?.message ?? null;

  const diagnosis = useMemo(() => {
    const diagnoses = detail?.diagnosis_result?.diagnoses;
    if (!Array.isArray(diagnoses) || diagnoses.length === 0) {
      return {} as JsonMap;
    }
    return asObject(diagnoses[0]);
  }, [detail]);

  const fix = useMemo(() => asObject(diagnosis.fix), [diagnosis]);
  const evidence = useMemo(() => asObject(diagnosis.evidence), [diagnosis]);
  const blastRadius = useMemo(() => asObject(diagnosis.blast_radius), [diagnosis]);
  const promptText = useMemo(() => (detail ? extractPromptText(detail.payload) : null), [detail]);
  const responseText = useMemo(() => (detail ? extractResponseText(detail.payload) : null), [detail]);

  async function submitFeedback(wasHelpful: boolean) {
    if (!callId) return;
    try {
      await feedbackMutation.mutateAsync({ callId, wasHelpful, note: actionNote.trim() || undefined });
      setActionNote(wasHelpful ? "Marked helpful." : "Marked not helpful.");
    } catch (feedbackError) {
      const message = feedbackError instanceof Error ? feedbackError.message : "Feedback action failed.";
      setActionNote(message);
    }
  }

  async function shareDiagnosis() {
    if (!callId) return;
    try {
      const created = await shareMutation.mutateAsync(callId);
      setShare(created);
      setActionNote("Read-only share link created.");
    } catch (shareError) {
      const message = shareError instanceof Error ? shareError.message : "Share action failed.";
      setActionNote(message);
    }
  }

  async function markResolved() {
    if (!callId) return;
    try {
      const resolved = await resolveMutation.mutateAsync(callId);
      setActionNote(resolved.message);
    } catch (resolveError) {
      const message = resolveError instanceof Error ? resolveError.message : "Resolve action failed.";
      setActionNote(message);
    }
  }

  async function copyFixSuggestion() {
    if (!callId) return;
    const snippet = safeString(fix.code, "").trim();
    if (!snippet) {
      setActionNote("No generated code snippet available to copy.");
      return;
    }
    try {
      if (typeof navigator === "undefined" || !navigator.clipboard) {
        throw new Error("Clipboard API is not available in this browser.");
      }
      await navigator.clipboard.writeText(snippet);
      await markFixCopiedMutation.mutateAsync(callId);
      setActionNote("Fix snippet copied and audit-logged.");
    } catch (copyError) {
      const message = copyError instanceof Error ? copyError.message : "Copy action failed.";
      setActionNote(message);
    }
  }

  async function onGeneratePr(data: PrGenerationFormData) {
    if (!callId) return;
    try {
      const created = await generatePrMutation.mutateAsync({
        callId,
        repoOwner: data.repositoryOwner.trim() || undefined,
        repoName: data.repositoryName.trim() || undefined,
        baseBranch: data.baseBranch.trim() || undefined,
      });
      setPrResult(created);
      setActionNote(`PR #${created.pull_request_number} generated successfully.`);
    } catch (generateError) {
      const message = generateError instanceof Error ? generateError.message : "Generate PR failed.";
      setActionNote(message);
    }
  }

  if (loading) {
    return (
      <section className="panel">
        <div className="loading" />
      </section>
    );
  }

  if (error || !detail) {
    return (
      <section className="panel">
        <p>{error ?? "Call detail unavailable."}</p>
      </section>
    );
  }

  const comparisonMultiplier = numberFromUnknown(diagnosis.comparison_multiplier || diagnosis.anomaly_multiplier);
  const wastedCostUsd = numberFromUnknown(diagnosis.wasted_cost_usd || diagnosis.cost_impact_usd);
  const errorCode = detail.call.error_code ?? null;
  const errorMessage = typeof detail.payload.error_message === "string" ? detail.payload.error_message : null;
  const failureReason =
    detail.payload.failure_reason && typeof detail.payload.failure_reason === "object" && !Array.isArray(detail.payload.failure_reason)
      ? (detail.payload.failure_reason as Record<string, unknown>)
      : null;
  const newerCall = prevCallQuery.data?.items.find((item) => item.call_id !== callId) ?? null;
  const olderCall = nextCallQuery.data?.items.find((item) => item.call_id !== callId) ?? null;
  const requestPayload = asObject(detail.payload.request);
  const responsePayload = asObject(detail.payload.response);

  return (
    <div className="calls-detail-workspace">
      {/* ── Breadcrumb ── */}
      <nav className="detail-breadcrumb" aria-label="breadcrumb">
        <Link href="/calls" className="breadcrumb-back">← Call Evidence</Link>
        <span className="breadcrumb-sep">/</span>
        <span className="breadcrumb-current mono">{callId.slice(0, 16)}…</span>
      </nav>

      <section className="detail-nav-row" aria-label="Call navigation">
        {newerCall ? (
          <Link href={`/calls/${newerCall.call_id}`} className="btn btn-soft btn-sm">
            ← Prev Call
          </Link>
        ) : <span />}
        {olderCall ? (
          <Link href={`/calls/${olderCall.call_id}`} className="btn btn-soft btn-sm">
            Next Call →
          </Link>
        ) : null}
      </section>

      {/* ── Call header ── */}
      <section className="panel" id="call-header">
        <header className="panel-header">
          <div>
            <div className="call-id-row">
              <h3>Call Detail</h3>
              <span className="call-id-pill mono">{callId}</span>
              <CopyButton text={callId} label="Call ID" />
              <ConfidenceBadge
                confidence={detail.call.cost_confidence}
                version={detail.call.pricing_version}
                ageDays={detail.call.pricing_age_days}
              />
            </div>
            <p>{formatDateTime(detail.call.created_at)}{detail.call.agent_name ? ` · Agent: ${detail.call.agent_name}` : ""}{detail.call.user_id ? ` · User: ${detail.call.user_id}` : ""}</p>
          </div>
          <StatusPill value={detail.call.status} />
        </header>

        {/* ── KPI grid (8 cards) ── */}
        <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
          <article className="kpi-card">
            <span className="kpi-label">Provider</span>
            <strong className="kpi-value">{safeString(detail.call.provider, "unknown")}</strong>
          </article>
          <article className="kpi-card">
            <span className="kpi-label">Model</span>
            <strong className="kpi-value">{safeString(detail.call.model, "unknown")}</strong>
          </article>
          <article className="kpi-card">
            <span className="kpi-label">Cost</span>
            <strong className="kpi-value mono">{formatUsd(detail.call.cost_usd)}</strong>
          </article>
          <article className="kpi-card">
            <span className="kpi-label">Latency</span>
            <strong className="kpi-value mono">
              {detail.call.latency_ms != null
                ? detail.call.latency_ms < 1000
                  ? `${detail.call.latency_ms}ms`
                  : `${(detail.call.latency_ms / 1000).toFixed(2)}s`
                : "—"}
            </strong>
          </article>
          <article className="kpi-card">
            <span className="kpi-label">Total Tokens</span>
            <strong className="kpi-value mono">{formatCount(detail.call.total_tokens)}</strong>
          </article>
          <article className="kpi-card">
            <span className="kpi-label">Prompt Tokens</span>
            <strong className="kpi-value mono">{numberFromUnknown(detail.payload.prompt_tokens) > 0 ? formatCount(numberFromUnknown(detail.payload.prompt_tokens)) : "—"}</strong>
          </article>
          <article className="kpi-card">
            <span className="kpi-label">Completion Tokens</span>
            <strong className="kpi-value mono">{numberFromUnknown(detail.payload.completion_tokens) > 0 ? formatCount(numberFromUnknown(detail.payload.completion_tokens)) : "—"}</strong>
          </article>
          <article className="kpi-card">
            <span className="kpi-label">Call Type</span>
            <strong className="kpi-value">{safeString(detail.call.call_type, "—")}</strong>
          </article>
        </div>

        {(errorCode || errorMessage || failureReason) && (
          <div className="list" style={{ marginTop: 12 }}>
            {errorCode && (
              <div className="list-row">
                <div className="list-main">
                  <strong>Error Code</strong>
                  <span className="mono" style={{ color: "#ef4444" }}>{errorCode}</span>
                </div>
              </div>
            )}
            {errorMessage && (
              <div className="list-row">
                <div className="list-main">
                  <strong>Error Message</strong>
                  <span>{errorMessage}</span>
                </div>
              </div>
            )}
            {failureReason && (
              <div className="list-row">
                <div className="list-main">
                  <strong>Failure Reason</strong>
                </div>
                <pre className="panel-muted" style={{ padding: 8, borderRadius: 8, fontSize: 12, overflowX: "auto", marginTop: 4, width: "100%" }}>
                  {JSON.stringify(failureReason, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="grid-two">
        <article className="panel">
          <header className="panel-header">
            <div>
              <h3>Raw Prompt</h3>
              <p>Captured input payload or prompt content for this call.</p>
            </div>
            {promptText ? <CopyButton text={promptText} label="prompt" /> : null}
          </header>
          {promptText ? (
            <pre className="code-block raw-call-pre">{promptText}</pre>
          ) : (
            <div className="empty">No prompt text captured for this call.</div>
          )}
          {Object.keys(requestPayload).length > 0 ? (
            <details className="raw-call-details">
              <summary>Request payload JSON</summary>
              <pre className="struct-pre raw-call-json">{JSON.stringify(requestPayload, null, 2)}</pre>
            </details>
          ) : null}
        </article>

        <article className="panel">
          <header className="panel-header">
            <div>
              <h3>Raw Response</h3>
              <p>Captured model output or response payload for this call.</p>
            </div>
            {responseText ? <CopyButton text={responseText} label="response" /> : null}
          </header>
          {responseText ? (
            <pre className="code-block raw-call-pre">{responseText}</pre>
          ) : (
            <div className="empty">No response text captured for this call.</div>
          )}
          {Object.keys(responsePayload).length > 0 ? (
            <details className="raw-call-details">
              <summary>Response payload JSON</summary>
              <pre className="struct-pre raw-call-json">{JSON.stringify(responsePayload, null, 2)}</pre>
            </details>
          ) : null}
        </article>
      </section>

      {/* ── Diagnosis summary ── */}
      {safeString(diagnosis.root_cause, "") && (
        <section className="panel">
          <header className="panel-header">
            <div>
              <h3>Diagnosis</h3>
              <p>Root cause determined by the diagnosis engine.</p>
            </div>
          </header>
          <p className="diagnosis-root-cause">{safeString(diagnosis.root_cause, "")}</p>
        </section>
      )}

      {/* ── Counterfactual ROI ──
          "If Zroky hadn't caught this, X dollars and Y calls would have
          continued to burn." Renders silently when we can't ground the
          projection in real numbers — never fabricates figures. */}
      <CounterfactualImpact diagnosis={diagnosis as Record<string, unknown>} />

      {/* ── Layer 3 judge surfaces ──
          The narrative card is the screenshot-worthy hero — verbatim judge
          reasoning as a blockquote with a copy-to-clipboard CTA. The
          scorecard underneath shows per-dimension bars + reasons. Both
          render conditionally, silent when no judge data is present, so
          they're safe on calls that never went through Layer 3. */}
      <JudgeNarrativeCard
        source={evidence as Record<string, unknown>}
        category={typeof diagnosis.category === "string" ? diagnosis.category : null}
      />
      <JudgeScorecard source={evidence as Record<string, unknown>} />


      <section className="grid-two">
        <article className="panel" id="evidence">
          <header className="panel-header">
            <div>
              <h3>Evidence</h3>
              <p>Machine-extracted signals for this failure.</p>
            </div>
          </header>
          <StructuredObject data={evidence} emptyLabel="No evidence extracted." />
        </article>

        <article className="panel">
          <header className="panel-header">
            <div>
              <h3>Fix Guidance</h3>
              <p>Primary and fallback recommendations.</p>
            </div>
          </header>

          <div className="list">
            <div className="list-row">
              <div className="list-main">
                <strong>Primary Fix</strong>
                <span>{safeString(fix.primary, "No primary fix returned.")}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Alternative</strong>
                <span>{safeString(fix.alternative, "No alternative fix returned.")}</span>
              </div>
            </div>
            {safeString(fix.code, "") && (
              <>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Code Suggestion</strong>
                  </div>
                </div>
                <pre className="code-block">{safeString(fix.code, "")}</pre>
              </>
            )}
          </div>
        </article>
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Multi-Agent Trace Tree</h3>
            <p>Which agent did what, in order — with costs, latency, and failures highlighted.</p>
          </div>
          {traceTree?.trace_id ? (
            <Link href={`/trace/${traceTree.trace_id}`} className="btn btn-soft">
              View in Traces →
            </Link>
          ) : null}
        </header>

        {traceTree ? (
          <>
            <div className="list">
              {traceTree.root_failure && (
                <div className="list-row">
                  <div className="list-main">
                    <strong>Root Failure</strong>
                    <span>
                      {safeString(traceTree.root_failure.category, "unknown")} · {safeString(traceTree.root_failure.root_cause, "No root cause available")}
                    </span>
                  </div>
                </div>
              )}
              <div className="list-row">
                <div className="list-main"><strong>Trace ID</strong></div>
                <span className="mono">{safeString(traceTree.trace_id, "n/a")}</span>
              </div>
              <div className="list-row">
                <div className="list-main"><strong>Downstream Calls</strong></div>
                <span className="mono">{formatCount(traceTree.total_downstream_calls)}</span>
              </div>
              <div className="list-row">
                <div className="list-main"><strong>Total Wasted Cost</strong></div>
                <span className="mono">{formatUsd(traceTree.total_wasted_cost_usd)}</span>
              </div>
            </div>

            {/* Agent attribution grid */}
            {(() => {
              const stats = new Map<string, { calls: number; cost: number; failed: boolean }>();
              collectAgentStats(traceTree.root_node, stats);
              const entries = Array.from(stats.entries());
              if (entries.length === 0) return null;
              return (
                <div style={{ marginTop: 16, marginBottom: 16 }}>
                  <p style={{ fontSize: 12, color: "var(--muted)", marginBottom: 8, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    Agent Attribution ({entries.length} agent{entries.length !== 1 ? "s" : ""})
                  </p>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
                    {entries.map(([name, s]) => (
                      <div
                        key={name}
                        style={{
                          border: s.failed ? "1px solid rgba(239,68,68,0.4)" : "1px solid var(--border)",
                          borderRadius: 8,
                          padding: "8px 12px",
                          background: s.failed ? "rgba(239,68,68,0.05)" : "var(--surface-muted)",
                        }}
                      >
                        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{name}</div>
                        <div style={{ fontSize: 12, color: "var(--muted)" }}>
                          {s.calls} call{s.calls !== 1 ? "s" : ""}
                          {s.cost > 0 ? ` · wasted ${formatUsd(s.cost)}` : ""}
                        </div>
                        {s.failed && (
                          <div style={{ fontSize: 11, color: "#ef4444", marginTop: 2 }}>⚠ had failure</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}

            <div style={{ marginTop: 8 }}>
              <ul style={{ margin: 0, padding: 0 }}>
                <TraceTreeView node={traceTree.root_node} depth={0} />
              </ul>
            </div>
          </>
        ) : (
          <div className="empty">No trace context available for this call.</div>
        )}
      </section>

      <section className="grid-three">
        <article className="panel panel-muted">
          <header className="panel-header">
            <div>
              <h3>Tool Timeline</h3>
              <p>Trace trail if tools were involved.</p>
            </div>
          </header>
          <StructuredObject
            data={asObject(detail.payload.tool_lifecycle_summary)}
            emptyLabel="No tool activity recorded."
          />
        </article>

        <article className="panel panel-muted">
          <header className="panel-header">
            <div>
              <h3>Reasoning / Cache</h3>
              <p>Cost composition from payload.</p>
            </div>
          </header>
          <div className="list">
            <div className="list-row">
              <div className="list-main">
                <strong>Reasoning Cost</strong>
              </div>
              <span className="mono">{formatUsd(numberFromUnknown(detail.payload.reasoning_cost_usd))}</span>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Cache Savings</strong>
              </div>
              <span className="mono">{formatUsd(numberFromUnknown(detail.payload.cache_savings_usd))}</span>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Pricing Source</strong>
              </div>
              <span className="mono">{safeString(detail.payload.pricing_source as string, "—")}</span>
            </div>
          </div>
        </article>

        <article className="panel panel-muted">
          <header className="panel-header">
            <div>
              <h3>Blast Radius</h3>
              <p>Impact scope if linked traces exist.</p>
            </div>
          </header>
          <StructuredObject data={blastRadius} emptyLabel="No blast radius data." />
        </article>
      </section>

      <section className="grid-three">
        <article className="panel">
          <h3>Comparison Context</h3>
          <p className="hint">Compared against rolling project baseline.</p>
          <strong className="kpi-value">{comparisonMultiplier > 0 ? `${comparisonMultiplier.toFixed(2)}x` : "n/a"}</strong>
        </article>

        <article className="panel">
          <h3>Wasted Cost</h3>
          <p className="hint">Current estimated avoidable spend for this incident.</p>
          <strong className="kpi-value mono">{formatUsd(wastedCostUsd)}</strong>
        </article>

        <article className="panel">
          <h3>Fix Watch Status</h3>
          <p className="hint">Health monitoring state after recommendation rollout.</p>
          <StatusPill value={fixWatch?.status ?? safeString(diagnosis.watch_status, "not_started")} />
          {fixWatch ? (
            <p className="hint">
              {fixWatch.message} · Recurrences {formatCount(fixWatch.recurrence_count)}
              {fixWatch.watch_expires_at ? ` · Expires ${formatDateTime(fixWatch.watch_expires_at)}` : ""}
            </p>
          ) : null}
        </article>
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Generate GitHub PR</h3>
            <p>Create a branch + pull request from current diagnosis fix guidance.</p>
          </div>
          <StatusPill value={prResult?.auth_source ?? "not_generated"} />
        </header>

        <form className="grid-three" onSubmit={handleSubmit(onGeneratePr)}>
          <div className="field">
            <label htmlFor="repoOwner">Repository Owner</label>
            <input
              id="repoOwner"
              {...register("repositoryOwner")}
              placeholder="acme"
            />
          </div>

          <div className="field">
            <label htmlFor="repoName">Repository Name</label>
            <input
              id="repoName"
              {...register("repositoryName")}
              placeholder="demo-repo"
            />
          </div>

          <div className="field">
            <label htmlFor="baseBranch">Base Branch</label>
            <input
              id="baseBranch"
              {...register("baseBranch")}
              placeholder="main"
            />
          </div>

          <div className="actions" style={{ gridColumn: "1 / -1" }}>
            <button className="btn btn-primary" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Generating PR..." : "Generate PR"}
            </button>
          </div>
        </form>

        {prResult ? (
          <div className="panel-muted" style={{ padding: 12, borderRadius: 12 }}>
            <p className="hint">
              Latest PR: #{prResult.pull_request_number} · Source <strong>{prResult.auth_source}</strong>
            </p>
            <p>
              <a href={prResult.pull_request_url} target="_blank" rel="noreferrer">
                {prResult.pull_request_url}
              </a>
            </p>
          </div>
        ) : null}

        {prLinks.length > 0 ? (
          <div className="list">
            {prLinks.map((link) => (
              <div key={link.pr_link_id} className="list-row">
                <div className="list-main">
                  <strong>PR #{link.pull_request_number}</strong>
                  <span>{link.repository_owner}/{link.repository_name} · {formatDateTime(link.created_at)}</span>
                </div>
                <a className="btn btn-soft" href={link.pull_request_url} target="_blank" rel="noreferrer">
                  Open PR
                </a>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty">No PR links recorded yet for this diagnosis.</div>
        )}
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Actions</h3>
            <p>Resolve flow, diagnosis feedback, and read-only sharing.</p>
          </div>
        </header>

        <div className="actions">
          <button type="button" className="btn btn-primary" onClick={() => void submitFeedback(true)}>
            Helpful: Yes
          </button>
          <button type="button" className="btn btn-danger" onClick={() => void submitFeedback(false)}>
            Helpful: No
          </button>
          <button type="button" className="btn btn-soft" onClick={() => void markResolved()}>
            Mark Resolved
          </button>
          <button type="button" className="btn btn-soft" onClick={() => void copyFixSuggestion()}>
            Copy Fix Snippet
          </button>
          <button type="button" className="btn btn-soft" onClick={() => void submitFeedback(false)}>
            Dismissed
          </button>
          <button type="button" className="btn btn-soft" onClick={() => void shareDiagnosis()}>
            Share Diagnosis (24h)
          </button>
        </div>

        {actionNote ? <p className="hint">{actionNote}</p> : null}

        {share ? (
          <div className="panel-muted" style={{ padding: 12, borderRadius: 12 }}>
            <p className="hint">Share link (read-only · 24h):</p>
            <div className="share-url-row">
              <code className="mono share-url">{typeof window !== "undefined" ? `${window.location.origin}/share/${share.token}` : share.token}</code>
              <CopyButton text={typeof window !== "undefined" ? `${window.location.origin}/share/${share.token}` : share.token} label="share link" />
            </div>
            <p className="hint">Expires: {formatDateTime(share.expires_at)}</p>
          </div>
        ) : null}

        <div className="panel-muted" style={{ padding: 12, borderRadius: 12 }}>
          <p className="hint">
            Feedback totals: Helpful {formatCount(detail.feedback_summary.helpful_count)} · Not helpful {formatCount(detail.feedback_summary.not_helpful_count)}
          </p>
        </div>
      </section>
    </div>
  );
}
