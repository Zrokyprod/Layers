"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  DollarSign,
  Filter,
  GitPullRequest,
  RotateCcw,
  Search,
  ShieldCheck,
} from "lucide-react";

import { EmptyQueue, KpiCard, SectionHeader } from "@/components/command-center-primitives";
import {
  createReplayRunFromIssue,
  listIssues,
} from "@/lib/api";
import { ProviderKeyReplayGate } from "@/components/provider-key-replay-gate";
import { detectorLabel, severityBadgeColor } from "@/lib/detector-meta";
import { formatCount, formatDateTime, formatUsd } from "@/lib/format";
import { useActiveProviderKeys } from "@/lib/hooks";
import { replayLabel, severityRank } from "@/lib/issue-format";
import { DEFAULT_VERIFICATION_REPLAY_MODE, STUB_REPLAY_MODE } from "@/lib/replay-mode";
import { hasActiveProviderKey } from "@/lib/provider-key-gate";
import type { IssueItem, IssueStatus } from "@/lib/types";

type StatusFilter = IssueStatus | "all";
type IssueNextAction = "run_replay" | "promote_golden" | "run_ci_gate" | "open_ci_gate" | "assign_resolve";

type Filters = {
  status: StatusFilter;
  severity: string;
  failureCode: string;
  agentName: string;
  replayProof: string;
  search: string;
};

const INITIAL_FILTERS: Filters = {
  status: "open",
  severity: "",
  failureCode: "",
  agentName: "",
  replayProof: "",
  search: "",
};

const UNTRUSTED_REPLAY_STATUSES = new Set([
  "covered_failed",
  "sanity_replay_passed",
  "real_replay_missing_tool_proof",
  "stub_only",
  "not_verified",
  "tool_snapshot_missing",
  "inconclusive",
  "unknown",
  "not_covered",
  "covered_not_run",
  "fix_pending_replay",
  "replay_missing",
  "real_replay_passed",
  "covered_passed",
  "replay_running",
]);

function normalizedReplayStatus(issue: IssueItem): string {
  return issue.replay_coverage_status?.trim().toLowerCase() || "unknown";
}

function hasVerifiedFix(issue: IssueItem): boolean {
  return normalizedReplayStatus(issue) === "verified_fix";
}

function isUntrustedReplay(issue: IssueItem): boolean {
  return !hasVerifiedFix(issue) || UNTRUSTED_REPLAY_STATUSES.has(normalizedReplayStatus(issue));
}

function hasActiveGolden(issue: IssueItem): boolean {
  return Boolean(issue.proof?.golden?.golden_trace_id && issue.proof.golden.status === "active");
}

function hasCiGateRun(issue: IssueItem): boolean {
  return Boolean(issue.proof?.ci_gate?.run_id);
}

function hasDeployPr(issue: IssueItem): boolean {
  return Boolean(issue.deploy_pr_url?.trim());
}

function usableUsd(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}

function issueImpactUsd(issue: IssueItem): number | null {
  return usableUsd(issue.blast_radius_usd) ?? usableUsd(issue.cost_impact_usd);
}

function formatIssueImpact(issue: IssueItem): string {
  const impact = issueImpactUsd(issue);
  return impact == null ? "\u2014" : formatUsd(impact);
}

function issueAgent(issue: IssueItem): string {
  return issue.affected_agent ?? issue.agent_name ?? "Agent not captured";
}

function issueProvider(issue: IssueItem): string | null {
  return issue.evidence_traces.find((trace) => trace.provider?.trim())?.provider ?? null;
}

function affectedTraceCount(issue: IssueItem): number {
  return issue.affected_trace_count ?? issue.blast_radius?.affected_traces ?? issue.occurrence_count;
}

function affectedUserCount(issue: IssueItem): number | null {
  const count = issue.affected_user_count ?? issue.blast_radius?.affected_users;
  return typeof count === "number" && count > 0 ? count : null;
}

function issueVersion(issue: IssueItem): string {
  return issue.suspected_introduced_version?.trim() || "version unknown";
}

