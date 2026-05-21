"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { listIssues, resolveIssue, listDetectors } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { IssueItem, IssueStatus, DetectorInfo } from "@/lib/types";
import {
  allDetectorCategories,
  detectorBadgeClass,
  detectorLabel,
  getDetectorMeta,
  severityBadgeColor,
} from "@/lib/detector-meta";

// ── Tab definition ────────────────────────────────────────────────────────────

type Tab = "open" | "resolved" | "ignored" | "rules";

const TABS: { id: Tab; label: string; helper: string }[] = [
  { id: "open", label: "Open", helper: "Untriaged issues needing fix." },
  { id: "resolved", label: "Resolved", helper: "Closed via fix or auto-resolve." },
  { id: "ignored", label: "Ignored", helper: "Muted by triage — not actionable but tracked." },
  { id: "rules", label: "Rules", helper: "Detector vocabulary + thresholds." },
];

// ── Helpers ───────────────────────────────────────────────────────────────────
//
// Vocab + colors come from `@/lib/detector-meta` so every page renders the same
// label and badge color for any backend-emitted category — including the 11
// new Layer 1-3 detectors that didn't exist when this page was first written.

function codeLabel(code: string): string {
  return detectorLabel(code);
}

function codeBadgeClass(code: string): string {
  return detectorBadgeClass(code);
}

function severityBadge(sev: string) {
  const color = severityBadgeColor(sev);
  return (
    <span
      className={`alert-cat-badge badge-${color}`}
      style={{ fontSize: "0.65rem", padding: "1px 6px" }}
    >
      {sev}
    </span>
  );
}

function formatUsd(val: number): string {
  if (val === 0) return "$0";
  if (val < 0.01) return `<$0.01`;
  return `$${val.toFixed(2)}`;
}

// ── Main page ─────────────────────────────────────────────────────────────────

function IssuesPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const rawTab = searchParams.get("tab") as Tab | null;
  const activeTab: Tab = rawTab && ["open", "resolved", "rules"].includes(rawTab) ? rawTab : "open";

  function setTab(tab: Tab) {
    router.replace(`/issues?tab=${tab}`);
  }

  return (
    <div>
      <div className="tab-bar" role="tablist" aria-label="Issues tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={activeTab === t.id}
            className={`tab-btn${activeTab === t.id ? " tab-btn-active" : ""}`}
            onClick={() => setTab(t.id)}
            title={t.helper}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "open" && <IssueList status="open" />}
      {activeTab === "resolved" && <IssueList status="resolved" />}
      {activeTab === "ignored" && <IssueList status="ignored" />}
      {activeTab === "rules" && <RulesPanel />}
    </div>
  );
}

export default function IssuesPage() {
  return (
    <Suspense fallback={<p className="hint">Loading issues…</p>}>
      <IssuesPageContent />
    </Suspense>
  );
}

// ── Filter toolbar ─────────────────────────────────────────────────────────────

interface Filters {
  failure_code: string;
  severity: string;
  has_fix: "" | "true" | "false";
}

function FilterBar({ filters, onChange }: { filters: Filters; onChange: (f: Filters) => void }) {
  return (
    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", padding: "0.75rem 0" }}>
      <select
        className="input input-sm"
        value={filters.failure_code}
        onChange={(e) => onChange({ ...filters, failure_code: e.target.value })}
        aria-label="Filter by code"
      >
        <option value="">All codes</option>
        {allDetectorCategories().map((meta) => (
          <option key={meta.code} value={meta.code}>{meta.label}</option>
        ))}
      </select>

      <select
        className="input input-sm"
        value={filters.severity}
        onChange={(e) => onChange({ ...filters, severity: e.target.value })}
        aria-label="Filter by severity"
      >
        <option value="">All severities</option>
        <option value="critical">Critical</option>
        <option value="high">High</option>
        <option value="medium">Medium</option>
        <option value="low">Low</option>
      </select>

      <select
        className="input input-sm"
        value={filters.has_fix}
        onChange={(e) => onChange({ ...filters, has_fix: e.target.value as Filters["has_fix"] })}
        aria-label="Filter by fix status"
      >
        <option value="">Fix: any</option>
        <option value="true">Has fix</option>
        <option value="false">No fix</option>
      </select>

      {(filters.failure_code || filters.severity || filters.has_fix) && (
        <button
          className="btn btn-soft btn-sm"
          onClick={() => onChange({ failure_code: "", severity: "", has_fix: "" })}
        >
          Clear
        </button>
      )}
    </div>
  );
}

// ── Issue list ─────────────────────────────────────────────────────────────────

