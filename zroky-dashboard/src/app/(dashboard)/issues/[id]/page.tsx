"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Archive,
  CheckCircle2,
  ExternalLink,
  Link2,
  Play,
  Save,
  ShieldAlert,
} from "lucide-react";

import { getIssue, ignoreIssue, resolveIssue, updateIssueTriage } from "@/lib/api";
import { useCreateReplayRunFromIssue } from "@/lib/hooks";
import { formatDateTime, formatUsd } from "@/lib/format";
import { replayLabel } from "@/lib/issue-format";
import { DEFAULT_VERIFICATION_REPLAY_MODE, REPLAY_MODE_OPTIONS, STUB_REPLAY_MODE, replayModeProof } from "@/lib/replay-mode";
import type { ReplayMode } from "@/lib/api";
import type { IssueEvidenceTrace, IssueItem } from "@/lib/types";
import { detectorLabel, severityBadgeColor } from "@/lib/detector-meta";

export default function IssueDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [issue, setIssue] = useState<IssueItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);
  const [ignoring, setIgnoring] = useState(false);
  const [acceptingRisk, setAcceptingRisk] = useState(false);
  const [triaging, setTriaging] = useState(false);
  const [assigneeDraft, setAssigneeDraft] = useState("");
  const [deployDraft, setDeployDraft] = useState("");
  const [replayMode, setReplayMode] = useState<ReplayMode>(DEFAULT_VERIFICATION_REPLAY_MODE);
  const createReplay = useCreateReplayRunFromIssue({
    onSuccess: (run) => router.push(`/replay/${run.id}`),
  });

  useEffect(() => {
    if (!id) return;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    getIssue(id, ctrl.signal)
      .then((loaded) => {
        setIssue(loaded);
        setAssigneeDraft(loaded.assigned_to ?? "");
        setDeployDraft(loaded.deploy_pr_url ?? "");
      })
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        setError((error as { message?: string }).message ?? "Failed to load issue.");
      })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [id]);

  async function onResolve() {
    if (!issue) return;
    setResolving(true);
    try {
      await resolveIssue(issue.id, { resolution_source: "manual" });
      router.push("/issues");
    } finally {
      setResolving(false);
    }
  }

  async function onAcceptedRisk() {
    if (!issue) return;
    setAcceptingRisk(true);
    try {
      await resolveIssue(issue.id, { resolution_source: "accepted_risk" });
      router.push("/issues?tab=resolved");
    } finally {
      setAcceptingRisk(false);
    }
  }

  async function onIgnore() {
    if (!issue) return;
    setIgnoring(true);
    try {
      await ignoreIssue(issue.id);
      router.push("/issues?tab=ignored");
    } finally {
      setIgnoring(false);
    }
  }

  function onCreateReplay() {
    if (!issue) return;
    createReplay.mutate({ issueId: issue.id, payload: { replay_mode: replayMode } });
  }

  async function onSaveTriage() {
    if (!issue) return;
    setTriaging(true);
    try {
      const updated = await updateIssueTriage(issue.id, {
        assigned_to: assigneeDraft.trim() || null,
        deploy_pr_url: deployDraft.trim() || null,
      });
      setIssue(updated);
      setAssigneeDraft(updated.assigned_to ?? "");
      setDeployDraft(updated.deploy_pr_url ?? "");
      setActionError(null);
    } catch (error: unknown) {
      setActionError((error as { message?: string }).message ?? "Failed to update issue triage.");
    } finally {
      setTriaging(false);
    }
  }

  if (loading) return <div className="loading" />;
  if (error) {
    return (
      <div className="detail-page">
        <section className="panel">
          <p className="notif-error">{error}</p>
          <Link href="/issues" className="btn btn-soft">
            <ArrowLeft aria-hidden="true" />
            Back
          </Link>
        </section>
      </div>
    );
  }
  if (!issue) return null;

  const firstTraceId = issue.evidence_traces[0]?.trace_id ?? issue.sample_call_id ?? null;
  const metadataRows: [string, ReactNode][] = [
    ["Issue ID", issue.id],
    ["Project", issue.project_id],
    ["Failure code", issue.failure_code],
    ["Severity", issue.severity],
    ["Status", issue.status],
    ["Occurrences", String(issue.occurrence_count)],
    ["Cost impact", formatUsd(issue.cost_impact_usd)],
    ["Replay coverage", issue.replay_coverage_status],
    ["Prompt fingerprint", issue.prompt_fingerprint ?? "-"],
    ["Sample call", issue.sample_call_id ?? "-"],
    ["Sample diagnosis", issue.sample_diagnosis_id ?? "-"],
    ["Last fix", issue.last_fix_id ?? "-"],
    ["Resolution source", issue.resolution_source ?? "-"],
    ["Assigned to", issue.assigned_to ?? "-"],
    [
      "Deploy/PR",
      issue.deploy_pr_url ? (
        <a href={issue.deploy_pr_url} target="_blank" rel="noreferrer" className="notif-action-link">
          <Link2 aria-hidden="true" />
          {issue.deploy_pr_url}
        </a>
      ) : "-",
    ],
  ];

  return (
    <div className="detail-page issue-detail-page">
      <Link href="/issues" className="detail-back-link">
        <ArrowLeft aria-hidden="true" />
        Back to issues
      </Link>

      {actionError && (
        <section className="panel">
          <p className="notif-error">{actionError}</p>
        </section>
      )}

      <section className="panel detail-hero">
        <div className="detail-hero-main">
          <div className="detail-badge-row">
            {severityBadge(issue.severity)}
            <span className="alert-cat-badge badge-gray">{detectorLabel(issue.failure_code)}</span>
            <span className="alert-cat-badge badge-gray">{issue.status}</span>
          </div>
          <h1>{issue.title}</h1>
          <div className="detail-meta-row">
            <span>{issue.affected_agent ?? "Agent not captured"}</span>
            <span>{issue.affected_workflow ?? "Workflow not captured"}</span>
            <span>First {formatDateTime(issue.first_seen_at)}</span>
            <span>Last {formatDateTime(issue.last_seen_at)}</span>
            {issue.assigned_to && <span>Assigned to {issue.assigned_to}</span>}
            {issue.deploy_pr_url && (
              <a href={issue.deploy_pr_url} target="_blank" rel="noreferrer" className="notif-action-link">
                <ExternalLink aria-hidden="true" />
                Deploy/PR linked
              </a>
            )}
          </div>
        </div>

        <aside className="detail-hero-side">
          <div className={`detail-impact-value${issue.cost_impact_usd > 1 ? " is-danger" : ""}`}>
            {formatUsd(issue.cost_impact_usd)}
          </div>
          <span className="notif-meta">{issue.occurrence_count} affected calls</span>
        </aside>
      </section>

      <section className="detail-section-grid">
        <SummaryPanel title="Root cause" value={issue.root_cause} />
        <SummaryPanel title="User impact" value={issue.user_impact} />
        <SummaryPanel title="Replay coverage" value={replayLabel(issue.replay_coverage_status)} />
        <SummaryPanel title="Recommended next action" value={issue.recommended_next_action} />
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Triage</h3>
            <p>Persist ownership and deploy context directly on the issue.</p>
          </div>
        </header>
        <div className="detail-form-grid">
          <label className="detail-field">
            <span className="detail-field-label">Assigned to</span>
            <input
              className="input"
              value={assigneeDraft}
              onChange={(event) => setAssigneeDraft(event.target.value)}
              placeholder="team member or channel"
            />
          </label>
          <label className="detail-field">
            <span className="detail-field-label">Deploy or PR URL</span>
            <input
              className="input"
              value={deployDraft}
              onChange={(event) => setDeployDraft(event.target.value)}
              placeholder="https://github.com/acme/repo/pull/42"
            />
          </label>
          <button className="btn btn-primary" type="button" onClick={() => void onSaveTriage()} disabled={triaging}>
            <Save aria-hidden="true" />
            {triaging ? "Saving..." : "Save triage"}
          </button>
        </div>
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Evidence traces</h3>
            <p>
              {issue.evidence_traces.length} representative trace{issue.evidence_traces.length === 1 ? "" : "s"} behind this grouped issue.
            </p>
          </div>
        </header>

        {issue.evidence_traces.length === 0 ? (
          <div className="empty">No evidence trace captured for this issue.</div>
        ) : (
          <div className="list">
            {issue.evidence_traces.map((trace, index) => (
              <EvidenceTraceRow key={`${trace.call_id ?? trace.trace_id ?? index}-${index}`} trace={trace} />
            ))}
          </div>
        )}
      </section>

      <section className="detail-action-bar">
        <div className="detail-action-group">
          {issue.sample_call_id && (
            <Link href={`/calls/${issue.sample_call_id}`} className="btn btn-soft">
              Open sample call
            </Link>
          )}
          {firstTraceId && (
            <Link href={`/trace/${firstTraceId}`} className="btn btn-soft">
              Open trace
            </Link>
          )}
          {issue.sample_call_id && (
            <>
              <select
                value={replayMode}
                onChange={(event) => setReplayMode(event.target.value as ReplayMode)}
                className="input detail-mode-select"
              >
                {REPLAY_MODE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <span
                className="alert-cat-badge badge-gray"
                title={replayMode === STUB_REPLAY_MODE ? "Stub replay is a sanity check, not a verified fix." : undefined}
              >
                {replayModeProof(replayMode)}
              </span>
              <button className="btn btn-primary" type="button" onClick={onCreateReplay} disabled={createReplay.isPending}>
                <Play aria-hidden="true" />
                {createReplay.isPending ? "Creating..." : "Create replay"}
              </button>
            </>
          )}
        </div>
        {issue.status === "open" && (
          <div className="detail-action-group detail-action-split">
            <button className="btn btn-soft" type="button" onClick={() => void onAcceptedRisk()} disabled={acceptingRisk}>
              <ShieldAlert aria-hidden="true" />
              {acceptingRisk ? "Accepting..." : "Accepted risk"}
            </button>
            <button className="btn btn-soft" type="button" onClick={() => void onResolve()} disabled={resolving}>
              <CheckCircle2 aria-hidden="true" />
              {resolving ? "Resolving..." : "Resolve"}
            </button>
            <button className="btn btn-soft" type="button" onClick={() => void onIgnore()} disabled={ignoring}>
              <Archive aria-hidden="true" />
              {ignoring ? "Muting..." : "Ignore/mute"}
            </button>
          </div>
        )}
      </section>

      <section className="panel">
        <header className="panel-header">
          <h3>Issue metadata</h3>
        </header>
        <table className="detail-table">
          <tbody>
            {metadataRows.map(([label, value]) => (
              <tr key={label}>
                <td>{label}</td>
                <td className="mono">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function SummaryPanel({ title, value }: { title: string; value: string }) {
  return (
    <article className="detail-summary-card">
      <span>{title}</span>
      <p>{value}</p>
    </article>
  );
}

function EvidenceTraceRow({ trace }: { trace: IssueEvidenceTrace }) {
  const traceId = trace.trace_id ?? trace.call_id;
  return (
    <div className="list-row">
      <div className="list-main">
        <div className="detail-badge-row">
          <span className="mono">{traceId ?? "trace unavailable"}</span>
          {trace.status && <span className="alert-cat-badge badge-gray">{trace.status}</span>}
          <span className="notif-meta">{formatDateTime(trace.created_at)}</span>
        </div>
        <div className="detail-meta-row">
          {trace.workflow_name && <span>{trace.workflow_name}</span>}
          {trace.prompt_version && <span>prompt {trace.prompt_version}</span>}
          {trace.model && <span>{trace.provider ?? "provider"} / {trace.model}</span>}
          {trace.latency_ms != null && <span>{Math.round(trace.latency_ms)} ms</span>}
          <span>{formatUsd(trace.cost_usd)}</span>
        </div>
        {trace.evidence_summary && <p className="issue-root-cause">{trace.evidence_summary}</p>}
      </div>
      <div className="notif-actions">
        {trace.call_id && (
          <Link href={`/calls/${trace.call_id}`} className="btn btn-soft btn-sm">
            Call
          </Link>
        )}
        {traceId && (
          <Link href={`/trace/${traceId}`} className="btn btn-soft btn-sm">
            Trace
          </Link>
        )}
      </div>
    </div>
  );
}

function severityBadge(severity: string) {
  return (
    <span className={`alert-cat-badge badge-${severityBadgeColor(severity)}`}>
      {severity}
    </span>
  );
}
