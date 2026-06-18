"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  Archive,
  ArrowLeft,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  DollarSign,
  ExternalLink,
  FileSearch,
  GitPullRequest,
  ListChecks,
  LockKeyhole,
  RotateCcw,
  Save,
  ShieldCheck,
} from "lucide-react";

import { hasPlanEntitlement } from "@/components/feature-gate";
import { ProviderKeyReplayGate } from "@/components/provider-key-replay-gate";
import {
  createReplayRunFromCall,
  createReplayRunFromIssue,
  getBillingMe,
  getIssue,
  ignoreIssue,
  promoteIssueToGolden,
  resolveIssue,
  runIssueCiGate,
  updateIssueTriage,
} from "@/lib/api";
import { detectorLabel, severityBadgeColor } from "@/lib/detector-meta";
import { formatCount, formatDateTime, formatUsd } from "@/lib/format";
import { useActiveProviderKeys } from "@/lib/hooks";
import { replayLabel } from "@/lib/issue-format";
import { DEFAULT_VERIFICATION_REPLAY_MODE, STUB_REPLAY_MODE } from "@/lib/replay-mode";
import { hasActiveProviderKey } from "@/lib/provider-key-gate";
import type { BillingMeResponse, IssueEvidenceTrace, IssueItem } from "@/lib/types";

type ActionState = "issue_replay" | "call_replay" | "promote_golden" | "ci_gate" | "resolve" | "ignore" | "triage" | null;
type ConfirmAction = "resolve" | "ignore" | null;
type ProviderKeyPendingAction =
  | { type: "issue"; provider?: string | null }
  | { type: "call"; callId: string; provider?: string | null }
  | { type: "ci"; provider?: string | null };
type ProofState = "good" | "warn" | "blocked" | "neutral";
type PrimaryAction =
  | "run_replay"
  | "promote_golden"
  | "run_ci_gate"
  | "open_ci_gate"
  | "upgrade_replay"
  | "upgrade_goldens"
  | "upgrade_ci"
  | "blocked_missing_sample"
  | "link_pr"
  | "back_to_queue";

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

function averageFailedCallCost(issue: IssueItem): string {
  const impact = issueImpactUsd(issue);
  if (!impact || issue.occurrence_count <= 0) return "\u2014";
  return formatUsd(impact / issue.occurrence_count);
}

function issueAgent(issue: IssueItem): string {
  return issue.affected_agent ?? issue.agent_name ?? "Agent not captured";
}

function issueWorkflow(issue: IssueItem): string {
  return issue.affected_workflow ?? "Workflow not captured";
}

function issueEnvironment(): string {
  const env = process.env.NEXT_PUBLIC_DASHBOARD_ENV ?? "production";
  return env.charAt(0).toUpperCase() + env.slice(1);
}

function titleCase(value: string): string {
  return value ? value.replace(/_/g, " ").replace(/^\w/, (match) => match.toUpperCase()) : "Unknown";
}

function sortedEvidence(traces: IssueEvidenceTrace[]): IssueEvidenceTrace[] {
  return [...traces].sort((a, b) => {
    const aTime = a.created_at ? Date.parse(a.created_at) : 0;
    const bTime = b.created_at ? Date.parse(b.created_at) : 0;
    return aTime - bTime;
  });
}

function traceTarget(trace: IssueEvidenceTrace): string | null {
  return trace.trace_id ?? trace.call_id;
}

function issueProvider(issue: IssueItem | null): string | null {
  return issue?.evidence_traces.find((trace) => trace.provider?.trim())?.provider ?? null;
}

function callProvider(issue: IssueItem | null, callId: string): string | null {
  if (!issue) return null;
  return (
    issue.evidence_traces.find((trace) => trace.call_id === callId && trace.provider?.trim())?.provider ??
    issueProvider(issue)
  );
}

function hasEvidence(issue: IssueItem): boolean {
  return issue.evidence_traces.length > 0 || Boolean(issue.sample_call_id);
}

function hasRootCause(issue: IssueItem): boolean {
  return Boolean(issue.root_cause?.trim()) || issue.evidence_traces.some((trace) => Boolean(trace.evidence_summary?.trim()));
}

function goldenEligible(issue: IssueItem): boolean {
  return hasVerifiedFix(issue) && Boolean(issue.sample_call_id);
}

function hasActiveGolden(issue: IssueItem): boolean {
  return Boolean(issue.proof?.golden?.golden_trace_id && issue.proof.golden.status === "active");
}

