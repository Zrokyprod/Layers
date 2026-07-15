"use client";

import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { DashboardWorkspace } from "@/components/dashboard-scaffold";
import {
  getActionIntentReceipt,
  getEvidenceLedger,
  getEvidenceManifest,
  getRuntimePolicyEvidencePack,
  type ActionReceiptResponse,
  type RuntimePolicyEvidencePackResponse,
} from "@/lib/api";
import { statusLabel, statusTone } from "@/lib/action-status";
import { dashboardWindowDays } from "@/lib/dashboard-window";
import {
  resolveEvidenceLedgerDeepLink,
  type EvidenceLedgerCounts,
  type EvidenceLedgerFilter,
  type EvidenceLedgerRow,
} from "@/lib/evidence-ledger";
import { buildEvidenceArtifact } from "@/lib/evidence-artifact";
import { formatDateTime } from "@/lib/format";
import { useDashboardStore } from "@/lib/store";
import { EvidenceLedger } from "./EvidenceLedger";
import type { EvidenceProofMetric } from "./EvidenceProofStrip";
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
  counts: EvidenceLedgerCounts;
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

function metricsForCounts(counts: EvidenceLedgerCounts): EvidenceProofMetric[] {
  return [
    {
      detail: "matched signed receipts",
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
      detail: "action records, guard decisions, and outcomes",
      href: "/evidence?filter=all",
      label: "Total proof records",
      tone: "neutral",
      value: String(counts.total),
    },
  ];
}

export default function EvidencePage() {
  const [initial] = useState(() => readSearchParams());
  const [deepLink, setDeepLink] = useState<DeepLinkState>(initial.deepLink);
  const [filter, setFilter] = useState<EvidenceLedgerFilter>(initial.filter);
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const dateRange = useDashboardStore((state) => state.dateRange);
  const selectedProject = useDashboardStore((state) => state.selectedProject);
  const windowDays = useMemo(() => dashboardWindowDays(dateRange), [dateRange]);
  const deferredSearch = useDeferredValue(search.trim());

  const ledgerQuery = useInfiniteQuery({
    queryKey: ["evidence", "ledger", selectedProject, windowDays, filter, deferredSearch],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => getEvidenceLedger({
      days: windowDays,
      filter,
      limit: 100,
      offset: pageParam,
      search: deferredSearch,
    }, signal),
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.offset + lastPage.items.length : undefined,
    placeholderData: (previousData) => previousData,
    staleTime: 15_000,
  });
  const rows = useMemo<EvidenceLedgerRow[]>(() => (
    ledgerQuery.data?.pages.flatMap((page) => page.items.map((item) => ({
      actionId: item.action_id,
      actionType: item.action_type,
      agentName: item.agent_name,
      callId: item.call_id,
      checkedAt: item.checked_at,
      decisionId: item.decision_id,
      detail: item.detail,
      digest: item.digest,
      exportKind: item.export_kind,
      exportable: item.exportable,
      href: item.href,
      id: item.id,
      kind: item.kind,
      outcomeId: item.outcome_id,
      sourceLabel: item.source_label,
      status: item.status,
      statusLabel: statusLabel(item.status),
      systemRef: item.system_ref,
      title: item.title,
      tone: statusTone(item.status),
      traceId: item.trace_id,
    }))) ?? []
  ), [ledgerQuery.data?.pages]);
  const firstLedgerPage = ledgerQuery.data?.pages[0];
  const loading = ledgerQuery.isLoading;
  const error = ledgerQuery.error;
  const counts: EvidenceLedgerCounts = firstLedgerPage ? {
    exceptions: firstLedgerPage.counts.exceptions,
    exportReady: firstLedgerPage.counts.export_ready,
    needsVerification: firstLedgerPage.counts.needs_verification,
    total: firstLedgerPage.counts.total,
  } : { exceptions: 0, exportReady: 0, needsVerification: 0, total: 0 };
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
    await ledgerQuery.refetch();
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

  async function exportAuditManifest() {
    setMessage("");
    setExporting(true);
    try {
      const manifest = await getEvidenceManifest({
        dashboard_origin: typeof window === "undefined" ? undefined : window.location.origin,
        days: windowDays,
        end_date: "",
        filter,
        search,
        start_date: "",
      });
      const scope = [
        filter,
        search.trim() ? safeFilePart(search.trim()) : "all",
        "current",
      ].join("-");
      downloadJsonFile(manifest, `zroky-evidence-manifest-${safeFilePart(scope)}.json`);
      const count = manifest.scope.total_records;
      setMessage(`Audit manifest exported for ${count} proof record${count === 1 ? "" : "s"}.`);
    } catch (downloadError) {
      setMessage(downloadError instanceof Error ? downloadError.message : "Evidence manifest export failed.");
    } finally {
      setExporting(false);
    }
  }

  const verdict = buildVerdict({ counts, error, loading });
  const updatedAt = latestCheckedAt(rows);
  const isRefreshing = ledgerQuery.isFetching;

  return (
    <div className="dashboard-page evidence-page evidence-ledger-page ev-page">
      {message ? <div className="alert-strip ev-alert-strip">{message}</div> : null}
      <EvidenceVerdictHero
        {...verdict}
        isRefreshing={isRefreshing}
        metrics={metricsForCounts(counts)}
        onMetricClick={applyFilterHref}
        onRefresh={() => void refreshEvidence()}
        updatedLabel={loading ? "Syncing" : updatedAt ? `Updated ${formatDateTime(updatedAt)}` : "No records"}
      />
      <DashboardWorkspace
        left={(
          <EvidenceLedger
            filter={filter}
            hasMore={Boolean(ledgerQuery.hasNextPage)}
            isError={Boolean(error)}
            isExporting={exporting}
            isLoading={loading}
            isLoadingMore={ledgerQuery.isFetchingNextPage}
            onFilterChange={(nextFilter) => applyFilterHref(`/evidence?filter=${nextFilter}`)}
            onExportManifest={() => void exportAuditManifest()}
            onLoadMore={() => void ledgerQuery.fetchNextPage()}
            onSearchChange={setSearch}
            onSelectRow={selectRow}
            rows={rows}
            search={search}
            selectedRowId={focusedRow?.id ?? null}
            totalMatching={firstLedgerPage?.total_matching ?? rows.length}
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
