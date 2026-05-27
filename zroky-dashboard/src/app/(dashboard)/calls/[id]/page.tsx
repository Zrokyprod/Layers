"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle, Check, CheckCircle2, Copy, Play } from "lucide-react";

import { formatCount, formatDateTime, formatUsd, numberFromUnknown, safeString } from "@/lib/format";
import {
  useCallDetail,
  useAdjacentCalls,
  useCallTraceTree,
  useDiagnosisFixWatch,
  useDiagnosisPrLinks,
  useSubmitDiagnosisFeedback,
  useResolveDiagnosis,
  useCreateShareLink,
  useGenerateDiagnosisPr,
  useMarkDiagnosisFixCopied,
  useGithubConnectionStatus,
  useCreateReplayRunFromCall,
} from "@/lib/hooks";
import { prGenerationSchema, type PrGenerationFormData } from "@/lib/schemas";
import type { ReplayMode } from "@/lib/api";
import type { JsonMap, TraceTreeNode } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";
import { JudgeScorecard } from "@/components/judge-scorecard";
import { JudgeNarrativeCard } from "@/components/judge-narrative-card";
import { CounterfactualImpact } from "@/components/counterfactual-impact";
import { DEFAULT_VERIFICATION_REPLAY_MODE, REPLAY_MODE_OPTIONS, STUB_REPLAY_MODE, replayModeProof } from "@/lib/replay-mode";
import { TraceTreeView, isFailedTraceStatus } from "@/components/trace-tree-view";

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
      {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
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
      {low ? <AlertTriangle aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
      {low ? "Low confidence" : "Pricing verified"} {version ? `v${version}` : ""}
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


function collectAgentStats(node: TraceTreeNode, acc: Map<string, { calls: number; cost: number; failed: boolean }>) {
  const key = node.agent_name ?? "unknown-agent";
  const prev = acc.get(key) ?? { calls: 0, cost: 0, failed: false };
  acc.set(key, {
    calls: prev.calls + 1,
    cost: prev.cost + node.wasted_cost_usd,
    failed: prev.failed || isFailedTraceStatus(node.status),
  });
  for (const child of node.children) {
    collectAgentStats(child, acc);
  }
}

export default function CallDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const callId = typeof params.id === "string" ? params.id : "";

  const detailQuery = useCallDetail(callId);
  const adjacentQuery = useAdjacentCalls(callId);
  const traceTreeQuery = useCallTraceTree(callId);
  const fixWatchQuery = useDiagnosisFixWatch(callId);
  const prLinksQuery = useDiagnosisPrLinks(callId);
  const githubStatus = useGithubConnectionStatus();

  const feedbackMutation = useSubmitDiagnosisFeedback();
  const resolveMutation = useResolveDiagnosis();
  const shareMutation = useCreateShareLink();
  const generatePrMutation = useGenerateDiagnosisPr();
  const markFixCopiedMutation = useMarkDiagnosisFixCopied();
  const createReplayMutation = useCreateReplayRunFromCall({
    onSuccess: (run) => router.push(`/replay/${run.id}`),
  });

  const [share, setShare] = useState<Awaited<ReturnType<ReturnType<typeof useCreateShareLink>["mutateAsync"]>> | null>(null);
  const [prResult, setPrResult] = useState<Awaited<ReturnType<ReturnType<typeof useGenerateDiagnosisPr>["mutateAsync"]>> | null>(null);
  const [feedbackNote, setFeedbackNote] = useState<string>("");
  const [resolveNote, setResolveNote] = useState<string>("");
  const [shareNote, setShareNote] = useState<string>("");
  const [replayMode, setReplayMode] = useState<ReplayMode>(DEFAULT_VERIFICATION_REPLAY_MODE);

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
  const traceTree = traceTreeQuery.data ?? null;
  const fixWatch = fixWatchQuery.data ?? null;
  const prLinks = prLinksQuery.data ?? [];
  const loading = detailQuery.isLoading;
  const error = detailQuery.error?.message ?? traceTreeQuery.error?.message ?? fixWatchQuery.error?.message ?? null;
  const traceAgentStats = useMemo(() => {
    if (!traceTree?.root_node) {
      return [];
    }
    const acc = new Map<string, { calls: number; cost: number; failed: boolean }>();
    collectAgentStats(traceTree.root_node, acc);
    return Array.from(acc.entries())
      .map(([agent, stats]) => ({ agent, ...stats }))
      .sort((a, b) => b.cost - a.cost || b.calls - a.calls);
  }, [traceTree]);

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
      await feedbackMutation.mutateAsync({ callId, wasHelpful, note: feedbackNote.trim() || undefined });
      setFeedbackNote(wasHelpful ? "Marked helpful." : "Marked not helpful.");
    } catch (feedbackError) {
      const message = feedbackError instanceof Error ? feedbackError.message : "Feedback action failed.";
      setFeedbackNote(message);
    }
  }

  async function shareDiagnosis() {
    if (!callId) return;
    try {
      const created = await shareMutation.mutateAsync(callId);
      setShare(created);
      setShareNote("Read-only share link created.");
    } catch (shareError) {
      const message = shareError instanceof Error ? shareError.message : "Share action failed.";
      setShareNote(message);
    }
  }

  async function markResolved() {
    if (!callId) return;
    try {
      const resolved = await resolveMutation.mutateAsync(callId);
      setResolveNote(resolved.message);
    } catch (resolveError) {
      const message = resolveError instanceof Error ? resolveError.message : "Resolve action failed.";
      setResolveNote(message);
    }
  }

  async function copyFixSuggestion() {
    if (!callId) return;
    const snippet = safeString(fix.code, "").trim();
    if (!snippet) {
      setShareNote("No generated code snippet available to copy.");
      return;
    }
    try {
      if (typeof navigator === "undefined" || !navigator.clipboard) {
        throw new Error("Clipboard API is not available in this browser.");
      }
      await navigator.clipboard.writeText(snippet);
      await markFixCopiedMutation.mutateAsync(callId);
      setShareNote("Fix snippet copied and audit-logged.");
    } catch (copyError) {
      const message = copyError instanceof Error ? copyError.message : "Copy action failed.";
      setShareNote(message);
    }
  }

  function createReplay() {
    if (!callId) return;
    createReplayMutation.mutate({ callId, payload: { replay_mode: replayMode } });
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
      setResolveNote(`PR #${created.pull_request_number} generated successfully.`);
    } catch (generateError) {
      const message = generateError instanceof Error ? generateError.message : "Generate PR failed.";
      setResolveNote(message);
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
  const newerCall = adjacentQuery.data?.prev ?? null;
  const olderCall = adjacentQuery.data?.next ?? null;
  const requestPayload = asObject(detail.payload.request);
  const responsePayload = asObject(detail.payload.response);

  return (
    <div className="call-detail-page">
      {/* ── Breadcrumb ── */}
      <nav className="detail-breadcrumb" aria-label="breadcrumb">
        <Link href="/calls" className="breadcrumb-back">← Calls</Link>
        <span className="breadcrumb-sep">/</span>
        <span className="breadcrumb-current mono">{callId.slice(0, 16)}…</span>
      </nav>

      <section className="detail-nav-row" aria-label="Call navigation">
        {newerCall ? (
          <Link href={`/calls/${newerCall.id}`} className="btn btn-soft btn-sm">
            ← {newerCall.model ?? "Prev"} · {newerCall.status}
          </Link>
        ) : <span />}
        {olderCall ? (
          <Link href={`/calls/${olderCall.id}`} className="btn btn-soft btn-sm">
            {olderCall.model ?? "Next"} · {olderCall.status} →
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
          <div className="detail-action-group">
            <select
              value={replayMode}
              onChange={(event) => setReplayMode(event.target.value as typeof replayMode)}
              className="input detail-mode-select"
            >
              {REPLAY_MODE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="alert-cat-badge badge-gray" title={replayMode === STUB_REPLAY_MODE ? "Stub replay is a sanity check, not a verified fix." : undefined}>
              {replayModeProof(replayMode)}
            </span>
            <button type="button" className="btn btn-primary btn-sm" onClick={createReplay} disabled={createReplayMutation.isPending}>
              <Play aria-hidden="true" />
              {createReplayMutation.isPending ? "Creating..." : "Replay"}
            </button>
            <button
              type="button"
              className="ask-trigger-btn"
              onClick={() => window.dispatchEvent(new CustomEvent("open-ask-zroky", {
                detail: {
                  context: { call_id: callId },
                  prefill: "Why did this call behave this way?",
                },
              }))}
              title="Ask Zroky why this call behaved this way"
            >
              <span className="ask-trigger-text">Ask Zroky about this call</span>
            </button>
            <StatusPill value={detail.call.status} />
          </div>
        </header>

        {/* ── KPI grid (8 cards) ── */}
        <div className="kpi-grid detail-kpi-grid">
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
          <div className="list detail-list-stack">
            {errorCode && (
              <div className="list-row">
                <div className="list-main">
                  <strong>Error Code</strong>
                  <span className="mono detail-error-code">{errorCode}</span>
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
                <pre className="struct-pre detail-inset">
                  {JSON.stringify(failureReason, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </section>

      {traceTree ? (
        <section className="panel">
          <header className="panel-header">
            <div>
              <h3>Trace Tree</h3>
              <p>Downstream calls grouped by agent, provider, cost, and failure status.</p>
            </div>
            <StatusPill value={traceTree.root_failure ? "failed" : "ok"} />
          </header>
          <div className="kpi-grid detail-kpi-grid">
            <article className="kpi-card">
              <span className="kpi-label">Downstream Calls</span>
              <strong className="kpi-value mono">{formatCount(traceTree.total_downstream_calls)}</strong>
            </article>
            <article className="kpi-card">
              <span className="kpi-label">Wasted Cost</span>
              <strong className="kpi-value mono">{formatUsd(traceTree.total_wasted_cost_usd)}</strong>
            </article>
            <article className="kpi-card">
              <span className="kpi-label">Root Failure</span>
              <strong className="kpi-value">{traceTree.root_failure?.category ?? "None"}</strong>
            </article>
            <article className="kpi-card">
              <span className="kpi-label">Agents</span>
              <strong className="kpi-value mono">{formatCount(traceAgentStats.length)}</strong>
            </article>
          </div>
          {traceAgentStats.length > 0 ? (
            <div className="detail-chip-row">
              {traceAgentStats.map((stats) => (
                <span key={stats.agent} className="trace-badge trace-badge-multi">
                  {stats.agent}: {formatCount(stats.calls)} calls
                  {stats.cost > 0 ? `, ${formatUsd(stats.cost)} wasted` : ""}
                  {stats.failed ? ", failed" : ""}
                </span>
              ))}
            </div>
          ) : null}
          <ul className="trace-tree-list">
            <TraceTreeView node={traceTree.root_node} />
          </ul>
        </section>
      ) : null}

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

        {wastedCostUsd > 0 && (
          <article className="panel">
            <h3>Wasted Cost</h3>
            <p className="hint">Current estimated avoidable spend for this incident.</p>
            <strong className="kpi-value mono">{formatUsd(wastedCostUsd)}</strong>
          </article>
        )}

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
        {comparisonMultiplier > 0 && (
          <article className="panel">
            <h3>Comparison Context</h3>
            <p className="hint">Compared against rolling project baseline.</p>
            <strong className="kpi-value">{`${comparisonMultiplier.toFixed(2)}x`}</strong>
          </article>
        )}

        <article className="panel">
          <h3>Wasted Cost</h3>
          <p className="hint">Current estimated avoidable spend for this incident.</p>
          <strong className="kpi-value mono">{formatUsd(wastedCostUsd)}</strong>
        </article>

        {fixWatch && (
          <article className="panel">
            <h3>Fix Watch Status</h3>
            <p className="hint">Health monitoring state after recommendation rollout.</p>
            <StatusPill value={fixWatch.status} />
            <p className="hint">
              {fixWatch.message} · Recurrences {formatCount(fixWatch.recurrence_count)}
              {fixWatch.watch_expires_at ? ` · Expires ${formatDateTime(fixWatch.watch_expires_at)}` : ""}
            </p>
          </article>
        )}
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Generate GitHub PR</h3>
            <p>Create a branch + pull request from current diagnosis fix guidance.</p>
          </div>
          <StatusPill value={prResult?.auth_source ?? "not_generated"} />
        </header>

        {!githubStatus.isLoading && !githubStatus.data?.connected && (
          <div className="detail-warning">
            <strong>GitHub not connected.</strong>{" "}
            <Link href="/settings/providers">Connect GitHub in Settings - Providers</Link> to generate PRs.
          </div>
        )}
        {githubStatus.data?.connected && (
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

          <div className="actions grid-wide">
            <button className="btn btn-primary" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Generating PR..." : "Generate PR"}
            </button>
          </div>
        </form>
        )}

        {prResult ? (
          <div className="detail-inset">
            <p className="hint">
              PR #{prResult.pull_request_number} via <strong>{prResult.auth_source}</strong>
            </p>
            <p className="detail-chip-row">
              <span className="alert-cat-badge badge-green">PR Opened</span>
              {prResult.last_ci_state ? (
                <span className={`alert-cat-badge ${prResult.last_ci_state === "success" ? "badge-green" : prResult.last_ci_state === "failure" ? "badge-red" : "badge-yellow"}`}>CI: {prResult.last_ci_state}</span>
              ) : <span className="calls-row-muted">CI: pending</span>}
              {prResult.merged_at ? (
                <span className="alert-cat-badge badge-green">Merged</span>
              ) : <span className="calls-row-muted">Not merged</span>}
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

        <div className="call-actions-stack">
          <div className="actions">
            <button type="button" className="btn btn-primary" onClick={() => void markResolved()}>
              Mark Resolved
            </button>
            {resolveNote ? <span className="hint">{resolveNote}</span> : null}
          </div>
          <div className="actions">
            <button type="button" className="btn btn-soft" onClick={() => void submitFeedback(true)}>
              Helpful
            </button>
            <button type="button" className="btn btn-danger" onClick={() => void submitFeedback(false)}>
              Not helpful
            </button>
            {feedbackNote ? <span className="hint">{feedbackNote}</span> : null}
          </div>
          <div className="actions">
            <button type="button" className="btn btn-soft" onClick={() => void copyFixSuggestion()}>
              Copy Fix Snippet
            </button>
            <button type="button" className="btn btn-soft" onClick={() => void shareDiagnosis()}>
              Share Diagnosis (24h)
            </button>
            {shareNote ? <span className="hint">{shareNote}</span> : null}
          </div>
        </div>

        

        {share ? (
          <div className="detail-inset">
            <p className="hint">Share link (read-only · 24h):</p>
            <div className="share-url-row">
              <code className="mono share-url">{typeof window !== "undefined" ? `${window.location.origin}/share/${share.token}` : share.token}</code>
              <CopyButton text={typeof window !== "undefined" ? `${window.location.origin}/share/${share.token}` : share.token} label="share link" />
            </div>
            <p className="hint">Expires: {formatDateTime(share.expires_at)}</p>
          </div>
        ) : null}

        <div className="detail-inset">
          <p className="hint">
            Feedback totals: Helpful {formatCount(detail.feedback_summary.helpful_count)} · Not helpful {formatCount(detail.feedback_summary.not_helpful_count)}
          </p>
        </div>
      </section>
    </div>
  );
}
