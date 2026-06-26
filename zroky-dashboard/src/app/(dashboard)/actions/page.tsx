"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ComponentType } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Gauge,
  ReceiptText,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Workflow,
} from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import {
  getBillingUsage,
  getOutcomeReconciliationSummary,
  getSourceMutationSummary,
  listOutcomeReconciliations,
  listRuntimePolicyApprovals,
  listUnreceiptedSourceMutations,
  type OutcomeReconciliationView,
  type RuntimePolicyDecisionResponse,
  type SourceMutationView,
} from "@/lib/api";
import { formatCount, formatDateTime } from "@/lib/format";
import type { BillingUsageMeter } from "@/lib/types";

type Tone = "danger" | "warning" | "success" | "neutral";

type ActionLifecycleRow = {
  key: string;
  title: string;
  agentName: string;
  actionType: string;
  policyStatus: string;
  proofStatus: string;
  receiptStatus: string;
  systemRef: string;
  priority: { label: string; detail: string };
  tone: Tone;
  createdAt: string | null;
  decision: RuntimePolicyDecisionResponse | null;
  outcome: OutcomeReconciliationView | null;
  mutation: SourceMutationView | null;
};

type MetricCardProps = {
  label: string;
  value: string;
  helper: string;
  tone?: Tone;
  Icon: ComponentType<{ size?: number; className?: string }>;
};

const EMPTY_JSON = "{}";

function compactJson(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value !== "object") return String(value);
  if (Array.isArray(value)) return value.length > 0 ? JSON.stringify(value, null, 2) : "[]";
  const entries = Object.entries(value as Record<string, unknown>).filter(([, item]) => item != null && item !== "");
  if (entries.length === 0) return EMPTY_JSON;
  return JSON.stringify(Object.fromEntries(entries), null, 2);
}

function humanize(value: string | null | undefined): string {
  if (!value) return "-";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\w/, (char) => char.toUpperCase());
}

function summary(value: Record<string, unknown> | null | undefined, fallback: string): string {
  const candidate = value?.summary;
  return typeof candidate === "string" && candidate.trim() ? candidate : fallback;
}

function formatMeter(meter: BillingUsageMeter | null | undefined): string {
  if (!meter) return "Loading";
  const used = formatCount(meter.used);
  if (meter.unlimited || meter.limit == null) return `${used} used`;
  return `${used} / ${formatCount(meter.limit)}`;
}

function meterHelper(label: string, meter: BillingUsageMeter | null | undefined): string {
  if (!meter) return `${label} usage is loading.`;
  if (meter.state === "exceeded") return `${label} exceeded by ${formatCount(meter.overage ?? 0)}.`;
  if (meter.state === "near_limit") return `${label} is near the current plan limit.`;
  if (meter.state === "blocked") return `${label} is blocked on this plan.`;
  if (meter.unlimited) return `${label} is unlimited on this plan.`;
  return meter.resets_at ? `Resets ${meter.resets_at}.` : "Current billing period.";
}

function decisionTitle(item: RuntimePolicyDecisionResponse): string {
  return summary(item.intended_action, item.tool_name ?? item.action_type ?? "Agent action");
}

function outcomeTitle(item: OutcomeReconciliationView): string {
  const refundId = item.claimed.refund_id;
  if (typeof refundId === "string" && refundId.trim()) return `Refund ${refundId}`;
  const paymentId = item.claimed.payment_id;
  if (typeof paymentId === "string" && paymentId.trim()) return `Payment ${paymentId}`;
  const email = item.claimed.email;
  if (typeof email === "string" && email.trim()) return `Email ${email}`;
  return item.system_ref ?? humanize(item.action_type) ?? "Outcome check";
}

function mutationTitle(item: SourceMutationView): string {
  return item.system_ref ?? item.resource_id ?? item.mutation_id;
}

function rowTone(row: Pick<ActionLifecycleRow, "policyStatus" | "proofStatus" | "mutation">): Tone {
  if (row.mutation?.classification === "policy_bypass" || row.mutation?.classification === "unmanaged_agent_action") {
    return "danger";
  }
  if (["blocked", "rejected", "mismatched", "fail", "policy_bypass"].includes(row.policyStatus)) return "danger";
  if (["mismatched", "fail"].includes(row.proofStatus)) return "danger";
  if (["pending_approval", "not_verified", "pending", "unverifiable", "legacy_path", "unknown_actor"].includes(row.policyStatus)) {
    return "warning";
  }
  if (["not_verified", "pending", "unverifiable"].includes(row.proofStatus)) return "warning";
  if (["approved", "allowed", "matched", "verified", "pass"].includes(row.policyStatus)) return "success";
  if (["matched", "verified", "pass"].includes(row.proofStatus)) return "success";
  return "neutral";
}

