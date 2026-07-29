"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { DashboardWorkspace } from "@/components/dashboard-scaffold";
import {
  fetchOutcomeGraphCoverage,
  fetchOutcomeGraphEvidenceExport,
  fetchOutcomeGraphs,
  type OutcomeGraphClassification,
  type OutcomeGraphCoverageSummary,
} from "@/lib/api";
import {
  buildOutcomeGraphLedgerRows,
  type EvidenceLedgerFilter,
  type EvidenceLedgerRow,
} from "@/lib/evidence-ledger";
import { EvidenceLedger } from "./EvidenceLedger";
import type { EvidenceProofMetric } from "./EvidenceProofStrip";
import { EvidenceVerdictHero } from "./EvidenceVerdictHero";
import { FocusedProofPanel } from "./FocusedProofPanel";

type EvidenceVerdict = {
  badge: string;
  copy: string;
  ctaHref: string;
  ctaLabel: string;
  title: string;
  tone: "danger" | "neutral" | "success" | "warning";
};

const caughtClassifications = new Set<OutcomeGraphClassification>(["wrong", "missing", "forbidden", "duplicate"]);
const attentionClassifications = new Set<OutcomeGraphClassification>(["stale", "conflicted", "unknown"]);

function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

function readFilter(): EvidenceLedgerFilter {
  if (typeof window === "undefined") return "all";
  const value = new URLSearchParams(window.location.search).get("filter");
  return value === "proven" || value === "caught" || value === "pending" || value === "needs_attention" ? value : "all";
}

function readGraphId(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("graph_id")?.trim() || null;
}

function replaceUrl(href: string) {
  if (typeof window !== "undefined") {
    window.history.replaceState({}, "", href);
  }
}

function classificationParam(filter: EvidenceLedgerFilter): OutcomeGraphClassification | undefined {
  if (filter === "proven") return "verified";
  if (filter === "pending") return "pending";
  return undefined;
}

function counts(summary: OutcomeGraphCoverageSummary | undefined): OutcomeGraphCoverageSummary["counts"] {
  const base = {
    conflicted: 0,
    duplicate: 0,
    forbidden: 0,
    missing: 0,
    pending: 0,
    stale: 0,
    unknown: 0,
    verified: 0,
    wrong: 0,
  } satisfies OutcomeGraphCoverageSummary["counts"];
  return { ...base, ...(summary?.counts ?? {}) };
}

function caughtCount(summary: OutcomeGraphCoverageSummary | undefined): number {
  const value = counts(summary);
  return value.wrong + value.missing + value.forbidden + value.duplicate;
}

function buildVerdict({
  error,
  loading,
  summary,
}: {
  error: unknown;
  loading: boolean;
  summary: OutcomeGraphCoverageSummary | undefined;
}): EvidenceVerdict {
  if (error) {
    return {
      badge: "Unavailable",
      copy: "Outcome graph ledger could not load.",
      ctaHref: "/integrations",
      ctaLabel: "Check integrations",
      title: "Proof ledger unavailable",
      tone: "danger",
    };
  }
  if (loading) {
    return {
      badge: "Syncing",
      copy: "Loading source-of-record outcome graphs.",
      ctaHref: "/evidence",
      ctaLabel: "Loading",
      title: "Loading proof ledger",
      tone: "neutral",
    };
  }
  const caught = caughtCount(summary);
  if ((summary?.total ?? 0) === 0) {
    return {
      badge: "No proof yet",
      copy: "Declare your first intent, then bind an Assurance Pack to start proving actions.",
      ctaHref: "/workflows",
      ctaLabel: "Declare intent",
      title: "No outcome graphs yet",
      tone: "neutral",
    };
  }
  if (caught === 0) {
    return {
      badge: "All proven",
      copy: `${formatCount(summary?.total ?? 0)} actions checked against the system of record.`,
      ctaHref: "/evidence?filter=proven",
      ctaLabel: "Review proven",
      title: `All ${formatCount(summary?.total ?? 0)} actions proven`,
      tone: "success",
    };
  }
  return {
    badge: "Caught",
    copy: "Actions claimed but not proven in this period.",
    ctaHref: "/evidence?filter=caught",
    ctaLabel: `Review ${formatCount(caught)}`,
    title: `${formatCount(caught)} actions claimed but not proven`,
    tone: "danger",
  };
}

function metricsForSummary(summary: OutcomeGraphCoverageSummary | undefined): EvidenceProofMetric[] {
  if (summary && summary.total === 0) {
    return [
      {
        detail: "Declare your first intent",
        href: "/workflows",
        label: "Setup",
        tone: "neutral",
        value: "Start",
      },
    ];
  }
  const value = counts(summary);
  return [
    {
      detail: "verified in system of record",
      href: "/evidence?filter=proven",
      label: "Verified",
      tone: "success",
      value: `${summary?.coverage_percent ?? 0}%`,
    },
    {
      detail: "wrong, missing, forbidden, duplicate",
      href: "/evidence?filter=caught",
      label: "Caught",
      tone: caughtCount(summary) > 0 ? "danger" : "neutral",
      value: String(caughtCount(summary)),
    },
    {
      detail: "waiting for source observations",
      href: "/evidence?filter=pending",
      label: "Pending",
      tone: value.pending > 0 ? "warning" : "neutral",
      value: String(value.pending),
    },
    {
      detail: "stale, conflicted, unknown",
      href: "/evidence?filter=needs_attention",
      label: "Needs attention",
      tone: value.stale + value.conflicted + value.unknown > 0 ? "warning" : "neutral",
      value: String(value.stale + value.conflicted + value.unknown),
    },
  ];
}

