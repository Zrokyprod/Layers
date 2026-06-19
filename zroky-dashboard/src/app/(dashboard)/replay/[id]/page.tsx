"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  GitBranch,
  RotateCcw,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addGoldenTrace,
  createGoldenSet,
  getCallDetail,
  listGoldenSets,
  runGoldenSet,
  runRegressionCI,
} from "@/lib/api";
import type {
  GoldenSetView,
  RegressionCIRunResponse,
  ReplayMode,
  ReplayRunDetailItem,
  ReplayRunTraceItem,
} from "@/lib/api";
import { useReplayRunDetail } from "@/lib/hooks";
import { formatDateTime, formatUsd, numberFromUnknown, safeString } from "@/lib/format";
import type { CallDetailResponse, JsonMap } from "@/lib/types";
import {
  replayModeLabel,
  replayModeProof,
  replayVerifiedFix,
  STUB_REPLAY_MODE,
} from "@/lib/replay-mode";

const STATUS_CLASS: Record<string, string> = {
  pending: "badge-yellow",
  running: "badge-yellow",
  pass: "badge-green",
  fail: "badge-red",
  error: "badge-red",
  not_verified: "badge-yellow",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  running: "Running",
  pass: "Pass",
  fail: "Fail",
  error: "Error",
  not_verified: "Not verified",
};

type ReplayConfidenceLevel = "verified_fix" | "stub_only" | "fix_failed" | "not_verified" | "inconclusive";

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
  if (value == null) return null;
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value);
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
    if (value) return value;
  }
  return null;
}

function firstPresentValue(payload: JsonMap, paths: string[][]): unknown {
  for (const path of paths) {
    const value = readPath(payload, path);
    if (stringifyValue(value)) return value;
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

function extractToolBehavior(payload: JsonMap): unknown {
  return firstPresentValue(payload, [
    ["tool_behavior"],
    ["tool_calls"],
    ["tools"],
    ["request", "tool_behavior"],
    ["request", "tool_calls"],
    ["request", "tools"],
    ["response", "tool_behavior"],
    ["response", "tool_calls"],
    ["payload", "tool_behavior"],
    ["payload", "tool_calls"],
  ]);
}

function extractRetrievalContext(payload: JsonMap): unknown {
  return firstPresentValue(payload, [
    ["retrieval_context"],
    ["retrieval"],
    ["context"],
    ["request", "retrieval_context"],
    ["request", "retrieval"],
    ["payload", "retrieval_context"],
    ["payload", "retrieval"],
  ]);
}

function extractFailureReason(detail: CallDetailResponse | null, trace: ReplayRunTraceItem | null): string | null {
  if (!detail) return traceErrorReason(trace);
  return (
    firstPresent(detail.payload, [
      ["failure_reason"],
      ["error_message"],
      ["error"],
      ["diagnosis", "root_cause"],
      ["payload", "failure_reason"],
      ["response", "error_message"],
    ]) ??
    detail.call.error_code ??
    traceErrorReason(trace)
  );
}

function parseJudgeScores(trace: ReplayRunTraceItem | null): JsonMap {
  if (!trace?.judge_scores_json) return {};
  try {
    return asObject(JSON.parse(trace.judge_scores_json));
  } catch {
    return {};
  }
}

function traceErrorReason(trace: ReplayRunTraceItem | null): string | null {
  const scores = parseJudgeScores(trace);
  return firstPresent(scores, [
    ["reason"],
    ["error"],
    ["error_message"],
    ["rationale"],
    ["summary"],
  ]);
}

function jsonPreview(value: unknown): string | null {
  return stringifyValue(value);
}

function inlineSummaryValue(value: unknown): string {
  if (value == null) return "Not captured";
  if (typeof value === "string") return value.trim() || "Not captured";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    const parts = value.map((item) => inlineSummaryValue(item)).filter(Boolean);
    return parts.length ? parts.join(", ") : "None";
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as JsonMap)
      .slice(0, 3)
      .map(([key, child]) => `${key}: ${inlineSummaryValue(child)}`);
    return entries.length ? entries.join("; ") : "No fields captured";
  }
  return String(value);
}

function summaryRowsFor(value: unknown): { label: string; value: string }[] {
  if (value == null) return [];
  if (typeof value !== "object" || Array.isArray(value)) {
    const summary = inlineSummaryValue(value);
    return summary === "Not captured" ? [] : [{ label: "Summary", value: summary }];
  }

  const payload = value as JsonMap;
  const preferred = [
    "before",
    "after",
    "changed",
    "matched",
    "missing_count",
    "unverified_count",
    "stub",
    "error",
    "reason",
    "replay_mode",
    "executor_replay_mode",
    "candidate_model_override",
    "git_sha",
    "trigger",
  ];
  const rows = preferred
    .filter((key) => key in payload && payload[key] != null)
    .map((key) => ({ label: key.replaceAll("_", " "), value: inlineSummaryValue(payload[key]) }));

  if (rows.length > 0) return rows.slice(0, 5);

  return Object.entries(payload)
    .slice(0, 4)
    .map(([key, child]) => ({ label: key.replaceAll("_", " "), value: inlineSummaryValue(child) }));
}

function formatMs(value: number | null | undefined): string {
  if (value == null) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value} ms`;
}

function compactPercent(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "-";
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(0)}%`;
}

function proofLabel(value: boolean | null | undefined): string {
  if (value === true) return "yes";
  if (value === false) return "no";
  return "unknown";
}

function isReplayMode(value: string): value is ReplayMode {
  return ["stub", "real_llm", "mocked-tool", "live-sandbox", "shadow"].includes(value);
}