function hasCiGateRun(issue: IssueItem): boolean {
  return Boolean(issue.proof?.ci_gate?.run_id);
}

function replayBlocker(issue: IssueItem): string {
  if (!issue.sample_call_id) return "Trusted replay needs a representative sample call.";
  if (hasVerifiedFix(issue)) return "Trusted replay verified the fix.";
  const label = replayLabel(issue.replay_coverage_status);
  return `${label} is not trusted enough for Goldens or CI gates.`;
}

function goldenBlocker(issue: IssueItem, canGoldens: boolean): string {
  if (hasActiveGolden(issue)) return "Active Golden guard is linked to this issue.";
  if (!hasVerifiedFix(issue)) return "Needs trusted replay before Golden promotion.";
  if (!issue.sample_call_id) return "Needs a sample call before Golden promotion.";
  if (!canGoldens) return "Current plan does not unlock Goldens.";
  return "Ready to promote this verified scenario into a Golden guard.";
}

function ciBlocker(issue: IssueItem, canCi: boolean): string {
  if (hasCiGateRun(issue)) return "A replay-backed CI gate run is linked to this issue.";
  if (!hasActiveGolden(issue)) return "Promote this verified issue to an active Golden before CI can block regressions.";
  if (!canCi) return "Current plan does not unlock CI gates.";
  if (!issue.deploy_pr_url) return "Ready for CI, but no deployment PR is linked yet.";
  return "Ready to run a replay-backed CI gate for the linked PR.";
}

function costInterpretation(issue: IssueItem): string {
  if (hasCiGateRun(issue)) {
    return "CI gate proof exists. Repeat spend is now guarded by replay before merge.";
  }
  if (hasActiveGolden(issue)) {
    return "Golden proof exists. Run the CI gate to turn this into a release blocker.";
  }
  if (hasVerifiedFix(issue)) {
    return "Verified replay exists. Promote the scenario to Golden and CI to prevent repeat spend.";
  }
  if (issueImpactUsd(issue) != null) {
    return "This is current loaded exposure, not projected savings. Verify the fix before treating it as avoided cost.";
  }
  return "No reliable cost estimate is attached yet. Capture more failed calls to quantify exposure.";
}

function evidenceSummary(issue: IssueItem): string {
  return (
    issue.what_happened?.trim() ??
    issue.evidence_traces.find((trace) => trace.evidence_summary?.trim())?.evidence_summary ??
    issue.user_impact ??
    "No evidence summary captured yet."
  );
}

function whyItMatters(issue: IssueItem): string {
  return issue.why_it_matters?.trim() || issue.user_impact || "Business impact is not captured yet.";
}

function affectedTraceCount(issue: IssueItem): number {
  return issue.affected_trace_count ?? issue.blast_radius?.affected_traces ?? issue.occurrence_count;
}

function affectedUserCount(issue: IssueItem): number {
  return issue.affected_user_count ?? issue.blast_radius?.affected_users ?? 0;
}

function suspectedVersion(issue: IssueItem): string {
  return issue.suspected_introduced_version?.trim() || "Version not captured";
}

function primaryActionForIssue(
  issue: IssueItem,
  caps: { canReplay: boolean; canGoldens: boolean; canCi: boolean },
): PrimaryAction {
  if (issue.status !== "open") return "back_to_queue";
  if (isUntrustedReplay(issue)) {
    if (!issue.sample_call_id) return "blocked_missing_sample";
    return caps.canReplay ? "run_replay" : "upgrade_replay";
  }
  if (hasCiGateRun(issue)) return "open_ci_gate";
  if (hasActiveGolden(issue)) {
    if (!caps.canCi) return "upgrade_ci";
    if (!issue.deploy_pr_url) return "link_pr";
    return "run_ci_gate";
  }
  if (goldenEligible(issue)) {
    if (!caps.canGoldens) return "upgrade_goldens";
    return "promote_golden";
  }
  return "back_to_queue";
}

function primaryActionLabel(action: PrimaryAction): string {
  if (action === "run_replay") return "Run trusted replay";
  if (action === "promote_golden") return "Promote to Golden";
  if (action === "run_ci_gate") return "Run CI gate";
  if (action === "open_ci_gate") return "Open CI gate";
  if (action === "upgrade_replay") return "Upgrade for replay";
  if (action === "upgrade_goldens") return "Upgrade for Goldens";
  if (action === "upgrade_ci") return "Upgrade for CI gates";
  if (action === "blocked_missing_sample") return "Sample call required";
  if (action === "link_pr") return "Link deployment PR";
  return "Back to queue";
}