function priorityFor(row: Pick<ActionLifecycleRow, "policyStatus" | "proofStatus" | "mutation">): { label: string; detail: string } {
  if (row.mutation?.classification === "policy_bypass") return { label: "P0", detail: "policy bypass" };
  if (row.mutation?.classification === "unmanaged_agent_action") return { label: "P0", detail: "unmanaged action" };
  if (["blocked", "rejected", "mismatched", "fail"].includes(row.policyStatus) || ["mismatched", "fail"].includes(row.proofStatus)) {
    return { label: "P0", detail: "unsafe path" };
  }
  if (row.policyStatus === "pending_approval") return { label: "P1", detail: "needs approval" };
  if (["not_verified", "pending", "unverifiable"].includes(row.proofStatus)) return { label: "P1", detail: "needs proof" };
  return { label: "P2", detail: "controlled" };
}

function latestOutcomeByDecision(outcomes: OutcomeReconciliationView[]): Map<string, OutcomeReconciliationView> {
  const byDecision = new Map<string, OutcomeReconciliationView>();
  for (const outcome of outcomes) {
    if (!outcome.runtime_policy_decision_id) continue;
    const current = byDecision.get(outcome.runtime_policy_decision_id);
    if (!current || new Date(outcome.checked_at).getTime() > new Date(current.checked_at).getTime()) {
      byDecision.set(outcome.runtime_policy_decision_id, outcome);
    }
  }
  return byDecision;
}

function buildRows({
  decisions,
  outcomes,
  mutations,
}: {
  decisions: RuntimePolicyDecisionResponse[];
  outcomes: OutcomeReconciliationView[];
  mutations: SourceMutationView[];
}): ActionLifecycleRow[] {
  const outcomeByDecision = latestOutcomeByDecision(outcomes);
  const linkedOutcomeIds = new Set<string>();
  const rows: ActionLifecycleRow[] = [];

  for (const decision of decisions) {
    const outcome = outcomeByDecision.get(decision.id) ?? null;
    if (outcome) linkedOutcomeIds.add(outcome.id);
    const proofStatus = outcome?.verdict ?? (decision.status === "approved" || decision.status === "allowed" ? "not_verified" : "pending");
    const receiptStatus = outcome?.verdict === "matched" ? "receipt_ready" : decision.status === "approved" ? "receipt_pending" : "not_ready";
    const partial = {
      policyStatus: decision.status,
      proofStatus,
      mutation: null,
    };
    const row: ActionLifecycleRow = {
      key: `decision:${decision.id}`,
      title: decisionTitle(decision),
      agentName: decision.agent_name ?? "Unknown agent",
      actionType: humanize(decision.action_type ?? decision.tool_name),
      policyStatus: decision.status,
      proofStatus,
      receiptStatus,
      systemRef: outcome?.system_ref ?? decision.call_id ?? decision.trace_id ?? decision.id,
      priority: priorityFor(partial),
      tone: rowTone(partial),
      createdAt: decision.created_at,
      decision,
      outcome,
      mutation: null,
    };
    rows.push(row);
  }

  for (const outcome of outcomes) {
    if (linkedOutcomeIds.has(outcome.id)) continue;
    const partial = {
      policyStatus: "unlinked_outcome",
      proofStatus: outcome.verdict,
      mutation: null,
    };
    rows.push({
      key: `outcome:${outcome.id}`,
      title: outcomeTitle(outcome),
      agentName: "Unlinked action",
      actionType: humanize(outcome.action_type),
      policyStatus: "unlinked_outcome",
      proofStatus: outcome.verdict,
      receiptStatus: "not_ready",
      systemRef: outcome.system_ref ?? outcome.id,
      priority: priorityFor(partial),
      tone: rowTone(partial),
      createdAt: outcome.checked_at,
      decision: null,
      outcome,
      mutation: null,
    });
  }

  for (const mutation of mutations.slice(0, 8)) {
    const policyStatus = mutation.classification;
    const partial = {
      policyStatus,
      proofStatus: mutation.action_receipt_id ? "matched" : "not_verified",
      mutation,
    };
    rows.push({
      key: `mutation:${mutation.id}`,
      title: `Bypass: ${mutationTitle(mutation)}`,
      agentName: mutation.actor_id ?? mutation.actor_type ?? "Unknown actor",
      actionType: humanize(mutation.action_type ?? mutation.resource_type),
      policyStatus,
      proofStatus: partial.proofStatus,
      receiptStatus: mutation.action_receipt_id ? "receipt_linked" : "unreceipted",
      systemRef: mutation.system_ref ?? mutation.mutation_id,
      priority: priorityFor(partial),
      tone: rowTone(partial),
      createdAt: mutation.occurred_at,
      decision: null,
      outcome: null,
      mutation,
    });
  }

  return rows.sort((a, b) => {
    const timeA = a.createdAt ? new Date(a.createdAt).getTime() : 0;
    const timeB = b.createdAt ? new Date(b.createdAt).getTime() : 0;
    return timeB - timeA;
  });
}

