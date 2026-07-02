import Link from "next/link";
import { Search } from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import { StatusPill } from "@/components/status-pill";
import type { EvidenceLedgerFilter, EvidenceLedgerRow } from "@/lib/evidence-ledger";
import { filterEvidenceLedger } from "@/lib/evidence-ledger";
import { formatDateTime } from "@/lib/format";

const filters: Array<{ label: string; value: EvidenceLedgerFilter }> = [
  { label: "All", value: "all" },
  { label: "Matched", value: "matched" },
  { label: "Needs verification", value: "needs_verification" },
  { label: "Exceptions", value: "exceptions" },
];

type EvidenceLedgerProps = {
  filter: EvidenceLedgerFilter;
  isError: boolean;
  isLoading: boolean;
  onFilterChange: (filter: EvidenceLedgerFilter) => void;
  onSearchChange: (value: string) => void;
  onSelectRow: (row: EvidenceLedgerRow) => void;
  rows: EvidenceLedgerRow[];
  search: string;
  selectedRowId: string | null;
};

function rowKindLabel(kind: EvidenceLedgerRow["kind"]): string {
  if (kind === "action_receipt") return "Action receipt";
  if (kind === "orphan_decision") return "Guard-only evidence";
  return "Unlinked outcome";
}

function actionLabel(row: EvidenceLedgerRow): string {
  if (row.exportable) {
    return row.exportKind === "receipt" ? "Open receipt" : "Open pack";
  }
  return row.kind === "unlinked_outcome" ? "Not exportable" : "Review row";
}

export function EvidenceLedger({
  filter,
  isError,
  isLoading,
  onFilterChange,
  onSearchChange,
  onSelectRow,
  rows,
  search,
  selectedRowId,
}: EvidenceLedgerProps) {
  const filteredRows = filterEvidenceLedger(rows, filter, search);

  return (
    <section className="ev-ledger-panel" aria-label="Evidence ledger">
      <header className="ev-section-head">
        <div>
          <span className="ev-eyebrow">Evidence ledger</span>
          <h2>Proof records</h2>
          <p>Receipt-first rows are primary. Guard-only decisions stay visible as secondary evidence.</p>
        </div>
        <strong>{filteredRows.length} shown</strong>
      </header>

      <div className="ev-filter-group" aria-label="Evidence filters">
        {filters.map((item) => (
          <button
            key={item.value}
            className="ev-filter-chip"
            data-active={filter === item.value ? "true" : undefined}
            type="button"
            onClick={() => onFilterChange(item.value)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <label className="ev-search-field">
        <Search size={14} aria-hidden="true" />
        <input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Search action, agent, system ref, digest..."
        />
      </label>

      {isLoading ? (
        <div className="ev-skeleton-list" aria-label="Loading evidence rows">
          <span />
          <span />
          <span />
        </div>
      ) : isError ? (
        <div className="ev-empty-state">Evidence could not load. Verify backend connectivity and project access.</div>
      ) : rows.length === 0 ? (
        <div className="ev-empty-state">
          <strong>No proof yet.</strong>
          <span>Run a protected action to generate the first signed receipt.</span>
          <div className="ev-empty-contract" aria-label="Evidence export contract">
            <span>Runtime decision</span>
            <span>Approval audit</span>
            <span>Outcome proof</span>
            <span>Evidence hash</span>
          </div>
        </div>
      ) : filteredRows.length === 0 ? (
        <div className="ev-empty-state">No records match this filter or search.</div>
      ) : (
        <div className="ev-ledger-list">
          {filteredRows.map((row) => {
            const selected = row.id === selectedRowId;
            return (
              <article
                key={row.id}
                className="ev-ledger-row"
                data-focused={selected ? "true" : undefined}
                data-kind={row.kind}
                data-tone={row.tone}
                aria-current={selected ? "true" : undefined}
              >
                <div className="ev-ledger-main">
                  <div className="ev-ledger-titleline">
                    <div>
                      <span className="ev-row-kind">{rowKindLabel(row.kind)}</span>
                      <h3>{row.title}</h3>
                    </div>
                    <StatusPill value={row.status} label={row.statusLabel} tone={row.tone} />
                  </div>
                  <p>{row.agentName} / {row.actionType}</p>
                  <dl className="ev-row-meta">
                    {row.digest ? (
                      <div>
                        <dt>Digest</dt>
                        <dd>
                          <code>{row.digest}</code>
                        </dd>
                      </div>
                    ) : null}
                    <div>
                      <dt>System</dt>
                      <dd>{row.systemRef ?? "not linked"}</dd>
                    </div>
                    <div>
                      <dt>Checked</dt>
                      <dd>{formatDateTime(row.checkedAt)}</dd>
                    </div>
                    <div>
                      <dt>Export</dt>
                      <dd>{row.exportable ? row.sourceLabel : "not linked / not exportable"}</dd>
                    </div>
                  </dl>
                  <small>{row.detail}</small>
                </div>
                <div className="ev-ledger-actions">
                  <DashboardButton onClick={() => onSelectRow(row)} size="sm" variant="soft">
                    {actionLabel(row)}
                  </DashboardButton>
                  {row.kind === "unlinked_outcome" ? (
                    <Link className="ev-link" href="/outcomes">Open outcomes</Link>
                  ) : (
                    <Link
                      className="ev-link"
                      href={row.href}
                      onClick={(event) => {
                        event.preventDefault();
                        onSelectRow(row);
                      }}
                    >
                      Deep link
                    </Link>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