function sortIssues(items: IssueItem[]): IssueItem[] {
  return [...items].sort((a, b) => {
    const severityDelta = severityRank(b.severity) - severityRank(a.severity);
    if (severityDelta !== 0) return severityDelta;
    const trustDelta = Number(isUntrustedReplay(b)) - Number(isUntrustedReplay(a));
    if (trustDelta !== 0) return trustDelta;
    const impactDelta = (issueImpactUsd(b) ?? 0) - (issueImpactUsd(a) ?? 0);
    if (impactDelta !== 0) return impactDelta;
    const occurrenceDelta = b.occurrence_count - a.occurrence_count;
    if (occurrenceDelta !== 0) return occurrenceDelta;
    return new Date(b.last_seen_at).getTime() - new Date(a.last_seen_at).getTime();
  });
}

function issueNextAction(issue: IssueItem): IssueNextAction {
  if (isUntrustedReplay(issue) && issue.sample_call_id) return "run_replay";
  if (hasCiGateRun(issue)) return "open_ci_gate";
  if (hasActiveGolden(issue) && hasDeployPr(issue)) return "run_ci_gate";
  if (hasVerifiedFix(issue) && issue.sample_call_id && !hasActiveGolden(issue)) return "promote_golden";
  return "assign_resolve";
}

function issueNextActionLabel(action: IssueNextAction): string {
  if (action === "run_replay") return "Run replay";
  if (action === "promote_golden") return "Promote Contract";
  if (action === "run_ci_gate") return "Run CI gate";
  if (action === "open_ci_gate") return "Open CI gate";
  return "Assign / resolve";
}

function issueNextActionHref(issue: IssueItem): string {
  const action = issueNextAction(issue);
  if (action === "open_ci_gate" && issue.proof?.ci_gate?.run_id) return `/ci-gates/${issue.proof.ci_gate.run_id}`;
  if (action === "promote_golden" && issue.sample_call_id) return `/contracts?call_id=${encodeURIComponent(issue.sample_call_id)}`;
  return `/issues/${issue.id}`;
}

function replayProofMatches(issue: IssueItem, filter: string): boolean {
  const status = normalizedReplayStatus(issue);
  if (!filter) return true;
  if (filter === "no_trusted_replay") return status !== "verified_fix";
  if (filter === "verified_fix") return status === "verified_fix";
  if (filter === "stub_only") return status === "stub_only" || status === "sanity_replay_passed";
  if (filter === "not_verified") return status === "not_verified";
  if (filter === "missing_tool_proof") {
    return status === "real_replay_missing_tool_proof" || status === "tool_snapshot_missing";
  }
  if (filter === "replay_failed") return status === "covered_failed";
  if (filter === "inconclusive") return status === "inconclusive";
  return true;
}

