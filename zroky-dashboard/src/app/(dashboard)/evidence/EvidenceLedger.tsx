import Link from "next/link";
import { ChevronDown, Download, Search } from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import { StatusPill } from "@/components/status-pill";
import type { EvidenceLedgerFilter, EvidenceLedgerRow } from "@/lib/evidence-ledger";
import { filterEvidenceLedger } from "@/lib/evidence-ledger";
import { timeSince } from "@/lib/format";

const filters: Array<{ label: string; value: EvidenceLedgerFilter }> = [
  { label: "All", value: "all" },
  { label: "Proven", value: "proven" },
  { label: "Caught", value: "caught" },
  { label: "Pending", value: "pending" },
  { label: "Needs attention", value: "needs_attention" },
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
  projectTotal: number;
  rows: EvidenceLedgerRow[];
  search: string;
  selectedRowId: string | null;
  totalCount: number;
};

function shortId(value: string | null | undefined): string {
  if (!value) return "-";
  return value.length > 14 ? `${value.slice(0, 10)}...` : value;
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
  projectTotal,
  rows,
  search,
  selectedRowId,
  totalCount,
}: EvidenceLedgerProps) {
  const filteredRows = filterEvidenceLedger(rows, filter, search);
  const exportableCount = filteredRows.filter((row) => row.exportable).length;

  return (
    <section className="ev-ledger-panel" aria-label="Evidence ledger">
      <header className="ev-section-head">
        <div>
          <span className="ev-eyebrow">Evidence ledger</span>
          <h2>Proof records</h2>
          <p>Select an outcome graph to inspect source-of-record proof.</p>
        </div>
        <strong>
          {search.trim()
            ? `${filteredRows.length} shown`
            : rows.length < totalCount
              ? `${rows.length} of ${totalCount} shown`
              : `${rows.length} shown`}
        </strong>
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
          {isExporting ? "Exporting" : "Export view"}
        </DashboardButton>
      </div>

      <div className="ev-ledger-search-row">
        <label className="ev-search-field">
          <Search size={14} aria-hidden="true" />
          <input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search outcome graphs..."
          />
        </label>
        <div className="ev-manifest-scope" aria-label="Manifest scope">
          <strong>{exportableCount}</strong>
          <span>graphs in view</span>
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
      ) : projectTotal === 0 ? (
        <div className="ev-empty-state">
          <strong>Declare your first intent.</strong>
          <span>Outcome graphs appear here once an agent run is verified against your systems of record.</span>
          <div className="ev-empty-contract" aria-label="Evidence export contract">
            <span>Declare intent</span>
            <span>Bind Assurance Pack</span>
            <span>Read source</span>
            <span>Store graph</span>
          </div>
          <a href="/docs">Read setup docs</a>
        </div>
      ) : rows.length === 0 ? (
        <div className="ev-empty-state">No records match this classification.</div>
      ) : filteredRows.length === 0 ? (
        <div className="ev-empty-state">No records match this filter or search.</div>
      ) : (
        <>
          <div className="ev-ledger-table-wrap">
            <table className="ev-ledger-table">
              <thead>
                <tr>
                  <th scope="col">Created</th>
                  <th scope="col">Workflow</th>
                  <th scope="col">Classification</th>
                  <th scope="col">Reason</th>
                  <th scope="col">Intent</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => {
                  const selected = row.id === selectedRowId;
                  return (
                    <tr
                      key={row.id}
                      className="ev-ledger-row"
                      data-focused={selected ? "true" : undefined}
                      data-kind={row.kind}
                      data-tone={row.tone}
                      aria-current={selected ? "true" : undefined}
                      onClick={() => onSelectRow(row)}
                    >
                      <td>
                        <span className="ev-signed-cell">
                          {timeSince(row.createdAt ?? row.checkedAt)}
                          <small>{row.environment ?? "environment"}</small>
                        </span>
                      </td>
                      <td>
                        <span className="ev-proof-name">
                          <span className="ev-proof-dot" aria-hidden="true" />
                          <strong>{row.title}</strong>
                        </span>
                      </td>
                      <td><StatusPill value={row.status} label={row.statusLabel} tone={row.tone} /></td>
                      <td>
                        {(row.classification === "pending" || row.classification === "unknown") && row.reasonCode ? (
                          <code>{row.reasonCode}</code>
                        ) : "-"}
                      </td>
                      <td>
                        <Link href={`/operations?intent_id=${encodeURIComponent(row.intentId ?? "")}`} onClick={(event) => event.stopPropagation()}>
                          <code>{shortId(row.intentId)}</code>
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {hasMore ? (
            <div className="ev-ledger-load-more">
              <DashboardButton
                icon={<ChevronDown size={15} />}
                loading={isLoadingMore}
                onClick={onLoadMore}
                variant="soft"
              >
                Load more
              </DashboardButton>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
