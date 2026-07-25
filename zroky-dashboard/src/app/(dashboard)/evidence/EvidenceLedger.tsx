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
  isError: boolean;
  isExporting: boolean;
  isLoading: boolean;
  onFilterChange: (filter: EvidenceLedgerFilter) => void;
  onExportManifest: () => void;
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
  isExporting,
  isLoading,
  onFilterChange,
  onExportManifest,
  onSearchChange,
  onSelectRow,
  rows,
  search,
  selectedRowId,
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
        <strong>{filteredRows.length} shown</strong>
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
        <div className="ev-manifest-scope" aria-label="Manifest scope">
          <strong>{exportableCount}</strong>
          <span>exportable in view</span>
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
        <div className="ev-ledger-table-wrap">
          <table className="ev-ledger-table">
            <thead>
              <tr>
                <th scope="col">Proof</th>
                <th scope="col">Workflow</th>
                <th scope="col">Source</th>
                <th scope="col">Verdict</th>
                <th scope="col">Signed</th>
                <th scope="col">Action</th>
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
                  >
                    <td>
                      <span className="ev-proof-name">
                        <span className="ev-proof-dot" aria-hidden="true" />
                        <span>
                          <strong>{row.title}</strong>
                          <small>{rowKindLabel(row.kind)}</small>
                          {row.digest ? (
                            <small className="ev-proof-digest">
                              <span>Digest</span>
                              <code>{row.digest}</code>
                            </small>
                          ) : null}
                        </span>
                      </span>
                    </td>
                    <td>{row.kind === "unlinked_outcome" ? row.actionType : row.agentName}</td>
                    <td>{row.systemRef ?? row.sourceLabel}</td>
                    <td><StatusPill value={row.status} label={row.statusLabel} tone={row.tone} /></td>
                    <td>
                      <span className="ev-signed-cell">
                        {row.id.startsWith("demo:") ? row.detail : formatDateTime(row.checkedAt)}
                        <small>{row.exportable ? row.sourceLabel : "not linked / not exportable"}</small>
                      </span>
                    </td>
                    <td>
                      <DashboardButton onClick={() => onSelectRow(row)} size="sm" variant="soft">
                        {row.exportable ? "View" : actionLabel(row)}
                      </DashboardButton>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
