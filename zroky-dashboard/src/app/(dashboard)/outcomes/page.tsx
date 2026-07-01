"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  ExternalLink,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { DashboardMetricStrip, DashboardVerdictHero, DashboardWorkspace, type DashboardMetric } from "@/components/dashboard-scaffold";
import { StatusPill } from "@/components/status-pill";
import { statusLabel, type StatusTone } from "@/lib/action-status";
import { compactJson, field, formatCount, formatDateTime, humanize, timeSince } from "@/lib/format";
import {
  buildClaimedActualDiff,
  buildOutcomeLedger,
  type OutcomeDiffRow,
  type OutcomeLedger,
  type OutcomeLedgerFilter,
  type OutcomeLedgerRow,
} from "@/lib/outcome-ledger";
import {
  useOutcomeReconciliationSummary,
  useOutcomeReconciliations,
  useSourceMutationSummary,
  useUnreceiptedSourceMutations,
} from "@/lib/hooks";

const FILTERS: Array<{ id: OutcomeLedgerFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "mismatched", label: "Mismatched" },
  { id: "not_verified", label: "Not verified" },
  { id: "matched", label: "Matched" },
];

function initialCheckId(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("check_id");
}

function verdictFor({
  bypass,
  isError,
  matched,
  mismatched,
  notVerified,
  total,
}: {
  bypass: number;
  isError: boolean;
  matched: number;
  mismatched: number;
  notVerified: number;
  total: number;
}): { copy: string; pill: string; title: string; tone: StatusTone | "setup" } {
  if (isError) {
    return {
      copy: "System-of-record verification did not refresh cleanly. Keep the affected agent actions under review.",
      pill: "Refresh failed",
      title: "Outcome visibility unavailable",
      tone: "danger",
    };
  }
  if (mismatched > 0) {
    return {
      copy: `${formatCount(total)} actions checked, ${formatCount(mismatched)} mismatched against the real system. Inspect the selected diff before trusting the action.`,
      pill: `${formatCount(mismatched)} mismatch${mismatched === 1 ? "" : "es"}`,
      title: "Verified action mismatch",
      tone: "danger",
    };
  }
  if (bypass > 0) {
    return {
      copy: `${formatCount(bypass)} source mutation${bypass === 1 ? "" : "s"} have no Zroky receipt. Investigate possible bypass or unmanaged automation.`,
      pill: `${formatCount(bypass)} unreceipted`,
      title: "Bypass risk detected",
      tone: "danger",
    };
  }
  if (notVerified > 0) {
    return {
      copy: `${formatCount(notVerified)} controlled action${notVerified === 1 ? "" : "s"} still need independent source-of-record confirmation.`,
      pill: `${formatCount(notVerified)} not verified`,
      title: "Verification incomplete",
      tone: "warning",
    };
  }
  if (total === 0) {
    return {
      copy: "No outcome checks yet. Verified source-of-record reads will appear here after protected actions execute.",
      pill: "No checks",
      title: "No outcome checks yet",
      tone: "neutral",
    };
  }
  return {
    copy: `${formatCount(matched)} checked action${matched === 1 ? "" : "s"} matched the system of record.`,
    pill: "All matched",
    title: "All outcomes verified",
    tone: "success",
  };
}

function metricsFor(ledger: OutcomeLedger): DashboardMetric[] {
  return [
    {
      helper: "Claim equals actual record",
      icon: <CheckCircle2 size={16} />,
      id: "matched",
      label: "Verified",
      tone: "success",
      value: formatCount(ledger.counts.matched),
    },
    {
      helper: "Claim differs from reality",
      icon: <AlertTriangle size={16} />,
      id: "mismatched",
      label: "Mismatched",
      tone: ledger.counts.mismatched > 0 ? "danger" : "neutral",
      value: formatCount(ledger.counts.mismatched),
    },
    {
      helper: "Connector proof missing",
      icon: <Clock3 size={16} />,
      id: "not_verified",
      label: "Not verified",
      tone: ledger.counts.notVerified > 0 ? "warning" : "neutral",
      value: formatCount(ledger.counts.notVerified),
    },
    {
      helper: "System changes with no receipt",
      icon: <ShieldAlert size={16} />,
      id: "bypass",
      label: "Bypass risk",
      tone: ledger.counts.bypass > 0 ? "danger" : "neutral",
      value: formatCount(ledger.counts.bypass),
    },
    {
      helper: "Matched / total checks",
      icon: <ShieldCheck size={16} />,
      id: "rate",
      label: "Verified rate",
      tone: ledger.counts.verifiedRate === 100 && ledger.counts.total > 0 ? "success" : "neutral",
      value: `${ledger.counts.verifiedRate}%`,
    },
  ];
}

