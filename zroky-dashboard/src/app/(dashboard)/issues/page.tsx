"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  CircleDot,
  GitPullRequestArrow,
  Loader2,
  MessageSquareText,
  ShieldCheck,
  Target,
  UserRoundPlus,
  XCircle,
} from "lucide-react";
import { ignoreIssue, listIssues, resolveIssue, updateIssueTriage } from "@/lib/api";
import { formatDateTime, formatUsd } from "@/lib/format";
import { replayLabel } from "@/lib/issue-format";
import { DEFAULT_VERIFICATION_REPLAY_MODE } from "@/lib/replay-mode";
import { useCreateReplayRunFromIssue } from "@/lib/hooks";
import type { IssueItem, IssueStatus } from "@/lib/types";
import { detectorLabel, severityBadgeColor } from "@/lib/detector-meta";

type Tab = "open" | "resolved" | "ignored";

const TABS: { id: Tab; label: string; helper: string }[] = [
  { id: "open", label: "Top problems", helper: "The highest-impact open issues right now." },
  { id: "resolved", label: "Resolved", helper: "Problems already fixed or manually closed." },
  { id: "ignored", label: "Ignored", helper: "Problems muted by triage but still tracked." },
];

interface Filters {
  severity: string;
  has_fix: "" | "true" | "false";
}

export default function IssuesPage() {
  return (
    <Suspense fallback={<p className="hint">Loading issues...</p>}>
      <IssuesPageContent />
    </Suspense>
  );
}

function IssuesPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const rawTab = searchParams.get("tab") as Tab | null;
  const activeTab: Tab = rawTab && ["open", "resolved", "ignored"].includes(rawTab) ? rawTab : "open";

  function setTab(tab: Tab) {
    router.replace(tab === "open" ? "/issues" : `/issues?tab=${tab}`);
  }

  return (
    <div className="issue-workspace">
      <section className="module-hero issue-hero">
        <div className="module-hero-header">
          <div>
            <div className="module-eyebrow">
              <Target aria-hidden="true" />
              Production problem queue
            </div>
            <h1>Issues</h1>
            <p>Top grouped production problems with root cause, evidence, replay status, impact, and the next action.</p>
          </div>
          <div className="issue-hero-meta">
            <span className="mono">default view: top 5</span>
            <span>Fix the queue from the top down.</span>
          </div>
        </div>
      </section>

      <div className="tab-bar" role="tablist" aria-label="Issues tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`tab-btn${activeTab === tab.id ? " tab-btn-active" : ""}`}
            onClick={() => setTab(tab.id)}
            title={tab.helper}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <IssueList status={activeTab} />
    </div>
  );
}

function FilterBar({ filters, onChange }: { filters: Filters; onChange: (filters: Filters) => void }) {
  return (
    <div className="issue-filter-bar">
      <select
        className="input input-sm"
        value={filters.severity}
        onChange={(event) => onChange({ ...filters, severity: event.target.value })}
        aria-label="Filter by severity"
      >
        <option value="">All severities</option>
        <option value="critical">Critical</option>
        <option value="high">High</option>
        <option value="medium">Medium</option>
        <option value="low">Low</option>
      </select>

      <select
        className="input input-sm"
        value={filters.has_fix}
        onChange={(event) => onChange({ ...filters, has_fix: event.target.value as Filters["has_fix"] })}
        aria-label="Filter by fix status"
      >
        <option value="">Replay/fix: any</option>
        <option value="true">Fix attached</option>
        <option value="false">No fix yet</option>
      </select>

      {(filters.severity || filters.has_fix) && (
        <button className="btn btn-soft btn-sm" onClick={() => onChange({ severity: "", has_fix: "" })}>
          Clear
        </button>
      )}
    </div>
  );
}

function IssuesLoadingState() {
  return (
    <section className="panel issue-loading-panel" aria-label="Loading issues">
      <Loader2 aria-hidden="true" />
      <div>
        <strong>Loading issue queue</strong>
        <p className="notif-meta">Grouping raw traces into product issues.</p>
      </div>
    </section>
  );
}