function heroState({
  bypassRisk,
  error,
  loading,
  mismatched,
  pending,
  protectedActions,
}: {
  bypassRisk: number;
  error: boolean;
  loading: boolean;
  mismatched: number;
  pending: number;
  protectedActions: number;
}): { title: string; copy: string; pill: string; tone: Tone } {
  if (error) {
    return {
      title: "Action control visibility unavailable",
      copy: "Quota, policy, verification, or bypass feeds did not refresh cleanly.",
      pill: "refresh failed",
      tone: "danger",
    };
  }
  if (loading) {
    return {
      title: "Loading protected action control",
      copy: "Refreshing policy decisions, action meters, outcome checks, receipts, and source mutations.",
      pill: "loading",
      tone: "neutral",
    };
  }
  if (bypassRisk > 0) {
    return {
      title: "Bypass risk visible before customer handoff",
      copy: `${formatCount(bypassRisk)} source mutation${bypassRisk === 1 ? "" : "s"} need receipt matching or exception classification.`,
      pill: `${formatCount(bypassRisk)} unreceipted`,
      tone: "danger",
    };
  }
  if (mismatched > 0) {
    return {
      title: "Verified action mismatch",
      copy: `${formatCount(mismatched)} protected action${mismatched === 1 ? "" : "s"} do not match the source of record.`,
      pill: `${formatCount(mismatched)} mismatch`,
      tone: "danger",
    };
  }
  if (pending > 0) {
    return {
      title: "Actions held before execution",
      copy: `${formatCount(pending)} high-risk action${pending === 1 ? "" : "s"} are waiting for approval.`,
      pill: `${formatCount(pending)} held`,
      tone: "warning",
    };
  }
  if (protectedActions > 0) {
    return {
      title: "Protected actions controlled",
      copy: "Policy decisions, runner execution volume, verification checks, and receipts are visible for this billing period.",
      pill: `${formatCount(protectedActions)} controlled`,
      tone: "success",
    };
  }
  return {
    title: "Action control plane ready",
    copy: "Protected action lifecycle, quotas, proof, and bypass visibility will populate as agents route actions through Zroky.",
    pill: "ready",
    tone: "neutral",
  };
}

function MetricCard({ Icon, helper, label, tone = "neutral", value }: MetricCardProps) {
  return (
    <article className={`outcome-metric-card tone-${tone}`}>
      <Icon aria-hidden="true" />
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{helper}</small>
    </article>
  );
}

function evidenceHref(decisionId: string): string {
  return `/evidence?decision_id=${encodeURIComponent(decisionId)}`;
}