function chooseDefaultTrace(run: ReplayRunDetailItem | null): ReplayRunTraceItem | null {
  if (!run || run.traces.length === 0) return null;
  return run.traces.find((trace) => trace.status === "fail" || trace.status === "error") ?? run.traces[0];
}

function confidenceLevel(run: ReplayRunDetailItem): ReplayConfidenceLevel {
  const verificationStatus = run.summary.verification_status;
  if (run.replay_mode === STUB_REPLAY_MODE || verificationStatus === "sanity_check_only") {
    return "stub_only";
  }
  if (verificationStatus === "verified_fix" && replayVerifiedFix(run.replay_mode, run.summary.verified_fix) && run.status === "pass") {
    return "verified_fix";
  }
  if (verificationStatus === "not_verified") {
    return "not_verified";
  }
  if (run.status === "fail" || run.status === "error" || verificationStatus.includes("failed")) {
    return "fix_failed";
  }
  return "inconclusive";
}

function recommendedNextReplayMode(run: ReplayRunDetailItem): ReplayMode {
  if (run.replay_mode === STUB_REPLAY_MODE) return "real_llm";
  const status = run.summary.verification_status;
  const toolDiff = run.summary.tool_behavior_diff ?? {};
  if (
    status.includes("missing_tool") ||
    status.includes("tool_proof") ||
    numberFromUnknown(toolDiff.missing_count) > 0 ||
    numberFromUnknown(toolDiff.unverified_count) > 0
  ) {
    return "mocked-tool";
  }
  return "live-sandbox";
}

function warningFor(run: ReplayRunDetailItem, trace: ReplayRunTraceItem | null): string | null {
  if (run.replay_mode_warning) return run.replay_mode_warning;
  if (run.replay_mode === STUB_REPLAY_MODE) {
    return "Fixture validation checks recorded wiring only and cannot prove a candidate fix is safe.";
  }
  if (run.summary.verification_status === "not_verified") {
    return "Replay finished, but verification did not prove a trusted fix.";
  }
  if (run.summary.verification_status.includes("missing_tool") || run.summary.verification_status.includes("tool_proof")) {
    return "This replay is missing enough tool-behavior proof to call the fix verified.";
  }
  if (run.status === "error") return traceErrorReason(trace) ?? "Replay encountered an error.";
  return null;
}

function toolBehaviorVerdict(value: unknown, confidence: ReplayConfidenceLevel): string {
  if (confidence === "verified_fix") return "Tool behavior corrected";
  if (confidence === "stub_only") return "Tool behavior not proven";
  if (confidence === "not_verified") return "Tool behavior not verified";
  if (confidence === "fix_failed") return "Tool behavior still failing";
  const rows = summaryRowsFor(value);
  return rows.some((row) => row.label.includes("missing") || row.label.includes("unverified"))
    ? "Tool proof incomplete"
    : "Tool behavior needs review";
}

function verdictTitle(confidence: ReplayConfidenceLevel): string {
  if (confidence === "verified_fix") return "Verified fix";
  if (confidence === "stub_only") return "Fixture validation only";
  if (confidence === "not_verified") return "Not verified";
  if (confidence === "fix_failed") return "Replay failed";
  return "Needs review";
}

function verdictDescription(run: ReplayRunDetailItem, confidence: ReplayConfidenceLevel): string {
  if (confidence === "verified_fix") {
    return `Candidate replay passed with ${replayModeProof(run.replay_mode)}.`;
  }
  if (confidence === "stub_only") {
    return "This replay only regraded recorded behavior. It cannot verify a fix.";
  }
  if (confidence === "not_verified") {
    return "Replay completed, but the result is not trusted enough for CI or Contract fixture creation.";
  }
  if (confidence === "fix_failed") {
    return "Candidate replay did not prove the failure is fixed.";
  }
  return `Run ${replayModeLabel(recommendedNextReplayMode(run))} replay to collect trusted proof.`;
}

function judgeConfidence(trace: ReplayRunTraceItem | null): number | null {
  const scores = parseJudgeScores(trace);
  for (const key of ["confidence", "judge_confidence", "overall_confidence", "score", "overall_score"]) {
    const value = numberFromUnknown(scores[key]);
    if (value > 0) return value;
  }
  return null;
}

function promotionCriteria(run: ReplayRunDetailItem, trace: ReplayRunTraceItem): string {
  return JSON.stringify({
    source: "replay_lab_create_golden",
    source_replay_run_id: run.id,
    source_replay_trace_id: trace.id,
    source_golden_trace_id: trace.golden_trace_id,
    replay_mode: run.replay_mode,
    executor_replay_mode: run.executor_replay_mode,
    replay_status: run.status,
    replay_trace_status: trace.status,
    verification_status: run.summary.verification_status,
    verified_fix: replayVerifiedFix(run.replay_mode, run.summary.verified_fix),
    diff_metric: trace.diff_metric,
    cost_delta_usd: trace.cost_delta_usd,
    latency_delta_ms: trace.latency_delta_ms,
    output_diff: trace.output_diff,
    tool_behavior_diff: trace.tool_behavior_diff,
    promoted_at: new Date().toISOString(),
  });
}

function sourceTypeFor(run: ReplayRunDetailItem, trace: ReplayRunTraceItem | null): "call" | "golden" {
  return trace?.call_id_replayed ? "call" : "golden";
}

function sourceTitleFor(run: ReplayRunDetailItem, trace: ReplayRunTraceItem | null): string {
  if (trace?.call_id_replayed) return trace.call_id_replayed;
  if (trace?.golden_trace_id) return trace.golden_trace_id;
  return run.golden_set_id;
}