function OutcomeFeed({
  filter,
  loading,
  onFilterChange,
  onSearchChange,
  onSelect,
  rows,
  search,
  selectedId,
}: {
  filter: OutcomeLedgerFilter;
  loading: boolean;
  onFilterChange: (filter: OutcomeLedgerFilter) => void;
  onSearchChange: (value: string) => void;
  onSelect: (row: OutcomeLedgerRow) => void;
  rows: OutcomeLedgerRow[];
  search: string;
  selectedId: string | null;
}) {
  return (
    <section className="outcomes-feed-panel" aria-label="Reconciliation feed">
      <div className="outcomes-panel-head">
        <div>
          <span className="dashboard-eyebrow">Reconciliation feed</span>
          <h2>{formatCount(rows.length)} proof check{rows.length === 1 ? "" : "s"}</h2>
        </div>
        <span className="outcomes-live-chip">{loading ? "Refreshing" : "Live"}</span>
      </div>

      <div className="outcomes-toolbar" aria-label="Outcome filters">
        <div className="outcomes-filter-group">
          {FILTERS.map((item) => (
            <button
              key={item.id}
              className={`outcomes-filter-chip${filter === item.id ? " is-active" : ""}`}
              type="button"
              onClick={() => onFilterChange(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <label className="outcomes-search">
          <Search size={14} aria-hidden="true" />
          <input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search system ref, connector, claim..."
          />
        </label>
      </div>

      {rows.length === 0 ? (
        <div className="outcomes-empty-state">
          <ShieldCheck size={20} aria-hidden="true" />
          <strong>No outcome checks match this view.</strong>
          <p>Matched, mismatched, and not_verified checks will appear here after connector reconciliation.</p>
        </div>
      ) : (
        <div className="outcomes-feed-list">
          {rows.map((row) => (
            <button
              key={row.id}
              className={`outcomes-feed-row tone-${row.tone}${selectedId === row.id ? " is-selected" : ""}`}
              type="button"
              onClick={() => onSelect(row)}
            >
              <span className="outcomes-row-status">
                <StatusPill value={row.verdict} />
              </span>
              <span className="outcomes-row-main">
                <strong>{row.title}</strong>
                <small>{row.agentLabel} / {row.actionType}</small>
                <em>{row.detail}</em>
              </span>
              <span className="outcomes-row-side">
                <span>{row.amountLabel}</span>
                <small>{timeSince(row.checkedAt)}</small>
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function DiffTable({ rows }: { rows: OutcomeDiffRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="outcomes-diff-empty">
        <strong>No comparable fields.</strong>
        <p>The connector did not return a field-level comparison for this check.</p>
      </div>
    );
  }

  return (
    <div className="outcomes-diff-table" role="table" aria-label="Claimed versus actual field comparison">
      <div className="outcomes-diff-head" role="row">
        <span role="columnheader">Field</span>
        <span role="columnheader">Claimed</span>
        <span role="columnheader">Actual</span>
        <span role="columnheader">Verdict</span>
      </div>
      {rows.map((row) => (
        <div key={row.field} className="outcomes-diff-row" data-tone={row.tone} role="row">
          <span role="cell" className="mono">{row.field}</span>
          <span role="cell">{row.claimed}</span>
          <span role="cell">{row.actual}</span>
          <span role="cell"><StatusPill value={row.status} /></span>
        </div>
      ))}
    </div>
  );
}

function OutcomeInspector({ row }: { row: OutcomeLedgerRow | null }) {
  if (!row) {
    return (
      <section className="outcomes-inspector-panel outcomes-empty-state" aria-label="Selected outcome check">
        <ShieldCheck size={22} aria-hidden="true" />
        <strong>Select a verification check.</strong>
        <p>Claimed-vs-actual comparison will appear here.</p>
      </section>
    );
  }

  const check = row.check;
  const diffRows = buildClaimedActualDiff(check);

  return (
    <section className="outcomes-inspector-panel" aria-label="Selected outcome check">
      <div className="outcomes-inspector-header">
        <div>
          <span className="dashboard-eyebrow">Claim vs reality</span>
          <h2>{row.title}</h2>
          <p>{row.systemRef} / {row.reasonLabel}</p>
        </div>
        <StatusPill value={row.verdict} />
      </div>

      <div className="outcomes-proof-callout" data-tone={row.tone}>
        <div>
          <span className="dashboard-eyebrow">Verification result</span>
          <strong>{statusLabel(row.verdict, "proof")}</strong>
          <p>
            {row.verdict === "mismatched"
              ? "The agent claim differs from the system-of-record response."
              : row.verdict === "not_verified"
                ? "The real system could not provide trusted proof yet."
                : "The connector confirmed the claim against the actual record."}
          </p>
        </div>
        <strong>{row.amountLabel}</strong>
      </div>

      <dl className="outcomes-fact-grid">
        <div>
          <dt>Agent</dt>
          <dd>{row.agentLabel}</dd>
        </div>
        <div>
          <dt>Connector</dt>
          <dd>{row.connectorLabel}</dd>
        </div>
        <div>
          <dt>Action</dt>
          <dd>{row.actionType}</dd>
        </div>
        <div>
          <dt>Checked</dt>
          <dd>{formatDateTime(row.checkedAt)}</dd>
        </div>
        <div>
          <dt>System ref</dt>
          <dd className="mono">{row.systemRef}</dd>
        </div>
        <div>
          <dt>Check id</dt>
          <dd className="mono">{row.id}</dd>
        </div>
      </dl>

      <section className="outcomes-diff-section">
        <div className="outcomes-section-head">
          <span className="dashboard-eyebrow">Field diff</span>
          <strong>Claimed vs actual</strong>
        </div>
        <DiffTable rows={diffRows} />
      </section>

      <div className="outcomes-inspector-actions">
        {row.evidenceHref ? (
          <DashboardButtonLink href={row.evidenceHref} variant="primary" icon={<ExternalLink size={14} />}>
            Open signed evidence
          </DashboardButtonLink>
        ) : null}
        {row.actionHref ? (
          <DashboardButtonLink href={row.actionHref} variant="soft" icon={<ExternalLink size={14} />}>
            Open action
          </DashboardButtonLink>
        ) : null}
      </div>

      <details className="outcomes-json-details">
        <summary>Raw connector payload</summary>
        <div className="outcomes-json-grid">
          <section>
            <h3>Claimed</h3>
            <pre>{compactJson(check.claimed)}</pre>
          </section>
          <section>
            <h3>Actual</h3>
            <pre>{compactJson(check.actual)}</pre>
          </section>
          <section>
            <h3>Comparison</h3>
            <pre>{compactJson(check.comparison)}</pre>
          </section>
          <section>
            <h3>Metadata</h3>
            <pre>{compactJson(check.metadata)}</pre>
          </section>
        </div>
      </details>
    </section>
  );
}

function BypassStrip({ ledger }: { ledger: OutcomeLedger }) {
  return (
    <section className="outcomes-bypass-strip" data-tone={ledger.counts.bypass > 0 ? "danger" : "success"} aria-label="Bypass risk">
      <div className="outcomes-bypass-copy">
        <span className="dashboard-eyebrow">Bypass detection</span>
        <h2>{ledger.counts.bypass > 0 ? `${formatCount(ledger.counts.bypass)} system changes with no receipt` : "No unreceipted source mutations"}</h2>
        <p>Source mutations must map back to a Zroky receipt. Anything else is a bypass risk or unmanaged path.</p>
      </div>
      {ledger.bypassRows.length > 0 ? (
        <div className="outcomes-bypass-list">
          {ledger.bypassRows.slice(0, 4).map((row) => (
            <article key={row.id} className="outcomes-bypass-row" data-tone={row.tone}>
              <StatusPill value={row.classification} />
              <strong>{row.title}</strong>
              <span>{row.actorLabel} / {row.detail}</span>
              <small>{timeSince(row.occurredAt)}</small>
            </article>
          ))}
        </div>
      ) : (
        <div className="outcomes-bypass-clear">
          <StatusPill value="clear" />
          <span>All observed protected mutations are receipted or authorized.</span>
        </div>
      )}
    </section>
  );
}

export default function OutcomesPage() {
  const [filter, setFilter] = useState<OutcomeLedgerFilter>("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(() => initialCheckId());

  const summaryQuery = useOutcomeReconciliationSummary(30);
  const checksQuery = useOutcomeReconciliations("all", 100);
  const sourceMutationSummaryQuery = useSourceMutationSummary();
  const unreceiptedMutationsQuery = useUnreceiptedSourceMutations(50);

  const checks = checksQuery.data?.items ?? [];
  const ledger = useMemo(
    () => buildOutcomeLedger({
      checks,
      filter,
      mutations: unreceiptedMutationsQuery.data?.items ?? [],
      search,
    }),
    [checks, filter, search, unreceiptedMutationsQuery.data?.items],
  );
  const selectedRow = useMemo(
    () => ledger.rows.find((row) => row.id === selectedId) ?? ledger.rows[0] ?? null,
    [ledger.rows, selectedId],
  );

  useEffect(() => {
    if (ledger.rows.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!selectedRow) setSelectedId(ledger.rows[0]?.id ?? null);
  }, [ledger.rows, selectedRow]);

  const summaryMismatch = summaryQuery.data?.mismatched ?? ledger.counts.mismatched;
  const summaryNotVerified = summaryQuery.data?.not_verified ?? ledger.counts.notVerified;
  const summaryMatched = summaryQuery.data?.matched ?? ledger.counts.matched;
  const summaryTotal = summaryQuery.data?.total ?? ledger.counts.total;
  const bypassCount = sourceMutationSummaryQuery.data?.unreceipted ?? ledger.counts.bypass;
  const loading = checksQuery.isLoading || summaryQuery.isLoading;
  const fetching =
    checksQuery.isFetching ||
    summaryQuery.isFetching ||
    sourceMutationSummaryQuery.isFetching ||
    unreceiptedMutationsQuery.isFetching;
  const isError =
    checksQuery.isError ||
    summaryQuery.isError ||
    sourceMutationSummaryQuery.isError ||
    unreceiptedMutationsQuery.isError;
  const verdict = verdictFor({
    bypass: bypassCount,
    isError,
    matched: summaryMatched,
    mismatched: summaryMismatch,
    notVerified: summaryNotVerified,
    total: summaryTotal,
  });

  function refresh() {
    void checksQuery.refetch();
    void summaryQuery.refetch();
    void sourceMutationSummaryQuery.refetch();
    void unreceiptedMutationsQuery.refetch();
  }

  return (
    <div className="dashboard-page outcomes-page">
      <DashboardVerdictHero
        actions={
          <DashboardButton
            icon={<RefreshCw size={15} />}
            loading={fetching}
            onClick={refresh}
            variant="soft"
          >
            Refresh
          </DashboardButton>
        }
        ariaLabel="Outcome verification verdict"
        copy={verdict.copy}
        eyebrow="Outcomes"
        icon={<ShieldCheck size={20} />}
        pill={verdict.pill}
        tone={verdict.tone}
        title={verdict.title}
        updatedLabel={loading ? "Loading" : "Live"}
      />

      <DashboardMetricStrip
        ariaLabel="Outcome verification metrics"
        columns={5}
        metrics={metricsFor({
          ...ledger,
          counts: {
            ...ledger.counts,
            bypass: bypassCount,
            matched: summaryMatched,
            mismatched: summaryMismatch,
            notVerified: summaryNotVerified,
            total: summaryTotal,
            verifiedRate: summaryTotal > 0 ? Math.round((summaryMatched / summaryTotal) * 100) : 0,
          },
        })}
        onMetricClick={(metric) => {
          if (metric.id === "matched" || metric.id === "mismatched" || metric.id === "not_verified") {
            setFilter(metric.id);
          }
        }}
      />

      {isError ? (
        <div className="outcomes-error-banner">
          <AlertTriangle size={16} aria-hidden="true" />
          <span>One or more verification feeds did not refresh cleanly. Loaded data remains visible.</span>
        </div>
      ) : null}

      <BypassStrip ledger={{ ...ledger, counts: { ...ledger.counts, bypass: bypassCount } }} />

      <DashboardWorkspace
        className="outcomes-workspace"
        left={
          <OutcomeFeed
            filter={filter}
            loading={fetching}
            onFilterChange={setFilter}
            onSearchChange={setSearch}
            onSelect={(row) => setSelectedId(row.id)}
            rows={ledger.rows}
            search={search}
            selectedId={selectedRow?.id ?? null}
          />
        }
        right={<OutcomeInspector row={selectedRow} />}
      />

      <p className="outcomes-footnote">
        Outcomes verifies live source-of-record truth. Signed export artifacts stay in <Link href="/evidence">Evidence</Link>.
        {field(sourceMutationSummaryQuery.data?.total, "") ? ` ${formatCount(sourceMutationSummaryQuery.data?.total)} source mutation${sourceMutationSummaryQuery.data?.total === 1 ? "" : "s"} observed.` : ""}
      </p>
    </div>
  );
}
