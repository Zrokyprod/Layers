"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getIssue, ignoreIssue, resolveIssue, updateIssueTriage } from "@/lib/api";
import { useCreateReplayRunFromIssue } from "@/lib/hooks";
import { formatDateTime, formatUsd } from "@/lib/format";
import { replayLabel } from "@/lib/issue-format";
import { REPLAY_MODE_OPTIONS, replayModeProof } from "@/lib/replay-mode";
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
  const [replayMode, setReplayMode] = useState<ReplayMode>("stub");
  const createReplay = useCreateReplayRunFromIssue({
    onSuccess: (run) => router.push(`/replay/${run.id}`),
  });

  useEffect(() => {
    if (!id) return;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    getIssue(id, ctrl.signal)
      .then(setIssue)
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

  async function onAssign() {
    if (!issue) return;
    const assignee = window.prompt("Assign this issue to:", issue.assigned_to ?? "");
    if (assignee === null) return;
    setTriaging(true);
    try {
      setIssue(await updateIssueTriage(issue.id, { assigned_to: assignee.trim() || null }));
      setActionError(null);
    } catch (error: unknown) {
      setActionError((error as { message?: string }).message ?? "Failed to update issue assignment.");
    } finally {
      setTriaging(false);
    }
  }

  async function onLinkDeploy() {
    if (!issue) return;
    const link = window.prompt("Paste deploy or PR URL:", issue.deploy_pr_url ?? "");
    if (link === null) return;
    setTriaging(true);
    try {
      setIssue(await updateIssueTriage(issue.id, { deploy_pr_url: link.trim() || null }));
      setActionError(null);
    } catch (error: unknown) {
      setActionError((error as { message?: string }).message ?? "Failed to update deploy/PR link.");
    } finally {
      setTriaging(false);
    }
  }

  if (loading) return <div className="loading" />;
  if (error) {
    return (
      <div className="panel">
        <p className="notif-error">{error}</p>
        <Link href="/issues" className="btn btn-soft" style={{ marginTop: "1rem" }}>
          Back
        </Link>
      </div>
    );
  }
  if (!issue) return null;

  return (
    <div>
      <div style={{ marginBottom: "1rem", fontSize: "0.85rem" }}>
        <Link href="/issues" className="notif-action-link">Back to issues</Link>
      </div>
      {actionError && (
        <div className="panel" style={{ marginBottom: "1rem" }}>
          <p className="notif-error">{actionError}</p>
        </div>
      )}

      <section className="panel" style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center", marginBottom: "0.75rem" }}>
          {severityBadge(issue.severity)}
          <span className="alert-cat-badge badge-gray" style={{ fontSize: "0.65rem" }}>
            {detectorLabel(issue.failure_code)}
          </span>
          <span className="alert-cat-badge badge-gray" style={{ fontSize: "0.65rem" }}>
            {issue.status}
          </span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: "1.25rem", alignItems: "start" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: "1.45rem", lineHeight: 1.2 }}>{issue.title}</h1>
            <div className="notif-meta" style={{ display: "flex", gap: "0.9rem", flexWrap: "wrap", marginTop: "0.6rem" }}>
              <span>{issue.affected_agent ?? "Agent not captured"}</span>
              <span>{issue.affected_workflow ?? "Workflow not captured"}</span>
              <span>First: {formatDateTime(issue.first_seen_at)}</span>
              <span>Last: {formatDateTime(issue.last_seen_at)}</span>
              {issue.assigned_to && <span>Assigned to {issue.assigned_to}</span>}
              {issue.deploy_pr_url && <a href={issue.deploy_pr_url} target="_blank" rel="noreferrer" className="notif-action-link">Deploy/PR linked</a>}
            </div>
          </div>

          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "1.35rem", fontWeight: 700, color: issue.cost_impact_usd > 1 ? "var(--color-red)" : "inherit" }}>
              {formatUsd(issue.cost_impact_usd)}
            </div>
            <div className="notif-meta" style={{ fontSize: "0.72rem" }}>
              {issue.occurrence_count} affected calls
            </div>
          </div>
        </div>
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "0.75rem", marginBottom: "1rem" }}>
        <SummaryPanel title="Root cause" value={issue.root_cause} />
        <SummaryPanel title="User impact" value={issue.user_impact} />
        <SummaryPanel title="Replay coverage" value={replayLabel(issue.replay_coverage_status)} />
        <SummaryPanel title="Recommended next action" value={issue.recommended_next_action} />
      </section>

      <section className="panel" style={{ marginBottom: "1rem" }}>
        <header className="panel-header">
          <div>
            <h3>Evidence traces</h3>
            <p>{issue.evidence_traces.length} representative trace{issue.evidence_traces.length === 1 ? "" : "s"} behind this grouped issue.</p>
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

      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1rem", flexWrap: "wrap" }}>
        {issue.sample_call_id && (
          <Link href={`/calls/${issue.sample_call_id}`} className="btn btn-soft">
            Open sample call
          </Link>
        )}
        {(issue.evidence_traces[0]?.trace_id || issue.sample_call_id) && (
          <Link href={`/trace/${issue.evidence_traces[0]?.trace_id ?? issue.sample_call_id}`} className="btn btn-soft">
            Open trace
          </Link>
        )}
        {issue.sample_call_id && (
          <>
            <select
              value={replayMode}
              onChange={(event) => setReplayMode(event.target.value as typeof replayMode)}
              className="input"
              style={{ maxWidth: 170 }}
            >
              {REPLAY_MODE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="alert-cat-badge badge-gray" title={replayMode === "stub" ? "Stub replay is a sanity check, not a verified fix." : undefined}>
              {replayModeProof(replayMode)}
            </span>
            <button className="btn btn-primary" onClick={onCreateReplay} disabled={createReplay.isPending}>
              {createReplay.isPending ? "Creating..." : "Create Replay"}
            </button>
          </>
        )}
        <button className="btn btn-soft" onClick={() => void onAssign()} disabled={triaging}>
          {issue.assigned_to ? "Reassign" : "Assign"}
        </button>
        <button className="btn btn-soft" onClick={() => void onLinkDeploy()} disabled={triaging}>
          {issue.deploy_pr_url ? "Edit Deploy/PR" : "Link Deploy/PR"}
        </button>
        {issue.status === "open" && (
          <>
            <button className="btn btn-soft" onClick={() => void onAcceptedRisk()} disabled={acceptingRisk}>
              {acceptingRisk ? "Accepting..." : "Accepted Risk"}
            </button>
            <button className="btn btn-soft" onClick={() => void onResolve()} disabled={resolving}>
              {resolving ? "Resolving..." : "Resolve"}
            </button>
            <button className="btn btn-soft" onClick={() => void onIgnore()} disabled={ignoring}>
              {ignoring ? "Muting..." : "Ignore/Mute"}
            </button>
          </>
        )}
      </div>

      <section className="panel">
        <header className="panel-header">
          <h3>Issue metadata</h3>
        </header>
        <table style={{ width: "100%", fontSize: "0.85rem", borderCollapse: "collapse" }}>
          <tbody>
            {[
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
              ["Deploy/PR", issue.deploy_pr_url ?? "-"],
            ].map(([label, value]) => (
              <tr key={label} style={{ borderBottom: "1px solid var(--color-border)" }}>
                <td style={{ padding: "0.4rem 0.75rem", color: "var(--color-muted)", whiteSpace: "nowrap" }}>{label}</td>
                <td style={{ padding: "0.4rem 0.75rem" }} className="mono">{value}</td>
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
    <div className="panel">
      <div className="notif-meta" style={{ fontSize: "0.72rem", marginBottom: "0.4rem" }}>{title}</div>
      <div style={{ fontSize: "0.9rem", lineHeight: 1.45 }}>{value}</div>
    </div>
  );
}

function EvidenceTraceRow({ trace }: { trace: IssueEvidenceTrace }) {
  const traceId = trace.trace_id ?? trace.call_id;
  return (
    <div className="notif-row">
      <div className="notif-body">
        <div className="notif-title-row">
          <span className="mono" style={{ fontSize: "0.78rem" }}>{traceId ?? "trace unavailable"}</span>
          {trace.status && (
            <span className="alert-cat-badge badge-gray" style={{ fontSize: "0.65rem" }}>{trace.status}</span>
          )}
          <span className="notif-meta" style={{ marginLeft: "auto" }}>{formatDateTime(trace.created_at)}</span>
        </div>
        <div className="notif-meta" style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginTop: "0.3rem" }}>
          {trace.workflow_name && <span>{trace.workflow_name}</span>}
          {trace.prompt_version && <span>prompt {trace.prompt_version}</span>}
          {trace.model && <span>{trace.provider ?? "provider"} / {trace.model}</span>}
          {trace.latency_ms != null && <span>{Math.round(trace.latency_ms)} ms</span>}
          <span>{formatUsd(trace.cost_usd)}</span>
        </div>
        {trace.evidence_summary && (
          <p style={{ margin: "0.45rem 0 0", fontSize: "0.85rem" }}>{trace.evidence_summary}</p>
        )}
      </div>
      <div className="notif-actions">
        {trace.call_id && (
          <Link href={`/calls/${trace.call_id}`} className="btn btn-soft btn-sm">Call</Link>
        )}
        {traceId && (
          <Link href={`/trace/${traceId}`} className="btn btn-soft btn-sm">Trace</Link>
        )}
      </div>
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
