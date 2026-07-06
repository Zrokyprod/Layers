"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import { DashboardWorkspace } from "@/components/dashboard-scaffold";
import {
  getActionIntentReceipt,
  getRuntimePolicyEvidencePack,
  listActionIntents,
  listOutcomeReconciliations,
  listRuntimePolicyApprovals,
  type ActionReceiptResponse,
  type RuntimePolicyEvidencePackResponse,
} from "@/lib/api";
import {
  buildEvidenceLedger,
  evidenceLedgerCounts,
  filterEvidenceLedger,
  resolveEvidenceLedgerDeepLink,
  type EvidenceLedgerFilter,
  type EvidenceLedgerRow,
} from "@/lib/evidence-ledger";
import { buildEvidenceArtifact } from "@/lib/evidence-artifact";
import { actionReceiptPublicKeyUrl } from "@/lib/evidence-verification";
import { formatDateTime } from "@/lib/format";
import { EvidenceLedger } from "./EvidenceLedger";
import { EvidenceProofStrip, type EvidenceProofMetric } from "./EvidenceProofStrip";
import { EvidenceReport } from "./EvidenceReport";
import { EvidenceVerdictHero } from "./EvidenceVerdictHero";
import { FocusedProofPanel } from "./FocusedProofPanel";

type DeepLinkState = {
  actionId: string | null;
  decisionId: string | null;
};

type EvidenceVerdict = {
  badge: string;
  copy: string;
  ctaHref: string;
  ctaLabel: string;
  title: string;
  tone: "danger" | "neutral" | "success" | "warning";
};

type EvidenceAuditManifest = {
  artifact: "zroky.evidence_manifest";
  schema_version: "zroky.evidence_manifest.v1";
  generated_at: string;
  scope: {
    filter: EvidenceLedgerFilter;
    search: string | null;
    start_date: string | null;
    end_date: string | null;
    total_records: number;
    exportable_records: number;
    non_exportable_records: number;
  };
  verification: {
    public_key_url: string;
    instructions: string[];
  };
  records: Array<{
    action_id: string | null;
    checked_at: string | null;
    decision_id: string | null;
    digest: string | null;
    export_kind: EvidenceLedgerRow["exportKind"];
    exportable: boolean;
    href: string;
    id: string;
    kind: EvidenceLedgerRow["kind"];
    source_label: string;
    status: string;
    system_ref: string | null;
    title: string;
    trace_id: string | null;
  }>;
};

function safeFilePart(value: string) {
  return value.replace(/[^a-zA-Z0-9_.-]+/g, "_");
}