function ActionQueue({
  rows,
  selectedKey,
  onSelect,
}: {
  rows: ActionLifecycleRow[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
}) {
  return (
    <section className="outcome-queue-panel" aria-label="Action lifecycle queue">
      <div className="outcome-panel-head">
        <div>
          <span className="eyebrow">Lifecycle queue</span>
          <strong>{formatCount(rows.length)} protected action signal{rows.length === 1 ? "" : "s"}</strong>
        </div>
        <span className="outcome-live-dot">live</span>
      </div>
      <div className="outcome-queue-list">
        {rows.length === 0 ? (
          <div className="outcome-empty-state">
            <h2>No protected action signals</h2>
            <p>Policy decisions, verified outcomes, and bypass mutations will appear here.</p>
          </div>
        ) : (
          rows.map((row) => (
            <button
              className={`outcome-queue-row tone-${row.tone}${row.key === selectedKey ? " selected" : ""}`}
              key={row.key}
              onClick={() => onSelect(row.key)}
              type="button"
            >
              <span className="outcome-priority">{row.priority.label}</span>
              <span className="outcome-queue-main">
                <strong>{row.title}</strong>
                <small>
                  {row.agentName} / {row.actionType}
                </small>
                <em>{row.priority.detail}</em>
              </span>
              <span className="outcome-queue-side">
                <StatusPill value={row.policyStatus} />
                <small>{formatDateTime(row.createdAt)}</small>
              </span>
            </button>
          ))
        )}
      </div>
    </section>
  );
}

function SelectedActionPanel({ row }: { row: ActionLifecycleRow | null }) {
  if (!row) {
    return (
      <section className="outcome-empty-state" aria-label="Selected action lifecycle">
        <h2>No action selected</h2>
        <p>Select a protected action signal to inspect policy, proof, receipt, and bypass state.</p>
      </section>
    );
  }

  return (
    <section className="outcome-inspector-panel" aria-label="Selected action lifecycle">
      <header className="outcome-inspector-header">
        <div>
          <span className="eyebrow">Selected action</span>
          <h2>{row.title}</h2>
          <p>
            {row.agentName} / {row.actionType} / {row.systemRef}
          </p>
        </div>
        <StatusPill value={row.proofStatus} />
      </header>

      <div className={`outcome-proof-strip tone-${row.tone}`}>
        <div>
          <span className="eyebrow">Control state</span>
          <strong>{humanize(row.policyStatus)}</strong>
          <p>{row.priority.detail}</p>
        </div>
        <StatusPill value={row.receiptStatus} />
      </div>

      <dl className="outcome-inspector-metrics">
        <div>
          <dt>Decision</dt>
          <dd>{row.decision?.id ?? "-"}</dd>
        </div>
        <div>
          <dt>Outcome</dt>
          <dd>{row.outcome?.id ?? "-"}</dd>
        </div>
        <div>
          <dt>Mutation</dt>
          <dd>{row.mutation?.mutation_id ?? "-"}</dd>
        </div>
      </dl>

      <div className="actions">
        <Link href="/approvals" className="btn btn-secondary">
          Open Approvals
        </Link>
        <Link href="/outcomes" className="btn btn-secondary">
          Open Outcomes
        </Link>
        {row.decision ? (
          <Link href={evidenceHref(row.decision.id)} className="btn btn-primary">
            Open Evidence Pack
          </Link>
        ) : (
          <Link href="/evidence" className="btn btn-primary">
            Open Evidence
          </Link>
        )}
      </div>

      <div className="outcome-inspector-grid">
        <section>
          <h4>Intended action</h4>
          <pre>{compactJson(row.decision?.intended_action ?? row.outcome?.claimed ?? row.mutation?.metadata)}</pre>
        </section>
        <section>
          <h4>Source proof</h4>
          <pre>{compactJson(row.outcome?.actual ?? row.outcome?.comparison ?? row.mutation)}</pre>
        </section>
      </div>
    </section>
  );
}

export default function ActionsPage() {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const billingQuery = useQuery({
    queryKey: ["billing", "usage", "protected-action-dashboard"],
    queryFn: ({ signal }) => getBillingUsage(signal),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
  const decisionsQuery = useQuery({
    queryKey: ["runtime-policy", "actions", "all"],
    queryFn: ({ signal }) => listRuntimePolicyApprovals("all", signal),
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
  const outcomeSummaryQuery = useQuery({
    queryKey: ["outcomes", "actions", "summary", 30],
    queryFn: ({ signal }) => getOutcomeReconciliationSummary(30, signal),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
  const outcomesQuery = useQuery({
    queryKey: ["outcomes", "actions", "reconciliation"],
    queryFn: ({ signal }) => listOutcomeReconciliations({ verdict: "all", limit: 50 }, signal),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
  const sourceMutationSummaryQuery = useQuery({
    queryKey: ["outcomes", "actions", "source-mutations", "summary"],
    queryFn: ({ signal }) => getSourceMutationSummary(signal),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
  const unreceiptedMutationsQuery = useQuery({
    queryKey: ["outcomes", "actions", "source-mutations", "unreceipted"],
    queryFn: ({ signal }) => listUnreceiptedSourceMutations(20, signal),
    staleTime: 15_000,
    refetchInterval: 15_000,
  });

  const billing = billingQuery.data;
  const outcomeSummary = outcomeSummaryQuery.data;
  const sourceSummary = sourceMutationSummaryQuery.data;
  const decisions = useMemo(() => decisionsQuery.data?.items ?? [], [decisionsQuery.data?.items]);
  const outcomes = useMemo(() => outcomesQuery.data?.items ?? [], [outcomesQuery.data?.items]);
  const unreceiptedMutations = useMemo(
    () => unreceiptedMutationsQuery.data?.items ?? [],
    [unreceiptedMutationsQuery.data?.items],
  );
  const pending = decisions.filter((item) => item.status === "pending_approval").length;
  const bypassRisk = sourceSummary?.unreceipted ?? unreceiptedMutations.length;
  const protectedActionCount = billing?.protected_actions.used ?? 0;
  const mismatched = outcomeSummary?.mismatched ?? outcomes.filter((item) => item.verdict === "mismatched").length;
  const matched = outcomeSummary?.matched ?? outcomes.filter((item) => item.verdict === "matched").length;
  const notVerified = outcomeSummary?.not_verified ?? outcomes.filter((item) => item.verdict === "not_verified").length;
  const loading =
    billingQuery.isLoading ||
    decisionsQuery.isLoading ||
    outcomeSummaryQuery.isLoading ||
    outcomesQuery.isLoading ||
    sourceMutationSummaryQuery.isLoading ||
    unreceiptedMutationsQuery.isLoading;
  const hasError =
    billingQuery.isError ||
    decisionsQuery.isError ||
    outcomeSummaryQuery.isError ||
    outcomesQuery.isError ||
    sourceMutationSummaryQuery.isError ||
    unreceiptedMutationsQuery.isError;

  const rows = useMemo(
    () => buildRows({ decisions, outcomes, mutations: unreceiptedMutations }),
    [decisions, outcomes, unreceiptedMutations],
  );
  const selectedRow = rows.find((row) => row.key === selectedKey) ?? rows[0] ?? null;
  const hero = heroState({
    bypassRisk,
    error: hasError,
    loading,
    mismatched,
    pending,
    protectedActions: protectedActionCount,
  });

  useEffect(() => {
    if (rows.length === 0) {
      setSelectedKey(null);
      return;
    }
    if (!selectedKey || !rows.some((row) => row.key === selectedKey)) {
      setSelectedKey(rows[0].key);
    }
  }, [rows, selectedKey]);

  return (
    <main className="outcomes-cockpit actions-command-center">
      <section className="outcomes-hero" data-tone={hero.tone}>
        <div>
          <span className="eyebrow">Verified Action Control Plane</span>
          <h1>{hero.title}</h1>
          <p>{hero.copy}</p>
        </div>
        <div className="outcomes-hero-rail">
          <span className="outcome-hero-pill">{hero.pill}</span>
          <span className="outcome-hero-pill">Quota {formatMeter(billing?.protected_actions)}</span>
          <span className="outcome-hero-pill">Receipts {formatMeter(billing?.action_receipts)}</span>
        </div>
      </section>

      <section className="outcomes-metric-grid" aria-label="Protected action control metrics">
        <MetricCard
          Icon={ShieldCheck}
          label="Protected actions"
          value={formatMeter(billing?.protected_actions)}
          helper={meterHelper("Protected actions", billing?.protected_actions)}
          tone={protectedActionCount > 0 ? "success" : "neutral"}
        />
        <MetricCard
          Icon={Gauge}
          label="Policy checks"
          value={formatMeter(billing?.policy_checks)}
          helper={meterHelper("Policy checks", billing?.policy_checks)}
          tone={pending > 0 ? "warning" : "neutral"}
        />
        <MetricCard
          Icon={Workflow}
          label="Runner executions"
          value={formatMeter(billing?.runner_executions)}
          helper={meterHelper("Runner executions", billing?.runner_executions)}
          tone={(billing?.runner_executions.used ?? 0) > 0 ? "success" : "neutral"}
        />
        <MetricCard
          Icon={ReceiptText}
          label="Receipts"
          value={formatMeter(billing?.action_receipts)}
          helper={meterHelper("Action receipts", billing?.action_receipts)}
          tone={(billing?.action_receipts.used ?? 0) > 0 ? "success" : "warning"}
        />
        <MetricCard
          Icon={CheckCircle2}
          label="Verified outcomes"
          value={formatCount(matched)}
          helper={`${formatCount(mismatched)} mismatched / ${formatCount(notVerified)} not verified.`}
          tone={mismatched > 0 ? "danger" : notVerified > 0 ? "warning" : matched > 0 ? "success" : "neutral"}
        />
        <MetricCard
          Icon={ShieldAlert}
          label="Bypass risk"
          value={formatCount(bypassRisk)}
          helper={`${formatCount(sourceSummary?.policy_bypass ?? 0)} policy bypass / ${formatCount(sourceSummary?.unmanaged_agent_action ?? 0)} unmanaged.`}
          tone={bypassRisk > 0 ? "danger" : "success"}
        />
      </section>

      <section className="outcome-proof-contract" aria-label="Protected action lifecycle coverage">
        <div>
          <span className="eyebrow">Lifecycle coverage</span>
          <h2>Control, execution, verification, receipt, and bypass visibility are live.</h2>
          <p>These states are backed by billing meters, runtime policy decisions, system-of-record checks, and source mutation reconciliation.</p>
        </div>
        <div className="outcome-proof-state-grid">
          <article data-tone={pending > 0 ? "warning" : "success"}>
            <StatusPill value="policy" />
            <strong>{formatMeter(billing?.policy_checks)}</strong>
            <span>{formatCount(pending)} approval hold{pending === 1 ? "" : "s"}.</span>
          </article>
          <article data-tone={(billing?.runner_executions.used ?? 0) > 0 ? "success" : "warning"}>
            <StatusPill value="runner" />
            <strong>{formatMeter(billing?.runner_executions)}</strong>
            <span>Credential-isolated execution volume.</span>
          </article>
          <article data-tone={mismatched > 0 ? "danger" : notVerified > 0 ? "warning" : "success"}>
            <StatusPill value="verification" />
            <strong>{formatMeter(billing?.verification_checks)}</strong>
            <span>{formatCount(matched)} matched source-of-record check{matched === 1 ? "" : "s"}.</span>
          </article>
          <article data-tone={bypassRisk > 0 ? "danger" : "success"}>
            <StatusPill value="reconciliation" />
            <strong>{formatCount(bypassRisk)}</strong>
            <span>Unreceipted mutation{bypassRisk === 1 ? "" : "s"}.</span>
          </article>
        </div>
      </section>

      <div className="outcome-cockpit-grid">
        <ActionQueue rows={rows} selectedKey={selectedRow?.key ?? null} onSelect={setSelectedKey} />
        <SelectedActionPanel row={selectedRow} />
      </div>

      <section className="outcome-proof-contract" aria-label="Bypass risk watch">
        <div>
          <span className="eyebrow">Bypass watch</span>
          <h2>Source mutations must map back to a Zroky receipt or an approved exception.</h2>
          <p>Unreceipted mutations stay visible until matched, classified, or migrated behind the protected runner path.</p>
        </div>
        <div className="outcome-proof-state-grid">
          <article data-tone="success">
            <StatusPill value="matched_receipt" />
            <strong>{formatCount(sourceSummary?.matched_receipt ?? 0)}</strong>
            <span>Receipted source mutations.</span>
          </article>
          <article data-tone="warning">
            <StatusPill value="authorized_external" />
            <strong>{formatCount(sourceSummary?.authorized_external ?? 0)}</strong>
            <span>Approved outside Zroky.</span>
          </article>
          <article data-tone={bypassRisk > 0 ? "danger" : "success"}>
            <StatusPill value="unreceipted" />
            <strong>{formatCount(bypassRisk)}</strong>
            <span>Needs receipt matching.</span>
          </article>
        </div>
      </section>

      {hasError ? (
        <section className="outcome-proof-strip tone-danger" role="status">
          <div>
            <span className="eyebrow">Refresh status</span>
            <strong>One or more control feeds failed</strong>
            <p>Keep protected action launch review conservative until all feeds refresh cleanly.</p>
          </div>
          <AlertTriangle aria-hidden="true" />
        </section>
      ) : null}

      <div className="actions">
        <Link href="/approvals" className="btn btn-secondary">
          Approvals
        </Link>
        <Link href="/outcomes" className="btn btn-secondary">
          Verification
        </Link>
        <Link href="/evidence" className="btn btn-secondary">
          Evidence
        </Link>
        <Link href="/settings/billing" className="btn btn-primary">
          Billing
        </Link>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => {
            void Promise.all([
              billingQuery.refetch(),
              decisionsQuery.refetch(),
              outcomeSummaryQuery.refetch(),
              outcomesQuery.refetch(),
              sourceMutationSummaryQuery.refetch(),
              unreceiptedMutationsQuery.refetch(),
            ]);
          }}
        >
          <RefreshCw aria-hidden="true" size={14} />
          Refresh
        </button>
      </div>
    </main>
  );
}
