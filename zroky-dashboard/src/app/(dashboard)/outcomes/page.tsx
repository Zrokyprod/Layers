"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  Clock3,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import { formatCount, formatDateTime, formatUsd } from "@/lib/format";
import {
  useOutcomeReconciliationSummary,
  useOutcomeReconciliations,
  useSourceMutationSummary,
  useUnreceiptedSourceMutations,
} from "@/lib/hooks";
import type {
  OutcomeReconciliationVerdict,
  OutcomeReconciliationView,
  SourceMutationView,
} from "@/lib/api";

type Filter = OutcomeReconciliationVerdict | "all";
type VerdictTone = "danger" | "warning" | "success" | "neutral";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "mismatched", label: "Mismatched" },
  { id: "not_verified", label: "Not verified" },
  { id: "matched", label: "Matched" },
];

function compactJson(value: unknown): string {
  if (value == null) return "-";
  if (typeof value === "object" && Object.keys(value as Record<string, unknown>).length === 0) {
    return "{}";
  }
  return JSON.stringify(value, null, 2);
}

function field(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function humanize(value: string | null | undefined): string {
  if (!value) return "-";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\w/, (char) => char.toUpperCase());
}

function evidencePackHref(decisionId: string): string {
  return `/evidence?decision_id=${encodeURIComponent(decisionId)}`;
}

function verdictTone(verdict: OutcomeReconciliationVerdict): "danger" | "warning" | "success" {
  if (verdict === "mismatched") return "danger";
  if (verdict === "not_verified") return "warning";
  return "success";
}

function titleFor(item: OutcomeReconciliationView): string {
  const claimed = item.claimed;
  const summary = claimed.summary;
  if (typeof summary === "string" && summary.trim()) return summary;
  const refundId = claimed.refund_id;
  if (typeof refundId === "string" && refundId.trim()) return `Refund ${refundId}`;
  const paymentId = claimed.payment_id;
  if (typeof paymentId === "string" && paymentId.trim()) return `Payment ${paymentId}`;
  const email = claimed.email;
  if (typeof email === "string" && email.trim()) return `Email ${email}`;
  if (item.system_ref) return item.system_ref;
  return humanize(item.action_type) === "-" ? "Outcome check" : humanize(item.action_type);
}

function amountLabel(amountUsd: number | null, currency: string | null): string {
  if (amountUsd == null) return "-";
  if (!currency || currency.toUpperCase() === "USD") return formatUsd(amountUsd);
  return `${amountUsd.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${currency.toUpperCase()}`;
}

function searchMatches(item: OutcomeReconciliationView, search: string): boolean {
  const needle = search.trim().toLowerCase();
  if (!needle) return true;
  const haystack = [
    item.id,
    item.call_id,
    item.trace_id,
    item.action_type,
    item.connector_type,
    item.system_ref,
    item.verdict,
    item.reason,
    compactJson(item.claimed),
    compactJson(item.actual),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(needle);
}

function verifiedRate(total: number, matched: number): string {
  if (total <= 0) return "0%";
  return `${Math.round((matched / total) * 100)}%`;
}

function timeSince(value: string | null): string {
  if (!value) return "-";
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) return "-";
  const diff = Math.max(0, Date.now() - time);
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m old`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h old`;
  return `${Math.floor(hours / 24)}d old`;
}

function mismatchCount(item: OutcomeReconciliationView): number {
  const mismatches = item.comparison?.mismatches;
  return Array.isArray(mismatches) ? mismatches.length : 0;
}

function outcomePriority(item: OutcomeReconciliationView): { score: number; label: string; detail: string } {
  if (item.verdict === "mismatched") {
    const count = mismatchCount(item);
    return {
      score: 0,
      label: "P0",
      detail: count > 0 ? `${count} field mismatch${count === 1 ? "" : "es"}` : "system record differs",
    };
  }
  if (item.verdict === "not_verified") {
    return { score: 1, label: "P1", detail: "proof missing" };
  }
  return { score: 2, label: "P2", detail: "matched proof" };
}

function proofCopy(item: OutcomeReconciliationView): { title: string; body: string } {
  if (item.verdict === "mismatched") {
    return {
      title: "Outcome mismatch",
      body: "The agent claim does not match the real system outcome. Treat this path as unsafe until reconciled.",
    };
  }
  if (item.verdict === "not_verified") {
    return {
      title: "Not verified",
      body: "No trusted real-system proof is attached yet. Do not mark this agent action as complete.",
    };
  }
  return {
    title: "Outcome matched",
    body: "The claimed agent action matches the system-of-record reconciliation check.",
  };
}

