"use client";

import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock3,
  ExternalLink,
  GitBranch,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { DashboardMetricStrip, DashboardVerdictHero, DashboardWorkspace, type DashboardMetric } from "@/components/dashboard-scaffold";
import { StatusPill } from "@/components/status-pill";
import { statusLabel, type StatusTone } from "@/lib/action-status";
import {
  reconcileSavedConnector,
  type OutcomeReconciliationView,
  type SavedConnectorReconciliationConnector,
  type SavedConnectorReconciliationPayload,
} from "@/lib/api";
import { compactJson, field, formatCount, formatDateTime, humanize, timeSince } from "@/lib/format";
import {
  buildClaimedActualDiff,
  buildOutcomeLedger,
  type OutcomeBypassRow,
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

type VerificationTrendPoint = {
  key: string;
  label: string;
  matched: number;
  mismatched: number;
  notVerified: number;
  rate: number;
  total: number;
};

type ConnectorHealthRow = {
  connectorType: string;
  label: string;
  latestAt: string;
  matched: number;
  mismatched: number;
  notVerified: number;
  rate: number;
  tone: StatusTone;
  total: number;
};

type ReverifyNotice = {
  checkId: string;
  text: string;
  tone: "danger" | "success";
};

function initialCheckId(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("check_id");
}

function checkedAtMs(check: OutcomeReconciliationView): number {
  const parsed = new Date(check.checked_at).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

function trendKey(check: OutcomeReconciliationView): string {
  const date = new Date(check.checked_at);
  if (Number.isNaN(date.getTime())) return "unknown";
  return date.toISOString().slice(0, 10);
}

function trendLabel(key: string): string {
  if (key === "unknown") return "Unknown";
  const date = new Date(`${key}T00:00:00Z`);
  return new Intl.DateTimeFormat("en-US", { day: "numeric", month: "short", timeZone: "UTC" }).format(date);
}

function buildVerificationTrend(checks: OutcomeReconciliationView[]): VerificationTrendPoint[] {
  const groups = new Map<string, VerificationTrendPoint>();
  for (const check of checks) {
    const key = trendKey(check);
    const current = groups.get(key) ?? {
      key,
      label: trendLabel(key),
      matched: 0,
      mismatched: 0,
      notVerified: 0,
      rate: 0,
      total: 0,
    };
    current.total += 1;
    if (check.verdict === "matched") current.matched += 1;
    if (check.verdict === "mismatched") current.mismatched += 1;
    if (check.verdict === "not_verified") current.notVerified += 1;
    current.rate = current.total > 0 ? Math.round((current.matched / current.total) * 100) : 0;
    groups.set(key, current);
  }

  return Array.from(groups.values())
    .sort((a, b) => a.key.localeCompare(b.key))
    .slice(-7);
}

function buildConnectorHealth(checks: OutcomeReconciliationView[]): ConnectorHealthRow[] {
  const groups = new Map<string, ConnectorHealthRow>();
  for (const check of checks) {
    const connectorType = check.connector_type || "unknown_connector";
    const current = groups.get(connectorType) ?? {
      connectorType,
      label: humanize(connectorType, "Unknown connector"),
      latestAt: check.checked_at,
      matched: 0,
      mismatched: 0,
      notVerified: 0,
      rate: 0,
      tone: "neutral" as StatusTone,
      total: 0,
    };
    current.total += 1;
    if (check.verdict === "matched") current.matched += 1;
    if (check.verdict === "mismatched") current.mismatched += 1;
    if (check.verdict === "not_verified") current.notVerified += 1;
    if (checkedAtMs(check) > new Date(current.latestAt).getTime()) current.latestAt = check.checked_at;
    current.rate = current.total > 0 ? Math.round((current.matched / current.total) * 100) : 0;
    current.tone = current.mismatched > 0 ? "danger" : current.notVerified > 0 ? "warning" : "success";
    groups.set(connectorType, current);
  }

  return Array.from(groups.values()).sort((a, b) => {
    const risk = (b.mismatched + b.notVerified) - (a.mismatched + a.notVerified);
    if (risk !== 0) return risk;
    return b.total - a.total;
  });
}

function matchFieldsFor(check: OutcomeReconciliationView): string[] | null {
  const compared = check.comparison?.compared_fields;
  if (!Array.isArray(compared)) return null;
  const fields = compared.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const fieldName = (item as Record<string, unknown>).field;
    return typeof fieldName === "string" && fieldName.trim() ? [fieldName] : [];
  });
  return fields.length > 0 ? Array.from(new Set(fields)) : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function reverifyConnectorFor(check: OutcomeReconciliationView): SavedConnectorReconciliationConnector | null {
  const connector = check.reverify_connector?.trim();
  return connector ? (connector as SavedConnectorReconciliationConnector) : null;
}

function reverifyPayloadFor(row: OutcomeLedgerRow): SavedConnectorReconciliationPayload {
  const check = row.check;
  const connector = reverifyConnectorFor(check);
  if (!connector) {
    throw new Error(`Connector ${check.connector_type} cannot be re-verified from this page yet.`);
  }
  return {
    action_type: check.action_type,
    amount_usd: check.amount_usd,
    call_id: check.call_id,
    claimed: check.claimed,
    connector,
    currency: check.currency,
    customer_id: stringValue(check.claimed.customer_id),
    idempotency_key: check.idempotency_key,
    match_fields: matchFieldsFor(check),
    metadata: {
      ...(check.metadata ?? {}),
      previous_check_id: check.id,
      source: "outcomes_page_reverify",
    },
    record_ref: check.system_ref ?? stringValue(check.claimed.record_id),
    refund_id: stringValue(check.claimed.refund_id),
    runtime_policy_decision_id: check.runtime_policy_decision_id,
    system_ref: check.system_ref,
    trace_id: check.trace_id,
  };
}

function mutationMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message
    : "Saved connector re-verification failed.";
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

function VerificationTrendPanel({ points, verifiedRate }: { points: VerificationTrendPoint[]; verifiedRate: number }) {
  const latest = points[points.length - 1] ?? null;
  const previous = points[points.length - 2] ?? null;
  const delta = latest && previous ? latest.rate - previous.rate : null;
  const maxTotal = Math.max(1, ...points.map((point) => point.total));

  return (
    <section className="outcomes-trend-panel" aria-label="Verified rate trend">
      <div className="outcomes-panel-head">
        <div>
          <span className="dashboard-eyebrow">Trend</span>
          <h2>Verified rate trend</h2>
        </div>
        <span className="outcomes-live-chip">{verifiedRate}% now</span>
      </div>
      {points.length > 0 ? (
        <>
          <div className="outcomes-trend-summary">
            <BarChart3 size={16} aria-hidden="true" />
            <strong>
              {latest ? `${latest.rate}% on ${latest.label}` : `${verifiedRate}% verified`}
            </strong>
            <span>
              {delta == null
                ? `${formatCount(points.reduce((sum, point) => sum + point.total, 0))} loaded checks`
                : `${delta >= 0 ? "+" : ""}${delta} pts vs previous check day`}
            </span>
          </div>
          <div className="outcomes-trend-bars" aria-label="Daily verified rate bars">
            {points.map((point) => (
              <div key={point.key} className="outcomes-trend-bar" title={`${point.label}: ${point.rate}% verified`}>
                <span style={{ height: `${Math.max(8, (point.total / maxTotal) * 58)}px` }} data-rate={point.rate} />
                <small>{point.label}</small>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="outcomes-empty-state">
          <BarChart3 size={18} aria-hidden="true" />
          <strong>No trend yet.</strong>
          <p>Daily verification rate appears after saved connector checks run.</p>
        </div>
      )}
    </section>
  );
}

function ConnectorHealthPanel({ connectors }: { connectors: ConnectorHealthRow[] }) {
  return (
    <section className="outcomes-connector-panel" aria-label="Connector health">
      <div className="outcomes-panel-head">
        <div>
          <span className="dashboard-eyebrow">Source of record</span>
          <h2>Connector health</h2>
        </div>
        <DashboardButtonLink href="/integrations" variant="ghost" size="sm" icon={<ExternalLink size={14} />}>
          Open connectors
        </DashboardButtonLink>
      </div>
      {connectors.length > 0 ? (
        <div className="outcomes-connector-list">
          {connectors.slice(0, 4).map((connector) => (
            <article key={connector.connectorType} className="outcomes-connector-row" data-tone={connector.tone}>
              <span>
                <strong>{connector.label}</strong>
                <small>{formatCount(connector.total)} check{connector.total === 1 ? "" : "s"} / last {timeSince(connector.latestAt)}</small>
              </span>
              <span>
                <StatusPill value={connector.tone === "success" ? "verified" : connector.tone === "danger" ? "mismatched" : "not_verified"} />
                <small>{connector.rate}% matched</small>
              </span>
            </article>
          ))}
        </div>
      ) : (
        <div className="outcomes-empty-state">
          <GitBranch size={18} aria-hidden="true" />
          <strong>No connector checks yet.</strong>
          <p>Saved source-of-record verifiers will show health by connector here.</p>
        </div>
      )}
    </section>
  );
}

function OutcomeOpsPanel({
  connectors,
  trend,
  verifiedRate,
}: {
  connectors: ConnectorHealthRow[];
  trend: VerificationTrendPoint[];
  verifiedRate: number;
}) {
  return (
    <div className="outcomes-ops-grid">
      <VerificationTrendPanel points={trend} verifiedRate={verifiedRate} />
      <ConnectorHealthPanel connectors={connectors} />
    </div>
  );
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

function OutcomeInspector({
  onReverify,
  reverifyLoadingId,
  reverifyNotice,
  row,
}: {
  onReverify: (row: OutcomeLedgerRow) => void;
  reverifyLoadingId: string | null;
  reverifyNotice: ReverifyNotice | null;
  row: OutcomeLedgerRow | null;
}) {
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
  const canReverify = row.verdict !== "matched" && reverifyConnectorFor(check) != null;
  const rowNotice = reverifyNotice?.checkId === row.id ? reverifyNotice : null;

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

      <section className="outcomes-investigation-panel" data-tone={row.tone} aria-label="Outcome investigation workflow">
        <div>
          <span className="dashboard-eyebrow">Investigation</span>
          <strong>
            {row.verdict === "mismatched"
              ? "Mismatch needs investigation"
              : row.verdict === "not_verified"
                ? "Proof can be retried"
                : "No operator action required"}
          </strong>
          <p>
            {row.verdict === "mismatched"
              ? "Compare the field diff, open signed evidence, then re-check the saved connector before escalating."
              : row.verdict === "not_verified"
                ? canReverify
                  ? "Retry the source-of-record verifier after connector credentials, scope, or record availability recover."
                  : "This connector type does not have a saved re-check path yet. Open connectors to verify the source-of-record setup."
                : "The latest source-of-record read matched the agent claim."}
          </p>
        </div>
        <div className="outcomes-investigation-actions">
          <DashboardButton
            disabled={!canReverify}
            icon={<RefreshCw size={14} />}
            loading={reverifyLoadingId === row.id}
            onClick={() => onReverify(row)}
            size="sm"
            variant={canReverify ? "primary" : "soft"}
          >
            Re-verify saved connector
          </DashboardButton>
          {rowNotice ? <small data-tone={rowNotice.tone}>{rowNotice.text}</small> : null}
        </div>
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

function BypassStrip({
  ledger,
  onSelect,
  selectedRow,
}: {
  ledger: OutcomeLedger;
  onSelect: (row: OutcomeBypassRow) => void;
  selectedRow: OutcomeBypassRow | null;
}) {
  return (
    <section className="outcomes-bypass-strip" data-tone={ledger.counts.bypass > 0 ? "danger" : "success"} aria-label="Bypass risk">
      <div className="outcomes-bypass-copy">
        <span className="dashboard-eyebrow">Bypass detection</span>
        <h2>{ledger.counts.bypass > 0 ? `${formatCount(ledger.counts.bypass)} system changes with no receipt` : "No unreceipted source mutations"}</h2>
        <p>Source mutations must map back to a Zroky receipt. Anything else is a bypass risk or unmanaged path.</p>
        {selectedRow ? (
          <section className="outcomes-bypass-detail" aria-label="Selected bypass mutation">
            <StatusPill value={selectedRow.classification} />
            <strong>{selectedRow.title}</strong>
            <span>{selectedRow.actorLabel} changed {selectedRow.detail} without a Zroky receipt.</span>
            <small>
              Mutation id <span className="mono">{selectedRow.mutation.mutation_id}</span> / {formatDateTime(selectedRow.occurredAt)}
            </small>
            <div>
              {selectedRow.mutation.zroky_action_id ? (
                <DashboardButtonLink
                  href={`/actions?action_id=${encodeURIComponent(selectedRow.mutation.zroky_action_id)}`}
                  variant="soft"
                  size="sm"
                  icon={<ExternalLink size={14} />}
                >
                  Open linked action
                </DashboardButtonLink>
              ) : (
                <DashboardButtonLink href="/actions?filter=bypassed" variant="soft" size="sm" icon={<ExternalLink size={14} />}>
                  Investigate in Actions
                </DashboardButtonLink>
              )}
            </div>
          </section>
        ) : null}
      </div>
      {ledger.bypassRows.length > 0 ? (
        <div className="outcomes-bypass-list">
          {ledger.bypassRows.slice(0, 4).map((row) => (
            <button
              key={row.id}
              className={`outcomes-bypass-row${selectedRow?.id === row.id ? " is-selected" : ""}`}
              data-tone={row.tone}
              type="button"
              onClick={() => onSelect(row)}
            >
              <StatusPill value={row.classification} />
              <strong>{row.title}</strong>
              <span>{row.actorLabel} / {row.detail}</span>
              <small>{timeSince(row.occurredAt)}</small>
            </button>
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
  const [reverifyLoadingId, setReverifyLoadingId] = useState<string | null>(null);
  const [reverifyNotice, setReverifyNotice] = useState<ReverifyNotice | null>(null);
  const [search, setSearch] = useState("");
  const [selectedBypassId, setSelectedBypassId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(() => initialCheckId());

  const summaryQuery = useOutcomeReconciliationSummary(30);
  const checksQuery = useOutcomeReconciliations("all", 100);
  const sourceMutationSummaryQuery = useSourceMutationSummary();
  const unreceiptedMutationsQuery = useUnreceiptedSourceMutations(50);

  const checks = useMemo(() => checksQuery.data?.items ?? [], [checksQuery.data?.items]);
  const unreceiptedMutations = useMemo(
    () => unreceiptedMutationsQuery.data?.items ?? [],
    [unreceiptedMutationsQuery.data?.items],
  );
  const ledger = useMemo(
    () => buildOutcomeLedger({
      checks,
      filter,
      mutations: unreceiptedMutations,
      search,
    }),
    [checks, filter, search, unreceiptedMutations],
  );
  const trend = useMemo(() => buildVerificationTrend(checks), [checks]);
  const connectorHealth = useMemo(() => buildConnectorHealth(checks), [checks]);
  const selectedRow = useMemo(
    () => ledger.rows.find((row) => row.id === selectedId) ?? ledger.rows[0] ?? null,
    [ledger.rows, selectedId],
  );
  const selectedBypassRow = useMemo(
    () => ledger.bypassRows.find((row) => row.id === selectedBypassId) ?? ledger.bypassRows[0] ?? null,
    [ledger.bypassRows, selectedBypassId],
  );

  useEffect(() => {
    if (ledger.rows.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!selectedRow) setSelectedId(ledger.rows[0]?.id ?? null);
  }, [ledger.rows, selectedRow]);

  useEffect(() => {
    if (ledger.bypassRows.length === 0) {
      setSelectedBypassId(null);
      return;
    }
    if (!selectedBypassRow) setSelectedBypassId(ledger.bypassRows[0]?.id ?? null);
  }, [ledger.bypassRows, selectedBypassRow]);

  const summaryMismatch = summaryQuery.data?.mismatched ?? ledger.counts.mismatched;
  const summaryNotVerified = summaryQuery.data?.not_verified ?? ledger.counts.notVerified;
  const summaryMatched = summaryQuery.data?.matched ?? ledger.counts.matched;
  const summaryTotal = summaryQuery.data?.total ?? ledger.counts.total;
  const verifiedRate = summaryTotal > 0 ? Math.round((summaryMatched / summaryTotal) * 100) : 0;
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

  const reverifyMutation = useMutation({
    mutationFn: (row: OutcomeLedgerRow) => reconcileSavedConnector(reverifyPayloadFor(row)),
    onError: (error, row) => {
      setReverifyNotice({
        checkId: row.id,
        text: mutationMessage(error),
        tone: "danger",
      });
    },
    onMutate: (row) => {
      setReverifyLoadingId(row.id);
      setReverifyNotice(null);
    },
    onSettled: () => {
      setReverifyLoadingId(null);
    },
    onSuccess: (result, row) => {
      setReverifyNotice({
        checkId: row.id,
        text: `Re-check created: ${statusLabel(result.verdict, "proof")}.`,
        tone: "success",
      });
      refresh();
    },
  });

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
            verifiedRate,
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

      <OutcomeOpsPanel connectors={connectorHealth} trend={trend} verifiedRate={verifiedRate} />

      <BypassStrip
        ledger={{ ...ledger, counts: { ...ledger.counts, bypass: bypassCount } }}
        onSelect={(row) => setSelectedBypassId(row.id)}
        selectedRow={selectedBypassRow}
      />

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
        right={
          <OutcomeInspector
            onReverify={(row) => reverifyMutation.mutate(row)}
            reverifyLoadingId={reverifyLoadingId}
            reverifyNotice={reverifyNotice}
            row={selectedRow}
          />
        }
      />

      <p className="outcomes-footnote">
        Outcomes verifies live source-of-record truth. Signed export artifacts stay in <Link href="/evidence">Evidence</Link>.
        {field(sourceMutationSummaryQuery.data?.total, "") ? ` ${formatCount(sourceMutationSummaryQuery.data?.total)} source mutation${sourceMutationSummaryQuery.data?.total === 1 ? "" : "s"} observed.` : ""}
      </p>
    </div>
  );
}