function downloadJsonFile(payload: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function dayKey(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString().slice(0, 10);
}

function rowsInDateRange(rows: EvidenceLedgerRow[], startDate: string, endDate: string): EvidenceLedgerRow[] {
  if (!startDate && !endDate) return rows;
  return rows.filter((row) => {
    const checkedDay = dayKey(row.checkedAt);
    if (!checkedDay) return false;
    if (startDate && checkedDay < startDate) return false;
    if (endDate && checkedDay > endDate) return false;
    return true;
  });
}

function buildEvidenceManifest({
  endDate,
  filter,
  rows,
  search,
  startDate,
}: {
  endDate: string;
  filter: EvidenceLedgerFilter;
  rows: EvidenceLedgerRow[];
  search: string;
  startDate: string;
}): EvidenceAuditManifest {
  return {
    artifact: "zroky.evidence_manifest",
    generated_at: new Date().toISOString(),
    records: rows.map((row) => ({
      action_id: row.actionId,
      checked_at: row.checkedAt,
      decision_id: row.decisionId,
      digest: row.digest,
      export_kind: row.exportKind,
      exportable: row.exportable,
      href: row.href,
      id: row.id,
      kind: row.kind,
      source_label: row.sourceLabel,
      status: row.status,
      system_ref: row.systemRef,
      title: row.title,
      trace_id: row.traceId,
    })),
    schema_version: "zroky.evidence_manifest.v1",
    scope: {
      end_date: endDate || null,
      exportable_records: rows.filter((row) => row.exportable).length,
      filter,
      non_exportable_records: rows.filter((row) => !row.exportable).length,
      search: search.trim() || null,
      start_date: startDate || null,
      total_records: rows.length,
    },
    verification: {
      public_key_url: actionReceiptPublicKeyUrl(),
      instructions: [
        "Use this manifest as an index, not as a signed evidence bundle.",
        "Export each referenced Action Receipt or Evidence Pack JSON before audit review.",
        "For Action Receipts, verify the Ed25519 signature over signed_payload using the published public key.",
        "For Evidence Packs, compare the evidence_hash in the exported proof with the value shown in Zroky.",
      ],
    },
  };
}

function readSearchParams(): { deepLink: DeepLinkState; filter: EvidenceLedgerFilter } {
  if (typeof window === "undefined") {
    return {
      deepLink: { actionId: null, decisionId: null },
      filter: "all",
    };
  }
  const params = new URLSearchParams(window.location.search);
  const rawFilter = params.get("filter");
  const filter: EvidenceLedgerFilter =
    rawFilter === "matched" || rawFilter === "needs_verification" || rawFilter === "exceptions" ? rawFilter : "all";
  return {
    deepLink: {
      actionId: params.get("action_id")?.trim() || null,
      decisionId: params.get("decision_id")?.trim() || null,
    },
    filter,
  };
}

function replaceUrl(href: string) {
  if (typeof window !== "undefined") {
    window.history.replaceState({}, "", href);
  }
}

function fallbackRowFromDeepLink(deepLink: DeepLinkState): EvidenceLedgerRow | null {
  if (deepLink.actionId) {
    return {
      actionId: deepLink.actionId,
      actionType: "Protected action",
      agentName: "Linked action",
      callId: null,
      checkedAt: null,
      decisionId: null,
      detail: "Action Receipt is loaded directly from the deep link.",
      digest: null,
      exportKind: "receipt",
      exportable: true,
      href: `/evidence?action_id=${encodeURIComponent(deepLink.actionId)}`,
      id: `external-action:${deepLink.actionId}`,
      kind: "action_receipt",
      outcomeId: null,
      sourceLabel: "Action Receipt",
      status: "pending",
      statusLabel: "Pending",
      systemRef: null,
      title: deepLink.actionId,
      tone: "warning",
      traceId: null,
    };
  }
  if (deepLink.decisionId) {
    return {
      actionId: null,
      actionType: "Runtime policy decision",
      agentName: "Guard-only action",
      callId: null,
      checkedAt: null,
      decisionId: deepLink.decisionId,
      detail: "Evidence Pack is loaded directly from the deep link.",
      digest: null,
      exportKind: "evidence_pack",
      exportable: true,
      href: `/evidence?decision_id=${encodeURIComponent(deepLink.decisionId)}`,
      id: `external-decision:${deepLink.decisionId}`,
      kind: "orphan_decision",
      outcomeId: null,
      sourceLabel: "Guard-only Evidence Pack",
      status: "pending",
      statusLabel: "Pending",
      systemRef: null,
      title: deepLink.decisionId,
      tone: "warning",
      traceId: null,
    };
  }
  return null;
}

function latestCheckedAt(rows: EvidenceLedgerRow[]): string | null {
  let latest: string | null = null;
  let latestTime = -1;
  for (const row of rows) {
    const time = row.checkedAt ? new Date(row.checkedAt).getTime() : 0;
    if (Number.isFinite(time) && time > latestTime) {
      latest = row.checkedAt;
      latestTime = time;
    }
  }
  return latest;
}

function buildVerdict({
  counts,
  error,
  loading,
}: {
  counts: ReturnType<typeof evidenceLedgerCounts>;
  error: unknown;
  loading: boolean;
}): EvidenceVerdict {
  if (error) {
    return {
      badge: "Unavailable",
      copy: "Evidence cannot be trusted until action intents, runtime policy decisions, and outcome checks load cleanly.",
      ctaHref: "/outcomes",
      ctaLabel: "Open outcomes",
      title: "Evidence ledger unavailable",
      tone: "danger",
    };
  }
  if (loading) {
    return {
      badge: "Syncing",
      copy: "Loading signed receipts, guard-only decisions, and system-of-record outcome checks.",
      ctaHref: "/actions",
      ctaLabel: "Open actions",
      title: "Loading evidence ledger",
      tone: "neutral",
    };
  }
  if (counts.total === 0) {
    return {
      badge: "No evidence yet",
      copy: "Run a protected action to generate the first signed receipt and export-ready proof record.",
      ctaHref: "/agents/setup",
      ctaLabel: "Run protected action",
      title: "No evidence yet",
      tone: "neutral",
    };
  }
  if (counts.exceptions > 0) {
    return {
      badge: "Exception",
      copy: "At least one action proof is mismatched or failed. Review the selected proof before using it for audit.",
      ctaHref: "/evidence?filter=exceptions",
      ctaLabel: `Review ${counts.exceptions} exception${counts.exceptions === 1 ? "" : "s"}`,
      title: "Exception needs review",
      tone: "danger",
    };
  }
  if (counts.needsVerification > 0) {
    return {
      badge: "Needs verification",
      copy: "Some proof records are controlled but not verified yet. Keep them visible, but do not treat them as success.",
      ctaHref: "/evidence?filter=needs_verification",
      ctaLabel: `Review ${counts.needsVerification} pending`,
      title: "Needs verification",
      tone: "warning",
    };
  }
  return {
    badge: "Evidence ready",
    copy: "Matched proof and generated receipts are ready for export from the selected record.",
    ctaHref: "/evidence?filter=matched",
    ctaLabel: "Export latest",
    title: "Evidence ready",
    tone: "success",
  };
}

function metricsForCounts(counts: ReturnType<typeof evidenceLedgerCounts>): EvidenceProofMetric[] {
  return [
    {
      detail: "matched + generated receipt",
      href: "/evidence?filter=matched",
      label: "Export-ready",
      tone: "success",
      value: String(counts.exportReady),
    },
    {
      detail: "not_verified, missing, or pending",
      href: "/evidence?filter=needs_verification",
      label: "Needs verification",
      tone: counts.needsVerification > 0 ? "warning" : "neutral",
      value: String(counts.needsVerification),
    },
    {
      detail: "mismatched or failed proof",
      href: "/evidence?filter=exceptions",
      label: "Exceptions",
      tone: counts.exceptions > 0 ? "danger" : "neutral",
      value: String(counts.exceptions),
    },
    {
      detail: "receipts, guard decisions, and unlinked outcomes",
      href: "/evidence?filter=all",
      label: "Total proof records",
      tone: "neutral",
      value: String(counts.total),
    },
  ];
}

function EvidenceAuditTools({
  endDate,
  filter,
  onEndDateChange,
  onExportManifest,
  onStartDateChange,
  rows,
  search,
  startDate,
}: {
  endDate: string;
  filter: EvidenceLedgerFilter;
  onEndDateChange: (value: string) => void;
  onExportManifest: () => void;
  onStartDateChange: (value: string) => void;
  rows: EvidenceLedgerRow[];
  search: string;
  startDate: string;
}) {
  const exportableCount = rows.filter((row) => row.exportable).length;
  return (
    <section className="ev-audit-tools" aria-label="Audit export tools">
      <div>
        <span className="ev-eyebrow">Audit export</span>
        <h2>Filtered proof manifest</h2>
        <p>Export a date-scoped index of visible proof records. Individual receipts and Evidence Packs remain separately signed.</p>
      </div>
      <div className="ev-audit-controls">
        <label>
          <span>Start</span>
          <input type="date" value={startDate} onChange={(event) => onStartDateChange(event.target.value)} />
        </label>
        <label>
          <span>End</span>
          <input type="date" value={endDate} onChange={(event) => onEndDateChange(event.target.value)} />
        </label>
        <DashboardButton icon={<Download size={15} />} onClick={onExportManifest} variant="primary">
          Export audit manifest
        </DashboardButton>
      </div>
      <div className="ev-audit-scope" aria-label="Manifest scope">
        <strong>{rows.length} in scope</strong>
        <span>{exportableCount} exportable</span>
        <span>{rows.length - exportableCount} visible but not exportable</span>
        <span>{filter.replace("_", " ")}{search.trim() ? ` / ${search.trim()}` : ""}</span>
      </div>
    </section>
  );
}

export default function EvidencePage() {
  const [initial] = useState(() => readSearchParams());
  const [auditEndDate, setAuditEndDate] = useState("");
  const [auditStartDate, setAuditStartDate] = useState("");
  const [deepLink, setDeepLink] = useState<DeepLinkState>(initial.deepLink);
  const [filter, setFilter] = useState<EvidenceLedgerFilter>(initial.filter);
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const actionsQuery = useQuery({
    queryKey: ["action-intents", "evidence-index"],
    queryFn: ({ signal }) => listActionIntents({ status: "all", limit: 100 }, signal),
  });
  const decisionsQuery = useQuery({
    queryKey: ["runtime-policy", "evidence-index"],
    queryFn: ({ signal }) => listRuntimePolicyApprovals("all", signal),
  });
  const outcomesQuery = useQuery({
    queryKey: ["outcomes", "evidence-index"],
    queryFn: ({ signal }) => listOutcomeReconciliations({ limit: 100 }, signal),
  });

  const rows = useMemo(
    () => buildEvidenceLedger({
      decisions: decisionsQuery.data?.items ?? [],
      intents: actionsQuery.data?.items ?? [],
      outcomes: outcomesQuery.data?.items ?? [],
    }),
    [actionsQuery.data?.items, decisionsQuery.data?.items, outcomesQuery.data?.items],
  );
  const loading = actionsQuery.isLoading || decisionsQuery.isLoading || outcomesQuery.isLoading;
  const error = actionsQuery.error || decisionsQuery.error || outcomesQuery.error;
  const counts = useMemo(() => evidenceLedgerCounts(rows), [rows]);
  const visibleRows = useMemo(() => filterEvidenceLedger(rows, filter, search), [filter, rows, search]);
  const auditRows = useMemo(
    () => rowsInDateRange(visibleRows, auditStartDate, auditEndDate),
    [auditEndDate, auditStartDate, visibleRows],
  );
  const selectedRow = rows.find((row) => row.id === selectedRowId) ?? null;
  const focusedRow = selectedRow ?? fallbackRowFromDeepLink(deepLink);
  const selectedActionId = focusedRow?.exportKind === "receipt" ? focusedRow.actionId : null;
  const selectedDecisionId = focusedRow?.exportKind === "evidence_pack" ? focusedRow.decisionId : null;

  const receiptQuery = useQuery({
    queryKey: ["action-receipt", selectedActionId],
    enabled: Boolean(selectedActionId),
    retry: false,
    queryFn: ({ signal }) => {
      if (!selectedActionId) throw new Error("Action id is required.");
      return getActionIntentReceipt(selectedActionId, signal);
    },
  });
  const evidencePackQuery = useQuery({
    queryKey: ["runtime-policy", "evidence-pack", selectedDecisionId],
    enabled: Boolean(selectedDecisionId),
    retry: false,
    queryFn: ({ signal }) => {
      if (!selectedDecisionId) throw new Error("Decision id is required.");
      return getRuntimePolicyEvidencePack(selectedDecisionId, signal);
    },
  });

  useEffect(() => {
    if (loading) return;
    if (selectedRowId && rows.some((row) => row.id === selectedRowId)) return;
    const linkedRow = resolveEvidenceLedgerDeepLink(rows, deepLink);
    if (linkedRow) {
      setSelectedRowId(linkedRow.id);
      return;
    }
    if (deepLink.actionId || deepLink.decisionId) {
      setSelectedRowId(null);
      return;
    }
    setSelectedRowId(rows[0]?.id ?? null);
  }, [deepLink, loading, rows, selectedRowId]);

  function selectRow(row: EvidenceLedgerRow) {
    setDeepLink({ actionId: null, decisionId: null });
    setSelectedRowId(row.id);
    replaceUrl(row.href);
  }

  function applyFilterHref(href: string) {
    const url = new URL(href, "http://zroky.local");
    const rawFilter = url.searchParams.get("filter");
    const nextFilter: EvidenceLedgerFilter =
      rawFilter === "matched" || rawFilter === "needs_verification" || rawFilter === "exceptions" ? rawFilter : "all";
    setFilter(nextFilter);
    replaceUrl(`/evidence?filter=${nextFilter}`);
  }

  async function refreshEvidence() {
    await Promise.all([actionsQuery.refetch(), decisionsQuery.refetch(), outcomesQuery.refetch()]);
  }

  async function exportSelectedProof() {
    if (!focusedRow?.exportable) return;
    setMessage("");
    setExporting(true);
    try {
      if (focusedRow.exportKind === "receipt" && selectedActionId) {
        const receipt: ActionReceiptResponse = receiptQuery.data ?? await getActionIntentReceipt(selectedActionId);
        downloadJsonFile(
          buildEvidenceArtifact({ kind: "receipt", receipt }),
          `zroky-action-receipt-${safeFilePart(selectedActionId)}.json`,
        );
        setMessage("Action Receipt JSON exported.");
        return;
      }
      if (focusedRow.exportKind === "evidence_pack" && selectedDecisionId) {
        const pack: RuntimePolicyEvidencePackResponse = evidencePackQuery.data ?? await getRuntimePolicyEvidencePack(selectedDecisionId);
        downloadJsonFile(
          buildEvidenceArtifact({ kind: "evidence_pack", pack }),
          `zroky-evidence-pack-${safeFilePart(selectedDecisionId)}.json`,
        );
        setMessage("Evidence Pack JSON exported.");
      }
    } catch (downloadError) {
      setMessage(downloadError instanceof Error ? downloadError.message : "Evidence export failed.");
    } finally {
      setExporting(false);
    }
  }

  function exportAuditManifest() {
    const manifest = buildEvidenceManifest({
      endDate: auditEndDate,
      filter,
      rows: auditRows,
      search,
      startDate: auditStartDate,
    });
    const scope = [
      filter,
      search.trim() ? safeFilePart(search.trim()) : "all",
      auditStartDate || "start",
      auditEndDate || "end",
    ].join("-");
    downloadJsonFile(manifest, `zroky-evidence-manifest-${safeFilePart(scope)}.json`);
    setMessage(`Audit manifest exported for ${auditRows.length} proof record${auditRows.length === 1 ? "" : "s"}.`);
  }

  const verdict = buildVerdict({ counts, error, loading });
  const updatedAt = latestCheckedAt(rows);
  const isRefreshing = actionsQuery.isFetching || decisionsQuery.isFetching || outcomesQuery.isFetching;

  return (
    <div className="dashboard-page evidence-page evidence-ledger-page ev-page">
      {message ? <div className="alert-strip ev-alert-strip">{message}</div> : null}
      <EvidenceVerdictHero
        {...verdict}
        isRefreshing={isRefreshing}
        onRefresh={() => void refreshEvidence()}
        updatedLabel={loading ? "Syncing" : updatedAt ? `Updated ${formatDateTime(updatedAt)}` : "No records"}
      />
      <EvidenceProofStrip metrics={metricsForCounts(counts)} onMetricClick={applyFilterHref} />
      <EvidenceAuditTools
        endDate={auditEndDate}
        filter={filter}
        onEndDateChange={setAuditEndDate}
        onExportManifest={exportAuditManifest}
        onStartDateChange={setAuditStartDate}
        rows={auditRows}
        search={search}
        startDate={auditStartDate}
      />
      <DashboardWorkspace
        left={(
          <EvidenceLedger
            filter={filter}
            isError={Boolean(error)}
            isLoading={loading}
            onFilterChange={setFilter}
            onSearchChange={setSearch}
            onSelectRow={selectRow}
            rows={rows}
            search={search}
            selectedRowId={focusedRow?.id ?? null}
          />
        )}
        right={(
          <FocusedProofPanel
            evidenceError={evidencePackQuery.error instanceof Error ? evidencePackQuery.error : null}
            evidencePack={evidencePackQuery.data}
            isEvidenceLoading={evidencePackQuery.isLoading}
            isExporting={exporting}
            isReceiptLoading={receiptQuery.isLoading}
            onExport={() => void exportSelectedProof()}
            onPrint={() => {
              if (typeof window !== "undefined") window.print();
            }}
            receipt={receiptQuery.data}
            receiptError={receiptQuery.error instanceof Error ? receiptQuery.error : null}
            row={focusedRow}
          />
        )}
      />
      <EvidenceReport evidencePack={evidencePackQuery.data} receipt={receiptQuery.data} row={focusedRow} />
    </div>
  );
}