function outcomesVerdict({
  total,
  matched,
  mismatched,
  notVerified,
  loading,
  isError,
}: {
  total: number;
  matched: number;
  mismatched: number;
  notVerified: number;
  loading: boolean;
  isError: boolean;
}): { title: string; description: string; pill: string; tone: VerdictTone } {
  if (isError) {
    return {
      title: "Outcome verification unavailable",
      description: "The system-of-record reconciliation layer could not refresh. Keep unresolved agent actions under review.",
      pill: "refresh failed",
      tone: "danger",
    };
  }
  if (loading) {
    return {
      title: "Loading outcome verification",
      description: "Fetching system-of-record checks, claimed actions, actual records, and comparison results.",
      pill: "loading",
      tone: "neutral",
    };
  }
  if (mismatched > 0) {
    const mismatchCopy =
      mismatched === 1
        ? "One outcome does"
        : `${mismatched} outcomes do`;
    return {
      title: "Agent outcome mismatch",
      description: `${mismatchCopy} not match the agent claim. Treat the affected action as unsafe until reconciled.`,
      pill: `${mismatched} mismatch${mismatched === 1 ? "" : "es"}`,
      tone: "danger",
    };
  }
  if (notVerified > 0) {
    const proofCopyText =
      notVerified === 1
        ? "One outcome is"
        : `${notVerified} outcomes are`;
    return {
      title: "Outcome not verified",
      description: `${proofCopyText} missing trusted system-of-record confirmation after the agent action.`,
      pill: `${notVerified} missing`,
      tone: "warning",
    };
  }
  if (total === 0) {
    return {
      title: "No real outcome checks",
      description: "Outcome reconciliation is ready. Verified and failed system-of-record checks will land here.",
      pill: "clear",
      tone: "neutral",
    };
  }
  return {
    title: "Agent outcomes verified",
    description: `${matched} checked outcome${matched === 1 ? "" : "s"} matched the system of record.`,
    pill: `${verifiedRate(total, matched)} verified`,
    tone: "success",
  };
}

function ageSort(a: OutcomeReconciliationView, b: OutcomeReconciliationView): number {
  return new Date(b.checked_at).getTime() - new Date(a.checked_at).getTime();
}

function OutcomeSetupPaths() {
  return (
    <section className="outcome-setup-paths" aria-label="Outcome verification setup paths">
      <div>
        <span className="eyebrow">Send proof here</span>
        <h2>SDK helper and webhook bridge land in the same verification queue.</h2>
        <p>
          Use the SDK when your agent code can call Zroky directly. Use the webhook bridge when a legacy or no-code agent can only POST after an action completes.
        </p>
      </div>
      <div className="outcome-setup-card-grid">
        <article>
          <strong>SDK outcome helper</strong>
          <span>
            Call <code>verifyOutcome()</code> or <code>verify_outcome()</code> after the risky action returns.
          </span>
          <Link href="/settings/keys?intent=protect-agent" className="btn btn-soft btn-sm">
            Open SDK setup
            <ArrowRight size={14} aria-hidden="true" />
          </Link>
        </article>
        <article>
          <strong>Webhook proof bridge</strong>
          <span>
            POST <code>/v1/outcomes/reconciliation/saved</code> with <code>x-api-key</code> and a saved connector.
          </span>
          <Link href="/integrations#generic-rest-connector" className="btn btn-soft btn-sm">
            Open bridge setup
            <ArrowRight size={14} aria-hidden="true" />
          </Link>
        </article>
      </div>
    </section>
  );
}