function sourceContextTitle(run: ReplayRunDetailItem, trace: ReplayRunTraceItem | null): string {
  return run.source_context?.title || run.source_context?.failure_code || sourceTitleFor(run, trace);
}

function sourceContextReason(run: ReplayRunDetailItem): string {
  return run.source_context?.reason || "No source finding reason captured.";
}

function sourceContextMeta(run: ReplayRunDetailItem): { label: string; value: string }[] {
  const context = run.source_context;
  if (!context) {
    return [{ label: "Source", value: "legacy replay" }];
  }
  return [
    { label: "Origin", value: context.origin || context.kind || "source" },
    { label: "Failure", value: context.failure_code || "unknown" },
    { label: "Severity", value: context.severity || "unknown" },
    { label: "Agent", value: context.affected_agent || "unknown" },
    { label: "Workflow", value: context.affected_workflow || "unknown" },
    { label: "Occurrences", value: context.occurrence_count == null ? "unknown" : `${context.occurrence_count}x` },
  ].filter((item) => item.value !== "unknown");
}

function sourceContextHref(run: ReplayRunDetailItem, trace: ReplayRunTraceItem | null): string | null {
  if (run.source_context?.issue_id) return `/issues/${run.source_context.issue_id}`;
  if (run.source_context?.call_id) return `/calls/${run.source_context.call_id}`;
  if (trace?.call_id_replayed) return `/calls/${trace.call_id_replayed}`;
  return null;
}

function sourceContextId(run: ReplayRunDetailItem, trace: ReplayRunTraceItem | null): string | null {
  return run.source_context?.issue_id || run.source_context?.call_id || run.source_context?.id || trace?.call_id_replayed || null;
}

function EmptyValue({ children = "Not captured." }: { children?: string }) {
  return <span className="notif-meta">{children}</span>;
}

function TextBlock({ value, empty = "Not captured." }: { value: string | null | undefined; empty?: string }) {
  if (!value) return <EmptyValue>{empty}</EmptyValue>;
  return <pre className="code-block replay-lab-pre">{value}</pre>;
}

function JsonDisclosure({ value, label = "View JSON" }: { value: unknown; label?: string }) {
  const serialized = jsonPreview(value);
  if (!serialized) return null;
  return (
    <details className="replay-lab-json-disclosure">
      <summary>{label}</summary>
      <pre className="struct-pre replay-lab-json">{serialized}</pre>
    </details>
  );
}

function StructuredSummary({
  value,
  empty = "No structured summary captured.",
}: {
  value: unknown;
  empty?: string;
}) {
  const rows = summaryRowsFor(value);
  if (rows.length === 0) return <EmptyValue>{empty}</EmptyValue>;
  return (
    <div className="replay-lab-summary-block">
      <div className="replay-lab-summary-rows">
        {rows.map((row) => (
          <div key={`${row.label}:${row.value}`} className="replay-lab-summary-row">
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </div>
        ))}
      </div>
      <JsonDisclosure value={value} />
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="replay-lab-metric">
      <span>{label}</span>
      <strong>{value || "-"}</strong>
    </div>
  );
}

function DetailField({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="replay-lab-field">
      <span>{title}</span>
      <div>{children}</div>
    </div>
  );
}

