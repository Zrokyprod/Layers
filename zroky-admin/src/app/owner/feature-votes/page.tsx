"use client";

/**
 * /owner/feature-votes - Owner view of customer feature-interest polls.
 *
 * Lists every registered coming-soon feature with vote counts,
 * percentage interested, and a "ship threshold" status badge.
 * Clicking a row reveals recent votes with masked emails + use_case
 * text. Provides a CSV export link.
 *
 * Auth: gated by the owner layout's PROVISIONING_TOKEN flow.
 */

import { useCallback, useEffect, useState } from "react";

import {
  AdminAllFeaturesResponse,
  AdminFeatureDetailResponse,
  AdminVoteRow,
  AdminVoteSummary,
  fetchFeatureInterestDetail,
  fetchFeatureInterestList,
  featureInterestExportUrl,
  getOwnerToken,
} from "@/lib/owner-api";


type VoteFilter = "" | "interested" | "not_interested";


function formatPct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value: string | null): string {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function StatusBadge({ status }: { status: AdminVoteSummary["status"] }) {
  if (status === "above_threshold") {
    return (
      <span
        className="status-pill"
        style={{ background: "#064e3b", color: "#a7f3d0" }}
        title="At or above ship threshold - consider prioritizing"
      >
        above threshold
      </span>
    );
  }
  if (status === "no_votes") {
    return (
      <span className="status-pill" style={{ background: "#1f2937", color: "#9ca3af" }}>
        no votes yet
      </span>
    );
  }
  return (
    <span
      className="status-pill"
      style={{ background: "#3f2a08", color: "#fcd34d" }}
      title="Below ship threshold - collect more data"
    >
      below threshold
    </span>
  );
}

function ProgressBar({ value, threshold }: { value: number; threshold: number }) {
  const filled = Math.min(100, Math.max(0, Math.round(value * 100)));
  const markerLeft = Math.min(100, Math.max(0, Math.round(threshold * 100)));
  return (
    <div
      style={{
        position: "relative",
        height: 8,
        background: "var(--surface-2, #1f2937)",
        borderRadius: 4,
        overflow: "hidden",
        width: 200,
      }}
    >
      <div
        style={{
          width: `${filled}%`,
          height: "100%",
          background: value >= threshold ? "#10b981" : "#f59e0b",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: -2,
          left: `${markerLeft}%`,
          width: 2,
          height: 12,
          background: "#e5e7eb",
        }}
        title={`Ship threshold: ${formatPct(threshold)}`}
      />
    </div>
  );
}


export default function OwnerFeatureVotesPage() {
  const [list, setList] = useState<AdminAllFeaturesResponse | null>(null);
  const [detail, setDetail] = useState<AdminFeatureDetailResponse | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<VoteFilter>("");
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revealedEmails, setRevealedEmails] = useState<Set<string>>(new Set());

  const loadList = useCallback(() => {
    const controller = new AbortController();
    setLoadingList(true);
    setError(null);
    fetchFeatureInterestList(controller.signal)
      .then((res) => {
        setList(res);
        // Auto-select first feature with votes (or first feature)
        if (res.features.length > 0 && selected === null) {
          const firstWithVotes = res.features.find((f) => f.total > 0);
          setSelected((firstWithVotes ?? res.features[0]).feature_key);
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load."))
      .finally(() => setLoadingList(false));
    return () => controller.abort();
  }, [selected]);

  useEffect(() => loadList(), [loadList]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    setLoadingDetail(true);
    fetchFeatureInterestDetail(
      selected,
      { limit: 100, vote: filter || undefined },
      controller.signal,
    )
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load votes."))
      .finally(() => setLoadingDetail(false));
    return () => controller.abort();
  }, [selected, filter]);

  // CSV export with the admin token to trigger download.
  const handleExport = useCallback(async () => {
    if (!selected) return;
    const token = getOwnerToken();
    try {
      const res = await fetch(featureInterestExportUrl(selected), {
        headers: { "x-zroky-admin-token": token },
        cache: "no-store",
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `feature_votes_${selected.replace(/\./g, "_")}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed.");
    }
  }, [selected]);

  const toggleReveal = useCallback((voteId: string) => {
    setRevealedEmails((prev) => {
      const next = new Set(prev);
      if (next.has(voteId)) {
        next.delete(voteId);
      } else {
        next.add(voteId);
      }
      return next;
    });
  }, []);

  return (
    <div className="owner-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Feature Interest</h2>
          <p className="hint">
            Customer interest in coming-soon features. Used to validate demand
            before committing engineering time.
          </p>
        </div>
        <button
          className="btn btn-soft"
          onClick={loadList}
          disabled={loadingList}
        >
          Refresh
        </button>
      </div>

      {error && <div className="alert-strip alert-strip-error">{error}</div>}

      {/* ─── Feature summary table ─────────────────────────────────────── */}

      <div className="owner-table-wrap">
        <table className="owner-table">
          <thead>
            <tr>
              {["Feature", "Total", "Interested", "%", "Progress", "Status", "Last vote"].map((h) => (
                <th key={h} className="owner-th">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loadingList && (
              <tr>
                <td colSpan={7} className="owner-td owner-td-empty">Loading...</td>
              </tr>
            )}
            {!loadingList && list && list.features.length === 0 && (
              <tr>
                <td colSpan={7} className="owner-td owner-td-empty">
                  No coming-soon features registered. Add one in
                  app/services/feature_interest_registry.py.
                </td>
              </tr>
            )}
            {list?.features.map((f) => {
              const active = f.feature_key === selected;
              return (
                <tr
                  key={f.feature_key}
                  className="owner-tr"
                  style={{
                    cursor: "pointer",
                    background: active ? "var(--accent-bg, rgba(99,102,241,0.08))" : undefined,
                  }}
                  onClick={() => setSelected(f.feature_key)}
                >
                  <td className="owner-td">
                    <strong>{f.name}</strong>
                    <div className="hint" style={{ fontSize: 11 }}>
                      <code>{f.feature_key}</code>
                    </div>
                  </td>
                  <td className="owner-td">{f.total}</td>
                  <td className="owner-td">
                    <span style={{ color: "#10b981" }}>Interested {f.interested}</span>{" "}
                    <span className="hint">/ Not interested {f.not_interested}</span>
                  </td>
                  <td className="owner-td">{formatPct(f.interested_pct)}</td>
                  <td className="owner-td">
                    <ProgressBar value={f.interested_pct} threshold={f.ships_after_threshold} />
                  </td>
                  <td className="owner-td">
                    <StatusBadge status={f.status} />
                  </td>
                  <td className="owner-td owner-td-ts">{formatDate(f.last_voted_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ─── Detail panel for selected feature ─────────────────────────── */}

      {selected && (
        <div className="panel" style={{ marginTop: 24 }}>
          <div className="owner-page-header">
            <div>
              <h3 style={{ margin: 0 }}>
                Detail: <code>{selected}</code>
              </h3>
              {detail?.summary.description && (
                <p className="hint" style={{ marginTop: 4 }}>
                  {detail.summary.description}
                </p>
              )}
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <select
                className="owner-select"
                value={filter}
                onChange={(e) => setFilter(e.target.value as VoteFilter)}
              >
                <option value="">All votes</option>
                <option value="interested">Interested only</option>
                <option value="not_interested">Not interested only</option>
              </select>
              <button
                className="btn btn-soft"
                onClick={() => void handleExport()}
                disabled={!detail || detail.recent_votes.length === 0}
              >
                Export CSV
              </button>
            </div>
          </div>

          {loadingDetail && <p className="hint">Loading votes...</p>}

          {detail && !loadingDetail && (
            <div className="owner-table-wrap" style={{ marginTop: 12 }}>
              <table className="owner-table">
                <thead>
                  <tr>
                    {["When", "Vote", "User", "Project", "Use case"].map((h) => (
                      <th key={h} className="owner-th">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {detail.recent_votes.length === 0 && (
                    <tr>
                      <td colSpan={5} className="owner-td owner-td-empty">
                        No votes match the current filter.
                      </td>
                    </tr>
                  )}
                  {detail.recent_votes.map((row: AdminVoteRow) => {
                    const revealed = revealedEmails.has(row.vote_id);
                    return (
                      <tr key={row.vote_id} className="owner-tr">
                        <td className="owner-td owner-td-ts">{formatDate(row.created_at)}</td>
                        <td className="owner-td">
                          {row.vote === "interested" ? (
                            <span style={{ color: "#10b981" }}>Interested</span>
                          ) : (
                            <span className="hint">Not interested</span>
                          )}
                        </td>
                        <td className="owner-td owner-td-truncate">
                          {row.user_email_masked || (
                            <code>{row.user_subject}</code>
                          )}
                          {row.user_email_masked && (
                            <>
                              {" "}
                              <button
                                className="btn btn-soft"
                                style={{ padding: "2px 6px", fontSize: 11 }}
                                onClick={() => toggleReveal(row.vote_id)}
                                title="Show/hide full subject"
                              >
                                {revealed ? "hide" : "reveal"}
                              </button>
                              {revealed && (
                                <div className="hint" style={{ fontSize: 11 }}>
                                  subject: <code>{row.user_subject}</code>
                                </div>
                              )}
                            </>
                          )}
                        </td>
                        <td className="owner-td owner-td-truncate">
                          {row.project_name || (
                            <code className="hint">{row.project_id}</code>
                          )}
                        </td>
                        <td className="owner-td">
                          {row.use_case ? (
                            <em style={{ color: "#a3a3a3" }}>&ldquo;{row.use_case}&rdquo;</em>
                          ) : (
                            <span className="hint">-</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