function primaryActionReason(action: PrimaryAction, issue: IssueItem, canCi: boolean): string {
  if (action === "run_replay") return "Replay the exact failed scenario before any Golden or CI gate can be trusted.";
  if (action === "promote_golden") return "The fix is verified. Create the active Golden guard now.";
  if (action === "run_ci_gate") return ciBlocker(issue, canCi);
  if (action === "open_ci_gate") return "CI proof is already linked. Review the replay-backed gate result.";
  if (action === "upgrade_replay") return "Replay is locked on the current plan.";
  if (action === "upgrade_goldens") return "Golden promotion is locked on the current plan.";
  if (action === "upgrade_ci") return "CI gates are locked on the current plan.";
  if (action === "blocked_missing_sample") return replayBlocker(issue);
  if (action === "link_pr") return "Add the deployment PR URL in triage so this issue can run as a CI gate.";
  return "This issue no longer needs an active remediation action.";
}

function severityBadge(issue: IssueItem) {
  return (
    <span className={`alert-cat-badge badge-${severityBadgeColor(issue.severity)} im-severity-badge`}>
      <AlertTriangle aria-hidden="true" />
      {issue.severity}
    </span>
  );
}

function DetailMetric({ label, value, helper }: { label: string; value: string; helper?: string }) {
  return (
    <div className="imd-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {helper ? <small>{helper}</small> : null}
    </div>
  );
}

function SectionHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="imd-section-header">
      <div>
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {action}
    </header>
  );
}

function ProofStep({
  icon,
  label,
  state,
  value,
  helper,
}: {
  icon: ReactNode;
  label: string;
  state: ProofState;
  value: string;
  helper: string;
}) {
  return (
    <div className="imd-proof-step" data-state={state}>
      <div className="imd-proof-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{helper}</p>
    </div>
  );
}

function DiagnosisBlock({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="imd-diagnosis-block">
      <span>{label}</span>
      <p>{value}</p>
    </div>
  );
}

function ReadinessCard({
  icon,
  title,
  status,
  state,
  detail,
  action,
}: {
  icon: ReactNode;
  title: string;
  status: string;
  state: ProofState;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <div className="imd-readiness-card" data-state={state}>
      <div className="imd-readiness-head">
        <span>{icon}</span>
        <strong>{title}</strong>
      </div>
      <b>{status}</b>
      <p>{detail}</p>
      {action}
    </div>
  );
}

