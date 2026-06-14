"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  DollarSign,
  GitBranch,
  History,
  PlayCircle,
  ShieldCheck,
  TriangleAlert,
  XCircle,
} from "lucide-react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { KpiCard } from "@/components/command-center-primitives";
import {
  listGoldenSets,
  listIssues,
  runGoldenSet,
  runRegressionCI,
} from "@/lib/api";
import type {
  GoldenSetView,
  RegressionCIRunResponse,
  ReplayCreatePayload,
  ReplayCreateResponse,
  ReplayMode,
  ReplayRunItem,
  ReplaySourceContext,
} from "@/lib/api";
import {
  useCreateReplayRunFromCall,
  useCreateReplayRunFromIssue,
  useActiveProviderKeys,
  useListCalls,
  useReplayQuota,
  useReplayRuns,
} from "@/lib/hooks";
import {
  DEFAULT_VERIFICATION_REPLAY_MODE,
  REPLAY_MODE_OPTIONS,
  STUB_REPLAY_MODE,
  replayModeLabel,
  replayModeProof,
  replayVerificationLabel,
  replayVerifiedFix,
} from "@/lib/replay-mode";
import { ProviderKeyReplayGate } from "@/components/provider-key-replay-gate";
import { hasActiveProviderKey, replayModeRequiresProviderKey } from "@/lib/provider-key-gate";
import type { CallListItem, IssueItem } from "@/lib/types";

const STATUSES = ["", "pending", "running", "pass", "fail", "error"] as const;
const LAUNCH_SOURCES = [
  { value: "issue", label: "Issue", helper: "Best for proving a diagnosed production failure." },
  { value: "call", label: "Call", helper: "Replay one captured failed call directly." },
  { value: "golden", label: "Golden Set", helper: "Run a regression pack against current config." },
  { value: "ci", label: "PR / CI", helper: "Create a live regression gate tied to a commit SHA." },
] as const;

type LaunchSource = (typeof LAUNCH_SOURCES)[number]["value"];