function IssueQueueSummary({ items, status }: { items: IssueItem[]; status: IssueStatus }) {
  const highSeverity = items.filter((issue) => ["critical", "high"].includes(issue.severity.toLowerCase())).length;
  const unassigned = items.filter((issue) => !issue.assigned_to).length;
  const replayMissing = items.filter((issue) => {
    const replay = issue.replay_coverage_status;
    return replay === "not_covered" || replay === "fix_pending_replay" || replay === "covered_not_run";
  }).length;
  const impactUsd = items.reduce((sum, issue) => sum + issue.cost_impact_usd, 0);

  return (
    <section className="issue-summary-grid" aria-label={`${status} issue summary`}>
      <div className="issue-summary-card">
        <span>Visible issues</span>
        <strong>{items.length}</strong>
        <p>Loaded in this queue view.</p>
      </div>
      <div className="issue-summary-card">
        <span>Critical / high</span>
        <strong>{highSeverity}</strong>
        <p>Fix these before lower severity items.</p>
      </div>
      <div className="issue-summary-card">
        <span>Replay gaps</span>
        <strong>{replayMissing}</strong>
        <p>Needs replay proof before fix confidence.</p>
      </div>
      <div className="issue-summary-card">
        <span>Unassigned</span>
        <strong>{unassigned}</strong>
        <p>{formatUsd(impactUsd)} visible cost impact.</p>
      </div>
    </section>
  );
}