function IssueList({ status }: { status: IssueStatus }) {
  const [items, setItems] = useState<IssueItem[]>([]);
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>({ failure_code: "", severity: "", has_fix: "" });
  const abortRef = useRef<AbortController | null>(null);

  const loadPage = useCallback(
    async (nextCursor?: string | null, activeFilters?: Filters) => {
      if (nextCursor === null) return;
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      setError(null);
      const f = activeFilters ?? filters;
      try {
        const data = await listIssues(
          {
            status,
            cursor: nextCursor ?? undefined,
            limit: 25,
            ...(f.failure_code ? { failure_code: f.failure_code } : {}),
            ...(f.severity ? { severity: f.severity } : {}),
            ...(f.has_fix ? { has_fix: f.has_fix === "true" } : {}),
          },
          ctrl.signal,
        );
        setItems((prev) => (nextCursor ? [...prev, ...data.items] : data.items));
        setCursor(data.next_cursor);
      } catch (e: unknown) {
        if ((e as { name?: string }).name === "AbortError") return;
        setError((e as { message?: string }).message ?? "Failed to load issues.");
      } finally {
        setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [status],
  );

  useEffect(() => {
    setItems([]);
    setCursor(undefined);
    void loadPage(undefined, filters);
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  function applyFilters(f: Filters) {
    setFilters(f);
    setItems([]);
    setCursor(undefined);
    void loadPage(undefined, f);
  }

  async function onResolve(e: React.MouseEvent, issueId: string) {
    e.preventDefault();
    e.stopPropagation();
    setResolvingId(issueId);
    try {
      const updated = await resolveIssue(issueId, { resolution_source: "manual" });
      setItems((prev) => prev.filter((i) => i.id !== updated.id));
    } catch {
    } finally {
      setResolvingId(null);
    }
  }

  return (
    <section>
      <FilterBar filters={filters} onChange={applyFilters} />

      {loading && items.length === 0 ? (
        <div className="loading" />
      ) : error ? (
        <div className="panel">
          <p className="notif-error">{error}</p>
          <button className="btn btn-soft" onClick={() => void loadPage(undefined, filters)}>Retry</button>
        </div>
      ) : items.length === 0 ? (
        <div className="empty">
          {status === "open" ? "No open issues — all clear." : "No resolved issues."}
        </div>
      ) : (
        <div className="panel">
          <div className="list">
            {items.map((issue) => (
              <Link key={issue.id} href={`/issues/${issue.id}`} className="notif-row" style={{ textDecoration: "none", color: "inherit" }}>
                <div className="notif-body">
                  <div className="notif-title-row">
                    <span
                      className={codeBadgeClass(issue.failure_code)}
                      title={getDetectorMeta(issue.failure_code).description}
                    >
                      <span aria-hidden="true">{getDetectorMeta(issue.failure_code).icon}</span>{" "}
                      {codeLabel(issue.failure_code)}
                    </span>
                    <span
                      className={`detector-layer-chip layer-${getDetectorMeta(issue.failure_code).layer}`}
                      title={`Layer ${getDetectorMeta(issue.failure_code).layer}`}
                    >
                      {getDetectorMeta(issue.failure_code).layer}
                    </span>
                    {severityBadge(issue.severity)}
                    {issue.agent_name && (
                      <span className="mono" style={{ fontSize: "0.75rem" }}>
                        {issue.agent_name}
                      </span>
                    )}
                    <span className="notif-meta" style={{ marginLeft: "auto", display: "flex", gap: "1rem" }}>
                      <span title="Occurrences">{issue.occurrence_count}×</span>
                      <span title="Blast radius (cumulative cost)" style={{ color: issue.blast_radius_usd > 1 ? "var(--color-red)" : "inherit" }}>
                        {formatUsd(issue.blast_radius_usd)}
                      </span>
                    </span>
                  </div>

                  <div className="notif-meta" style={{ marginTop: "0.25rem" }}>
                    <span>First: {formatDateTime(issue.first_seen_at)}</span>
                    <span style={{ marginLeft: "1rem" }}>Last: {formatDateTime(issue.last_seen_at)}</span>
                    {issue.prompt_fingerprint && (
                      <span className="mono" style={{ marginLeft: "1rem", fontSize: "0.7rem" }}>
                        fp:{issue.prompt_fingerprint.slice(0, 8)}
                      </span>
                    )}
                    {issue.last_fix_id && (
                      <span style={{ marginLeft: "1rem", fontSize: "0.75rem", color: "var(--color-green)" }}>
                        ✓ fix pending
                      </span>
                    )}
                  </div>
                </div>

                {status === "open" && (
                  <div className="notif-actions" onClick={(e) => e.preventDefault()}>
                    <button
                      type="button"
                      className="btn btn-soft btn-sm"
                      onClick={(e) => void onResolve(e, issue.id)}
                      disabled={resolvingId === issue.id}
                    >
                      {resolvingId === issue.id ? "…" : "Resolve"}
                    </button>
                  </div>
                )}
              </Link>
            ))}
          </div>

          {cursor && (
            <div style={{ padding: "1rem", textAlign: "center" }}>
              <button className="btn btn-soft" onClick={() => void loadPage(cursor)} disabled={loading}>
                {loading ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

// ── Rules panel ────────────────────────────────────────────────────────────────

function RulesPanel() {
  const [detectors, setDetectors] = useState<DetectorInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    listDetectors(ctrl.signal)
      .then((res) => setDetectors(res.items))
      .catch((e: unknown) => {
        if ((e as { name?: string }).name === "AbortError") return;
        setError((e as { message?: string }).message ?? "Failed to load detectors.");
      })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, []);

  return (
    <section className="panel">
      <header className="panel-header">
        <div>
          <h3>Detection Rules</h3>
          <p>Live from the entry-point registry — {loading ? "loading…" : `${detectors.length} loaded`}</p>
        </div>
      </header>

      {loading && <div className="loading" />}

      {error && <p className="notif-error" style={{ padding: "0.75rem" }}>{error}</p>}

      {!loading && !error && (
        <div className="list">
          {detectors.map((d) => (
            <div key={d.name} className="notif-row">
              <div className="notif-body">
                <div className="notif-title-row">
                  <span className={codeBadgeClass(d.failure_code)}>{d.label}</span>
                  <span className="mono" style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>
                    {d.speed_class}
                  </span>
                  <span className="mono" style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>
                    conf ≥ {(d.confidence_threshold * 100).toFixed(0)}%
                  </span>
                  {!d.loaded && (
                    <span
                      className="alert-cat-badge badge-gray"
                      style={{ fontSize: "0.65rem", marginLeft: "auto" }}
                      title="Registered in metadata but not loaded at runtime"
                    >
                      not loaded
                    </span>
                  )}
                </div>
                <p style={{ marginTop: "0.25rem", fontSize: "0.85rem" }}>{d.description}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
