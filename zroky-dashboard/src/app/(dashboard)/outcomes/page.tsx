"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
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

function ReconciliationCard({ item }: { item: OutcomeReconciliationView }) {
  return (
    <article className={`panel outcome-check-card tone-${verdictTone(item.verdict)}`}>
      <div className="outcome-check-header">
        <div>
          <span className="eyebrow">{item.connector_type}</span>
          <h3>{titleFor(item)}</h3>
          <p>
            {item.system_ref ?? "No system reference"} · {humanize(item.reason)}
          </p>
        </div>
        <StatusPill value={item.verdict} />
      </div>

      <dl className="approval-meta-grid outcome-meta-grid">
        <div>
          <dt>Action</dt>
          <dd>{humanize(item.action_type)}</dd>
        </div>
        <div>
          <dt>Amount</dt>
          <dd>{amountLabel(item.amount_usd, item.currency)}</dd>
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
          <dt>Checked</dt>
          <dd>{formatDateTime(item.checked_at)}</dd>
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

      <div className="approval-evidence-grid outcome-evidence-grid">
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
    </article>
  );
}

export default function OutcomesPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const summaryQuery = useOutcomeReconciliationSummary(30);
  const checksQuery = useOutcomeReconciliations(filter, 50);

  const summary = summaryQuery.data;
  const visibleItems = useMemo(
    () => (checksQuery.data?.items ?? []).filter((item) => searchMatches(item, search)),
    [checksQuery.data?.items, search],
  );
  const mismatchCount = summary?.mismatched ?? 0;
  const notVerifiedCount = summary?.not_verified ?? 0;
  const matchedCount = summary?.matched ?? 0;
  const totalCount = summary?.total ?? 0;
  const loading = checksQuery.isLoading || summaryQuery.isLoading;
  const fetching = checksQuery.isFetching || summaryQuery.isFetching;

  return (
    <div className="dashboard-page outcome-verification-page">
      <section className="page-header">
        <div>
          <span className="eyebrow">Outcome verification</span>
          <h1>Outcomes</h1>
          <p>Real-world action checks against the system of record.</p>
        </div>
        <div className="page-actions">
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

      <section className="metric-grid compact" aria-label="Outcome reconciliation summary">
        <article className="metric-card tone-danger">
          <AlertTriangle size={18} />
          <span>Mismatched</span>
          <strong>{formatCount(mismatchCount)}</strong>
        </article>
        <article className="metric-card tone-warning">
          <Clock3 size={18} />
          <span>Not verified</span>
          <strong>{formatCount(notVerifiedCount)}</strong>
        </article>
        <article className="metric-card tone-success">
          <CheckCircle size={18} />
          <span>Matched</span>
          <strong>{formatCount(matchedCount)}</strong>
        </article>
        <article className="metric-card tone-neutral">
          <ShieldCheck size={18} />
          <span>Verified rate</span>
          <strong>{verifiedRate(totalCount, matchedCount)}</strong>
        </article>
      </section>

      <section className="outcome-filter-bar" aria-label="Outcome filters">
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
      </section>

      {summaryQuery.isError ? (
        <div className="notice error">{summaryQuery.error.message}</div>
      ) : null}

      {checksQuery.isError ? (
        <div className="empty error">{checksQuery.error.message}</div>
      ) : loading ? (
        <div className="empty">Loading outcome checks...</div>
      ) : visibleItems.length === 0 ? (
        <div className="empty">
          {search.trim()
            ? "No outcome checks match this search."
            : "No outcome reconciliation checks in this view."}
        </div>
      ) : (
        <section className="outcome-check-list">
          {visibleItems.map((item) => (
            <ReconciliationCard key={item.id} item={item} />
          ))}
        </section>
      )}
    </div>
  );
}