function IssueList({ status }: { status: IssueStatus }) {
  const router = useRouter();
  const [items, setItems] = useState<IssueItem[]>([]);
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [ignoringId, setIgnoringId] = useState<string | null>(null);
  const [acceptingRiskId, setAcceptingRiskId] = useState<string | null>(null);
  const [replayingId, setReplayingId] = useState<string | null>(null);
  const [triagingId, setTriagingId] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>({ severity: "", has_fix: "" });
  const abortRef = useRef<AbortController | null>(null);
  const createReplay = useCreateReplayRunFromIssue({
    onSuccess: (run) => router.push(`/replay/${run.id}`),
  });

  const loadPage = useCallback(
    async (nextCursor?: string | null, activeFilters: Filters = filters) => {
      if (nextCursor === null) return;
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      setError(null);
      try {
        const data = await listIssues(
          {
            status,
            cursor: nextCursor ?? undefined,
            limit: 5,
            ...(activeFilters.severity ? { severity: activeFilters.severity } : {}),
            ...(activeFilters.has_fix ? { has_fix: activeFilters.has_fix === "true" } : {}),
          },
          ctrl.signal,
        );
        setItems((prev) => (nextCursor ? [...prev, ...data.items] : data.items));
        setCursor(data.next_cursor);
      } catch (error: unknown) {
        if ((error as { name?: string }).name === "AbortError") return;
        setError((error as { message?: string }).message ?? "Failed to load issues.");
      } finally {
        setLoading(false);
      }
    },
    [filters, status],
  );

  useEffect(() => {
    setItems([]);
    setCursor(undefined);
    void loadPage(undefined, filters);
    return () => abortRef.current?.abort();
  }, [filters, loadPage, status]);

  function applyFilters(nextFilters: Filters) {
    setFilters(nextFilters);
  }

  async function onResolve(event: MouseEvent, issueId: string) {
    event.preventDefault();
    event.stopPropagation();
    setResolvingId(issueId);
    try {
      const updated = await resolveIssue(issueId, { resolution_source: "manual" });
      setItems((prev) => prev.filter((issue) => issue.id !== updated.id));
    } finally {
      setResolvingId(null);
    }
  }

  async function onAcceptedRisk(event: MouseEvent, issueId: string) {
    event.preventDefault();
    event.stopPropagation();
    setAcceptingRiskId(issueId);
    try {
      const updated = await resolveIssue(issueId, { resolution_source: "accepted_risk" });
      setItems((prev) => prev.filter((issue) => issue.id !== updated.id));
    } finally {
      setAcceptingRiskId(null);
    }
  }

  async function onIgnore(event: MouseEvent, issueId: string) {
    event.preventDefault();
    event.stopPropagation();
    setIgnoringId(issueId);
    try {
      const updated = await ignoreIssue(issueId);
      setItems((prev) => prev.filter((issue) => issue.id !== updated.id));
    } finally {
      setIgnoringId(null);
    }
  }

  function onCreateReplay(event: MouseEvent, issueId: string) {
    event.preventDefault();
    event.stopPropagation();
    setReplayingId(issueId);
    createReplay.mutate(
      { issueId, payload: { replay_mode: DEFAULT_VERIFICATION_REPLAY_MODE } },
      { onSettled: () => setReplayingId(null) },
    );
  }

  async function onAssign(event: MouseEvent, issue: IssueItem) {
    event.preventDefault();
    event.stopPropagation();
    const assignee = window.prompt("Assign this issue to:", issue.assigned_to ?? "");
    if (assignee === null) return;
    const trimmed = assignee.trim();
    setTriagingId(issue.id);
    try {
      const updated = await updateIssueTriage(issue.id, { assigned_to: trimmed || null });
      setItems((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setActionError(null);
    } catch (error: unknown) {
      setActionError((error as { message?: string }).message ?? "Failed to update issue assignment.");
    } finally {
      setTriagingId(null);
    }
  }

  async function onLinkDeploy(event: MouseEvent, issue: IssueItem) {
    event.preventDefault();
    event.stopPropagation();
    const link = window.prompt("Paste deploy or PR URL:", issue.deploy_pr_url ?? "");
    if (link === null) return;
    const trimmed = link.trim();
    setTriagingId(issue.id);
    try {
      const updated = await updateIssueTriage(issue.id, { deploy_pr_url: trimmed || null });
      setItems((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setActionError(null);
    } catch (error: unknown) {
      setActionError((error as { message?: string }).message ?? "Failed to update deploy/PR link.");
    } finally {
      setTriagingId(null);
    }
  }

  return (
    <section>
      <FilterBar filters={filters} onChange={applyFilters} />
      {actionError && (
        <div className="panel" style={{ marginBottom: "0.75rem" }}>
          <p className="notif-error">{actionError}</p>
        </div>
      )}

      {loading && items.length === 0 ? (
        <IssuesLoadingState />
      ) : error ? (
        <div className="panel">
          <p className="notif-error">{error}</p>
          <button className="btn btn-soft" onClick={() => void loadPage(undefined, filters)}>
            Retry
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="empty">
          {status === "open" ? "No open product issues." : status === "resolved" ? "No resolved issues." : "No ignored issues."}
        </div>
      ) : (
        <div className="issue-list-stack">
          <IssueQueueSummary items={items} status={status} />
          {items.map((issue) => (
            <IssueCard
              key={issue.id}
              issue={issue}
              status={status}
              resolving={resolvingId === issue.id}
              ignoring={ignoringId === issue.id}
              acceptingRisk={acceptingRiskId === issue.id}
              replaying={replayingId === issue.id}
              triaging={triagingId === issue.id}
              onResolve={onResolve}
              onIgnore={onIgnore}
              onAcceptedRisk={onAcceptedRisk}
              onCreateReplay={onCreateReplay}
              onAssign={onAssign}
              onLinkDeploy={onLinkDeploy}
            />
          ))}

          {cursor && (
            <div className="issue-load-more">
              <button className="btn btn-soft" onClick={() => void loadPage(cursor, filters)} disabled={loading}>
                {loading ? "Loading..." : "Load next 5"}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function IssueCard({
  issue,
  status,
  resolving,
  ignoring,
  acceptingRisk,
  replaying,
  triaging,
  onResolve,
  onIgnore,
  onAcceptedRisk,
  onCreateReplay,
  onAssign,
  onLinkDeploy,
}: {
  issue: IssueItem;
  status: IssueStatus;
  resolving: boolean;
  ignoring: boolean;
  acceptingRisk: boolean;
  replaying: boolean;
  triaging: boolean;
  onResolve: (event: MouseEvent, issueId: string) => void;
  onIgnore: (event: MouseEvent, issueId: string) => void;
  onAcceptedRisk: (event: MouseEvent, issueId: string) => void;
  onCreateReplay: (event: MouseEvent, issueId: string) => void;
  onAssign: (event: MouseEvent, issue: IssueItem) => void;
  onLinkDeploy: (event: MouseEvent, issue: IssueItem) => void;
}) {
  const firstTrace = issue.evidence_traces[0];
  const traceTarget = firstTrace?.trace_id ?? firstTrace?.call_id ?? issue.sample_call_id;
  const canCreateReplay = Boolean(issue.sample_call_id || issue.evidence_traces.length > 0);
  const highImpact = issue.cost_impact_usd > 1;

  return (
    <article className="panel issue-card">
      <div className="issue-card-grid">
        <div className="issue-card-main">
          <div className="issue-card-badges">
            {severityBadge(issue.severity)}
            <span className="alert-cat-badge badge-gray issue-small-badge">
              {detectorLabel(issue.failure_code)}
            </span>
            <span className="mono notif-meta issue-score">
              score {issue.priority_score.toFixed(0)}
            </span>
          </div>

          <h2 className="issue-title">
            <Link href={`/issues/${issue.id}`}>
              {issue.title}
            </Link>
          </h2>

          <div className="issue-meta-row">
            <span>
              <Bot aria-hidden="true" />
              {issue.affected_agent ?? "Agent not captured"}
            </span>
            <span>{issue.affected_workflow ?? "Workflow not captured"}</span>
            <span>{issue.occurrence_count} affected calls</span>
            <span>{formatDateTime(issue.last_seen_at)}</span>
            {issue.assigned_to && <span>assigned to {issue.assigned_to}</span>}
            {issue.deploy_pr_url && (
              <a href={issue.deploy_pr_url} target="_blank" rel="noreferrer" className="notif-action-link">
                deploy/PR linked
              </a>
            )}
          </div>

          <p className="issue-root-cause">
            <strong>Root cause:</strong> {issue.root_cause}
          </p>

          <div className="issue-evidence-grid">
            <InfoCell label="Impact" value={`${issue.user_impact} - ${formatUsd(issue.cost_impact_usd)} blast radius`} />
            <InfoCell label="Replay" value={replayLabel(issue.replay_coverage_status)} />
            <InfoCell label="Next action" value={issue.recommended_next_action} />
          </div>

          {firstTrace && (
            <div className="issue-trace-row">
              <span>evidence: {issue.evidence_traces.length} trace{issue.evidence_traces.length === 1 ? "" : "s"}</span>
              {firstTrace.prompt_version && <span>prompt {firstTrace.prompt_version}</span>}
              {firstTrace.model && <span>{firstTrace.provider ?? "provider"} / {firstTrace.model}</span>}
              {traceTarget && (
                <Link href={`/trace/${traceTarget}`} className="notif-action-link">
                  trace {traceTarget.slice(0, 18)}
                </Link>
              )}
              {issue.sample_call_id && (
                <Link href={`/calls/${issue.sample_call_id}`} className="notif-action-link">
                  sample call
                </Link>
              )}
            </div>
          )}
        </div>

        <div className="issue-action-rail">
          <div className={`issue-impact-value${highImpact ? " is-high-impact" : ""}`}>
            {formatUsd(issue.cost_impact_usd)}
            <span>cost impact</span>
          </div>
          <Link href={`/issues/${issue.id}`} className="btn btn-soft btn-sm">
            <CircleDot aria-hidden="true" />
            Open issue
          </Link>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={(event) => onCreateReplay(event, issue.id)}
            disabled={!canCreateReplay || replaying}
            title={canCreateReplay ? "Create real LLM replay from issue evidence" : "No issue evidence available for replay"}
          >
            {replaying ? <Loader2 aria-hidden="true" /> : <ArrowRight aria-hidden="true" />}
            {replaying ? "Creating..." : "Create replay"}
          </button>
          <button type="button" className="btn btn-soft btn-sm" onClick={(event) => onAssign(event, issue)} disabled={triaging}>
            <UserRoundPlus aria-hidden="true" />
            {issue.assigned_to ? "Reassign" : "Assign"}
          </button>
          <button type="button" className="btn btn-soft btn-sm" onClick={(event) => onLinkDeploy(event, issue)} disabled={triaging}>
            <GitPullRequestArrow aria-hidden="true" />
            {issue.deploy_pr_url ? "Edit Deploy/PR" : "Link Deploy/PR"}
          </button>
          <button
            type="button"
            className="btn btn-soft btn-sm"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              window.dispatchEvent(new CustomEvent("open-ask-zroky", {
                detail: {
                  context: { issue_id: issue.id },
                  prefill: `Why is this happening: ${issue.title}`,
                },
              }));
            }}
          >
            <MessageSquareText aria-hidden="true" />
            Ask Zroky
          </button>
          {status === "open" && (
            <>
              <button type="button" className="btn btn-soft btn-sm" onClick={(event) => void onAcceptedRisk(event, issue.id)} disabled={acceptingRisk}>
                <ShieldCheck aria-hidden="true" />
                {acceptingRisk ? "..." : "Accepted Risk"}
              </button>
              <button type="button" className="btn btn-soft btn-sm" onClick={(event) => void onResolve(event, issue.id)} disabled={resolving}>
                <CheckCircle2 aria-hidden="true" />
                {resolving ? "..." : "Resolve"}
              </button>
              <button type="button" className="btn btn-soft btn-sm" onClick={(event) => void onIgnore(event, issue.id)} disabled={ignoring}>
                <XCircle aria-hidden="true" />
                {ignoring ? "..." : "Ignore/Mute"}
              </button>
            </>
          )}
        </div>
      </div>
    </article>
  );
}

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="issue-info-cell">
      <div className="notif-meta">{label}</div>
      <div>{value}</div>
    </div>
  );
}

function severityBadge(severity: string) {
  return (
    <span className={`alert-cat-badge badge-${severityBadgeColor(severity)} issue-small-badge`}>
      <AlertTriangle aria-hidden="true" />
      {severity}
    </span>
  );
}