function ProofStage({
  label,
  value,
  active,
  warn,
}: {
  label: string;
  value: string;
  active: boolean;
  warn?: boolean;
}) {
  return (
    <div className={`replay-lab-stage${active ? " is-active" : ""}${warn ? " is-warn" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function CreateGoldenPanel({
  run,
  isSafeVerifiedFix,
}: {
  run: ReplayRunDetailItem;
  isSafeVerifiedFix: boolean;
}) {
  const queryClient = useQueryClient();
  const [selectedSetId, setSelectedSetId] = useState("");
  const [newSetName, setNewSetName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const goldenSetsQuery = useQuery({
    queryKey: ["golden-sets", "replay-lab-create-golden"],
    queryFn: ({ signal }) => listGoldenSets({ limit: 100 }, signal),
  });
  const promotableTraces = useMemo(
    () => run.traces.filter((trace) => trace.status === "pass" && Boolean(trace.call_id_replayed) && Boolean(trace.output_text)),
    [run.traces],
  );
  const canCreateGolden = isSafeVerifiedFix && !run.replay_mode_warning && promotableTraces.length > 0;
  const createMutation = useMutation({
    mutationFn: async () => {
      setMessage(null);
      let targetSet: GoldenSetView | null = goldenSetsQuery.data?.items.find((set) => set.id === selectedSetId) ?? null;
      const name = newSetName.trim();
      if (!targetSet) {
        if (!name) throw new Error("Select a fixture set or create a new one.");
        targetSet = await createGoldenSet({
          name,
          description: `Created from verified replay ${run.id}`,
        });
      }
      const created = [];
      for (const trace of promotableTraces) {
        if (!trace.call_id_replayed || !trace.output_text) continue;
        created.push(await addGoldenTrace(targetSet.id, {
          call_id: trace.call_id_replayed,
          expected_output_text: trace.output_text,
          criteria_json: promotionCriteria(run, trace),
          weight: 1,
        }));
      }
      return { targetSet, createdCount: created.length };
    },
    onSuccess: ({ targetSet, createdCount }) => {
      setSelectedSetId(targetSet.id);
      setNewSetName("");
      setMessage(`${createdCount} verified replay trace${createdCount === 1 ? "" : "s"} added to ${targetSet.name}.`);
      void queryClient.invalidateQueries({ queryKey: ["golden-sets"] });
      void queryClient.invalidateQueries({ queryKey: ["golden-traces", targetSet.id] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "Create fixture failed."),
  });

  return (
    <section className="panel replay-lab-cta-card" aria-label="Contract fixture eligibility">
      <header className="panel-header">
        <div>
          <h3>Contract fixture eligibility</h3>
          <p>Only verified repository or managed replay fixes can be converted into fixture evidence for Contracts.</p>
        </div>
        <span className={`alert-cat-badge ${canCreateGolden ? "badge-green" : "badge-yellow"}`}>
          {canCreateGolden ? "Eligible" : "Not eligible yet"}
        </span>
      </header>

      {canCreateGolden ? (
        <div className="replay-lab-golden-ready">
          <CheckCircle2 aria-hidden="true" />
          <div>
            <strong>This replay can become a Contract fixture.</strong>
            <span>It can protect this flow in future CI runs once a Contract is approved.</span>
          </div>
        </div>
      ) : null}

      {!canCreateGolden ? (
        <div className="detail-warning">
          <strong>
            <AlertTriangle aria-hidden="true" />
            Run trusted replay before creating a Contract fixture.
          </strong>
          <span>
            {run.replay_mode === STUB_REPLAY_MODE
              ? "Fixture validation is wiring-only. Run repository replay or managed provider replay before converting this result into a fixture."
              : "Fixture creation is enabled only after verification_status is verified_fix and passing replay traces have source calls."}
          </span>
        </div>
      ) : null}

      {canCreateGolden ? (
        <div className="detail-form-grid">
          <label className="detail-field">
            <span className="detail-field-label">Fixture Set</span>
            <select
              className="input"
              value={selectedSetId}
              onChange={(event) => setSelectedSetId(event.target.value)}
              disabled={goldenSetsQuery.isLoading}
            >
              <option value="">Create a new set</option>
              {(goldenSetsQuery.data?.items ?? []).map((set) => (
                <option key={set.id} value={set.id}>
                  {set.name} - {set.trace_count} traces
                </option>
              ))}
            </select>
          </label>
          <label className="detail-field">
            <span className="detail-field-label">New Fixture Set name</span>
            <input
              className="input"
              value={newSetName}
              onChange={(event) => setNewSetName(event.target.value)}
              placeholder="Verified regression memory"
              disabled={Boolean(selectedSetId)}
            />
          </label>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending}
          >
            <ShieldCheck aria-hidden="true" />
            {createMutation.isPending ? "Creating..." : "Create Fixture"}
          </button>
        </div>
      ) : null}
      <p className="notif-meta">
        {promotableTraces.length} passing replay trace{promotableTraces.length === 1 ? "" : "s"} with source calls available.
      </p>
      {message ? <p className={createMutation.isError ? "notif-error" : "notif-meta"}>{message}</p> : null}
    </section>
  );
}

function CiGatePanel({
  run,
  isSafeVerifiedFix,
}: {
  run: ReplayRunDetailItem;
  isSafeVerifiedFix: boolean;
}) {
  const queryClient = useQueryClient();
  const [gitSha, setGitSha] = useState(run.git_sha ?? "");
  const [ciRun, setCiRun] = useState<RegressionCIRunResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setGitSha(run.git_sha ?? "");
    setCiRun(null);
    setMessage(null);
  }, [run.id, run.git_sha]);

  const ciMutation = useMutation({
    mutationFn: async () => {
      if (!isSafeVerifiedFix) throw new Error("Run verified repository or managed replay before opening a CI gate.");
      const sha = gitSha.trim();
      if (sha.length < 4) throw new Error("Enter a commit SHA before running a CI gate.");
      return runRegressionCI({ git_sha: sha, sample_window_days: 30 });
    },
    onSuccess: (created) => {
      setCiRun(created);
      setMessage(`CI gate created: ${created.run_id}`);
      void queryClient.invalidateQueries({ queryKey: ["replay-runs"] });
      void queryClient.invalidateQueries({ queryKey: ["replay-run", created.run_id] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "CI gate failed."),
  });

  return (
    <section className="panel replay-lab-cta-card replay-lab-ci-card" aria-label="CI gate">
      <header className="panel-header">
        <div>
          <h3>CI gate</h3>
          <p>Turn this verified replay proof into a commit-linked regression gate.</p>
        </div>
        <span className={`alert-cat-badge ${isSafeVerifiedFix ? "badge-green" : "badge-yellow"}`}>
          {isSafeVerifiedFix ? "Ready" : "Needs verified replay"}
        </span>
      </header>

      {!isSafeVerifiedFix ? (
        <div className="detail-warning">
          <strong>
            <AlertTriangle aria-hidden="true" />
            CI gate blocked
          </strong>
          <span>Only verified repository or managed replay fixes can create a regression CI gate.</span>
        </div>
      ) : null}

      <div className="detail-form-grid">
        <label className="detail-field">
          <span className="detail-field-label">Commit SHA</span>
          <input
            className="input"
            value={gitSha}
            onChange={(event) => setGitSha(event.target.value)}
            placeholder="abc1234"
          />
        </label>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => ciMutation.mutate()}
          disabled={!isSafeVerifiedFix || ciMutation.isPending || gitSha.trim().length < 4}
        >
          <GitBranch aria-hidden="true" />
          {ciMutation.isPending ? "Creating gate..." : "Run CI gate"}
        </button>
        {ciRun ? (
          <Link href={`/ci-gates/${ciRun.run_id}`} className="btn btn-soft">
            Open CI gate
          </Link>
        ) : null}
      </div>
      {message ? <p className={ciMutation.isError ? "notif-error" : "notif-meta"}>{message}</p> : null}
    </section>
  );
}

export default function ReplayRunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const runQuery = useReplayRunDetail(id);
  const run = runQuery.data ?? null;
  const [selectedTraceId, setSelectedTraceId] = useState("");
  useEffect(() => {
    setSelectedTraceId("");
  }, [id]);
  const defaultTrace = useMemo(() => chooseDefaultTrace(run), [run]);
  const selectedTrace = useMemo(
    () => run?.traces.find((trace) => trace.id === selectedTraceId) ?? defaultTrace,
    [defaultTrace, run?.traces, selectedTraceId],
  );
  const callId = selectedTrace?.call_id_replayed ?? "";
  const callDetailQuery = useQuery({
    queryKey: ["call-detail", callId],
    queryFn: ({ signal }) => getCallDetail(callId, signal),
    enabled: Boolean(callId),
  });
  const queryClient = useQueryClient();
  const [rerunMessage, setRerunMessage] = useState<string | null>(null);
  const [rerunId, setRerunId] = useState<string | null>(null);
  const rerunMutation = useMutation({
    mutationFn: async (replayModeOverride?: ReplayMode) => {
      if (!run) throw new Error("Replay run unavailable.");
      return runGoldenSet(run.golden_set_id, {
        trigger: "manual",
        replay_mode: replayModeOverride ?? (isReplayMode(run.replay_mode) ? run.replay_mode : undefined),
        candidate_prompt_override: run.candidate_prompt_override ?? undefined,
        candidate_model_override: run.candidate_model_override ?? undefined,
      });
    },
    onSuccess: (created) => {
      setRerunMessage(`Rerun created: ${created.id}`);
      setRerunId(created.id);
      void queryClient.invalidateQueries({ queryKey: ["replay-runs"] });
      void queryClient.invalidateQueries({ queryKey: ["replay-run", created.id] });
    },
    onError: (error) => {
      setRerunId(null);
      setRerunMessage(error instanceof Error ? error.message : "Rerun failed.");
    },
  });

  if (runQuery.isLoading) {
    return (
      <section className="panel">
        <div className="loading" />
      </section>
    );
  }

  if (runQuery.error || !run) {
    return (
      <section className="panel">
        <p className="notif-error">{runQuery.error?.message ?? "Replay run unavailable."}</p>
        <Link href="/replay" className="btn btn-soft">
          <ArrowLeft aria-hidden="true" />
          Back to replay runs
        </Link>
      </section>
    );
  }

  const summary = run.summary;
  const detail = callDetailQuery.data ?? null;
  const selectedScores = parseJudgeScores(selectedTrace);
  const confidence = confidenceLevel(run);
  const recommendedMode = recommendedNextReplayMode(run);
  const warning = warningFor(run, selectedTrace);
  const sourceType = run.source_context?.kind || sourceTypeFor(run, selectedTrace);
  const sourceTitle = sourceContextTitle(run, selectedTrace);
  const sourceHref = sourceContextHref(run, selectedTrace);
  const sourceId = sourceContextId(run, selectedTrace);
  const isSafeVerifiedFix = confidence === "verified_fix";
  const isUntrustedState = !isSafeVerifiedFix;
  const trustWarning = "This replay state is not trusted enough to create a Contract fixture or block CI. Run trusted replay first.";
  const originalInput = detail ? extractPromptText(detail.payload) : null;
  const originalOutput = detail ? extractResponseText(detail.payload) : null;
  const originalToolBehavior = detail ? extractToolBehavior(detail.payload) : null;
  const retrievalContext = detail ? extractRetrievalContext(detail.payload) : null;
  const failureReason = extractFailureReason(detail, selectedTrace);
  const candidateConfig = {
    replay_mode: run.replay_mode,
    executor_replay_mode: run.executor_replay_mode,
    candidate_model_override: run.candidate_model_override,
    git_sha: run.git_sha,
    trigger: run.trigger,
  };

  return (
    <div className="detail-page replay-detail-page replay-lab-page">
      <Link href="/replay" className="detail-back-link">
        <ArrowLeft aria-hidden="true" />
        Back to replay runs
      </Link>

      <section className="panel detail-hero replay-lab-hero">
        <div className="detail-hero-main">
          <div className="detail-badge-row">
            <span className={`alert-cat-badge ${STATUS_CLASS[run.status] ?? "badge-gray"}`}>
              {STATUS_LABEL[run.status] ?? run.status}
            </span>
            <span className={`alert-cat-badge ${isSafeVerifiedFix ? "badge-green" : confidence === "stub_only" ? "badge-yellow" : "badge-gray"}`}>
              {confidence}
            </span>
          </div>
          <h1>Replay</h1>
          <p>Replay failed agent calls, compare candidate behavior, and verify fixes before creating Contract fixtures.</p>
          <div className="detail-meta-row">
            <span className="mono">{run.id}</span>
            <span>{replayModeLabel(run.replay_mode)}</span>
            <span>{formatDateTime(run.created_at)}</span>
            {selectedTrace?.call_id_replayed ? (
              <Link href={`/calls/${selectedTrace.call_id_replayed}`} className="mono">
                Source call {selectedTrace.call_id_replayed}
              </Link>
            ) : null}
          </div>
        </div>
        <aside className="detail-hero-side">
          <div className={`detail-impact-value${run.status === "fail" || run.status === "error" ? " is-danger" : ""}`}>
            {STATUS_LABEL[run.status] ?? run.status}
          </div>
          <span className="notif-meta">{summary.trace_count_executed}/{summary.trace_count_at_dispatch} traces</span>
        </aside>
      </section>

      {warning ? (
        <div className="detail-warning">
          <strong>
            <AlertTriangle aria-hidden="true" />
            Replay warning
          </strong>
          <span>{warning}</span>
        </div>
      ) : null}

      <section className="panel replay-lab-stage-map" aria-label="Replay proof stages">
        <ProofStage
          label="Source"
          value={selectedTrace?.call_id_replayed ? "captured call" : "fixture trace"}
          active={Boolean(selectedTrace)}
        />
        <ProofStage
          label="Reproduce"
          value={proofLabel(summary.reproduced_original_failure)}
          active={summary.reproduced_original_failure === true}
          warn={summary.reproduced_original_failure !== true}
        />
        <ProofStage
          label="Candidate"
          value={`${summary.trace_count_executed}/${summary.trace_count_at_dispatch} traces`}
          active={summary.trace_count_executed > 0}
        />
        <ProofStage
          label="Judge"
          value={summary.verification_status}
          active={isSafeVerifiedFix}
          warn={!isSafeVerifiedFix}
        />
        <ProofStage
          label="Contract"
          value={isSafeVerifiedFix ? "eligible" : "blocked"}
          active={isSafeVerifiedFix}
          warn={!isSafeVerifiedFix}
        />
        <ProofStage
          label="CI gate"
          value={run.git_sha ? run.git_sha.slice(0, 8) : "needs SHA"}
          active={isSafeVerifiedFix && Boolean(run.git_sha)}
          warn={!isSafeVerifiedFix || !run.git_sha}
        />
      </section>

      {run.traces.length > 1 ? (
        <section className="panel replay-lab-trace-picker" aria-label="Replay trace selector">
          <div>
            <h3>Trace selector</h3>
            <p className="notif-meta">Switch the workbench between every trace executed in this replay run.</p>
          </div>
          <select
            className="input"
            value={selectedTrace?.id ?? ""}
            onChange={(event) => setSelectedTraceId(event.target.value)}
          >
            {run.traces.map((trace, index) => (
              <option key={trace.id} value={trace.id}>
                Trace {index + 1} - {trace.status} - {trace.call_id_replayed ?? trace.golden_trace_id ?? trace.id}
              </option>
            ))}
          </select>
        </section>
      ) : null}

      <section className="panel replay-lab-setup" aria-label="Replay setup">
        <header className="panel-header">
          <div>
            <h3>Replay setup</h3>
            <p>Source, replay mode, and candidate configuration used for this comparison.</p>
          </div>
          <span className={`alert-cat-badge ${isSafeVerifiedFix ? "badge-green" : "badge-yellow"}`}>
            {isSafeVerifiedFix ? "Trusted replay" : "Needs trusted replay"}
          </span>
        </header>

        <div className="replay-source-context-panel">
          <div>
            <span>What this replay is proving</span>
            <h4>{sourceTitle}</h4>
            <p>{sourceContextReason(run)}</p>
          </div>
          <div className="replay-source-context-facts">
            {sourceContextMeta(run).map((item) => (
              <span key={`${item.label}:${item.value}`}>
                <strong>{item.label}</strong>
                {item.value}
              </span>
            ))}
          </div>
          {sourceHref ? (
            <Link href={sourceHref} className="btn btn-soft">
              Open source
            </Link>
          ) : null}
        </div>

        <div className="replay-lab-setup-grid">
          <DetailField title="Source type">
            <strong>{sourceType}</strong>
          </DetailField>
          <DetailField title={sourceType === "issue" ? "Source issue" : sourceType === "call" ? "Source call" : "Source fixture"}>
            {sourceHref ? (
              <Link href={sourceHref} className="replay-lab-source-link mono">
                {sourceId ?? sourceTitle}
              </Link>
            ) : (
              <span className="mono">{sourceId ?? sourceTitle}</span>
            )}
          </DetailField>
          <DetailField title="Replay mode">
            <span>{replayModeLabel(run.replay_mode)}</span>
          </DetailField>
          <DetailField title="Candidate model">
            <span>{safeString(run.candidate_model_override, "No model override")}</span>
          </DetailField>
        </div>

        <div className="grid-two replay-lab-diff-grid">
          <article className="detail-inset">
            <h4>candidate_prompt</h4>
            <TextBlock value={run.candidate_prompt_override} empty="No candidate prompt override was supplied." />
          </article>
          <article className="detail-inset">
            <h4>candidate_config</h4>
            <StructuredSummary value={candidateConfig} empty="No candidate config captured." />
          </article>
        </div>

        {warning || isUntrustedState ? (
          <div className="replay-lab-setup-warning">
            <AlertTriangle aria-hidden="true" />
            <span>{warning ?? trustWarning}</span>
          </div>
        ) : null}

        <div className="replay-lab-action-row">
          <button
            type="button"
            className="btn btn-soft"
            onClick={() => rerunMutation.mutate(undefined)}
            disabled={rerunMutation.isPending}
          >
            <RotateCcw aria-hidden="true" />
            Rerun replay
          </button>
          {selectedTrace?.call_id_replayed ? (
            <Link href={`/calls/${selectedTrace.call_id_replayed}`} className="btn btn-soft">
              View source call
            </Link>
          ) : null}
          {rerunMessage ? <span className={rerunMutation.isError ? "notif-error" : "notif-meta"}>{rerunMessage}</span> : null}
          {rerunId ? (
            <Link href={`/replay/${rerunId}`} className="btn btn-soft">
              Open rerun
            </Link>
          ) : null}
        </div>
      </section>

      <section className="panel replay-lab-hero-diff" aria-label="Original versus candidate proof">
        <article>
          <span>Original failure</span>
          <TextBlock value={originalOutput} empty="Original output was not captured for this trace." />
        </article>
        <div className="replay-lab-hero-diff-center">
          <strong>Before / after proof</strong>
          <p>{failureReason || "No failure reason captured."}</p>
          <span>{formatMs(summary.latency_delta_ms)} latency delta</span>
        </div>
        <article>
          <span>Candidate replay</span>
          <TextBlock value={selectedTrace?.output_text} empty="No candidate output captured yet." />
        </article>
      </section>

      <div className="replay-lab-comparison">
        <section className="panel replay-lab-panel">
          <header className="panel-header">
            <div>
              <h3>Original Failure</h3>
              <p>Captured source behavior for the failed call.</p>
            </div>
            {detail ? (
              <span className={`alert-cat-badge ${STATUS_CLASS[detail.call.status] ?? "badge-gray"}`}>
                {detail.call.status}
              </span>
            ) : null}
          </header>

          {callDetailQuery.isLoading ? <div className="loading" /> : null}
          {callDetailQuery.error ? (
            <p className="notif-error">Original call detail unavailable.</p>
          ) : null}

          <div className="replay-lab-field-stack">
            <DetailField title="Input">
              <TextBlock value={originalInput} empty="Original input was not captured for this trace." />
            </DetailField>
            <DetailField title="Original output">
              <TextBlock value={originalOutput} empty="Original output was not captured for this trace." />
            </DetailField>
            <DetailField title="Failure reason">
              <TextBlock value={failureReason} empty="No failure reason captured." />
            </DetailField>
            <DetailField title="Failure code">
              <TextBlock value={detail?.call.error_code ?? selectedTrace?.status ?? null} empty="No failure code captured." />
            </DetailField>
            <DetailField title="Tool behavior">
              <StructuredSummary value={originalToolBehavior} empty="No original tool behavior captured." />
            </DetailField>
            <DetailField title="Retrieval context">
              <StructuredSummary value={retrievalContext} empty="No retrieval context captured." />
            </DetailField>
          </div>

          <div className="replay-lab-metrics">
            <MetricRow label="Cost" value={detail ? formatUsd(detail.call.cost_usd) : null} />
            <MetricRow label="Latency" value={detail?.call.latency_ms != null ? `${detail.call.latency_ms} ms` : null} />
            <MetricRow label="Provider" value={detail?.call.provider ?? null} />
            <MetricRow label="Model" value={detail?.call.model ?? null} />
          </div>
        </section>

        <section className="panel replay-lab-panel">
          <header className="panel-header">
            <div>
              <h3>Candidate Replay</h3>
              <p>Replay output produced by the candidate prompt, model, or config.</p>
            </div>
            {selectedTrace ? (
              <span className={`alert-cat-badge ${STATUS_CLASS[selectedTrace.status] ?? "badge-gray"}`}>
                {selectedTrace.status}
              </span>
            ) : null}
          </header>

          <div className="replay-lab-field-stack">
            <DetailField title="Candidate prompt/model/config">
              <StructuredSummary value={candidateConfig} />
              {run.candidate_prompt_override ? (
                <div className="detail-inset replay-lab-candidate-prompt">
                  <span className="detail-field-label">Candidate prompt override</span>
                  <TextBlock value={run.candidate_prompt_override} />
                </div>
              ) : null}
            </DetailField>
            <DetailField title="Candidate output">
              <TextBlock value={selectedTrace?.output_text} empty="No candidate output captured yet." />
            </DetailField>
            <DetailField title="Candidate tool behavior">
              <StructuredSummary value={selectedTrace?.tool_behavior_diff ?? summary.tool_behavior_diff} empty="No candidate tool behavior captured." />
            </DetailField>
            <DetailField title="Errors">
              <TextBlock value={selectedTrace?.status === "error" ? traceErrorReason(selectedTrace) : null} empty="No replay errors captured." />
            </DetailField>
          </div>

          <div className="replay-lab-metrics">
            <MetricRow label="Replay cost" value={summary.replay_cost_usd == null ? null : formatUsd(summary.replay_cost_usd)} />
            <MetricRow label="Cost delta" value={summary.cost_delta_usd == null ? null : formatUsd(summary.cost_delta_usd)} />
            <MetricRow label="Latency delta" value={formatMs(summary.latency_delta_ms)} />
            <MetricRow label="Model override" value={safeString(run.candidate_model_override, "-")} />
          </div>
        </section>
      </div>

      <section className="panel replay-lab-verification" aria-label="Verification Result">
        <header className="panel-header">
          <div>
            <h3>Verification Result</h3>
            <p>Before/after proof, replay trust level, and next safe action.</p>
          </div>
          <span className={`alert-cat-badge ${isSafeVerifiedFix ? "badge-green" : confidence === "fix_failed" ? "badge-red" : "badge-yellow"}`}>
            {confidence}
          </span>
        </header>

        <div className={`replay-lab-verdict-card${isSafeVerifiedFix ? " is-good" : confidence === "fix_failed" ? " is-bad" : " is-warn"}`}>
          <div className="replay-lab-verdict-main">
            <span>Verification verdict</span>
            <h4>{verdictTitle(confidence)}</h4>
            <p>{verdictDescription(run, confidence)}</p>
          </div>
          <div className="replay-lab-verdict-meta">
            <span>{toolBehaviorVerdict(selectedTrace?.tool_behavior_diff ?? summary.tool_behavior_diff, confidence)}</span>
            <span>Cost {summary.cost_delta_usd == null ? "-" : formatUsd(summary.cost_delta_usd)}</span>
            <span>Latency {formatMs(summary.latency_delta_ms)}</span>
          </div>
        </div>

        {(() => {
          const fid = judgeConfidence(selectedTrace);
          const pct = fid == null ? null : Math.round(fid <= 1 ? fid * 100 : fid);
          const ringTone = pct == null ? "" : confidence === "fix_failed" ? " is-low" : pct >= 85 ? " is-high" : pct >= 60 ? "" : " is-low";
          return (
            <div className="fidelity-panel">
              <div className={`fidelity-ring${ringTone}`} style={{ ["--fid" as string]: pct ?? 0 }}>
                <strong>{pct == null ? "—" : `${pct}%`}</strong>
                <span>fidelity</span>
              </div>
              <div>
                <h4>How faithfully did we reproduce this?</h4>
                <p>
                  {pct == null
                    ? "Replay fidelity is not available for this run — Zroky will not infer a score it cannot measure."
                    : confidence === "stub_only"
                      ? "Fixture validation only regraded recorded behavior. Fidelity reflects judge confidence, not a verified reproduction."
                      : confidence === "verified_fix"
                        ? `Replay reproduced the scenario and the candidate passed with ${replayModeProof(run.replay_mode)}.`
                        : "Replay completed, but fidelity is not high enough to trust this as a verified fix."}
                </p>
              </div>
            </div>
          );
        })()}

        <div className="detail-proof-grid">
          <ProofCard title="verification_status" value={summary.verification_status} tone={isSafeVerifiedFix ? "good" : confidence === "fix_failed" ? "bad" : "warn"} />
          <ProofCard title="verified_fix" value={isSafeVerifiedFix ? "true" : "false"} tone={isSafeVerifiedFix ? "good" : "warn"} />
          <ProofCard title="replay_mode" value={replayModeLabel(run.replay_mode)} />
          <ProofCard title="replay_confidence_level" value={confidence} tone={isSafeVerifiedFix ? "good" : confidence === "fix_failed" ? "bad" : "warn"} />
          <ProofCard title="mode proof" value={replayModeProof(run.replay_mode)} tone={confidence === "stub_only" ? "warn" : "neutral"} />
          <ProofCard title="cost_delta" value={summary.cost_delta_usd == null ? "-" : formatUsd(summary.cost_delta_usd)} />
          <ProofCard title="latency_delta" value={formatMs(summary.latency_delta_ms)} />
          <ProofCard title="judge_confidence" value={compactPercent(judgeConfidence(selectedTrace))} />
          <ProofCard title="traces" value={`${summary.trace_count_executed}/${summary.trace_count_at_dispatch}`} />
        </div>

        <div className="grid-two replay-lab-diff-grid">
          <article className="detail-inset">
            <h4>output_diff</h4>
            <StructuredSummary value={selectedTrace?.output_diff ?? summary.output_diff} />
          </article>
          <article className="detail-inset">
            <h4>tool_behavior_diff</h4>
            <StructuredSummary value={selectedTrace?.tool_behavior_diff ?? summary.tool_behavior_diff} />
          </article>
        </div>

        <div className="replay-lab-verdict-actions">
          {confidence === "verified_fix" ? (
            <span className="replay-lab-verdict-copy is-safe">
              <CheckCircle2 aria-hidden="true" />
              Verified fix. Create Fixture is available.
            </span>
          ) : null}
          {isUntrustedState ? (
            <span className="replay-lab-verdict-copy is-warn">
              <AlertTriangle aria-hidden="true" />
              {trustWarning}
            </span>
          ) : null}
          {confidence === "stub_only" ? (
            <span className="replay-lab-verdict-copy is-warn">
              <AlertTriangle aria-hidden="true" />
              Fixture validation is wiring-only and cannot display as verified.
            </span>
          ) : null}
          {isUntrustedState ? (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => rerunMutation.mutate(recommendedMode)}
              disabled={rerunMutation.isPending}
            >
              <RotateCcw aria-hidden="true" />
              {rerunMutation.isPending ? "Running..." : "Run trusted replay"}
            </button>
          ) : null}
          {confidence === "inconclusive" ? (
            <span className="replay-lab-verdict-copy is-warn">
              <AlertTriangle aria-hidden="true" />
              Recommended next replay mode: {replayModeLabel(recommendedMode)}
            </span>
          ) : null}
          {rerunMessage ? <span className={rerunMutation.isError ? "notif-error" : "notif-meta"}>{rerunMessage}</span> : null}
          {rerunId ? (
            <Link href={`/replay/${rerunId}`} className="btn btn-soft">
              Open rerun
            </Link>
          ) : null}
        </div>

        {Object.keys(selectedScores).length > 0 ? (
          <details className="raw-call-details">
            <summary>Judge scores JSON</summary>
            <pre className="struct-pre raw-call-json">{JSON.stringify(selectedScores, null, 2)}</pre>
          </details>
        ) : null}
      </section>

      <CreateGoldenPanel run={run} isSafeVerifiedFix={isSafeVerifiedFix} />
      <CiGatePanel run={run} isSafeVerifiedFix={isSafeVerifiedFix} />
    </div>
  );
}

function ProofCard({
  title,
  value,
  tone = "neutral",
}: {
  title: string;
  value: string;
  tone?: "good" | "warn" | "bad" | "neutral";
}) {
  return (
    <article className={`detail-proof-card${tone === "good" ? " is-good" : tone === "warn" ? " is-warn" : tone === "bad" ? " is-bad" : ""}`}>
      <span>{title}</span>
      <strong>
        {tone === "good" ? <CheckCircle2 aria-hidden="true" /> : tone === "warn" ? <AlertTriangle aria-hidden="true" /> : tone === "bad" ? <XCircle aria-hidden="true" /> : null}
        {value}
      </strong>
    </article>
  );
}