function timeAgo(iso: string) {
  const secs = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

function statusClass(status: string) {
  if (status === "pass") return "badge-green";
  if (status === "fail" || status === "error") return "badge-red";
  if (status === "running" || status === "pending") return "badge-yellow";
  return "badge-gray";
}

function statusLabel(status: string) {
  if (!status) return "All";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function proofLabel(value: boolean | null | undefined) {
  if (value === true) return "yes";
  if (value === false) return "no";
  return "unknown";
}

function deltaLabel(value: number | null | undefined, suffix = "") {
  if (value == null) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value}${suffix}`;
}

function moneyLabel(value: number | null | undefined, digits = 2) {
  if (value == null) return "n/a";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits })}`;
}

function moneyDeltaLabel(value: number | null | undefined) {
  if (value == null) return "n/a";
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toFixed(4)}`;
}

function quotaPercent(used: number, limit: number) {
  if (limit <= 0) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

function replayPayload(
  replayMode: ReplayMode,
  candidatePrompt: string,
  candidateModel: string,
): ReplayCreatePayload {
  return {
    replay_mode: replayMode,
    ...(candidatePrompt.trim() ? { candidate_prompt_override: candidatePrompt.trim() } : {}),
    ...(candidateModel.trim() ? { candidate_model_override: candidateModel.trim() } : {}),
  };
}

function optionIssueLabel(issue: IssueItem) {
  return `${issue.failure_code} - ${issue.agent_name ?? issue.affected_agent ?? "unknown agent"} - ${issue.occurrence_count}x`;
}

function optionCallLabel(call: CallListItem) {
  return `${call.error_code ?? call.status} - ${call.agent_name ?? "unknown agent"} - ${call.call_id.slice(0, 12)}`;
}

function issueReason(issue: IssueItem | null | undefined) {
  return issue?.root_cause || issue?.recommended_next_action || issue?.user_impact || "No source finding reason captured.";
}

function sourceContextLabel(context: ReplaySourceContext | null | undefined) {
  if (!context) return "Source context not captured";
  return context.title || context.failure_code || context.id || "Source context";
}

function sourceContextReason(context: ReplaySourceContext | null | undefined) {
  return context?.reason || "No source finding reason captured.";
}

function sourceContextMeta(context: ReplaySourceContext | null | undefined) {
  if (!context) return "legacy replay";
  const parts = [
    context.origin,
    context.severity,
    context.affected_agent,
    context.affected_workflow,
    context.occurrence_count != null ? `${context.occurrence_count}x` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" - ") : context.kind ?? "source";
}

function sourceContextId(context: ReplaySourceContext | null | undefined) {
  return context?.issue_id || context?.call_id || context?.id || null;
}

function sourceContextHref(context: ReplaySourceContext | null | undefined) {
  if (context?.issue_id) return `/issues/${context.issue_id}`;
  if (context?.call_id) return `/calls/${context.call_id}`;
  return null;
}

function matchesSearch(value: string, query: string) {
  const normalized = query.trim().toLowerCase();
  return !normalized || value.toLowerCase().includes(normalized);
}

function SourcePicker<T>({
  label,
  searchValue,
  searchPlaceholder,
  items,
  selectedId,
  emptyLabel,
  getId,
  getTitle,
  getMeta,
  getReason,
  getDisabled,
  onSearch,
  onSelect,
}: {
  label: string;
  searchValue: string;
  searchPlaceholder: string;
  items: T[];
  selectedId: string;
  emptyLabel: string;
  getId: (item: T) => string;
  getTitle: (item: T) => string;
  getMeta: (item: T) => string;
  getReason: (item: T) => string;
  getDisabled?: (item: T) => boolean;
  onSearch: (value: string) => void;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="replay-source-picker">
      <label className="detail-field">
        <span className="detail-field-label">{label}</span>
        <input
          className="input"
          value={searchValue}
          onChange={(event) => onSearch(event.target.value)}
          placeholder={searchPlaceholder}
        />
      </label>
      <div className="replay-source-option-list" role="listbox" aria-label={label}>
        {items.length === 0 ? (
          <div className="replay-source-option-empty">{emptyLabel}</div>
        ) : (
          items.map((item) => {
            const id = getId(item);
            const disabled = getDisabled?.(item) ?? false;
            return (
              <button
                key={id}
                type="button"
                role="option"
                aria-selected={selectedId === id}
                className={selectedId === id ? "is-active" : ""}
                disabled={disabled}
                onClick={() => onSelect(id)}
              >
                <strong>{getTitle(item)}</strong>
                <span>{getMeta(item)}</span>
                <small>{getReason(item)}</small>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`alert-cat-badge ${statusClass(status)}`}>{statusLabel(status)}</span>;
}

function SourceCard({
  title,
  value,
  helper,
  href,
}: {
  title: string;
  value: string;
  helper: string;
  href?: string;
}) {
  const body = (
    <>
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{helper}</small>
    </>
  );
  if (href) {
    return (
      <Link href={href} className="replay-source-card">
        {body}
      </Link>
    );
  }
  return <div className="replay-source-card">{body}</div>;
}

function ReplayProofStrip({ run }: { run: ReplayRunItem }) {
  const total = Math.max(run.summary.trace_count_at_dispatch, run.summary.trace_count_executed, 1);
  const passPct = Math.round((run.summary.pass_count / total) * 100);
  const failPct = Math.round((run.summary.fail_count / total) * 100);
  const errorPct = Math.round((run.summary.error_count / total) * 100);
  return (
    <div className="replay-proof-strip" aria-label="Replay proof composition">
      <div className="replay-proof-bars" aria-hidden="true">
        <span className="is-pass" style={{ width: `${passPct}%` }} />
        <span className="is-fail" style={{ width: `${failPct}%` }} />
        <span className="is-error" style={{ width: `${errorPct}%` }} />
      </div>
      <div className="replay-proof-facts">
        <span>{run.summary.trace_count_executed}/{run.summary.trace_count_at_dispatch} executed</span>
        <span>reproduced {proofLabel(run.summary.reproduced_original_failure)}</span>
        <span>fix {proofLabel(run.summary.fix_passed)}</span>
      </div>
    </div>
  );
}

function RunRow({ run }: { run: ReplayRunItem }) {
  const replayHref = `/replay/${run.id}`;
  const sourceId = sourceContextId(run.source_context);
  const sourceHref = sourceContextHref(run.source_context);
  const total = run.summary.trace_count_at_dispatch;
  const executed = run.summary.trace_count_executed;
  const passRate = total > 0 ? Math.round((run.summary.pass_count / total) * 100) : null;
  const isVerifiedFix = replayVerifiedFix(run.replay_mode, run.summary.verified_fix);
  const verificationLabel = replayVerificationLabel(run.replay_mode, run.summary.verified_fix, run.summary.verification_status);
  const isStub = run.replay_mode === "stub";
  const costDelta = moneyDeltaLabel(run.summary.cost_delta_usd);
  const latencyDelta = deltaLabel(run.summary.latency_delta_ms, "ms");

  return (
    <article className="replay-run-card">
      <div className="replay-run-main">
        <div className="replay-run-badges">
          <StatusBadge status={run.status} />
          <span className="alert-cat-badge badge-gray">{replayModeLabel(run.replay_mode)}</span>
          <span className={`alert-cat-badge ${isVerifiedFix ? "badge-green" : isStub ? "badge-yellow" : "badge-gray"}`}>
            {verificationLabel}
          </span>
        </div>

        <h2>
          <Link href={replayHref} className="replay-run-title-link">
            Run {run.id.slice(0, 16)}
            <span>...</span>
          </Link>
        </h2>

        <div className="replay-run-meta">
          <span>trigger: {run.trigger}</span>
          {run.git_sha && <span>sha: {run.git_sha.slice(0, 8)}</span>}
          <span>golden set: {run.golden_set_id.slice(0, 12)}...</span>
          <span>{timeAgo(run.created_at)}</span>
        </div>

        <p className="replay-proof-copy">proof: {replayModeProof(run.replay_mode)}</p>
        <div className="replay-run-source-context">
          <span>{sourceContextMeta(run.source_context)}</span>
          {sourceId && sourceHref ? (
            <Link href={sourceHref} className="replay-run-source-link mono">
              {sourceId}
            </Link>
          ) : sourceId ? (
            <small>{sourceId}</small>
          ) : null}
          <strong>{sourceContextLabel(run.source_context)}</strong>
          <p>{sourceContextReason(run.source_context)}</p>
        </div>
        {(run.replay_mode_warning || isStub) && (
          <p className="replay-warning">
            <TriangleAlert aria-hidden="true" />
            {isStub ? "Stub replay is a sanity check, not a verified fix." : run.replay_mode_warning}
          </p>
        )}
      </div>

      <div className="replay-run-proof">
        <div>
          <strong>{executed}/{total}</strong>
          <span>executed</span>
        </div>
        <div>
          <strong>{run.summary.pass_count} / {run.summary.fail_count}</strong>
          <span>pass / fail</span>
        </div>
        <div>
          <strong>{passRate == null ? "-" : `${passRate}%`}</strong>
          <span>pass rate</span>
        </div>
        <div>
          <strong>{proofLabel(run.summary.reproduced_original_failure)}</strong>
          <span>reproduced failure</span>
        </div>
        <div>
          <strong>{proofLabel(run.summary.fix_passed)}</strong>
          <span>fix passed</span>
        </div>
        <div>
          <strong>{costDelta} / {latencyDelta}</strong>
          <span>cost / latency delta</span>
        </div>
        <ReplayProofStrip run={run} />
      </div>

      <Link href={replayHref} className="replay-run-open" aria-label={`Open replay run ${run.id}`}>
        Open
        <ArrowRight aria-hidden="true" />
      </Link>
    </article>
  );
}

export default function ReplayPage() {
  return (
    <Suspense fallback={<p className="hint">Loading replay lab...</p>}>
      <ReplayPageContent />
    </Suspense>
  );
}

function ReplayPageContent() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [goldenSetId, setGoldenSetId] = useState(searchParams.get("golden_set_id") ?? "");
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [pages, setPages] = useState<string[]>([]);
  const [launchSource, setLaunchSource] = useState<LaunchSource>(
    searchParams.get("call_id") ? "call" : searchParams.get("golden_set_id") ? "golden" : "issue",
  );
  const [issueId, setIssueId] = useState(searchParams.get("issue_id") ?? "");
  const [callId, setCallId] = useState(searchParams.get("call_id") ?? "");
  const [selectedGoldenSetId, setSelectedGoldenSetId] = useState(searchParams.get("golden_set_id") ?? "");
  const [issueSearch, setIssueSearch] = useState("");
  const [callSearch, setCallSearch] = useState("");
  const [goldenSearch, setGoldenSearch] = useState("");
  const [replayMode, setReplayMode] = useState<ReplayMode>(DEFAULT_VERIFICATION_REPLAY_MODE);
  const [candidatePrompt, setCandidatePrompt] = useState("");
  const [candidateModel, setCandidateModel] = useState("");
  const [gitSha, setGitSha] = useState(searchParams.get("git_sha") ?? "");
  const [prNumber, setPrNumber] = useState(searchParams.get("pr_number") ?? "");
  const [launchMessage, setLaunchMessage] = useState<string | null>(null);
  const [providerKeyGateOpen, setProviderKeyGateOpen] = useState(false);

  const quotaQuery = useReplayQuota();
  const providerKeysQuery = useActiveProviderKeys();
  const quota = quotaQuery.data;
  const isPlanEnabled = quota?.enabled ?? null;
  const realComparisonEnabled = quota?.real_comparison_enabled !== false;
  const quotaIsPending = quotaQuery.isLoading || quotaQuery.isFetching;
  const quotaErrorMessage = quotaQuery.error instanceof Error ? quotaQuery.error.message : "Replay quota check failed.";

  useEffect(() => {
    if (!realComparisonEnabled && replayMode !== STUB_REPLAY_MODE) {
      setReplayMode(STUB_REPLAY_MODE);
    }
  }, [realComparisonEnabled, replayMode]);

  const issuesQuery = useQuery({
    queryKey: ["issues", "replay-launcher"],
    queryFn: ({ signal }) => listIssues({ status: "open", limit: 20 }, signal),
    enabled: isPlanEnabled === true,
    staleTime: 30_000,
  });
  const callsQuery = useListCalls({
    status: "failed",
    sort_by: "created_at",
    sort_order: "desc",
    limit: 20,
  });
  const goldenSetsQuery = useQuery({
    queryKey: ["golden-sets", "replay-launcher"],
    queryFn: ({ signal }) => listGoldenSets({ limit: 50 }, signal),
    enabled: isPlanEnabled === true,
    staleTime: 30_000,
  });

  const params = {
    ...(statusFilter ? { status: statusFilter } : {}),
    ...(goldenSetId.trim() ? { golden_set_id: goldenSetId.trim() } : {}),
    ...(cursor ? { cursor } : {}),
    limit: 20,
  };

  const query = useReplayRuns(params, {
    enabled: isPlanEnabled === true,
    refetchInterval: (q) =>
      q.state.data?.items.some((run) => run.status === "pending" || run.status === "running")
        ? 4_000
        : false,
  });
  const runs = useMemo(() => query.data?.items ?? [], [query.data?.items]);
  const nextCursor = query.data?.next_cursor;
  const issues = useMemo(() => issuesQuery.data?.items ?? [], [issuesQuery.data?.items]);
  const calls = useMemo(() => callsQuery.data?.items ?? [], [callsQuery.data?.items]);
  const goldenSets = useMemo(() => goldenSetsQuery.data?.items ?? [], [goldenSetsQuery.data?.items]);
  const runnableGoldenSets = goldenSets.filter((set) => set.trace_count > 0);
  const selectedIssueId = issueId.trim() || issues[0]?.id || "";
  const selectedCallId = callId.trim() || calls[0]?.call_id || "";
  const requestedGoldenSet = goldenSets.find((set) => set.id === selectedGoldenSetId.trim());
  const selectedGoldenId = requestedGoldenSet && requestedGoldenSet.trace_count > 0
    ? requestedGoldenSet.id
    : runnableGoldenSets[0]?.id || "";
  const filteredIssues = useMemo(
    () =>
      issues.filter((issue) =>
        matchesSearch(
          [issue.title, issue.failure_code, issue.agent_name, issue.affected_workflow, issue.root_cause, issue.recommended_next_action]
            .filter(Boolean)
            .join(" "),
          issueSearch,
        ),
      ),
    [issueSearch, issues],
  );
  const filteredCalls = useMemo(
    () =>
      calls.filter((call) =>
        matchesSearch(
          [call.call_id, call.error_code, call.status, call.agent_name, call.provider, call.model].filter(Boolean).join(" "),
          callSearch,
        ),
      ),
    [callSearch, calls],
  );
  const filteredGoldenSets = useMemo(
    () =>
      goldenSets.filter((set) =>
        matchesSearch([set.id, set.name, set.description, set.blocks_ci ? "blocks ci" : "non blocking"].filter(Boolean).join(" "), goldenSearch),
      ),
    [goldenSearch, goldenSets],
  );
  const selectedIssue = issues.find((issue) => issue.id === selectedIssueId) ?? issues[0] ?? null;
  const selectedCall = calls.find((call) => call.call_id === selectedCallId) ?? calls[0] ?? null;
  const selectedGolden = goldenSets.find((set) => set.id === selectedGoldenId) ?? runnableGoldenSets[0] ?? goldenSets[0] ?? null;

  const runStats = useMemo(() => {
    const verified = runs.filter((run) => replayVerifiedFix(run.replay_mode, run.summary.verified_fix)).length;
    const sanityOnly = runs.filter((run) => run.replay_mode === "stub" || run.summary.verification_status === "sanity_check_only").length;
    const failed = runs.filter((run) => run.status === "fail" || run.status === "error").length;
    const running = runs.filter((run) => run.status === "pending" || run.status === "running").length;
    const passingTraces = runs.reduce((sum, run) => sum + run.summary.pass_count, 0);
    const replayCost = runs.reduce((sum, run) => sum + (run.summary.replay_cost_usd ?? 0), 0);
    const preventedCost = runs.reduce((sum, run) => sum + (run.prevented_outcome_cost_usd ?? 0), 0);
    return { verified, sanityOnly, failed, running, passingTraces, replayCost, preventedCost };
  }, [runs]);

  function handleFilterChange() {
    setCursor(undefined);
    setPages([]);
  }

  function afterReplayCreate(created: ReplayCreateResponse) {
    setLaunchMessage(`Replay created: ${created.id}`);
    void queryClient.invalidateQueries({ queryKey: ["replay-runs"] });
    void queryClient.invalidateQueries({ queryKey: ["replay-quota"] });
    router.push(`/replay/${created.id}`);
  }

  function afterGoldenRun(created: { id: string }) {
    setLaunchMessage(`Replay created: ${created.id}`);
    void queryClient.invalidateQueries({ queryKey: ["replay-runs"] });
    void queryClient.invalidateQueries({ queryKey: ["replay-quota"] });
    router.push(`/replay/${created.id}`);
  }

  function afterCiRun(created: RegressionCIRunResponse) {
    setLaunchMessage(`CI gate created: ${created.run_id}`);
    void queryClient.invalidateQueries({ queryKey: ["replay-runs"] });
    router.push(`/ci-gates/${created.run_id}`);
  }

  const callReplayMutation = useCreateReplayRunFromCall({
    onSuccess: afterReplayCreate,
    onError: (error) => setLaunchMessage(error instanceof Error ? error.message : "Replay from call failed."),
  });
  const issueReplayMutation = useCreateReplayRunFromIssue({
    onSuccess: afterReplayCreate,
    onError: (error) => setLaunchMessage(error instanceof Error ? error.message : "Replay from issue failed."),
  });
  const goldenRunMutation = useMutation({
    mutationFn: (mode: ReplayMode) => {
      if (!selectedGoldenId) throw new Error("Select a Golden Set with at least one trace.");
      return runGoldenSet(selectedGoldenId, {
        trigger: "manual",
        replay_mode: mode,
        ...(candidatePrompt.trim() ? { candidate_prompt_override: candidatePrompt.trim() } : {}),
        ...(candidateModel.trim() ? { candidate_model_override: candidateModel.trim() } : {}),
      });
    },
    onSuccess: afterGoldenRun,
    onError: (error) => setLaunchMessage(error instanceof Error ? error.message : "Golden replay failed."),
  });
  const ciRunMutation = useMutation({
    mutationFn: () => {
      const sha = gitSha.trim();
      if (sha.length < 4) throw new Error("Enter a commit SHA before running a CI gate.");
      return runRegressionCI({
        git_sha: sha,
        ...(prNumber.trim() ? { pr_body: `PR #${prNumber.trim()}` } : {}),
        sample_window_days: 30,
      });
    },
    onSuccess: afterCiRun,
    onError: (error) => setLaunchMessage(error instanceof Error ? error.message : "CI gate failed."),
  });

  const isLaunching =
    callReplayMutation.isPending ||
    issueReplayMutation.isPending ||
    goldenRunMutation.isPending ||
    ciRunMutation.isPending;

  const launchDisabled =
    isLaunching ||
    isPlanEnabled !== true ||
    (!realComparisonEnabled && replayMode !== STUB_REPLAY_MODE) ||
    (launchSource === "issue" && !selectedIssueId) ||
    (launchSource === "call" && !selectedCallId) ||
    (launchSource === "golden" && !selectedGoldenId) ||
    (launchSource === "ci" && gitSha.trim().length < 4);

  function actionRequiresProviderKey(mode: ReplayMode) {
    return launchSource === "ci" || replayModeRequiresProviderKey(mode);
  }

  async function hasProviderKeyForReplay(mode: ReplayMode) {
    if (!actionRequiresProviderKey(mode)) return true;
    if (hasActiveProviderKey(providerKeysQuery.data?.items)) return true;
    const refreshed = await providerKeysQuery.refetch();
    return hasActiveProviderKey(refreshed.data?.items);
  }

  function dispatchReplay(mode: ReplayMode = replayMode) {
    setLaunchMessage(null);
    const payload = replayPayload(mode, candidatePrompt, candidateModel);
    if (launchSource === "issue") {
      issueReplayMutation.mutate({ issueId: selectedIssueId, payload });
      return;
    }
    if (launchSource === "call") {
      callReplayMutation.mutate({ callId: selectedCallId, payload });
      return;
    }
    if (launchSource === "golden") {
      goldenRunMutation.mutate(mode);
      return;
    }
    ciRunMutation.mutate();
  }

  async function startReplay() {
    setLaunchMessage(null);
    if (!(await hasProviderKeyForReplay(replayMode))) {
      setProviderKeyGateOpen(true);
      return;
    }
    dispatchReplay(replayMode);
  }

  function onProviderKeySavedAndRun() {
    dispatchReplay(replayMode);
  }

  function onUseStubReplay() {
    if (launchSource === "ci") {
      setLaunchMessage("CI gates require verified replay. Connect a provider key before running a CI gate.");
      return;
    }
    setReplayMode(STUB_REPLAY_MODE);
    setProviderKeyGateOpen(false);
    dispatchReplay(STUB_REPLAY_MODE);
  }

  function loadMore() {
    if (!nextCursor) return;
    setPages((p) => [...p, cursor ?? ""]);
    setCursor(nextCursor);
  }

  function loadPrev() {
    const prev = pages[pages.length - 1];
    setPages((p) => p.slice(0, -1));
    setCursor(prev || undefined);
  }

  if (isPlanEnabled === false) {
    return (
      <div className="replay-workspace replay-command-center">
        <section className="module-hero">
          <div className="module-hero-header">
            <div>
              <div className="module-eyebrow">
                <ShieldCheck aria-hidden="true" />
                Replay proof engine
              </div>
              <h1>Replay</h1>
              <p>Replay needs Pro or higher so fixes can be tested against pinned production traces before release.</p>
            </div>
            <Link href="/settings/billing?upgrade_hint=replay.monthly_runs" className="btn btn-primary">
              Upgrade plan
              <ArrowRight aria-hidden="true" />
            </Link>
          </div>
        </section>
        <section className="panel replay-plan-gate">
          <ShieldCheck aria-hidden="true" />
          <h2>Replay requires Pro or higher</h2>
          <p>The Replay module runs production traces against candidate prompt and model configuration to catch regressions before they ship.</p>
        </section>
      </div>
    );
  }

  return (
    <div className="replay-workspace replay-command-center">
      <section className="module-hero replay-hero replay-command-hero">
        <div className="module-hero-header">
          <div>
            <div className="module-eyebrow">
              <PlayCircle aria-hidden="true" />
              Replay proof engine
            </div>
            <h1>Replay</h1>
            <p>
              Launch trusted replay from an Issue, Call, Golden Set, or commit SHA. Zroky reproduces the failure, compares the
              candidate behavior, and tells you if the fix is safe enough for Golden memory or CI.
            </p>
          </div>
          <div className="replay-hero-actions">
            <a href="#replay-launcher" className="btn btn-primary">
              Start replay
              <ArrowRight aria-hidden="true" />
            </a>
            <Link href="/goldens" className="btn btn-soft">
              View Goldens
            </Link>
          </div>
        </div>
        <div className="replay-proof-ladder" aria-label="Replay proof ladder">
          {["source captured", "failure reproduced", "candidate replayed", "judge verified", "golden ready", "CI gate"].map((step, index) => (
            <span key={step} className={index < 3 ? "is-hot" : ""}>
              {step}
            </span>
          ))}
        </div>
      </section>

      <section className="fi-kpi-grid replay-command-metrics" aria-label="Replay summary">
        <KpiCard
          icon={<History aria-hidden="true" />}
          label="Visible runs"
          value={runs.length.toLocaleString()}
          helper="Current filtered queue"
        />
        <KpiCard
          icon={<CheckCircle2 aria-hidden="true" />}
          label="Verified fixes"
          value={runStats.verified.toLocaleString()}
          helper="Non-stub runs with proof"
        />
        <KpiCard
          icon={<Clock3 aria-hidden="true" />}
          label="Live queue"
          value={runStats.running.toLocaleString()}
          helper="Pending or running now"
        />
        <KpiCard
          icon={<DollarSign aria-hidden="true" />}
          label="Protected spend"
          value={moneyLabel(runStats.preventedCost)}
          helper={`${moneyLabel(runStats.replayCost)} replay cost visible`}
        />
      </section>

      {isPlanEnabled !== true ? (
        <section className="replay-quota-panel replay-quota-panel-warning" aria-live="polite">
          <div>
            <strong>{quotaIsPending ? "Checking replay quota" : "Replay quota unavailable"}</strong>
            <span>
              {quotaIsPending
                ? "Launch stays disabled while Zroky confirms plan and monthly replay usage."
                : `${quotaErrorMessage} Launch stays disabled until quota reloads.`}
            </span>
          </div>
          <span className="alert-cat-badge badge-yellow">Launch gated</span>
          <button type="button" className="btn btn-soft" onClick={() => void quotaQuery.refetch()} disabled={quotaIsPending}>
            {quotaIsPending ? "Checking..." : "Retry"}
          </button>
        </section>
      ) : null}

      <section id="replay-launcher" className="panel replay-launcher" aria-label="Start replay">
        <header className="panel-header">
          <div>
            <h3>Start replay</h3>
            <p>Select a real source, choose proof strength, and launch a live run. Stub stays marked as sanity-only.</p>
          </div>
          <span className="alert-cat-badge badge-gray">{replayModeProof(replayMode)}</span>
        </header>

        <div className="replay-source-tabs" role="tablist" aria-label="Replay source">
          {LAUNCH_SOURCES.map((source) => (
            <button
              key={source.value}
              type="button"
              className={launchSource === source.value ? "is-active" : ""}
              onClick={() => {
                setLaunchSource(source.value);
                setLaunchMessage(null);
              }}
            >
              <strong>{source.label}</strong>
              <span>{source.helper}</span>
            </button>
          ))}
        </div>

        <div className="replay-launch-grid">
          <div className="replay-launch-form">
            {launchSource === "issue" ? (
              <SourcePicker<IssueItem>
                label="Open Issue"
                searchValue={issueSearch}
                searchPlaceholder="Search failure code, agent, workflow, or reason..."
                items={filteredIssues}
                selectedId={selectedIssueId}
                emptyLabel={issues.length ? "No issues match this search." : "No open issues loaded."}
                getId={(issue) => issue.id}
                getTitle={(issue) => issue.title || optionIssueLabel(issue)}
                getMeta={(issue) =>
                  `${issue.failure_code} - ${issue.severity} - ${issue.occurrence_count}x - ${issue.affected_agent ?? issue.agent_name ?? "unknown agent"}`
                }
                getReason={issueReason}
                onSearch={setIssueSearch}
                onSelect={setIssueId}
              />
            ) : null}

            {launchSource === "call" ? (
              <SourcePicker<CallListItem>
                label="Failed Call"
                searchValue={callSearch}
                searchPlaceholder="Search call id, agent, model, or error..."
                items={filteredCalls}
                selectedId={selectedCallId}
                emptyLabel={calls.length ? "No calls match this search." : "No failed calls loaded."}
                getId={(call) => call.call_id}
                getTitle={optionCallLabel}
                getMeta={(call) => `${call.provider} - ${call.model} - ${call.status} - ${call.latency_ms ?? "-"}ms`}
                getReason={(call) => call.error_code ?? call.status}
                onSearch={setCallSearch}
                onSelect={setCallId}
              />
            ) : null}

            {launchSource === "golden" ? (
              <SourcePicker<GoldenSetView>
                label="Golden Set"
                searchValue={goldenSearch}
                searchPlaceholder="Search Golden Set name or id..."
                items={filteredGoldenSets}
                selectedId={selectedGoldenId}
                emptyLabel={goldenSets.length ? "No Golden Sets match this search." : "No Golden Sets loaded."}
                getId={(set) => set.id}
                getTitle={(set) => set.name}
                getMeta={(set) => `${set.trace_count} traces - ${set.blocks_ci ? "blocks CI" : "does not block CI"}`}
                getReason={(set) => set.description ?? (set.trace_count > 0 ? "Runnable regression pack." : "No traces yet.")}
                getDisabled={(set) => set.trace_count === 0}
                onSearch={setGoldenSearch}
                onSelect={setSelectedGoldenSetId}
              />
            ) : null}

            {launchSource === "ci" ? (
              <div className="replay-launch-row">
                <label className="detail-field">
                  <span className="detail-field-label">Commit SHA</span>
                  <input className="input" value={gitSha} onChange={(event) => setGitSha(event.target.value)} placeholder="abc1234" />
                </label>
                <label className="detail-field">
                  <span className="detail-field-label">PR number</span>
                  <input className="input" value={prNumber} onChange={(event) => setPrNumber(event.target.value)} placeholder="optional" />
                </label>
              </div>
            ) : null}

            <div className="replay-mode-grid" aria-label="Replay mode">
              {REPLAY_MODE_OPTIONS.map((option) => {
                const disabled = !realComparisonEnabled && option.value !== STUB_REPLAY_MODE;
                return (
                  <button
                    key={option.value}
                    type="button"
                    className={replayMode === option.value ? "is-active" : ""}
                    disabled={disabled}
                    title={disabled ? "Real comparison replay is disabled on this control plane." : undefined}
                    onClick={() => setReplayMode(option.value)}
                  >
                    <strong>{option.label}</strong>
                    <span>{option.proof}</span>
                  </button>
                );
              })}
            </div>

            <div className="replay-launch-row">
              <label className="detail-field">
                <span className="detail-field-label">Candidate model override</span>
                <input className="input" value={candidateModel} onChange={(event) => setCandidateModel(event.target.value)} placeholder="optional" />
              </label>
              <label className="detail-field">
                <span className="detail-field-label">Candidate prompt override</span>
                <textarea
                  className="input replay-prompt-input"
                  value={candidatePrompt}
                  onChange={(event) => setCandidatePrompt(event.target.value)}
                  placeholder="optional prompt patch"
                />
              </label>
            </div>

            <div className="replay-launch-actions">
              <button type="button" className="btn btn-primary" onClick={startReplay} disabled={launchDisabled}>
                <PlayCircle aria-hidden="true" />
                {isLaunching ? "Launching..." : launchSource === "ci" ? "Run CI gate" : "Start replay"}
              </button>
              {launchMessage ? <span className={launchMessage.includes("failed") || launchMessage.includes("Enter") ? "notif-error" : "notif-meta"}>{launchMessage}</span> : null}
            </div>

            {providerKeyGateOpen ? (
              <ProviderKeyReplayGate
                onClose={() => setProviderKeyGateOpen(false)}
                onSavedAndRun={onProviderKeySavedAndRun}
                onUseStub={onUseStubReplay}
                showUseStub={launchSource !== "ci"}
              />
            ) : null}
          </div>

          <aside className="replay-launch-proof">
            <SourceCard
              title="Selected source"
              value={
                launchSource === "issue"
                  ? selectedIssue?.title || selectedIssueId || "No issue"
                  : launchSource === "call"
                    ? selectedCall ? optionCallLabel(selectedCall) : selectedCallId || "No call"
                    : launchSource === "golden"
                      ? selectedGolden?.name || selectedGoldenId || "No Golden Set"
                      : gitSha.trim() || "No SHA"
              }
              helper={
                launchSource === "issue"
                  ? issueReason(selectedIssue)
                  : launchSource === "call"
                    ? `${selectedCall?.provider ?? "provider"} / ${selectedCall?.model ?? "model"} - ${selectedCall?.status ?? "status"}`
                    : launchSource === "golden"
                      ? `${selectedGolden?.trace_count ?? 0} traces - ${selectedGolden?.blocks_ci ? "blocks CI" : "manual replay"}`
                      : "Commit-linked regression gate."
              }
              href={
                launchSource === "issue" && selectedIssueId
                  ? `/issues/${selectedIssueId}`
                  : launchSource === "call" && selectedCallId
                    ? `/calls/${selectedCallId}`
                    : launchSource === "golden" && selectedGoldenId
                      ? `/goldens/${selectedGoldenId}`
                      : undefined
              }
            />
            <SourceCard title="Proof strength" value={replayModeLabel(replayMode)} helper={replayModeProof(replayMode)} />
            <SourceCard
              title={launchSource === "issue" ? "Sample call" : launchSource === "call" ? "Call id" : "Golden coverage"}
              value={
                launchSource === "issue"
                  ? selectedIssue?.sample_call_id ?? "No sample call"
                  : launchSource === "call"
                    ? selectedCall?.call_id ?? "No call"
                    : `${runnableGoldenSets.length}/${goldenSets.length}`
              }
              helper={
                launchSource === "issue"
                  ? `${selectedIssue?.failure_code ?? "issue"} - ${selectedIssue?.occurrence_count ?? 0} occurrences`
                  : launchSource === "call"
                    ? selectedCall?.error_code ?? "Replay the captured failed call."
                    : "Runnable sets with at least one trace."
              }
            />
          </aside>
        </div>
      </section>

      {quota && quota.limit !== -1 && (
        <section className="replay-quota-panel">
          <div>
            <strong>{quota.used.toLocaleString()} / {quota.limit.toLocaleString()}</strong>
            <span>replay runs used this month - resets {quota.resets_at}</span>
          </div>
          <div className="replay-quota-track" aria-hidden="true">
            <span style={{ width: `${quotaPercent(quota.used, quota.limit)}%` }} />
          </div>
          {quotaPercent(quota.used, quota.limit) >= 90 && (
            <Link href="/settings/billing?upgrade_hint=replay.monthly_runs" className="notif-action-link">
              Upgrade plan
            </Link>
          )}
        </section>
      )}

      <section className="replay-filter-bar replay-queue-filter" aria-label="Replay filters">
        <div>
          <h3>Replay queue</h3>
          <p className="notif-meta">Live run history with proof status, cost deltas, and failure reproduction.</p>
        </div>
        <div className="replay-status-tabs">
          {STATUSES.map((status) => (
            <button
              key={status || "all"}
              type="button"
              onClick={() => {
                setStatusFilter(status);
                handleFilterChange();
              }}
              className={statusFilter === status ? "is-active" : ""}
            >
              {statusLabel(status)}
            </button>
          ))}
        </div>
        <input
          type="text"
          placeholder="Filter by Golden Set ID..."
          value={goldenSetId}
          onChange={(event) => {
            setGoldenSetId(event.target.value);
            handleFilterChange();
          }}
          className="input input-sm replay-golden-filter"
        />
      </section>

      {query.isLoading ? (
        <section className="replay-skeleton" aria-label="Loading replay runs" aria-busy="true">
          <div className="replay-skel-row" />
          <div className="replay-skel-row" />
          <div className="replay-skel-row" />
        </section>
      ) : runs.length === 0 ? (
        <section className="empty replay-empty">
          <History aria-hidden="true" />
          <strong>No replay runs yet.</strong>
          <span>Prove a discovered failure: launch a replay from an Issue, Call, Golden Set, or CI commit above — Zroky reproduces the failure and scores how faithfully the fix holds.</span>
          <Link href="/home" className="btn btn-soft" style={{ marginTop: 6 }}>
            Go to Command Center
            <ArrowRight aria-hidden="true" />
          </Link>
        </section>
      ) : (
        <section className="replay-run-list" aria-label="Replay runs">
          {runs.map((run) => (
            <RunRow key={run.id} run={run} />
          ))}
        </section>
      )}

      {(pages.length > 0 || nextCursor) && (
        <div className="replay-pagination">
          <button type="button" onClick={loadPrev} disabled={pages.length === 0} className="btn btn-soft">
            Previous
          </button>
          <button type="button" onClick={loadMore} disabled={!nextCursor} className="btn btn-soft">
            Load more
          </button>
        </div>
      )}

      <section className="panel panel-muted replay-honesty-panel">
        <div>
          <TriangleAlert aria-hidden="true" />
          <strong>Replay honesty rule</strong>
        </div>
        <p>Stub replay is a cheap sanity check. A fix is only verified when a non-stub replay proves original failure reproduction and candidate fix pass.</p>
        <div className="replay-honesty-grid">
          <span><CheckCircle2 aria-hidden="true" /> real_llm: real comparison</span>
          <span><GitBranch aria-hidden="true" /> CI gate: commit-linked regression run</span>
          <span><XCircle aria-hidden="true" /> stub: sanity only</span>
        </div>
      </section>
    </div>
  );
}
