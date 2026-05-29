"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Archive,
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  GitPullRequest,
  LockKeyhole,
  RotateCcw,
  Save,
  ShieldCheck,
} from "lucide-react";

import { hasPlanEntitlement } from "@/components/feature-gate";
import {
  createReplayRunFromCall,
  createReplayRunFromIssue,
  getBillingMe,
  getIssue,
  ignoreIssue,
  resolveIssue,
  updateIssueTriage,
} from "@/lib/api";
import { detectorLabel, severityBadgeColor } from "@/lib/detector-meta";
import { formatCount, formatDateTime, formatUsd } from "@/lib/format";
import { replayLabel } from "@/lib/issue-format";
import { DEFAULT_VERIFICATION_REPLAY_MODE } from "@/lib/replay-mode";
import type { BillingMeResponse, IssueEvidenceTrace, IssueItem } from "@/lib/types";

type ActionState = "issue_replay" | "call_replay" | "resolve" | "ignore" | "triage" | null;

function normalizedReplayStatus(issue: IssueItem): string {
  return issue.replay_coverage_status?.trim().toLowerCase() || "unknown";
}

function hasVerifiedFix(issue: IssueItem): boolean {
  return normalizedReplayStatus(issue) === "verified_fix";
}

function isUntrustedReplay(issue: IssueItem): boolean {
  return !hasVerifiedFix(issue);
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

function issueEnvironment(): string {
  const env = process.env.NEXT_PUBLIC_DASHBOARD_ENV ?? "production";
  return env.charAt(0).toUpperCase() + env.slice(1);
}

function titleCase(value: string): string {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : "Unknown";
}

function sortedEvidence(traces: IssueEvidenceTrace[]): IssueEvidenceTrace[] {
  return [...traces].sort((a, b) => {
    const aTime = a.created_at ? Date.parse(a.created_at) : 0;
    const bTime = b.created_at ? Date.parse(b.created_at) : 0;
    return aTime - bTime;
  });
}

function averageFailedCallCost(issue: IssueItem): string {
  const impact = issueImpactUsd(issue);
  if (!impact || issue.occurrence_count <= 0) return "\u2014";
  return formatUsd(impact / issue.occurrence_count);
}

function traceTarget(trace: IssueEvidenceTrace): string | null {
  return trace.trace_id ?? trace.call_id;
}

function severityBadge(issue: IssueItem) {
  return (
    <span className={`alert-cat-badge badge-${severityBadgeColor(issue.severity)} im-severity-badge`}>
      {issue.severity}
    </span>
  );
}

function DetailMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="imd-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function IssueDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [issue, setIssue] = useState<IssueItem | null>(null);
  const [billing, setBilling] = useState<BillingMeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<ActionState>(null);
  const [assigneeDraft, setAssigneeDraft] = useState("");
  const [deployDraft, setDeployDraft] = useState("");

  useEffect(() => {
    if (!id) return;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    Promise.allSettled([getIssue(id, ctrl.signal), getBillingMe(ctrl.signal)])
      .then(([issueResult, billingResult]) => {
        if (issueResult.status === "rejected") throw issueResult.reason;
        const loadedIssue = issueResult.value;
        setIssue(loadedIssue);
        setBilling(billingResult.status === "fulfilled" ? billingResult.value : null);
        setAssigneeDraft(loadedIssue.assigned_to ?? "");
        setDeployDraft(loadedIssue.deploy_pr_url ?? "");
      })
      .catch((loadError) => {
        if ((loadError as { name?: string }).name === "AbortError") return;
        setError(loadError instanceof Error ? loadError.message : "Failed to load issue.");
      })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [id]);

  const planTemplate = billing?.plan_template;
  const canReplay = hasPlanEntitlement(planTemplate, "pilot.replay_stub");
  const canGoldens = hasPlanEntitlement(planTemplate, "pilot.goldens_basic");
  const orderedEvidence = useMemo(
    () => (issue ? sortedEvidence(issue.evidence_traces) : []),
    [issue],
  );

  async function onReplayIssue() {
    if (!issue) return;
    setActionError(null);
    setBusyAction("issue_replay");
    try {
      const run = await createReplayRunFromIssue(issue.id, {
        replay_mode: DEFAULT_VERIFICATION_REPLAY_MODE,
      });
      router.push(`/replay/${run.id}`);
    } catch (replayError) {
      setActionError(replayError instanceof Error ? replayError.message : "Failed to create replay.");
    } finally {
      setBusyAction(null);
    }
  }

  async function onReplayCall(callId: string) {
    setActionError(null);
    setBusyAction("call_replay");
    try {
      const run = await createReplayRunFromCall(callId, {
        replay_mode: DEFAULT_VERIFICATION_REPLAY_MODE,
      });
      router.push(`/replay/${run.id}`);
    } catch (replayError) {
      setActionError(replayError instanceof Error ? replayError.message : "Failed to create call replay.");
    } finally {
      setBusyAction(null);
    }
  }

  async function onResolve() {
    if (!issue) return;
    setActionError(null);
    setBusyAction("resolve");
    try {
      await resolveIssue(issue.id, { resolution_source: "manual" });
      router.push("/issues");
    } catch (resolveError) {
      setActionError(resolveError instanceof Error ? resolveError.message : "Failed to resolve issue.");
    } finally {
      setBusyAction(null);
    }
  }

  async function onIgnore() {
    if (!issue) return;
    setActionError(null);
    setBusyAction("ignore");
    try {
      await ignoreIssue(issue.id);
      router.push("/issues");
    } catch (ignoreError) {
      setActionError(ignoreError instanceof Error ? ignoreError.message : "Failed to ignore issue.");
    } finally {
      setBusyAction(null);
    }
  }

  async function onSaveTriage() {
    if (!issue) return;
    setActionError(null);
    setBusyAction("triage");
    try {
      const updated = await updateIssueTriage(issue.id, {
        assigned_to: assigneeDraft.trim() || null,
        deploy_pr_url: deployDraft.trim() || null,
      });
      setIssue(updated);
      setAssigneeDraft(updated.assigned_to ?? "");
      setDeployDraft(updated.deploy_pr_url ?? "");
    } catch (triageError) {
      setActionError(triageError instanceof Error ? triageError.message : "Failed to update issue triage.");
    } finally {
      setBusyAction(null);
    }
  }

  if (loading) return <div className="imd-loading" aria-label="Loading issue" />;

  if (error) {
    return (
      <div className="issue-detail-mvp">
        <section className="imd-notice imd-notice-error">
          <p>{error}</p>
          <Link href="/issues" className="btn btn-soft btn-sm im-btn-secondary">
            <ArrowLeft aria-hidden="true" />
            Back to issues
          </Link>
        </section>
      </div>
    );
  }

  if (!issue) return null;

  const verifiedFix = hasVerifiedFix(issue);
  const goldenEligible = verifiedFix && Boolean(issue.sample_call_id);
  const canCreateGolden = goldenEligible && canGoldens;
  const rootCause = issue.root_cause?.trim() || "No structured root cause available yet.";

  function renderPrimaryAction() {
    if (canCreateGolden && issue?.sample_call_id) {
      return (
        <Link href={`/goldens?call_id=${encodeURIComponent(issue.sample_call_id)}`} className="btn btn-primary btn-sm im-btn-primary">
          <ShieldCheck aria-hidden="true" />
          Create Golden
        </Link>
      );
    }
    if (goldenEligible && !canGoldens) {
      return (
        <Link href="/settings/billing" className="btn btn-soft btn-sm im-btn-secondary">
          <LockKeyhole aria-hidden="true" />
          Upgrade for Goldens
        </Link>
      );
    }
    if (isUntrustedReplay(issue)) {
      if (!canReplay) {
        return (
          <Link href="/settings/billing" className="btn btn-soft btn-sm im-btn-secondary">
            <LockKeyhole aria-hidden="true" />
            Upgrade for replay
          </Link>
        );
      }
      return (
        <button
          type="button"
          className="btn btn-primary btn-sm im-btn-primary"
          onClick={() => void onReplayIssue()}
          disabled={!issue.sample_call_id || busyAction === "issue_replay"}
          title={issue.sample_call_id ? "Run trusted replay" : "Trusted replay needs a sample call."}
        >
          <RotateCcw aria-hidden="true" />
          {busyAction === "issue_replay" ? "Creating..." : "Run trusted replay"}
        </button>
      );
    }
    return (
      <Link href="/issues" className="btn btn-soft btn-sm im-btn-secondary">
        Back to queue
      </Link>
    );
  }

  return (
    <div className="issue-detail-mvp">
      <Link href="/issues" className="imd-back-link">
        <ArrowLeft aria-hidden="true" />
        Back to issues
      </Link>

      {actionError ? (
        <section className="imd-notice imd-notice-error">
          <p>{actionError}</p>
        </section>
      ) : null}

      <section className="imd-hero" aria-label="Issue detail header">
        <div className="imd-hero-top">
          <div>
            <div className="imd-badge-row">
              {severityBadge(issue)}
              <span className="im-status-pill">{replayLabel(issue.replay_coverage_status)}</span>
              <span className="im-status-pill">{issue.status}</span>
            </div>
            <h1>{issue.title}</h1>
            <p>
              {detectorLabel(issue.failure_code)} &middot; {issueAgent(issue)} &middot; {issueEnvironment()}
            </p>
          </div>
        </div>
        <div className="imd-meta-strip" aria-label="Issue metadata">
          <DetailMetric label="Occurrences" value={formatCount(issue.occurrence_count)} />
          <DetailMetric label="Impact" value={formatIssueImpact(issue)} />
          <DetailMetric label="First seen" value={formatDateTime(issue.first_seen_at)} />
          <DetailMetric label="Last seen" value={formatDateTime(issue.last_seen_at)} />
          <DetailMetric label="Sample call" value={issue.sample_call_id ?? "Not captured"} />
        </div>
      </section>

      <section className="imd-layout">
        <main className="imd-main">
          <section className="imd-card">
            <header className="imd-section-header">
              <h2>Root cause</h2>
            </header>
            <p>{rootCause}</p>
            {issue.recommended_next_action ? (
              <div className="imd-recommendation">
                <span>Recommended next step</span>
                <strong>{issue.recommended_next_action}</strong>
              </div>
            ) : null}
            {isUntrustedReplay(issue) ? <p className="imd-muted">No trusted replay proof exists yet.</p> : null}
          </section>

          <section className="imd-card">
            <header className="imd-section-header">
              <h2>Evidence timeline</h2>
              <span>{formatCount(orderedEvidence.length)} traces</span>
            </header>
            {orderedEvidence.length === 0 ? (
              <div className="imd-empty">No structured evidence yet.</div>
            ) : (
              <ol className="imd-timeline">
                {orderedEvidence.map((trace, index) => (
                  <li key={`${trace.call_id ?? trace.trace_id ?? index}-${index}`}>
                    <strong>{trace.evidence_summary ?? trace.workflow_name ?? `Evidence ${index + 1}`}</strong>
                    <span>
                      {trace.status ?? "status unknown"} - {trace.provider ?? "provider unknown"} / {trace.model ?? "model unknown"} -{" "}
                      {trace.created_at ? formatDateTime(trace.created_at) : "time unknown"}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section className="imd-card">
            <header className="imd-section-header">
              <h2>Sample traces</h2>
            </header>
            <div className="imd-trace-list">
              {issue.sample_call_id ? (
                <div className="imd-trace-row">
                  <div>
                    <strong>{issue.sample_call_id}</strong>
                    <span>Representative sample call</span>
                  </div>
                  <div className="imd-row-actions">
                    <Link href={`/calls/${issue.sample_call_id}`} className="btn btn-soft btn-sm im-btn-secondary">
                      View call
                    </Link>
                    {canReplay ? (
                      <button
                        type="button"
                        className="btn btn-soft btn-sm im-btn-secondary"
                        onClick={() => void onReplayCall(issue.sample_call_id!)}
                        disabled={busyAction === "call_replay"}
                      >
                        <RotateCcw aria-hidden="true" />
                        {busyAction === "call_replay" ? "Creating..." : "Replay this call"}
                      </button>
                    ) : null}
                  </div>
                </div>
              ) : null}
              {orderedEvidence.slice(0, 5).map((trace, index) => {
                const target = traceTarget(trace);
                return (
                  <div className="imd-trace-row" key={`${target ?? index}-sample`}>
                    <div>
                      <strong>{target ?? "Trace unavailable"}</strong>
                      <span>
                        {trace.workflow_name ?? "Workflow not captured"} - {trace.status ?? "status unknown"} -{" "}
                        {trace.latency_ms != null ? `${Math.round(trace.latency_ms)} ms` : "latency unknown"}
                      </span>
                    </div>
                    <div className="imd-row-actions">
                      {target ? (
                        <Link href={`/trace/${target}`} className="btn btn-soft btn-sm im-btn-secondary">
                          View trace
                        </Link>
                      ) : null}
                      {trace.call_id && trace.call_id !== issue.sample_call_id && canReplay ? (
                        <button
                          type="button"
                          className="btn btn-soft btn-sm im-btn-secondary"
                          onClick={() => void onReplayCall(trace.call_id!)}
                          disabled={busyAction === "call_replay"}
                        >
                          Replay this call
                        </button>
                      ) : null}
                    </div>
                  </div>
                );
              })}
              {!issue.sample_call_id && orderedEvidence.length === 0 ? (
                <div className="imd-empty">No sample trace captured.</div>
              ) : null}
            </div>
          </section>

          <section className="imd-card">
            <header className="imd-section-header">
              <h2>Replay proof</h2>
            </header>
            <div className="imd-proof-row">
              <strong>{replayLabel(issue.replay_coverage_status)}</strong>
              {isUntrustedReplay(issue) ? (
                <p>This state is not trusted enough to create a Golden or block CI. Run trusted replay first.</p>
              ) : (
                <p>Verified fix evidence is available for this issue.</p>
              )}
            </div>
          </section>

          <section className="imd-card">
            <header className="imd-section-header">
              <h2>Golden status</h2>
            </header>
            {goldenEligible && issue.sample_call_id ? (
              <div className="imd-proof-row">
                <strong>Eligible</strong>
                <p>This issue has a verified replay fix and a sample call.</p>
                {canCreateGolden ? (
                  <Link href={`/goldens?call_id=${encodeURIComponent(issue.sample_call_id)}`} className="btn btn-soft btn-sm im-btn-secondary">
                    <ShieldCheck aria-hidden="true" />
                    Create Golden
                  </Link>
                ) : (
                  <Link href="/settings/billing" className="btn btn-soft btn-sm im-btn-secondary">
                    <LockKeyhole aria-hidden="true" />
                    Upgrade for Goldens
                  </Link>
                )}
              </div>
            ) : (
              <div className="imd-proof-row">
                <strong>Not eligible yet</strong>
                <p>
                  {verifiedFix
                    ? "A sample call and Golden entitlement are required before creating a Golden."
                    : "Run trusted replay before creating a Golden."}
                </p>
              </div>
            )}
          </section>
        </main>

        <aside className="imd-side" aria-label="Resolution">
          <section className="imd-card imd-sticky-card imd-action-panel">
            <div className="imd-side-head">
              <span>Resolution</span>
              <strong>Status: {titleCase(issue.status)}</strong>
            </div>
            <div className="imd-side-list">
              <div>
                <span>Status / owner</span>
                <strong>{titleCase(issue.status)} &middot; {issue.assigned_to ?? "Unassigned"}</strong>
              </div>
              <div>
                <span>Deploy / PR</span>
                {issue.deploy_pr_url ? (
                  <a href={issue.deploy_pr_url} target="_blank" rel="noreferrer">
                    Linked <ExternalLink aria-hidden="true" />
                  </a>
                ) : (
                  <strong>Not linked</strong>
                )}
              </div>
              <div>
                <span>Replay proof summary</span>
                <strong>{replayLabel(issue.replay_coverage_status)}</strong>
              </div>
              <div>
                <span>Cost impact</span>
                <strong>{formatIssueImpact(issue)} from {formatCount(issue.occurrence_count)} calls</strong>
              </div>
              <div>
                <span>Avg failed call cost</span>
                <strong>{averageFailedCallCost(issue)}</strong>
              </div>
            </div>
            <div className="imd-primary-action">
              <span>Primary action</span>
              {renderPrimaryAction()}
            </div>
            <div className="imd-triage-form">
              <span className="imd-side-section-title">Triage</span>
              <label>
                <span>Assign</span>
                <input value={assigneeDraft} onChange={(event) => setAssigneeDraft(event.target.value)} placeholder="team member" />
              </label>
              <label>
                <span>Add PR URL</span>
                <input value={deployDraft} onChange={(event) => setDeployDraft(event.target.value)} placeholder="https://github.com/..." />
              </label>
              <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={() => void onSaveTriage()} disabled={busyAction === "triage"}>
                <Save aria-hidden="true" />
                {busyAction === "triage" ? "Saving..." : "Save triage"}
              </button>
            </div>
            <div className="imd-row-actions imd-side-actions">
              <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={() => void onResolve()} disabled={busyAction === "resolve"}>
                <CheckCircle2 aria-hidden="true" />
                {busyAction === "resolve" ? "Resolving..." : "Resolve"}
              </button>
              <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={() => void onIgnore()} disabled={busyAction === "ignore"}>
                <Archive aria-hidden="true" />
                {busyAction === "ignore" ? "Ignoring..." : "Ignore"}
              </button>
              {issue.deploy_pr_url ? (
                <a href={issue.deploy_pr_url} target="_blank" rel="noreferrer" className="btn btn-soft btn-sm im-btn-secondary">
                  <GitPullRequest aria-hidden="true" />
                  Open PR
                </a>
              ) : null}
            </div>
          </section>
        </aside>
      </section>
    </div>
  );
}