function OutcomeProofContract() {
  const states = [
    {
      label: "matched",
      title: "Safe to export",
      body: "Agent claim matches the real system-of-record outcome.",
      tone: "success",
    },
    {
      label: "mismatched",
      title: "Block the path",
      body: "Agent claim and actual record differ; treat the action as unsafe.",
      tone: "danger",
    },
    {
      label: "not_verified",
      title: "Do not trust yet",
      body: "No trusted source-of-record confirmation is attached.",
      tone: "warning",
    },
  ];

  return (
    <section className="outcome-proof-contract" aria-label="Outcome proof state contract">
      <div>
        <span className="eyebrow">Proof state contract</span>
        <h2>Every risky action must end as matched, mismatched, or not_verified.</h2>
        <p>Green agent output is not proof. Zroky only trusts a real connector read or a signed outcome callback.</p>
      </div>
      <div className="outcome-proof-state-grid">
        {states.map((state) => (
          <article key={state.label} data-tone={state.tone}>
            <StatusPill value={state.label} />
            <strong>{state.title}</strong>
            <span>{state.body}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

function mutationTitle(item: SourceMutationView): string {
  if (item.system_ref) return item.system_ref;
  if (item.resource_id) return item.resource_id;
  if (item.action_type) return humanize(item.action_type);
  return item.mutation_id;
}

function mutationTone(classification: string): "danger" | "warning" | "success" {
  if (classification === "policy_bypass") return "danger";
  if (classification === "matched_receipt" || classification === "authorized_external") return "success";
  return "warning";
}

function ReconciliationBypassWatch({
  summary,
  mutations,
  loading,
  isError,
}: {
  summary: {
    total: number;
    matched_receipt: number;
    authorized_external: number;
    legacy_path: number;
    unmanaged_agent_action: number;
    policy_bypass: number;
    unknown_actor: number;
    unreceipted: number;
  } | null;
  mutations: SourceMutationView[];
  loading: boolean;
  isError: boolean;
}) {
  const policyBypass = summary?.policy_bypass ?? 0;
  const unmanaged = summary?.unmanaged_agent_action ?? 0;
  const unknown = summary?.unknown_actor ?? 0;
  const matched = summary?.matched_receipt ?? 0;

  return (
    <section className="outcome-proof-contract" aria-label="Reconciliation bypass watch">
      <div>
        <span className="eyebrow">Bypass watch</span>
        <h2>Source mutations must map back to a signed Zroky receipt.</h2>
        <p>
          Unreceipted protected mutations show where an agent or legacy path changed the source of record outside the controlled runner loop.
        </p>
      </div>
      <div className="outcome-proof-state-grid">
        <article data-tone={policyBypass > 0 ? "danger" : "success"}>
          <StatusPill value={policyBypass > 0 ? "policy_bypass" : "clear"} />
          <strong>{formatCount(policyBypass)}</strong>
          <span>Policy bypass</span>
        </article>
        <article data-tone={unmanaged > 0 || unknown > 0 ? "warning" : "success"}>
          <StatusPill value={unmanaged > 0 || unknown > 0 ? "unreceipted" : "clear"} />
          <strong>{formatCount(unmanaged + unknown)}</strong>
          <span>Unmanaged or unknown actor</span>
        </article>
        <article data-tone="success">
          <StatusPill value="matched_receipt" />
          <strong>{formatCount(matched)}</strong>
          <span>Matched receipts</span>
        </article>
      </div>

      {isError ? (
        <div className="notice error">Source mutation reconciliation is unavailable.</div>
      ) : loading ? (
        <div className="empty">Loading source mutations...</div>
      ) : mutations.length === 0 ? (
        <div className="empty-state">No unreceipted source mutations in the current project.</div>
      ) : (
        <div className="outcome-queue-list" aria-label="Unreceipted source mutations">
          {mutations.slice(0, 6).map((item) => (
            <div
              key={item.id}
              className={`outcome-queue-row tone-${mutationTone(item.classification)}`}
            >
              <span className="outcome-priority">{item.classification === "policy_bypass" ? "P0" : "P1"}</span>
              <span className="outcome-queue-main">
                <strong>{mutationTitle(item)}</strong>
                <small>
                  {humanize(item.source_system)} / {humanize(item.actor_type)}
                </small>
                <em>{humanize(item.classification)}</em>
              </span>
              <span className="outcome-queue-side">
                <StatusPill value={item.classification} />
                <small>{timeSince(item.occurred_at)}</small>
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function OutcomeQueue({
  items,
  selectedId,
  onSelect,
}: {
  items: OutcomeReconciliationView[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <section className="outcome-queue-panel" aria-label="Real outcome verification queue">
      <div className="outcome-panel-head">
        <div>
          <span className="eyebrow">Real outcome queue</span>
          <strong>{items.length} verification check{items.length === 1 ? "" : "s"}</strong>
        </div>
        <span className="outcome-live-dot">live</span>
      </div>
      <div className="outcome-queue-list">
        {items.map((item) => {
          const priority = outcomePriority(item);
          const selected = item.id === selectedId;
          return (
            <button
              key={item.id}
              type="button"
              className={`outcome-queue-row tone-${verdictTone(item.verdict)}${selected ? " selected" : ""}`}
              onClick={() => onSelect(item.id)}
            >
              <span className="outcome-priority">{priority.label}</span>
              <span className="outcome-queue-main">
                <strong>{titleFor(item)}</strong>
                <small>
                  {item.system_ref ?? "No system reference"} / {humanize(item.connector_type)}
                </small>
                <em>{priority.detail}</em>
              </span>
              <span className="outcome-queue-side">
                <StatusPill value={item.verdict} />
                <small>{timeSince(item.checked_at)}</small>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function OutcomeInspector({ item }: { item: OutcomeReconciliationView | null }) {
  if (!item) {
    return (
      <section className="outcome-inspector-panel empty-state">
        <ShieldCheck size={22} aria-hidden="true" />
        <h2>Select an outcome check.</h2>
        <p>Verification evidence appears here after a connector compares the agent claim to the real system record.</p>
      </section>
    );
  }

  const proof = proofCopy(item);

  return (
    <section className="outcome-inspector-panel" aria-label="Selected outcome verification">
      <div className="outcome-inspector-header">
        <div>
          <span className="eyebrow">Agent claim vs real outcome</span>
          <h2>{titleFor(item)}</h2>
          <p>
            {item.system_ref ?? "No system reference"} / {humanize(item.reason)}
          </p>
        </div>
        <StatusPill value={item.verdict} />
      </div>

      <section className={`outcome-proof-strip tone-${verdictTone(item.verdict)}`}>
        <div>
          <span className="eyebrow">Verification result</span>
          <strong>{proof.title}</strong>
          <p>{proof.body}</p>
        </div>
        <strong>{amountLabel(item.amount_usd, item.currency)}</strong>
      </section>

      <dl className="outcome-inspector-metrics">
        <div>
          <dt>Action</dt>
          <dd>{humanize(item.action_type)}</dd>
        </div>
        <div>
          <dt>Amount</dt>
          <dd>{amountLabel(item.amount_usd, item.currency)}</dd>
        </div>
        <div>
          <dt>System ref</dt>
          <dd>{field(item.system_ref)}</dd>
        </div>
        <div>
          <dt>Checked</dt>
          <dd>{formatDateTime(item.checked_at)}</dd>
        </div>
        <div>
          <dt>Call evidence</dt>
          <dd>
            {item.call_id ? (
              <Link href="/evidence">{item.call_id}</Link>
            ) : (
              "-"
            )}
          </dd>
        </div>
        <div>
          <dt>Trace evidence</dt>
          <dd>
            {item.trace_id ? (
              <Link href="/evidence">{item.trace_id}</Link>
            ) : (
              "-"
            )}
          </dd>
        </div>
        <div>
          <dt>Evidence Pack</dt>
          <dd>
            {item.runtime_policy_decision_id ? (
              <Link href={evidencePackHref(item.runtime_policy_decision_id)}>Open Evidence Pack</Link>
            ) : (
              "not_linked"
            )}
          </dd>
        </div>
        <div>
          <dt>Idempotency</dt>
          <dd>{field(item.idempotency_key)}</dd>
        </div>
        <div>
          <dt>Check ID</dt>
          <dd>{item.id}</dd>
        </div>
      </dl>

      <div className="outcome-inspector-grid">
        <section>
          <h4>Agent claim</h4>
          <pre>{compactJson(item.claimed)}</pre>
        </section>
        <section>
          <h4>Actual system record</h4>
          <pre>{compactJson(item.actual)}</pre>
        </section>
        <section>
          <h4>Field comparison</h4>
          <pre>{compactJson(item.comparison)}</pre>
        </section>
        <section>
          <h4>Connector metadata</h4>
          <pre>{compactJson(item.metadata)}</pre>
        </section>
      </div>
    </section>
  );
}

export default function OutcomesPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [selectedCheckId, setSelectedCheckId] = useState<string | null>(null);
  const summaryQuery = useOutcomeReconciliationSummary(30);
  const checksQuery = useOutcomeReconciliations(filter, 50);
  const sourceMutationSummaryQuery = useSourceMutationSummary();
  const unreceiptedMutationsQuery = useUnreceiptedSourceMutations(20);

  const summary = summaryQuery.data;
  const visibleItems = useMemo(
    () =>
      (checksQuery.data?.items ?? [])
        .filter((item) => searchMatches(item, search))
        .sort((a, b) => {
          const priorityDiff = outcomePriority(a).score - outcomePriority(b).score;
          if (priorityDiff !== 0) return priorityDiff;
          return ageSort(a, b);
        }),
    [checksQuery.data?.items, search],
  );
  const selectedItem = useMemo(
    () => visibleItems.find((item) => item.id === selectedCheckId) ?? visibleItems[0] ?? null,
    [selectedCheckId, visibleItems],
  );
  const mismatchCount = summary?.mismatched ?? 0;
  const notVerifiedCount = summary?.not_verified ?? 0;
  const matchedCount = summary?.matched ?? 0;
  const totalCount = summary?.total ?? 0;
  const loading = checksQuery.isLoading || summaryQuery.isLoading;
  const fetching =
    checksQuery.isFetching ||
    summaryQuery.isFetching ||
    sourceMutationSummaryQuery.isFetching ||
    unreceiptedMutationsQuery.isFetching;
  const hero = outcomesVerdict({
    total: totalCount,
    matched: matchedCount,
    mismatched: mismatchCount,
    notVerified: notVerifiedCount,
    loading,
    isError: summaryQuery.isError || checksQuery.isError,
  });

  useEffect(() => {
    if (visibleItems.length === 0) {
      setSelectedCheckId(null);
      return;
    }
    if (!selectedCheckId || !visibleItems.some((item) => item.id === selectedCheckId)) {
      setSelectedCheckId(visibleItems[0].id);
    }
  }, [selectedCheckId, visibleItems]);

  return (
    <div className="dashboard-page outcome-verification-page outcomes-cockpit">
      <section className="outcomes-hero" data-tone={hero.tone}>
        <div>
          <span className="eyebrow">Outcome verification</span>
          <h1>{hero.title}</h1>
          <p>{hero.description}</p>
        </div>
        <div className="outcomes-hero-rail">
          <span className="outcome-hero-pill">{hero.pill}</span>
          <button
            className="btn btn-secondary"
            type="button"
            onClick={() => {
              void summaryQuery.refetch();
              void checksQuery.refetch();
              void sourceMutationSummaryQuery.refetch();
              void unreceiptedMutationsQuery.refetch();
            }}
            disabled={fetching}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
      </section>

      <section className="outcomes-metric-grid" aria-label="Outcome reconciliation summary">
        <article className="outcome-metric-card tone-danger">
          <AlertTriangle size={18} />
          <span>Mismatched</span>
          <strong>{formatCount(mismatchCount)}</strong>
        </article>
        <article className="outcome-metric-card tone-warning">
          <Clock3 size={18} />
          <span>Not verified</span>
          <strong>{formatCount(notVerifiedCount)}</strong>
        </article>
        <article className="outcome-metric-card tone-success">
          <CheckCircle size={18} />
          <span>Matched</span>
          <strong>{formatCount(matchedCount)}</strong>
        </article>
        <article className="outcome-metric-card tone-neutral">
          <ShieldCheck size={18} />
          <span>Matched rate</span>
          <strong>{verifiedRate(totalCount, matchedCount)}</strong>
        </article>
      </section>

      <OutcomeSetupPaths />

      <OutcomeProofContract />

      <ReconciliationBypassWatch
        summary={sourceMutationSummaryQuery.data ?? null}
        mutations={unreceiptedMutationsQuery.data?.items ?? []}
        loading={sourceMutationSummaryQuery.isLoading || unreceiptedMutationsQuery.isLoading}
        isError={sourceMutationSummaryQuery.isError || unreceiptedMutationsQuery.isError}
      />

      <section className="outcome-filter-bar outcome-cockpit-toolbar" aria-label="Outcome filters">
        <div className="filter-bar" aria-label="Verdict filters">
          {FILTERS.map((item) => (
            <button
              key={item.id}
              className={`filter-chip ${filter === item.id ? "active" : ""}`}
              type="button"
              onClick={() => setFilter(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <label className="outcome-search-field">
          <span>Search</span>
          <div>
            <Search size={15} aria-hidden="true" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="System ref, call, trace, action, claim..."
            />
          </div>
        </label>
        <span>{fetching ? "Refreshing outcome verification..." : "Outcome verification live"}</span>
      </section>

      {summaryQuery.isError ? (
        <div className="notice error">{summaryQuery.error.message}</div>
      ) : null}

      {checksQuery.isError ? (
        <div className="empty error">{checksQuery.error.message}</div>
      ) : loading ? (
        <div className="empty">Loading outcome checks...</div>
      ) : visibleItems.length === 0 ? (
        <section className="outcome-empty-state">
          <ShieldCheck size={24} aria-hidden="true" />
          <h2>No outcome verification checks in this view.</h2>
          <p>
            {search.trim()
              ? "No outcome verification checks match this search."
              : "No system-of-record verification checks in this view."}
          </p>
        </section>
      ) : (
        <section className="outcome-cockpit-grid">
          <OutcomeQueue
            items={visibleItems}
            selectedId={selectedItem?.id ?? null}
            onSelect={setSelectedCheckId}
          />
          <OutcomeInspector item={selectedItem} />
        </section>
      )}
    </div>
  );
}
