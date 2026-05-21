"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { exportCallsCsv, exportCallsJson } from "@/lib/api";
import { formatCount, formatDateTime, formatUsd, safeString } from "@/lib/format";
import { useListCalls, useResolveDiagnosis } from "@/lib/hooks";
import { callsFilterSchema, type CallsFilterFormData } from "@/lib/schemas";
import { StatusPill } from "@/components/status-pill";
import type { CallListItem } from "@/lib/types";

const PAGE_SIZE = 50;

const emptyFilters: CallsFilterFormData = {
  status: "",
  model: "",
  user_id: "",
  call_type: "",
  agent_name: "",
  date_from: "",
  date_to: "",
  sort_by: "created_at",
  sort_order: "desc",
};

type SortKey = "created_at" | "cost_usd" | "total_tokens" | "latency_ms";

function resolveUserIdFilterFromSearchParams(searchParams: URLSearchParams): string {
  return searchParams.get("user_id")?.trim() || searchParams.get("user")?.trim() || "";
}

function SortTh({
  label,
  col,
  current,
  order,
  onSort,
}: {
  label: string;
  col: SortKey;
  current: SortKey;
  order: "asc" | "desc";
  onSort: (col: SortKey) => void;
}) {
  const active = current === col;
  return (
    <th
      className={`sortable-th calls-sort-th ${active ? "sortable-th-active" : ""}`}
      onClick={() => onSort(col)}
    >
      {label}
      {active ? (order === "desc" ? " ↓" : " ↑") : " ↕"}
    </th>
  );
}

