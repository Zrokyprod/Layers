import Link from "next/link";
import { Download, Search } from "lucide-react";

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
  hasMore: boolean;
  isError: boolean;
  isExporting: boolean;
  isLoading: boolean;
  isLoadingMore: boolean;
  onFilterChange: (filter: EvidenceLedgerFilter) => void;
  onExportManifest: () => void;
  onLoadMore: () => void;
  onSearchChange: (value: string) => void;
  onSelectRow: (row: EvidenceLedgerRow) => void;
  rows: EvidenceLedgerRow[];
  search: string;
  selectedRowId: string | null;
  totalMatching: number;
};

function rowKindLabel(row: EvidenceLedgerRow): string {
  if (row.kind === "action_receipt") {
    if (row.sourceLabel === "Blocked action audit") return "Blocked action audit";
    return row.exportable ? "Signed receipt" : "Protected action record";
  }
  if (row.kind === "orphan_decision") return "Guard-only evidence";
  return "Unlinked outcome";
}

function exportLabel(row: EvidenceLedgerRow): string {
  if (row.exportable) return row.sourceLabel;
  if (row.kind === "unlinked_outcome") return "not linked / not exportable";
  if (["blocked", "denied", "rejected", "expired", "cancelled"].includes(row.status)) return "not required";
  return "receipt not available";
}

function actionLabel(row: EvidenceLedgerRow): string {
  if (row.exportable) {
    return row.exportKind === "receipt" ? "Open receipt" : "Open pack";
  }
  return row.kind === "unlinked_outcome" ? "Not exportable" : "Review row";
}

export function EvidenceLedger({
  filter,
  hasMore,
  isError,
  isExporting,
  isLoading,
  isLoadingMore,
  onFilterChange,
  onExportManifest,
  onLoadMore,
  onSearchChange,
  onSelectRow,
  rows,
  search,
  selectedRowId,
  totalMatching,
}: EvidenceLedgerProps) {
  const filteredRows = filterEvidenceLedger(rows, filter, search);
  const exportableCount = filteredRows.filter((row) => row.exportable).length;

  return (
    <section className="ev-ledger-panel" aria-label="Evidence ledger">
      <header className="ev-section-head">
        <div>
          <span className="ev-eyebrow">Evidence ledger</span>
          <h2>Proof records</h2>
          <p>Select a proof record to verify, export, or print.</p>
        </div>
        <strong>{filteredRows.length} of {totalMatching} shown</strong>
      </header>

      <div className="ev-ledger-toolbar">
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

        <DashboardButton
          icon={<Download size={15} />}
          disabled={isExporting || filteredRows.length === 0}
          onClick={onExportManifest}
          variant="soft"
        >
          {isExporting ? "Exporting" : "Export manifest"}
        </DashboardButton>
      </div>

      <div className="ev-ledger-search-row">
        <label className="ev-search-field">
          <Search size={14} aria-hidden="true" />
          <input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search proof records..."
          />
        </label>
        <div
          className="ev-manifest-scope"
          aria-label={`Manifest scope: ${exportableCount} exportable record${exportableCount === 1 ? "" : "s"} in view`}
        >
          <strong>{exportableCount}</strong>
          <span>exportable</span>
        </div>
      </div>

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
        <>
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
                      <span className="ev-row-kind">{rowKindLabel(row)}</span>
                      <h3>{row.title}</h3>
                    </div>
                    <StatusPill value={row.status} label={row.statusLabel} tone={row.tone} />
                  </div>
                  <p>{row.agentName} / {row.actionType}</p>
                  <dl className="ev-row-meta">
                    {row.digest ? (
                      <div>
                        <dt>{row.kind === "action_receipt" ? "Intent digest" : "Digest"}</dt>
                        <dd>
                          <code>{row.digest}</code>
                        </dd>
                      </div>
                    ) : null}
                    <div>
                      <dt>Checked</dt>
                      <dd>{formatDateTime(row.checkedAt)}</dd>
                    </div>
                    <div>
                      <dt>Export</dt>
                      <dd>{exportLabel(row)}</dd>
                    </div>
                  </dl>
                  <small>{row.systemRef ?? row.detail}</small>
                </div>
                <div className="ev-ledger-actions">
                  <DashboardButton onClick={() => onSelectRow(row)} size="sm" variant="soft">
                    {row.exportable ? "View proof" : actionLabel(row)}
                  </DashboardButton>
                  {row.kind === "unlinked_outcome" ? (
                    <Link className="ev-link" href="/outcomes">Open outcomes</Link>
                  ) : null}
                </div>
              </article>
            );
          })}
          </div>
          {hasMore ? (
            <div className="ev-ledger-load-more">
              <DashboardButton disabled={isLoadingMore} onClick={onLoadMore} variant="soft">
                {isLoadingMore ? "Loading" : "Load more proof records"}
              </DashboardButton>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
