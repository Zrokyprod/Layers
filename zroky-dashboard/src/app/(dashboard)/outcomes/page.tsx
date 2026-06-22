"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
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
} from "@/lib/hooks";
import type {
  OutcomeReconciliationVerdict,
  OutcomeReconciliationView,
} from "@/lib/api";

type Filter = OutcomeReconciliationVerdict | "all";

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
      body: "The agent claim does not match the system of record. Treat this path as unsafe until reconciled.",
    };
  }
  if (item.verdict === "not_verified") {
    return {
      title: "Not verified",
      body: "No trusted system-of-record proof is attached yet. Do not mark this action as complete.",
    };
  }
  return {
    title: "Outcome matched",
    body: "The claimed action matches the system-of-record reconciliation check.",
  };
}

function ageSort(a: OutcomeReconciliationView, b: OutcomeReconciliationView): number {
  return new Date(b.checked_at).getTime() - new Date(a.checked_at).getTime();
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
    <section className="outcome-queue-panel" aria-label="Outcome check queue">
      <div className="outcome-panel-head">
        <div>
          <span className="eyebrow">Verification queue</span>
          <strong>{items.length} loaded check{items.length === 1 ? "" : "s"}</strong>
        </div>
        <span className="outcome-live-dot">proof</span>
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
        <p>Reconciliation evidence will appear here after a connector compares the agent claim to ground truth.</p>
      </section>
    );
  }

  const proof = proofCopy(item);

  return (
    <section className="outcome-inspector-panel" aria-label="Selected outcome inspector">
      <div className="outcome-inspector-header">
        <div>
          <span className="eyebrow">Selected outcome</span>
          <h2>{titleFor(item)}</h2>
          <p>
            {item.system_ref ?? "No system reference"} / {humanize(item.reason)}
          </p>
        </div>
        <StatusPill value={item.verdict} />
      </div>

      <section className={`outcome-proof-strip tone-${verdictTone(item.verdict)}`}>
        <div>
          <span className="eyebrow">Ground truth status</span>
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
          <dt>System</dt>
          <dd>{field(item.system_ref)}</dd>
        </div>
        <div>
          <dt>Checked</dt>
          <dd>{formatDateTime(item.checked_at)}</dd>
        </div>
        <div>
          <dt>Call</dt>
          <dd>
            {item.call_id ? (
              <Link href={`/calls/${encodeURIComponent(item.call_id)}`}>{item.call_id}</Link>
            ) : (
              "-"
            )}
          </dd>
        </div>
        <div>
          <dt>Trace</dt>
          <dd>
            {item.trace_id ? (
              <Link href={`/trace/${encodeURIComponent(item.trace_id)}`}>{item.trace_id}</Link>
            ) : (
              "-"
            )}
          </dd>
        </div>
        <div>
          <dt>Policy decision</dt>
          <dd>{field(item.runtime_policy_decision_id)}</dd>
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
          <h4>Claimed outcome</h4>
          <pre>{compactJson(item.claimed)}</pre>
        </section>
        <section>
          <h4>System record</h4>
          <pre>{compactJson(item.actual)}</pre>
        </section>
        <section>
          <h4>Comparison</h4>
          <pre>{compactJson(item.comparison)}</pre>
        </section>
        <section>
          <h4>Metadata</h4>
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
  const fetching = checksQuery.isFetching || summaryQuery.isFetching;

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
      <section className="outcomes-hero">
        <div>
          <span className="eyebrow">Outcome verification</span>
          <h1>Outcomes</h1>
          <p>Prove what actually landed in the system of record after an agent says the action succeeded.</p>
        </div>
        <div className="outcomes-hero-rail">
          <span className="outcome-hero-pill">{formatCount(totalCount)} checks</span>
          <button
            className="btn btn-secondary"
            type="button"
            onClick={() => {
              void summaryQuery.refetch();
              void checksQuery.refetch();
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
          <span>Verified rate</span>
          <strong>{verifiedRate(totalCount, matchedCount)}</strong>
        </article>
      </section>

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
              placeholder="System ref, call, trace, action..."
            />
          </div>
        </label>
        <span>{fetching ? "Refreshing reconciliation..." : "Ground-truth queue is live"}</span>
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
          <h2>No outcome checks in this view.</h2>
          <p>
          {search.trim()
            ? "No outcome checks match this search."
            : "No outcome reconciliation checks in this view."}
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
