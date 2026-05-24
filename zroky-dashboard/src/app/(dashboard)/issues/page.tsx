"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ignoreIssue, listIssues, resolveIssue } from "@/lib/api";
import { formatDateTime, formatUsd } from "@/lib/format";
import { replayLabel } from "@/lib/issue-format";
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
    <div>
      <header style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "flex-end", flexWrap: "wrap" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: "1.35rem" }}>Issues</h1>
            <p className="notif-meta" style={{ marginTop: "0.35rem" }}>
              Top grouped production problems, not raw traces.
            </p>
          </div>
          <div className="mono notif-meta" style={{ fontSize: "0.75rem" }}>
            default view: top 5
          </div>
        </div>
      </header>

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
    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", padding: "0.75rem 0" }}>
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

function IssueList({ status }: { status: IssueStatus }) {
  const router = useRouter();
  const [items, setItems] = useState<IssueItem[]>([]);
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [ignoringId, setIgnoringId] = useState<string | null>(null);
  const [acceptingRiskId, setAcceptingRiskId] = useState<string | null>(null);
  const [replayingId, setReplayingId] = useState<string | null>(null);
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [deployLinks, setDeployLinks] = useState<Record<string, string>>({});
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
      { issueId, payload: { replay_mode: "stub" } },
      { onSettled: () => setReplayingId(null) },
    );
  }

  function onAssign(event: MouseEvent, issueId: string) {
    event.preventDefault();
    event.stopPropagation();
    const assignee = window.prompt("Assign this issue to:", assignments[issueId] ?? "");
    if (assignee === null) return;
    const trimmed = assignee.trim();
    setAssignments((prev) => {
      const next = { ...prev };
      if (trimmed) next[issueId] = trimmed;
      else delete next[issueId];
      return next;
    });
  }

  function onLinkDeploy(event: MouseEvent, issueId: string) {
    event.preventDefault();
    event.stopPropagation();
    const link = window.prompt("Paste deploy or PR URL:", deployLinks[issueId] ?? "");
    if (link === null) return;
    const trimmed = link.trim();
    setDeployLinks((prev) => {
      const next = { ...prev };
      if (trimmed) next[issueId] = trimmed;
      else delete next[issueId];
      return next;
    });
  }

  return (
    <section>
      <FilterBar filters={filters} onChange={applyFilters} />

      {loading && items.length === 0 ? (
        <div className="loading" />
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
        <div style={{ display: "grid", gap: "0.75rem" }}>
          {items.map((issue) => (
            <IssueCard
              key={issue.id}
              issue={issue}
              status={status}
              resolving={resolvingId === issue.id}
              ignoring={ignoringId === issue.id}
              acceptingRisk={acceptingRiskId === issue.id}
              replaying={replayingId === issue.id}
              assignment={assignments[issue.id]}
              deployLink={deployLinks[issue.id]}
              onResolve={onResolve}
              onIgnore={onIgnore}
              onAcceptedRisk={onAcceptedRisk}
              onCreateReplay={onCreateReplay}
              onAssign={onAssign}
              onLinkDeploy={onLinkDeploy}
            />
          ))}

          {cursor && (
            <div style={{ textAlign: "center", padding: "0.5rem" }}>
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
  assignment,
  deployLink,
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
  assignment?: string;
  deployLink?: string;
  onResolve: (event: MouseEvent, issueId: string) => void;
  onIgnore: (event: MouseEvent, issueId: string) => void;
  onAcceptedRisk: (event: MouseEvent, issueId: string) => void;
  onCreateReplay: (event: MouseEvent, issueId: string) => void;
  onAssign: (event: MouseEvent, issueId: string) => void;
  onLinkDeploy: (event: MouseEvent, issueId: string) => void;
}) {
  const firstTrace = issue.evidence_traces[0];
  const traceTarget = firstTrace?.trace_id ?? firstTrace?.call_id ?? issue.sample_call_id;
  const canCreateReplay = Boolean(issue.sample_call_id || issue.evidence_traces.length > 0);

  return (
    <article className="panel">
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: "1rem", alignItems: "start" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap", marginBottom: "0.55rem" }}>
            {severityBadge(issue.severity)}
            <span className="alert-cat-badge badge-gray" style={{ fontSize: "0.65rem" }}>
              {detectorLabel(issue.failure_code)}
            </span>
            <span className="mono notif-meta" style={{ fontSize: "0.72rem" }}>
              score {issue.priority_score.toFixed(0)}
            </span>
          </div>

          <h2 style={{ margin: 0, fontSize: "1.05rem", lineHeight: 1.25 }}>
            <Link href={`/issues/${issue.id}`} style={{ color: "inherit", textDecoration: "none" }}>
              {issue.title}
            </Link>
          </h2>

          <div className="notif-meta" style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginTop: "0.45rem" }}>
            <span>{issue.affected_agent ?? "Agent not captured"}</span>
            <span>{issue.affected_workflow ?? "Workflow not captured"}</span>
            <span>{issue.occurrence_count} affected calls</span>
            <span>{formatDateTime(issue.last_seen_at)}</span>
            {assignment && <span>assigned to {assignment}</span>}
            {deployLink && <a href={deployLink} target="_blank" rel="noreferrer" className="notif-action-link">deploy/PR linked</a>}
          </div>

          <p style={{ margin: "0.75rem 0 0", fontSize: "0.9rem", lineHeight: 1.45 }}>
            <strong>Root cause:</strong> {issue.root_cause}
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.65rem", marginTop: "0.85rem" }}>
            <InfoCell label="Impact" value={`${issue.user_impact} · ${formatUsd(issue.cost_impact_usd)} blast radius`} />
            <InfoCell label="Replay" value={replayLabel(issue.replay_coverage_status)} />
            <InfoCell label="Next action" value={issue.recommended_next_action} />
          </div>

          {firstTrace && (
            <div className="mono notif-meta" style={{ marginTop: "0.85rem", fontSize: "0.72rem", display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
              <span>evidence: {issue.evidence_traces.length} trace{issue.evidence_traces.length === 1 ? "" : "s"}</span>
              {firstTrace.prompt_version && <span>prompt {firstTrace.prompt_version}</span>}
              {firstTrace.model && <span>{firstTrace.provider ?? "provider"} / {firstTrace.model}</span>}
              {traceTarget && <Link href={`/trace/${traceTarget}`} className="notif-action-link">trace {traceTarget.slice(0, 18)}</Link>}
              {issue.sample_call_id && <Link href={`/calls/${issue.sample_call_id}`} className="notif-action-link">sample call</Link>}
            </div>
          )}
        </div>

        <div style={{ display: "grid", gap: "0.45rem", minWidth: "132px", justifyItems: "stretch" }}>
          <div style={{ textAlign: "right", fontWeight: 700, color: issue.cost_impact_usd > 1 ? "var(--color-red)" : "inherit" }}>
            {formatUsd(issue.cost_impact_usd)}
          </div>
          <Link href={`/issues/${issue.id}`} className="btn btn-soft btn-sm">
            Open issue
          </Link>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={(event) => onCreateReplay(event, issue.id)}
            disabled={!canCreateReplay || replaying}
            title={canCreateReplay ? "Create replay from issue evidence" : "No issue evidence available for replay"}
          >
            {replaying ? "Creating..." : "Create Replay"}
          </button>
          <button type="button" className="btn btn-soft btn-sm" onClick={(event) => onAssign(event, issue.id)}>
            {assignment ? "Reassign" : "Assign"}
          </button>
          <button type="button" className="btn btn-soft btn-sm" onClick={(event) => onLinkDeploy(event, issue.id)}>
            {deployLink ? "Edit Deploy/PR" : "Link Deploy/PR"}
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
            Ask Zroky
          </button>
          {status === "open" && (
            <>
              <button type="button" className="btn btn-soft btn-sm" onClick={(event) => void onAcceptedRisk(event, issue.id)} disabled={acceptingRisk}>
                {acceptingRisk ? "..." : "Accepted Risk"}
              </button>
              <button type="button" className="btn btn-soft btn-sm" onClick={(event) => void onResolve(event, issue.id)} disabled={resolving}>
                {resolving ? "..." : "Resolve"}
              </button>
              <button type="button" className="btn btn-soft btn-sm" onClick={(event) => void onIgnore(event, issue.id)} disabled={ignoring}>
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
    <div style={{ borderTop: "1px solid var(--color-border)", paddingTop: "0.55rem" }}>
      <div className="notif-meta" style={{ fontSize: "0.68rem", marginBottom: "0.25rem" }}>{label}</div>
      <div style={{ fontSize: "0.82rem", lineHeight: 1.35 }}>{value}</div>
    </div>
  );
}

function severityBadge(severity: string) {
  return (
    <span className={`alert-cat-badge badge-${severityBadgeColor(severity)}`} style={{ fontSize: "0.65rem", padding: "1px 6px" }}>
      {severity}
    </span>
  );
}