function ConfirmPanel({
  action,
  busyAction,
  onCancel,
  onConfirm,
}: {
  action: ConfirmAction;
  busyAction: ActionState;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  if (!action) return null;
  const isResolve = action === "resolve";
  return (
    <div className="imd-confirm-panel" role="alert">
      <div>
        <strong>{isResolve ? "Resolve this issue?" : "Ignore this issue?"}</strong>
        <p>
          {isResolve
            ? "Only resolve after the fix path is understood or verified."
            : "Ignoring removes this issue from the active remediation queue."}
        </p>
      </div>
      <div className="imd-row-actions">
        <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={onCancel}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-primary btn-sm im-btn-primary"
          onClick={onConfirm}
          disabled={busyAction === action}
        >
          {busyAction === action ? "Working..." : isResolve ? "Confirm resolve" : "Confirm ignore"}
        </button>
      </div>
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
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<ActionState>(null);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null);
  const [assigneeDraft, setAssigneeDraft] = useState("");
  const [deployDraft, setDeployDraft] = useState("");
  const [providerKeyPendingAction, setProviderKeyPendingAction] = useState<ProviderKeyPendingAction | null>(null);
  const providerKeysQuery = useActiveProviderKeys();

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
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [id]);

  const planTemplate = billing?.plan_template;
  const caps = useMemo(
    () => ({
      canReplay: hasPlanEntitlement(planTemplate, "pilot.replay_stub"),
      canGoldens: hasPlanEntitlement(planTemplate, "pilot.goldens_basic"),
      canCi:
        hasPlanEntitlement(planTemplate, "pro.ci_gate_nonblocking") ||
        hasPlanEntitlement(planTemplate, "pro.ci_gate_blocking"),
    }),
    [planTemplate],
  );
  const orderedEvidence = useMemo(() => (issue ? sortedEvidence(issue.evidence_traces) : []), [issue]);

  async function hasProviderKeyForReplay(provider?: string | null) {
    if (hasActiveProviderKey(providerKeysQuery.data?.items, provider)) return true;
    const refreshed = await providerKeysQuery.refetch();
    return hasActiveProviderKey(refreshed.data?.items, provider);
  }

  async function runIssueReplay(replayMode = DEFAULT_VERIFICATION_REPLAY_MODE) {
    if (!issue) return;
    setActionError(null);
    setSuccessMessage(null);
    setBusyAction("issue_replay");
    try {
      const run = await createReplayRunFromIssue(issue.id, {
        replay_mode: replayMode,
      });
      router.push(`/replay/${run.id}`);
    } catch (replayError) {
      setActionError(replayError instanceof Error ? replayError.message : "Failed to create replay.");
    } finally {
      setBusyAction(null);
    }
  }

  async function onReplayIssue() {
    const provider = issueProvider(issue);
    if (await hasProviderKeyForReplay(provider)) {
      await runIssueReplay();
      return;
    }
    setProviderKeyPendingAction({ type: "issue", provider });
  }

  async function runCallReplay(callId: string, replayMode = DEFAULT_VERIFICATION_REPLAY_MODE) {
    setActionError(null);
    setSuccessMessage(null);
    setBusyAction("call_replay");
    try {
      const run = await createReplayRunFromCall(callId, {
        replay_mode: replayMode,
      });
      router.push(`/replay/${run.id}`);
    } catch (replayError) {
      setActionError(replayError instanceof Error ? replayError.message : "Failed to create call replay.");
    } finally {
      setBusyAction(null);
    }
  }

  async function onReplayCall(callId: string) {
    const provider = callProvider(issue, callId);
    if (await hasProviderKeyForReplay(provider)) {
      await runCallReplay(callId);
      return;
    }
    setProviderKeyPendingAction({ type: "call", callId, provider });
  }

  async function onPromoteGolden() {
    if (!issue) return;
    setActionError(null);
    setSuccessMessage(null);
    setBusyAction("promote_golden");
    try {
      const response = await promoteIssueToGolden(issue.id, { blocks_ci: true });
      setIssue(response.issue);
      setSuccessMessage("Golden guard created and linked to this issue.");
    } catch (goldenError) {
      setActionError(goldenError instanceof Error ? goldenError.message : "Failed to promote issue to Golden.");
    } finally {
      setBusyAction(null);
    }
  }

  async function onRunCiGate() {
    if (!issue) return;
    const provider = issueProvider(issue);
    if (!(await hasProviderKeyForReplay(provider))) {
      setProviderKeyPendingAction({ type: "ci", provider });
      return;
    }
    await runCiGate();
  }

  async function runCiGate() {
    if (!issue) return;
    setActionError(null);
    setSuccessMessage(null);
    setBusyAction("ci_gate");
    try {
      const response = await runIssueCiGate(issue.id, {
        replay_mode: DEFAULT_VERIFICATION_REPLAY_MODE,
      });
      setIssue(response.issue);
      if (response.ci_gate.run_id) router.push(`/ci-gates/${response.ci_gate.run_id}`);
    } catch (ciError) {
      setActionError(ciError instanceof Error ? ciError.message : "Failed to run CI gate.");
    } finally {
      setBusyAction(null);
    }
  }

  function onProviderKeySavedAndRun() {
    if (!providerKeyPendingAction) return;
    if (providerKeyPendingAction.type === "issue") {
      void runIssueReplay();
      return;
    }
    if (providerKeyPendingAction.type === "call") {
      void runCallReplay(providerKeyPendingAction.callId);
      return;
    }
    void runCiGate();
  }

  function onUseStubReplay() {
    if (!providerKeyPendingAction || providerKeyPendingAction.type === "ci") {
      setProviderKeyPendingAction(null);
      setActionError("CI gates require verified replay. Connect a provider key before running a CI gate.");
      return;
    }
    const pending = providerKeyPendingAction;
    setProviderKeyPendingAction(null);
    if (pending.type === "issue") {
      void runIssueReplay(STUB_REPLAY_MODE);
      return;
    }
    void runCallReplay(pending.callId, STUB_REPLAY_MODE);
  }

  async function onResolve() {
    if (!issue) return;
    setActionError(null);
    setSuccessMessage(null);
    setBusyAction("resolve");
    try {
      const updated = await resolveIssue(issue.id, { resolution_source: "manual" });
      setIssue(updated);
      setConfirmAction(null);
      setSuccessMessage("Issue resolved. It is no longer part of the active failure queue.");
    } catch (resolveError) {
      setActionError(resolveError instanceof Error ? resolveError.message : "Failed to resolve issue.");
    } finally {
      setBusyAction(null);
    }
  }

  async function onIgnore() {
    if (!issue) return;
    setActionError(null);
    setSuccessMessage(null);
    setBusyAction("ignore");
    try {
      const updated = await ignoreIssue(issue.id);
      setIssue(updated);
      setConfirmAction(null);
      setSuccessMessage("Issue ignored. It will not appear in the active remediation queue.");
    } catch (ignoreError) {
      setActionError(ignoreError instanceof Error ? ignoreError.message : "Failed to ignore issue.");
    } finally {
      setBusyAction(null);
    }
  }

  async function onSaveTriage() {
    if (!issue) return;
    setActionError(null);
    setSuccessMessage(null);
    setBusyAction("triage");
    try {
      const updated = await updateIssueTriage(issue.id, {
        assigned_to: assigneeDraft.trim() || null,
        deploy_pr_url: deployDraft.trim() || null,
      });
      setIssue(updated);
      setAssigneeDraft(updated.assigned_to ?? "");
      setDeployDraft(updated.deploy_pr_url ?? "");
      setSuccessMessage("Triage saved.");
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
        <section className="imd-notice imd-notice-error" role="alert">
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
  const hasSampleCall = Boolean(issue.sample_call_id);
  const activeGolden = hasActiveGolden(issue);
  const linkedCiGate = hasCiGateRun(issue);
  const canPromoteGolden = goldenEligible(issue) && caps.canGoldens;
  const canRunCiGate = activeGolden && caps.canCi && Boolean(issue.deploy_pr_url);
  const rootCause = issue.root_cause?.trim() || "No structured root cause available yet.";
  const primaryAction = primaryActionForIssue(issue, caps);
  const proofSteps = [
    {
      icon: <FileSearch aria-hidden="true" />,
      label: "Evidence",
      value: hasEvidence(issue) ? "Captured" : "Missing",
      helper: hasEvidence(issue) ? "Sample call or trace evidence exists." : "No sample call or evidence traces attached.",
      state: hasEvidence(issue) ? ("good" as const) : ("blocked" as const),
    },
    {
      icon: <ListChecks aria-hidden="true" />,
      label: "Root cause",
      value: hasRootCause(issue) ? "Explained" : "Missing",
      helper: hasRootCause(issue) ? "A diagnosis is available for review." : "Diagnosis needs stronger evidence.",
      state: hasRootCause(issue) ? ("good" as const) : ("warn" as const),
    },
    {
      icon: <RotateCcw aria-hidden="true" />,
      label: "Replay",
      value: verifiedFix ? "Trusted" : replayLabel(issue.replay_coverage_status),
      helper: replayBlocker(issue),
      state: verifiedFix ? ("good" as const) : hasSampleCall ? ("blocked" as const) : ("warn" as const),
    },
    {
      icon: <ShieldCheck aria-hidden="true" />,
      label: "Golden",
      value: activeGolden ? "Active" : canPromoteGolden ? "Ready" : "Blocked",
      helper: goldenBlocker(issue, caps.canGoldens),
      state: activeGolden ? ("good" as const) : canPromoteGolden ? ("warn" as const) : ("blocked" as const),
    },
    {
      icon: <GitPullRequest aria-hidden="true" />,
      label: "CI gate",
      value: linkedCiGate ? "Linked" : canRunCiGate ? "Ready" : "Blocked",
      helper: ciBlocker(issue, caps.canCi),
      state: linkedCiGate ? ("good" as const) : canRunCiGate ? ("warn" as const) : ("blocked" as const),
    },
    {
      icon: <CheckCircle2 aria-hidden="true" />,
      label: "Resolution",
      value: titleCase(issue.status),
      helper: issue.status === "open" ? "Issue is still in the active queue." : "Issue has left the active queue.",
      state: issue.status === "resolved" ? ("good" as const) : issue.status === "ignored" ? ("neutral" as const) : ("warn" as const),
    },
  ];

  function renderPrimaryAction() {
    if (!issue) return null;
    if (primaryAction === "run_replay") {
      return (
        <button
          type="button"
          className="btn btn-primary btn-sm im-btn-primary"
          onClick={() => void onReplayIssue()}
          disabled={busyAction === "issue_replay"}
        >
          <RotateCcw aria-hidden="true" />
          {busyAction === "issue_replay" ? "Creating..." : "Run trusted replay"}
        </button>
      );
    }
    if (primaryAction === "promote_golden") {
      return (
        <button
          type="button"
          className="btn btn-primary btn-sm im-btn-primary"
          onClick={() => void onPromoteGolden()}
          disabled={busyAction === "promote_golden"}
        >
          <ShieldCheck aria-hidden="true" />
          {busyAction === "promote_golden" ? "Promoting..." : "Promote to Golden"}
        </button>
      );
    }
    if (primaryAction === "run_ci_gate") {
      return (
        <button
          type="button"
          className="btn btn-primary btn-sm im-btn-primary"
          onClick={() => void onRunCiGate()}
          disabled={busyAction === "ci_gate"}
        >
          <GitPullRequest aria-hidden="true" />
          {busyAction === "ci_gate" ? "Dispatching..." : "Run CI gate"}
        </button>
      );
    }
    if (primaryAction === "open_ci_gate") {
      return (
        <Link href={`/ci-gates/${issue.proof?.ci_gate?.run_id}`} className="btn btn-primary btn-sm im-btn-primary">
          <GitPullRequest aria-hidden="true" />
          Open CI gate
        </Link>
      );
    }
    if (primaryAction === "upgrade_replay" || primaryAction === "upgrade_goldens" || primaryAction === "upgrade_ci") {
      return (
        <Link href="/settings/billing" className="btn btn-primary btn-sm im-btn-primary">
          <LockKeyhole aria-hidden="true" />
          {primaryActionLabel(primaryAction)}
        </Link>
      );
    }
    if (primaryAction === "link_pr") {
      return (
        <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={() => document.getElementById("issue-deploy-pr")?.focus()}>
          <GitPullRequest aria-hidden="true" />
          Add PR URL
        </button>
      );
    }
    if (primaryAction === "blocked_missing_sample") {
      return (
        <Link href="/calls" className="btn btn-soft btn-sm im-btn-secondary">
          <FileSearch aria-hidden="true" />
          Find sample call
        </Link>
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

      {successMessage ? (
        <section className="imd-notice imd-notice-success" role="status" aria-live="polite">
          <p>{successMessage}</p>
        </section>
      ) : null}

      {actionError ? (
        <section className="imd-notice imd-notice-error" role="alert">
          <p>{actionError}</p>
        </section>
      ) : null}

      {providerKeyPendingAction ? (
        <ProviderKeyReplayGate
          expectedProvider={providerKeyPendingAction.provider ?? null}
          onClose={() => setProviderKeyPendingAction(null)}
          onSavedAndRun={onProviderKeySavedAndRun}
          onUseStub={onUseStubReplay}
          showUseStub={providerKeyPendingAction.type !== "ci"}
        />
      ) : null}

      <section className="imd-hero imd-command-hero" aria-label="Issue command center">
        <div className="imd-hero-grid">
          <div className="imd-hero-main">
            <div className="imd-badge-row">
              {severityBadge(issue)}
              <span className="im-status-pill">{replayLabel(issue.replay_coverage_status)}</span>
              <span className="im-status-pill">{issue.status}</span>
            </div>
            <h1>{issue.title}</h1>
            <p>
              {detectorLabel(issue.failure_code)} - {issueAgent(issue)} - {issueWorkflow(issue)} - {issueEnvironment()}
            </p>
          </div>

          <aside className="imd-next-action-card" aria-label="Recommended next action">
            <span>Recommended next action</span>
            <strong>{primaryActionLabel(primaryAction)}</strong>
            <p>{primaryActionReason(primaryAction, issue, caps.canCi)}</p>
            {renderPrimaryAction()}
          </aside>
        </div>

        <div className="imd-proof-ladder" aria-label="Issue proof ladder">
          {proofSteps.map((step) => (
            <ProofStep key={step.label} {...step} />
          ))}
        </div>

        <div className="imd-meta-strip" aria-label="Issue metadata">
          <DetailMetric label="Occurrences" value={formatCount(issue.occurrence_count)} helper="Loaded failed calls" />
          <DetailMetric label="Affected traces" value={formatCount(affectedTraceCount(issue))} />
          <DetailMetric label="Affected users" value={affectedUserCount(issue) ? formatCount(affectedUserCount(issue)) : "Unknown"} />
          <DetailMetric label="Impact" value={formatIssueImpact(issue)} helper="Current exposure" />
          <DetailMetric label="First seen" value={formatDateTime(issue.first_seen_at)} />
          <DetailMetric label="Last seen" value={formatDateTime(issue.last_seen_at)} />
          <DetailMetric label="Suspected version" value={suspectedVersion(issue)} />
        </div>
      </section>

      <section className="imd-layout">
        <div className="imd-main">
          <section className="imd-card imd-diagnosis-card">
            <SectionHeader
              title="Executive diagnosis"
              description="The shortest reliable explanation of the failure and why this issue matters."
            />
            <div className="imd-diagnosis-grid">
              <DiagnosisBlock label="What happened" value={evidenceSummary(issue)} />
              <DiagnosisBlock label="Why it matters" value={whyItMatters(issue)} />
              <DiagnosisBlock label="Root cause" value={rootCause} />
              <DiagnosisBlock
                label="Blast radius"
                value={`${formatCount(affectedTraceCount(issue))} traces${
                  affectedUserCount(issue) ? ` across ${formatCount(affectedUserCount(issue))} users` : ""
                }`}
              />
              <DiagnosisBlock
                label="Recommended path"
                value={issue.recommended_next_action || primaryActionReason(primaryAction, issue, caps.canCi)}
              />
            </div>
          </section>

          <section className="imd-card">
            <SectionHeader
              title="Evidence workbench"
              description="Trace-level evidence attached to this issue. Use this to replay or inspect the exact failure."
              action={<span>{formatCount(orderedEvidence.length)} traces</span>}
            />
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

            <div className="imd-trace-list">
              {issue.sample_call_id ? (
                <div className="imd-trace-row">
                  <div>
                    <strong>{issue.sample_call_id}</strong>
                    <span>Representative sample call for replay.</span>
                  </div>
                  <div className="imd-row-actions">
                    <Link href={`/calls/${issue.sample_call_id}`} className="btn btn-soft btn-sm im-btn-secondary">
                      View call
                    </Link>
                    {caps.canReplay ? (
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
                        {trace.latency_ms != null ? `${Math.round(trace.latency_ms)} ms` : "latency unknown"} -{" "}
                        {trace.cost_usd != null ? formatUsd(trace.cost_usd) : "cost unknown"}
                      </span>
                    </div>
                    <div className="imd-row-actions">
                      {target ? (
                        <Link href={`/trace/${target}`} className="btn btn-soft btn-sm im-btn-secondary">
                          View trace
                        </Link>
                      ) : null}
                      {trace.call_id && trace.call_id !== issue.sample_call_id && caps.canReplay ? (
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
            <SectionHeader
              title="Replay, Golden, and CI readiness"
              description="This is the trust path from one failed run to a release gate."
            />
            <div className="imd-readiness-grid">
              <ReadinessCard
                icon={<RotateCcw aria-hidden="true" />}
                title="Replay proof"
                status={verifiedFix ? "Trusted replay verified" : replayLabel(issue.replay_coverage_status)}
                state={verifiedFix ? "good" : "blocked"}
                detail={replayBlocker(issue)}
                action={
                  isUntrustedReplay(issue) && caps.canReplay && issue.sample_call_id ? (
                    <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={() => void onReplayIssue()}>
                      Run replay
                    </button>
                  ) : null
                }
              />
              <ReadinessCard
                icon={<ShieldCheck aria-hidden="true" />}
                title="Golden readiness"
                status={activeGolden ? "Active Golden linked" : canPromoteGolden ? "Ready for Golden" : "Not ready"}
                state={activeGolden ? "good" : canPromoteGolden ? "warn" : "blocked"}
                detail={goldenBlocker(issue, caps.canGoldens)}
                action={
                  activeGolden && issue.proof?.golden?.golden_set_id ? (
                    <Link href={`/goldens/${issue.proof.golden.golden_set_id}`} className="btn btn-soft btn-sm im-btn-secondary">
                      Open Golden
                    </Link>
                  ) : canPromoteGolden ? (
                    <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={() => void onPromoteGolden()} disabled={busyAction === "promote_golden"}>
                      {busyAction === "promote_golden" ? "Promoting..." : "Promote Golden"}
                    </button>
                  ) : null
                }
              />
              <ReadinessCard
                icon={<GitPullRequest aria-hidden="true" />}
                title="CI gate readiness"
                status={linkedCiGate ? "Gate linked" : canRunCiGate ? "Gate-ready" : "Blocked"}
                state={linkedCiGate ? "good" : canRunCiGate ? "warn" : "blocked"}
                detail={ciBlocker(issue, caps.canCi)}
                action={
                  linkedCiGate && issue.proof?.ci_gate?.run_id ? (
                    <Link href={`/ci-gates/${issue.proof.ci_gate.run_id}`} className="btn btn-soft btn-sm im-btn-secondary">
                      Open CI gate
                    </Link>
                  ) : canRunCiGate ? (
                    <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={() => void onRunCiGate()} disabled={busyAction === "ci_gate"}>
                      {busyAction === "ci_gate" ? "Dispatching..." : "Run CI gate"}
                    </button>
                  ) : null
                }
              />
            </div>
          </section>

          <section className="imd-card">
            <SectionHeader title="Cost impact" description="Business signal for prioritization. No avoided-cost claim is made without proof." />
            <div className="imd-cost-grid">
              <DetailMetric label="Estimated wasted spend" value={formatIssueImpact(issue)} />
              <DetailMetric label="Affected traces" value={formatCount(affectedTraceCount(issue))} />
              <DetailMetric label="Average failed call cost" value={averageFailedCallCost(issue)} />
            </div>
            <p className="imd-cost-note">
              <DollarSign aria-hidden="true" />
              {costInterpretation(issue)}
            </p>
          </section>
        </div>

        <aside className="imd-side" aria-label="Resolution">
          <section className="imd-card imd-sticky-card imd-action-panel">
            <div className="imd-side-head">
              <span>Resolution controls</span>
              <strong>Status: {titleCase(issue.status)}</strong>
            </div>
            <div className="imd-side-list">
              <div>
                <span>Status / owner</span>
                <strong>
                  {titleCase(issue.status)} - {issue.assigned_to ?? "Unassigned"}
                </strong>
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
                <span>Replay proof</span>
                <strong>{replayLabel(issue.replay_coverage_status)}</strong>
              </div>
              <div>
                <span>Gate readiness</span>
                <strong>{linkedCiGate ? "CI gate linked" : canRunCiGate ? "CI-ready" : "Not CI-ready"}</strong>
              </div>
              <div>
                <span>Golden proof</span>
                <strong>{issue.proof?.golden?.golden_trace_id ? issue.proof.golden.status ?? "Linked" : "Not promoted"}</strong>
              </div>
              <div>
                <span>CI proof</span>
                <strong>{issue.proof?.ci_gate?.run_id ? issue.proof.ci_gate.status ?? "Linked" : "Not run"}</strong>
              </div>
              <div>
                <span>Suspected version</span>
                <strong>{suspectedVersion(issue)}</strong>
              </div>
              <div>
                <span>Cost impact</span>
                <strong>
                  {formatIssueImpact(issue)} from {formatCount(affectedTraceCount(issue))} traces
                </strong>
              </div>
              <div>
                <span>Avg failed call cost</span>
                <strong>{averageFailedCallCost(issue)}</strong>
              </div>
            </div>

            <div className="imd-triage-form">
              <span className="imd-side-section-title">Triage</span>
              <label>
                <span>Assign</span>
                <input value={assigneeDraft} onChange={(event) => setAssigneeDraft(event.target.value)} placeholder="team member" />
              </label>
              <label>
                <span>Add PR URL</span>
                <input id="issue-deploy-pr" value={deployDraft} onChange={(event) => setDeployDraft(event.target.value)} placeholder="https://github.com/..." />
              </label>
              <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={() => void onSaveTriage()} disabled={busyAction === "triage"}>
                <Save aria-hidden="true" />
                {busyAction === "triage" ? "Saving..." : "Save triage"}
              </button>
            </div>

            <ConfirmPanel
              action={confirmAction}
              busyAction={busyAction}
              onCancel={() => setConfirmAction(null)}
              onConfirm={() => void (confirmAction === "resolve" ? onResolve() : onIgnore())}
            />

            <div className="imd-row-actions imd-side-actions">
              <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={() => setConfirmAction("resolve")} disabled={busyAction === "resolve"}>
                <CheckCircle2 aria-hidden="true" />
                Resolve
              </button>
              <button type="button" className="btn btn-soft btn-sm im-btn-secondary" onClick={() => setConfirmAction("ignore")} disabled={busyAction === "ignore"}>
                <Archive aria-hidden="true" />
                Ignore
              </button>
              {issue.deploy_pr_url ? (
                <a href={issue.deploy_pr_url} target="_blank" rel="noreferrer" className="btn btn-soft btn-sm im-btn-secondary">
                  <GitPullRequest aria-hidden="true" />
                  Open PR
                </a>
              ) : null}
            </div>

            <div className="imd-side-footnote">
              <Clock3 aria-hidden="true" />
              Updated {formatDateTime(issue.updated_at)}
            </div>
          </section>
        </aside>
      </section>
    </div>
  );
}