function downloadSelectedCallsJson(rows: CallListItem[], selectedIds: Set<string>) {
  const selectedRows = rows.filter((row) => selectedIds.has(row.call_id));
  const blob = new Blob([
    JSON.stringify(
      {
        exported_at: new Date().toISOString(),
        row_count: selectedRows.length,
        items: selectedRows,
      },
      null,
      2,
    ),
  ], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "selected-calls.json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function CallsPageContent() {
  const searchParams = useSearchParams();
  const [page, setPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [exportingJson, setExportingJson] = useState(false);
  const [bulkMessage, setBulkMessage] = useState<string>("");
  const resolveDiagnosisMutation = useResolveDiagnosis();

  const [appliedFilters, setAppliedFilters] = useState<CallsFilterFormData>(() => ({
    status: searchParams.get("status")?.trim() ?? "",
    model: searchParams.get("model")?.trim() ?? "",
    user_id: resolveUserIdFilterFromSearchParams(searchParams),
    call_type: searchParams.get("call_type")?.trim() ?? "",
    agent_name: searchParams.get("agent_name")?.trim() ?? "",
    date_from: searchParams.get("date_from")?.trim() ?? "",
    date_to: searchParams.get("date_to")?.trim() ?? "",
    sort_by: (searchParams.get("sort_by") as SortKey) ?? "created_at",
    sort_order: (searchParams.get("sort_order") as "asc" | "desc") ?? "desc",
  }));

  const callsQuery = useListCalls({
    ...appliedFilters,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
  } = useForm<CallsFilterFormData>({
    resolver: zodResolver(callsFilterSchema),
    defaultValues: appliedFilters,
  });

  useEffect(() => {
    const urlFilters: CallsFilterFormData = {
      status: searchParams.get("status")?.trim() ?? "",
      model: searchParams.get("model")?.trim() ?? "",
      user_id: resolveUserIdFilterFromSearchParams(searchParams),
      call_type: searchParams.get("call_type")?.trim() ?? "",
      agent_name: searchParams.get("agent_name")?.trim() ?? "",
      date_from: searchParams.get("date_from")?.trim() ?? "",
      date_to: searchParams.get("date_to")?.trim() ?? "",
      sort_by: (searchParams.get("sort_by") as SortKey) ?? "created_at",
      sort_order: (searchParams.get("sort_order") as "asc" | "desc") ?? "desc",
    };
    reset(urlFilters);
    setAppliedFilters(urlFilters);
    setPage(0);
    setSelectedIds(new Set());
  }, [searchParams, reset]);

  const onSubmit = handleSubmit((data) => {
    setPage(0);
    setSelectedIds(new Set());
    setAppliedFilters(data);
  });

  const handleSort = (col: SortKey) => {
    const currentSortBy = appliedFilters.sort_by as SortKey;
    const newOrder: "asc" | "desc" = currentSortBy === col && appliedFilters.sort_order === "desc" ? "asc" : "desc";
    const updated = { ...appliedFilters, sort_by: col, sort_order: newOrder };
    setAppliedFilters(updated);
    setValue("sort_by", col);
    setValue("sort_order", newOrder);
    setPage(0);
  };

  const rows = callsQuery.data?.items ?? [];
  const total = callsQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const loading = callsQuery.isLoading;
  const error = callsQuery.error?.message ?? null;

  // Bulk selection
  const allSelected = rows.length > 0 && rows.every((r) => selectedIds.has(r.call_id));
  const toggleAll = () => {
    if (allSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        rows.forEach((r) => next.delete(r.call_id));
        return next;
      });
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        rows.forEach((r) => next.add(r.call_id));
        return next;
      });
    }
  };
  const toggleRow = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleExport = () => {
    exportCallsCsv({
      status: appliedFilters.status || undefined,
      model: appliedFilters.model || undefined,
      user_id: appliedFilters.user_id || undefined,
      call_type: appliedFilters.call_type || undefined,
      agent_name: appliedFilters.agent_name || undefined,
      start_time: appliedFilters.date_from || undefined,
      end_time: appliedFilters.date_to || undefined,
    });
  };

  const handleExportJson = async () => {
    setExportingJson(true);
    try {
      await exportCallsJson({
        status: appliedFilters.status || undefined,
        model: appliedFilters.model || undefined,
        user_id: appliedFilters.user_id || undefined,
        call_type: appliedFilters.call_type || undefined,
        agent_name: appliedFilters.agent_name || undefined,
        start_time: appliedFilters.date_from || undefined,
        end_time: appliedFilters.date_to || undefined,
        sort_by: appliedFilters.sort_by,
        sort_order: appliedFilters.sort_order,
      });
    } finally {
      setExportingJson(false);
    }
  };

  const hasActiveFilters = Boolean(
    appliedFilters.status ||
      appliedFilters.model ||
      appliedFilters.user_id ||
      appliedFilters.call_type ||
      appliedFilters.agent_name ||
      appliedFilters.date_from ||
      appliedFilters.date_to,
  );

  const sortBy = appliedFilters.sort_by as SortKey;
  const sortOrder = appliedFilters.sort_order as "asc" | "desc";
  const selectedRows = rows.filter((row) => selectedIds.has(row.call_id));
  const selectedDiagnosisIds = Array.from(
    new Set(
      selectedRows.flatMap((row) => row.diagnoses ?? []).filter((diagnosisId) => Boolean(diagnosisId)),
    ),
  );

  const handleBulkResolve = async () => {
    if (selectedDiagnosisIds.length === 0) {
      setBulkMessage("Selected calls do not have linked diagnoses to resolve.");
      return;
    }

    let resolvedCount = 0;
    let failedCount = 0;

    for (const diagnosisId of selectedDiagnosisIds) {
      try {
        await resolveDiagnosisMutation.mutateAsync(diagnosisId);
        resolvedCount += 1;
      } catch {
        failedCount += 1;
      }
    }

    setBulkMessage(
      failedCount > 0
        ? `Resolved ${resolvedCount} linked diagnoses. ${failedCount} failed.`
        : `Resolved ${resolvedCount} linked diagnoses successfully.`,
    );
    await callsQuery.refetch();
  };

  return (
    <>
      {/* ── Filter panel ── */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Calls</h3>
            <p>
              {callsQuery.data
                ? `${formatCount(total)} total · page ${page + 1} of ${totalPages}`
                : "Loading…"}
            </p>
          </div>
          <div className="actions">
            <button
              type="button"
              className="btn btn-soft"
              onClick={handleExport}
              title="Download current filter as CSV (up to 5,000 rows)"
            >
              Export CSV
            </button>
            <button
              type="button"
              className="btn btn-soft"
              onClick={() => void handleExportJson()}
              disabled={exportingJson}
              title="Download current filter as JSON (up to 2,000 rows)"
            >
              {exportingJson ? "Exporting…" : "Export JSON"}
            </button>
            <button type="button" className="btn btn-soft" onClick={() => void callsQuery.refetch()}>
              Refresh
            </button>
          </div>
        </header>

        <form className="filters" onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="status">Status</label>
            <select id="status" {...register("status")}>
              <option value="">All</option>
              <option value="queued">queued</option>
              <option value="processing">processing</option>
              <option value="completed">completed</option>
              <option value="failed">failed</option>
              <option value="enqueue_failed">enqueue_failed</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="model">Model</label>
            <input id="model" {...register("model")} placeholder="gpt-4.1-mini" />
          </div>

          <div className="field">
            <label htmlFor="agentName">Agent</label>
            <input id="agentName" {...register("agent_name")} placeholder="agent name" />
          </div>

          <div className="field">
            <label htmlFor="userId">User ID</label>
            <input id="userId" {...register("user_id")} placeholder="user id" />
          </div>

          <div className="field">
            <label htmlFor="callType">Call Type</label>
            <input id="callType" {...register("call_type")} placeholder="chat" />
          </div>

          <div className="field">
            <label htmlFor="dateFrom">From</label>
            <input id="dateFrom" type="datetime-local" {...register("date_from")} />
          </div>

          <div className="field">
            <label htmlFor="dateTo">To</label>
            <input id="dateTo" type="datetime-local" {...register("date_to")} />
          </div>

          <div className="actions calls-filter-actions">
            <button className="btn btn-primary" type="submit">
              Apply
            </button>
            <button
              className="btn btn-soft"
              type="button"
              onClick={() => {
                reset(emptyFilters);
                setAppliedFilters(emptyFilters);
                setPage(0);
              }}
            >
              Reset
            </button>
          </div>
        </form>

        {appliedFilters.user_id ? (
          <div className="hint">Prefilled for user: {appliedFilters.user_id}</div>
        ) : null}
      </section>

      {/* ── Bulk action bar ── */}
      {selectedIds.size > 0 ? (
        <div className="bulk-bar">
          <span className="bulk-bar-count">
            {selectedIds.size} selected · {selectedDiagnosisIds.length} linked diagnosis{selectedDiagnosisIds.length !== 1 ? "es" : ""}
          </span>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => void handleBulkResolve()}
            disabled={resolveDiagnosisMutation.isPending || selectedDiagnosisIds.length === 0}
          >
            {resolveDiagnosisMutation.isPending ? "Resolving…" : "Resolve linked diagnoses"}
          </button>
          <button
            type="button"
            className="btn btn-soft btn-sm"
            onClick={() => downloadSelectedCallsJson(rows, selectedIds)}
          >
            Export selected JSON
          </button>
          <button
            type="button"
            className="btn btn-soft btn-sm"
            onClick={() => void navigator.clipboard.writeText(Array.from(selectedIds).join("\n"))}
          >
            Copy IDs
          </button>
          <button
            type="button"
            className="btn btn-soft btn-sm"
            onClick={() => setSelectedIds(new Set())}
          >
            Clear selection
          </button>
        </div>
      ) : null}

      {bulkMessage ? <p className="hint">{bulkMessage}</p> : null}

      {error ? <section className="panel"><p className="text-error">{error}</p></section> : null}

      {loading ? (
        <section className="panel">
          <div className="loading" />
        </section>
      ) : null}

      {/* ── Table ── */}
      {!loading && rows.length > 0 ? (
        <section className="panel">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="calls-select-th">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleAll}
                      aria-label="Select all on this page"
                    />
                  </th>
                  <SortTh label="Time" col="created_at" current={sortBy} order={sortOrder} onSort={handleSort} />
                  <th>Provider</th>
                  <th>Model</th>
                  <th>Agent</th>
                  <th>User ID</th>
                  <SortTh label="Tokens" col="total_tokens" current={sortBy} order={sortOrder} onSort={handleSort} />
                  <SortTh label="Cost" col="cost_usd" current={sortBy} order={sortOrder} onSort={handleSort} />
                  <SortTh label="Latency" col="latency_ms" current={sortBy} order={sortOrder} onSort={handleSort} />
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.call_id}
                    className={selectedIds.has(row.call_id) ? "row-selected" : ""}
                  >
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(row.call_id)}
                        onChange={() => toggleRow(row.call_id)}
                        aria-label={`Select call ${row.call_id}`}
                      />
                    </td>
                    <td>{formatDateTime(row.created_at)}</td>
                    <td>{safeString(row.provider, "unknown")}</td>
                    <td>
                      <Link href={`/calls/${row.call_id}`}>{safeString(row.model, "unknown")}</Link>
                    </td>
                    <td>{safeString(row.agent_name, "-")}</td>
                    <td>{safeString(row.user_id, "-")}</td>
                    <td className="mono">{formatCount(row.total_tokens)}</td>
                    <td className="mono">{formatUsd(row.cost_usd)}</td>
                    <td className="mono">{row.latency_ms != null ? `${row.latency_ms}ms` : "-"}</td>
                    <td>
                      <StatusPill value={row.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* ── Pagination ── */}
          <div className="pagination">
            <button
              type="button"
              className="btn btn-soft btn-sm"
              disabled={page === 0}
              onClick={() => { setPage(0); setSelectedIds(new Set()); }}
            >
              «
            </button>
            <button
              type="button"
              className="btn btn-soft btn-sm"
              disabled={page === 0}
              onClick={() => { setPage((p) => p - 1); setSelectedIds(new Set()); }}
            >
              ← Prev
            </button>
            <span className="pagination-info">
              Page {page + 1} / {totalPages}
            </span>
            <button
              type="button"
              className="btn btn-soft btn-sm"
              disabled={page >= totalPages - 1}
              onClick={() => { setPage((p) => p + 1); setSelectedIds(new Set()); }}
            >
              Next →
            </button>
            <button
              type="button"
              className="btn btn-soft btn-sm"
              disabled={page >= totalPages - 1}
              onClick={() => { setPage(totalPages - 1); setSelectedIds(new Set()); }}
            >
              »
            </button>
          </div>
        </section>
      ) : null}

      {!loading && rows.length === 0 ? (
        <section className="panel">
          <div className="empty calls-empty-state">
            <strong className="calls-empty-title">No calls matched the current filters</strong>
            <p>
              {hasActiveFilters
                ? "Try widening the date range, clearing a filter, or exporting the current empty result set definition for debugging."
                : "Calls will appear here once your SDK starts sending traffic."}
            </p>
            <div className="actions calls-empty-actions">
              <button
                type="button"
                className="btn btn-soft"
                onClick={() => {
                  reset(emptyFilters);
                  setAppliedFilters(emptyFilters);
                  setPage(0);
                }}
              >
                Reset filters
              </button>
              <Link href="/settings/keys" className="btn btn-primary">
                Get API key
              </Link>
            </div>
          </div>
        </section>
      ) : null}
    </>
  );
}

export default function CallsPage() {
  return (
    <Suspense fallback={<section className="panel"><div className="loading" /></section>}>
      <CallsPageContent />
    </Suspense>
  );
}