function clientFilter(rows: EvidenceLedgerRow[], filter: EvidenceLedgerFilter): EvidenceLedgerRow[] {
  if (filter === "caught") {
    return rows.filter((row) => caughtClassifications.has(row.classification ?? "unknown"));
  }
  if (filter === "needs_attention") {
    return rows.filter((row) => attentionClassifications.has(row.classification ?? "unknown"));
  }
  return rows;
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

export default function EvidencePage() {
  const [filter, setFilter] = useState<EvidenceLedgerFilter>(() => readFilter());
  const [search, setSearch] = useState("");
  const [selectedRowId, setSelectedRowId] = useState<string | null>(() => readGraphId());
  const [message, setMessage] = useState("");
  const [exporting, setExporting] = useState(false);

  const graphQuery = useQuery({
    queryKey: ["outcome-graphs", filter],
    queryFn: ({ signal }) => fetchOutcomeGraphs({ classification: classificationParam(filter), limit: 100 }, signal),
  });
  const coverageQuery = useQuery({
    queryKey: ["outcome-graphs", "coverage-summary"],
    queryFn: ({ signal }) => fetchOutcomeGraphCoverage(signal),
  });

  const rows = useMemo(
    () => clientFilter(buildOutcomeGraphLedgerRows(graphQuery.data?.items ?? []), filter),
    [filter, graphQuery.data?.items],
  );
  const loading = graphQuery.isLoading || coverageQuery.isLoading;
  const error = graphQuery.error || coverageQuery.error;
  const selectedRow = rows.find((row) => row.id === selectedRowId) ?? null;
  const focusedRow = selectedRow ?? rows[0] ?? null;
  const verdict = buildVerdict({ error, loading, summary: coverageQuery.data });
  const metrics = metricsForSummary(coverageQuery.data);
  const caught = caughtCount(coverageQuery.data);
  const total = coverageQuery.data?.total ?? 0;
  const isRefreshing = graphQuery.isFetching || coverageQuery.isFetching;

  useEffect(() => {
    if (loading || selectedRowId && rows.some((row) => row.id === selectedRowId)) return;
    setSelectedRowId(rows[0]?.id ?? null);
  }, [loading, rows, selectedRowId]);

  function applyFilter(nextFilter: EvidenceLedgerFilter) {
    setFilter(nextFilter);
    setSelectedRowId(null);
    replaceUrl(`/evidence?filter=${nextFilter}`);
  }

  function applyFilterHref(href: string) {
    const value = new URL(href, "http://zroky.local").searchParams.get("filter") as EvidenceLedgerFilter | null;
    applyFilter(value ?? "all");
  }

  function selectRow(row: EvidenceLedgerRow) {
    setSelectedRowId(row.id);
    replaceUrl(row.href);
  }

  async function refreshEvidence() {
    await Promise.all([graphQuery.refetch(), coverageQuery.refetch()]);
  }

  function exportRows() {
    setExporting(true);
    try {
      downloadJsonFile({ artifact: "zroky.outcome_graph_view", rows }, "zroky-outcome-graphs.json");
      setMessage(`Exported ${rows.length} outcome graph${rows.length === 1 ? "" : "s"}.`);
    } finally {
      setExporting(false);
    }
  }

  async function exportSelectedGraph() {
    if (!focusedRow) return;
    setExporting(true);
    try {
      const evidencePack = await fetchOutcomeGraphEvidenceExport(focusedRow.id);
      downloadJsonFile(evidencePack, `zroky-evidence-${focusedRow.id}.json`);
      setMessage("Evidence pack exported.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="dashboard-page evidence-page evidence-ledger-page ev-page">
      {message ? <div className="alert-strip ev-alert-strip">{message}</div> : null}
      <EvidenceVerdictHero
        {...verdict}
        isRefreshing={isRefreshing}
        metrics={metrics}
        onMetricClick={applyFilterHref}
        onRefresh={() => void refreshEvidence()}
        summaryDetail={total === 0 ? "Declare your first intent" : `${coverageQuery.data?.coverage_percent ?? 0}% verified in system of record`}
        summaryTitle={total === 0 ? "No outcome graphs yet" : `${formatCount(caught)} actions claimed but not proven`}
      />
      <DashboardWorkspace
        left={(
          <EvidenceLedger
            filter={filter}
            isError={Boolean(error)}
            isExporting={exporting}
            isLoading={loading}
            onFilterChange={applyFilter}
            onExportManifest={exportRows}
            onSearchChange={setSearch}
            onSelectRow={selectRow}
            rows={rows}
            search={search}
            selectedRowId={focusedRow?.id ?? null}
          />
        )}
        right={(
          <FocusedProofPanel
            isExporting={exporting}
            onExport={() => void exportSelectedGraph()}
            row={focusedRow}
          />
        )}
      />
    </div>
  );
}