function searchMatches(issue: IssueItem, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  const haystack = [
    issue.title,
    issue.failure_code,
    detectorLabel(issue.failure_code),
    issue.agent_name,
    issue.affected_agent,
    issue.affected_workflow,
    issue.status,
    replayLabel(issue.replay_coverage_status),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(needle);
}

function severityBadge(issue: IssueItem) {
  return (
    <span className={`alert-cat-badge badge-${severityBadgeColor(issue.severity)} im-severity-badge`}>
      <AlertTriangle aria-hidden="true" />
      {issue.severity}
    </span>
  );
}

export default function IssuesPage() {
  const router = useRouter();
  const [items, setItems] = useState<IssueItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>(INITIAL_FILTERS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyIssueId, setBusyIssueId] = useState<string | null>(null);
  const [providerKeyGateIssue, setProviderKeyGateIssue] = useState<IssueItem | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const providerKeysQuery = useActiveProviderKeys();

  const loadIssues = useCallback(
    async (nextCursor?: string | null) => {
      if (nextCursor === null) return;
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      setError(null);
      try {
        const data = await listIssues(
          {
            status: filters.status,
            limit: 50,
            cursor: nextCursor ?? undefined,
            ...(filters.severity ? { severity: filters.severity } : {}),
            ...(filters.failureCode ? { failure_code: filters.failureCode.trim() } : {}),
            ...(filters.agentName ? { agent_name: filters.agentName.trim() } : {}),
          },
          ctrl.signal,
        );
        setItems((prev) => (nextCursor ? [...prev, ...data.items] : data.items));
        setCursor(data.next_cursor);
      } catch (loadError) {
        if ((loadError as { name?: string }).name === "AbortError") return;
        setError(loadError instanceof Error ? loadError.message : "Failed to load issues.");
      } finally {
        setLoading(false);
      }
    },
    [filters.agentName, filters.failureCode, filters.severity, filters.status],
  );

  useEffect(() => {
    setItems([]);
    setCursor(null);
    void loadIssues(undefined);
    return () => abortRef.current?.abort();
  }, [loadIssues]);

  const visibleIssues = useMemo(() => {
    return sortIssues(items.filter((issue) =>
      replayProofMatches(issue, filters.replayProof) && searchMatches(issue, filters.search),
    ));
  }, [filters.replayProof, filters.search, items]);

  const replayGapCount = visibleIssues.filter((issue) => !hasVerifiedFix(issue)).length;
  const verifiedFixCount = visibleIssues.filter(hasVerifiedFix).length;
  const goldenCandidateCount = visibleIssues.filter(
    (issue) => hasVerifiedFix(issue) && issue.sample_call_id && !hasActiveGolden(issue),
  ).length;
  const loadedIssueImpactUsd = visibleIssues.reduce((sum, issue) => sum + (issueImpactUsd(issue) ?? 0), 0);
  const defaultFailureSummaryActive =
    filters.status === INITIAL_FILTERS.status &&
    !filters.severity &&
    !filters.failureCode &&
    !filters.agentName &&
    !filters.replayProof &&
    !filters.search;

  function updateFilter<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  async function runReplay(issue: IssueItem, replayMode = DEFAULT_VERIFICATION_REPLAY_MODE) {
    setActionError(null);
    setBusyIssueId(issue.id);
    try {
      const run = await createReplayRunFromIssue(issue.id, {
        replay_mode: replayMode,
      });
      router.push(`/replay/${run.id}`);
    } catch (replayError) {
      setActionError(replayError instanceof Error ? replayError.message : "Failed to create replay run.");
    } finally {
      setBusyIssueId(null);
    }
  }

  async function onReplay(issue: IssueItem) {
    const expectedProvider = issueProvider(issue);
    if (hasActiveProviderKey(providerKeysQuery.data?.items, expectedProvider)) {
      await runReplay(issue);
      return;
    }
    const refreshed = await providerKeysQuery.refetch();
    if (hasActiveProviderKey(refreshed.data?.items, expectedProvider)) {
      await runReplay(issue);
      return;
    }
    setProviderKeyGateIssue(issue);
  }

  function onProviderKeySavedAndRun() {
    if (!providerKeyGateIssue) return;
    void runReplay(providerKeyGateIssue);
  }

  function onUseStubReplay() {
    if (!providerKeyGateIssue) return;
    const issue = providerKeyGateIssue;
    setProviderKeyGateIssue(null);
    void runReplay(issue, STUB_REPLAY_MODE);
  }

  function primaryAction(issue: IssueItem) {
    if (hasCiGateRun(issue) && issue.proof?.ci_gate?.run_id) {
      return (
        <Link href={`/ci-gates/${issue.proof.ci_gate.run_id}`} className="btn btn-primary btn-sm im-btn-primary">
          <GitPullRequest aria-hidden="true" />
          Open CI gate
        </Link>
      );
    }
    if (hasActiveGolden(issue) && hasDeployPr(issue)) {
      return (
        <Link href={`/issues/${issue.id}`} className="btn btn-primary btn-sm im-btn-primary">
          <GitPullRequest aria-hidden="true" />
          Run CI gate
        </Link>
      );
    }
    if (hasVerifiedFix(issue) && issue.sample_call_id && !hasActiveGolden(issue)) {
      return (
        <Link href={`/contracts?call_id=${encodeURIComponent(issue.sample_call_id)}`} className="btn btn-primary btn-sm im-btn-primary">
          <ShieldCheck aria-hidden="true" />
          Promote Contract
        </Link>
      );
    }
    if (isUntrustedReplay(issue) && issue.sample_call_id) {
      return (
        <button
          type="button"
          className="btn btn-primary btn-sm im-btn-primary"
          onClick={() => void onReplay(issue)}
          disabled={busyIssueId === issue.id}
        >
          <RotateCcw aria-hidden="true" />
          {busyIssueId === issue.id ? "Creating..." : "Replay"}
        </button>
      );
    }
    return (
      <Link href={`/issues/${issue.id}`} className="btn btn-primary btn-sm im-btn-primary">
        <ArrowRight aria-hidden="true" />
        View issue
      </Link>
    );
  }

  return (
    <div className="issues-mvp">
      <section className="im-hero">
        <div>
          <div className="im-eyebrow">
            <AlertTriangle aria-hidden="true" />
            Grouped failures
          </div>
          <h1>Incidents</h1>
          <p>Grouped production failures detected across your agents.</p>
        </div>
        <button
          type="button"
          className="btn btn-primary btn-sm im-btn-primary"
          onClick={() => {
            setFilters((prev) => ({ ...prev, status: "open", replayProof: "no_trusted_replay" }));
          }}
        >
          <RotateCcw aria-hidden="true" />
          Review replay gaps
        </button>
      </section>

      {error ? (
        <section className="im-notice im-notice-error">
          <p>{error}</p>
          <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={() => void loadIssues(undefined)}>
            Retry
          </button>
        </section>
      ) : null}

      {actionError ? (
        <section className="im-notice im-notice-error">
          <p>{actionError}</p>
        </section>
      ) : null}

      {providerKeyGateIssue ? (
        <ProviderKeyReplayGate
          expectedProvider={issueProvider(providerKeyGateIssue)}
          onClose={() => setProviderKeyGateIssue(null)}
          onSavedAndRun={onProviderKeySavedAndRun}
          onUseStub={onUseStubReplay}
        />
      ) : null}

      <section className="fi-kpi-grid im-kpi-grid" aria-label="Failure summary">
        <KpiCard
          icon={<AlertTriangle aria-hidden="true" />}
          label="Loaded failures"
          value={formatCount(visibleIssues.length)}
          helper="Grouped failures visible under current filters."
          active={defaultFailureSummaryActive}
          onClick={() => setFilters(INITIAL_FILTERS)}
        />
        <KpiCard
          icon={<RotateCcw aria-hidden="true" />}
          label="Replay gaps"
          value={formatCount(replayGapCount)}
          helper="Need trusted replay before Contract or CI protection."
          active={filters.replayProof === "no_trusted_replay"}
          onClick={() => setFilters((prev) => ({ ...prev, replayProof: "no_trusted_replay" }))}
        />
        <KpiCard
          icon={<ShieldCheck aria-hidden="true" />}
          label="Verified fixes"
          value={formatCount(verifiedFixCount)}
          helper="Replay proof exists; promote eligible traces."
          active={filters.replayProof === "verified_fix"}
          onClick={() => setFilters((prev) => ({ ...prev, replayProof: "verified_fix" }))}
        />
        <KpiCard
          icon={<DollarSign aria-hidden="true" />}
          label="Loaded impact"
          value={formatUsd(loadedIssueImpactUsd)}
          helper={`${formatCount(goldenCandidateCount)} verified fixes can become Contracts.`}
        />
      </section>

      <section className="im-filter-panel" aria-label="Issue filters">
        <label>
          <span>Status</span>
          <select value={filters.status} onChange={(event) => updateFilter("status", event.target.value as StatusFilter)}>
            <option value="open">Open</option>
            <option value="resolved">Resolved</option>
            <option value="ignored">Ignored</option>
            <option value="all">All</option>
          </select>
        </label>
        <label>
          <span>Severity</span>
          <select value={filters.severity} onChange={(event) => updateFilter("severity", event.target.value)}>
            <option value="">Any</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </label>
        <label>
          <span>Failure code</span>
          <input
            value={filters.failureCode}
            onChange={(event) => updateFilter("failureCode", event.target.value)}
            placeholder="LOOP_DETECTED"
          />
        </label>
        <label>
          <span>Agent</span>
          <input
            value={filters.agentName}
            onChange={(event) => updateFilter("agentName", event.target.value)}
            placeholder="Refund Agent"
          />
        </label>
        <label>
          <span>Replay proof</span>
          <select value={filters.replayProof} onChange={(event) => updateFilter("replayProof", event.target.value)}>
            <option value="">Any</option>
            <option value="no_trusted_replay">No trusted replay</option>
            <option value="verified_fix">Verified fix</option>
            <option value="stub_only">Fixture validation only</option>
            <option value="not_verified">Not verified</option>
            <option value="missing_tool_proof">Missing tool proof</option>
            <option value="replay_failed">Replay failed</option>
            <option value="inconclusive">Inconclusive</option>
          </select>
        </label>
        <label className="im-search-field">
          <span>Search</span>
          <div>
            <Search aria-hidden="true" />
            <input
              value={filters.search}
              onChange={(event) => updateFilter("search", event.target.value)}
              placeholder="Search issues, agents, failure codes..."
            />
          </div>
        </label>
        {(filters.status !== INITIAL_FILTERS.status ||
          filters.severity ||
          filters.failureCode ||
          filters.agentName ||
          filters.replayProof ||
          filters.search) ? (
          <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={() => setFilters(INITIAL_FILTERS)}>
            <Filter aria-hidden="true" />
            Clear
          </button>
        ) : null}
      </section>

      <section className="im-table-section">
        <SectionHeader
          title="Issue queue"
          description={`${formatCount(visibleIssues.length)} grouped failures loaded. ${formatCount(replayGapCount)} need trusted replay.`}
        />

        {loading && items.length === 0 ? (
          <div className="im-loading" aria-label="Loading issues" />
        ) : visibleIssues.length === 0 ? (
          <EmptyQueue>No issues match these filters.</EmptyQueue>
        ) : (
          <div className="im-table-wrap">
            <table className="im-issues-table">
              <colgroup>
                <col className="im-col-issue" />
                <col className="im-col-severity" />
                <col className="im-col-impact" />
                <col className="im-col-replay" />
                <col className="im-col-status" />
                <col className="im-col-last-seen" />
                <col className="im-col-next-action" />
                <col className="im-col-action" />
              </colgroup>
              <thead>
                <tr>
                  <th>Issue</th>
                  <th>Severity</th>
                  <th>Impact</th>
                  <th>Replay proof</th>
                  <th>Status</th>
                  <th>Last seen</th>
                  <th>Next action</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {visibleIssues.map((issue) => {
                  const nextAction = issueNextAction(issue);
                  return (
                    <tr key={issue.id}>
                      <td>
                        <div className="im-issue-cell">
                          <Link href={`/issues/${issue.id}`}>{issue.title}</Link>
                          <span>
                            {detectorLabel(issue.failure_code)} &middot; {issueAgent(issue)} &middot;{" "}
                            {formatCount(affectedTraceCount(issue))} affected traces
                            {affectedUserCount(issue) != null ? ` - ${formatCount(affectedUserCount(issue)!)} users` : ""} &middot;{" "}
                            {issueVersion(issue)}
                          </span>
                        </div>
                      </td>
                      <td>{severityBadge(issue)}</td>
                      <td>
                        <strong className="im-impact-value">{formatIssueImpact(issue)}</strong>
                      </td>
                      <td>{replayLabel(issue.replay_coverage_status)}</td>
                      <td>
                        <span className="im-status-pill">{issue.status}</span>
                      </td>
                      <td>{formatDateTime(issue.last_seen_at)}</td>
                      <td>
                        <Link href={issueNextActionHref(issue)} className="im-next-action-link">
                          {issueNextActionLabel(nextAction)}
                        </Link>
                      </td>
                      <td>
                        <div className="im-row-actions">
                          {primaryAction(issue)}
                          <Link href={`/issues/${issue.id}`} className="btn btn-soft btn-sm im-btn-secondary">
                            View issue
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {cursor ? (
          <div className="im-load-more">
            <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={() => void loadIssues(cursor)} disabled={loading}>
              {loading ? "Loading..." : "Load more"}
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
