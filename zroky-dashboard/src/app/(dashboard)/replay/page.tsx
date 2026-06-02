"use client";

import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  DollarSign,
  GitBranch,
  History,
  Loader2,
  PlayCircle,
  ShieldCheck,
  TriangleAlert,
  XCircle,
} from "lucide-react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  listGoldenSets,
  listIssues,
  runGoldenSet,
  runRegressionCI,
} from "@/lib/api";
import type {
  RegressionCIRunResponse,
  ReplayCreatePayload,
  ReplayCreateResponse,
  ReplayMode,
  ReplayRunItem,
} from "@/lib/api";
import {
  useCreateReplayRunFromCall,
  useCreateReplayRunFromIssue,
  useListCalls,
  useReplayQuota,
  useReplayRuns,
} from "@/lib/hooks";
import {
  DEFAULT_VERIFICATION_REPLAY_MODE,
  REPLAY_MODE_OPTIONS,
  replayModeLabel,
  replayModeProof,
  replayVerificationLabel,
  replayVerifiedFix,
} from "@/lib/replay-mode";
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

function ReplayMetric({
  icon,
  label,
  value,
  helper,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  helper: string;
}) {
  return (
    <div className="metric-card replay-metric-card">
      <div className="replay-metric-top">
        {icon}
        <span className="notif-meta">{label}</span>
      </div>
      <strong>{value}</strong>
      <span>{helper}</span>
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

function RunRow({ run }: { run: ReplayRunItem }) {
  const total = run.summary.trace_count_at_dispatch;
  const executed = run.summary.trace_count_executed;
  const passRate = total > 0 ? Math.round((run.summary.pass_count / total) * 100) : null;
  const isVerifiedFix = replayVerifiedFix(run.replay_mode, run.summary.verified_fix);
  const verificationLabel = replayVerificationLabel(run.replay_mode, run.summary.verified_fix, run.summary.verification_status);
  const isStub = run.replay_mode === "stub";
  const costDelta = moneyDeltaLabel(run.summary.cost_delta_usd);
  const latencyDelta = deltaLabel(run.summary.latency_delta_ms, "ms");

  return (
    <Link href={`/replay/${run.id}`} className="replay-run-card">
      <div className="replay-run-main">
        <div className="replay-run-badges">
          <StatusBadge status={run.status} />
          <span className="alert-cat-badge badge-gray">{replayModeLabel(run.replay_mode)}</span>
          <span className={`alert-cat-badge ${isVerifiedFix ? "badge-green" : isStub ? "badge-yellow" : "badge-gray"}`}>
            {verificationLabel}
          </span>
        </div>

        <h2>
          Run {run.id.slice(0, 16)}
          <span>...</span>
        </h2>

        <div className="replay-run-meta">
          <span>trigger: {run.trigger}</span>
          {run.git_sha && <span>sha: {run.git_sha.slice(0, 8)}</span>}
          <span>golden set: {run.golden_set_id.slice(0, 12)}...</span>
          <span>{timeAgo(run.created_at)}</span>
        </div>

        <p className="replay-proof-copy">proof: {replayModeProof(run.replay_mode)}</p>
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
      </div>

      <div className="replay-run-open">
        Open
        <ArrowRight aria-hidden="true" />
      </div>
    </Link>
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
  const [replayMode, setReplayMode] = useState<ReplayMode>(DEFAULT_VERIFICATION_REPLAY_MODE);
  const [candidatePrompt, setCandidatePrompt] = useState("");
  const [candidateModel, setCandidateModel] = useState("");
  const [gitSha, setGitSha] = useState(searchParams.get("git_sha") ?? "");
  const [prNumber, setPrNumber] = useState(searchParams.get("pr_number") ?? "");
  const [launchMessage, setLaunchMessage] = useState<string | null>(null);

  const quotaQuery = useReplayQuota();
  const quota = quotaQuery.data;
  const isPlanEnabled = quota?.enabled ?? null;

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
  const issues = issuesQuery.data?.items ?? [];
  const calls = callsQuery.data?.items ?? [];
  const goldenSets = goldenSetsQuery.data?.items ?? [];
  const runnableGoldenSets = goldenSets.filter((set) => set.trace_count > 0);
  const selectedIssueId = issueId.trim() || issues[0]?.id || "";
  const selectedCallId = callId.trim() || calls[0]?.call_id || "";
  const selectedGoldenId = selectedGoldenSetId.trim() || runnableGoldenSets[0]?.id || goldenSets[0]?.id || "";

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
    mutationFn: () => {
      if (!selectedGoldenId) throw new Error("Select a Golden Set with at least one trace.");
      return runGoldenSet(selectedGoldenId, {
        trigger: "manual",
        replay_mode: replayMode,
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
    (launchSource === "issue" && !selectedIssueId) ||
    (launchSource === "call" && !selectedCallId) ||
    (launchSource === "golden" && !selectedGoldenId) ||
    (launchSource === "ci" && gitSha.trim().length < 4);

  function startReplay() {
    setLaunchMessage(null);
    const payload = replayPayload(replayMode, candidatePrompt, candidateModel);
    if (launchSource === "issue") {
      issueReplayMutation.mutate({ issueId: selectedIssueId, payload });
      return;
    }
    if (launchSource === "call") {
      callReplayMutation.mutate({ callId: selectedCallId, payload });
      return;
    }
    if (launchSource === "golden") {
      goldenRunMutation.mutate();
      return;
    }
    ciRunMutation.mutate();
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

  if (quotaQuery.isLoading) {
    return (
      <section className="panel issue-loading-panel" aria-label="Loading replay quota">
        <Loader2 aria-hidden="true" />
        <div>
          <strong>Loading replay proof engine</strong>
          <p className="notif-meta">Checking plan quota and recent replay runs.</p>
        </div>
      </section>
    );
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
              <h1>Replay Lab</h1>
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
            <h1>Prove the fix before it ships.</h1>
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

      <section className="metric-strip replay-command-metrics" aria-label="Replay summary">
        <ReplayMetric icon={<History aria-hidden="true" />} label="Visible runs" value={runs.length.toLocaleString()} helper="Current filtered queue" />
        <ReplayMetric icon={<CheckCircle2 aria-hidden="true" />} label="Verified fixes" value={runStats.verified.toLocaleString()} helper="Non-stub runs with proof" />
        <ReplayMetric icon={<Clock3 aria-hidden="true" />} label="Live queue" value={runStats.running.toLocaleString()} helper="Pending or running now" />
        <ReplayMetric icon={<DollarSign aria-hidden="true" />} label="Protected spend" value={moneyLabel(runStats.preventedCost)} helper={`${moneyLabel(runStats.replayCost)} replay cost visible`} />
      </section>

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
              <label className="detail-field">
                <span className="detail-field-label">Open Issue</span>
                <select className="input" value={issueId} onChange={(event) => setIssueId(event.target.value)}>
                  <option value="">{issues.length ? "Use highest priority open issue" : "No open issues loaded"}</option>
                  {issues.map((issue) => (
                    <option key={issue.id} value={issue.id}>
                      {optionIssueLabel(issue)}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}

            {launchSource === "call" ? (
              <label className="detail-field">
                <span className="detail-field-label">Failed Call</span>
                <select className="input" value={callId} onChange={(event) => setCallId(event.target.value)}>
                  <option value="">{calls.length ? "Use most recent failed call" : "No failed calls loaded"}</option>
                  {calls.map((call) => (
                    <option key={call.call_id} value={call.call_id}>
                      {optionCallLabel(call)}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}

            {launchSource === "golden" ? (
              <label className="detail-field">
                <span className="detail-field-label">Golden Set</span>
                <select className="input" value={selectedGoldenSetId} onChange={(event) => setSelectedGoldenSetId(event.target.value)}>
                  <option value="">{goldenSets.length ? "Use first runnable Golden Set" : "No Golden Sets loaded"}</option>
                  {goldenSets.map((set) => (
                    <option key={set.id} value={set.id} disabled={set.trace_count === 0}>
                      {set.name} - {set.trace_count} traces
                    </option>
                  ))}
                </select>
              </label>
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
              {REPLAY_MODE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={replayMode === option.value ? "is-active" : ""}
                  onClick={() => setReplayMode(option.value)}
                >
                  <strong>{option.label}</strong>
                  <span>{option.proof}</span>
                </button>
              ))}
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
          </div>

          <aside className="replay-launch-proof">
            <SourceCard
              title="Selected source"
              value={
                launchSource === "issue"
                  ? selectedIssueId || "No issue"
                  : launchSource === "call"
                    ? selectedCallId || "No call"
                    : launchSource === "golden"
                      ? selectedGoldenId || "No Golden Set"
                      : gitSha.trim() || "No SHA"
              }
              helper="This is the live backend source used for dispatch."
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
            <SourceCard title="Golden coverage" value={`${runnableGoldenSets.length}/${goldenSets.length}`} helper="Runnable sets with at least one trace." />
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
        <section className="panel issue-loading-panel" aria-label="Loading replay runs">
          <Loader2 aria-hidden="true" />
          <div>
            <strong>Loading replay runs</strong>
            <p className="notif-meta">Reading recent proof results.</p>
          </div>
        </section>
      ) : runs.length === 0 ? (
        <section className="empty replay-empty">
          <History aria-hidden="true" />
          <strong>No replay runs found.</strong>
          <span>Start a replay from an Issue, Call, Golden Set, or CI commit above.</span>
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
