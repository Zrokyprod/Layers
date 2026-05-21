"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getIssue, resolveIssue } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { IssueItem } from "@/lib/types";
import {
  detectorBadgeClass,
  detectorLabel,
  getDetectorMeta,
  severityBadgeColor,
} from "@/lib/detector-meta";

// Vocab + colors share the central `lib/detector-meta` catalog. Local lookup
// tables removed — they only covered 6 of the 16 backend categories.

function formatUsd(val: number): string {
  if (val === 0) return "$0";
  if (val < 0.01) return "<$0.01";
  return `$${val.toFixed(2)}`;
}

export default function IssueDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [issue, setIssue] = useState<IssueItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);

  useEffect(() => {
    if (!id) return;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    getIssue(id, ctrl.signal)
      .then(setIssue)
      .catch((e: unknown) => {
        if ((e as { name?: string }).name === "AbortError") return;
        setError((e as { message?: string }).message ?? "Failed to load issue.");
      })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [id]);

  async function onResolve() {
    if (!issue) return;
    setResolving(true);
    try {
      await resolveIssue(issue.id, { resolution_source: "manual" });
      router.push("/issues");
    } catch {
    } finally {
      setResolving(false);
    }
  }

  if (loading) return <div className="loading" />;
  if (error) return (
    <div className="panel">
      <p className="notif-error">{error}</p>
      <Link href="/issues" className="btn btn-soft" style={{ marginTop: "1rem" }}>← Back</Link>
    </div>
  );
  if (!issue) return null;

  const meta = getDetectorMeta(issue.failure_code);
  const codeBadge = detectorBadgeClass(issue.failure_code);
  const sevBadge = `alert-cat-badge badge-${severityBadgeColor(issue.severity)}`;

  return (
    <div>
      {/* ── Breadcrumb ── */}
      <div style={{ marginBottom: "1rem", fontSize: "0.85rem" }}>
        <Link href="/issues" className="notif-action-link">← Issues</Link>
      </div>

      {/* ── Header ── */}
      <div className="panel" style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem", flexWrap: "wrap" }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap", marginBottom: "0.5rem" }}>
              <span className={codeBadge} title={meta.description}>
                <span aria-hidden="true">{meta.icon}</span>
                {detectorLabel(issue.failure_code)}
              </span>
              <span className={`detector-layer-chip layer-${meta.layer}`} title={`Layer ${meta.layer}`}>
                {meta.layer}
              </span>
              <span className={sevBadge} style={{ fontSize: "0.65rem" }}>{issue.severity}</span>
              {issue.status === "resolved" && (
                <span className="alert-cat-badge badge-gray" style={{ fontSize: "0.65rem" }}>resolved</span>
              )}
            </div>

            {issue.agent_name && (
              <div className="mono" style={{ fontSize: "0.85rem", marginBottom: "0.25rem" }}>
                Agent: {issue.agent_name}
              </div>
            )}
            {issue.prompt_fingerprint && (
              <div className="mono notif-meta" style={{ fontSize: "0.75rem" }}>
                Fingerprint: {issue.prompt_fingerprint}
              </div>
            )}
          </div>

          {/* ── Stats ── */}
          <div style={{ display: "flex", gap: "1.5rem", flexShrink: 0 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>{issue.occurrence_count}</div>
              <div className="notif-meta" style={{ fontSize: "0.7rem" }}>occurrences</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "1.5rem", fontWeight: 700, color: issue.blast_radius_usd > 1 ? "var(--color-red)" : "inherit" }}>
                {formatUsd(issue.blast_radius_usd)}
              </div>
              <div className="notif-meta" style={{ fontSize: "0.7rem" }}>blast radius</div>
            </div>
          </div>
        </div>

        <div className="notif-meta" style={{ marginTop: "0.75rem", fontSize: "0.8rem", gap: "1.5rem", display: "flex", flexWrap: "wrap" }}>
          <span>First seen: {formatDateTime(issue.first_seen_at)}</span>
          <span>Last seen: {formatDateTime(issue.last_seen_at)}</span>
          {issue.resolved_at && (
            <span>Resolved: {formatDateTime(issue.resolved_at)} · {issue.resolution_source}</span>
          )}
        </div>
      </div>

      {/* ── Actions ── */}
      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1rem", flexWrap: "wrap" }}>
        {issue.sample_diagnosis_id && (
          <Link href={`/diagnosis/${issue.sample_diagnosis_id}`} className="btn btn-soft">
            View sample diagnosis →
          </Link>
        )}
        {issue.sample_call_id && (
          <Link href={`/trace/${issue.sample_call_id}`} className="btn btn-soft">
            View trace →
          </Link>
        )}
        {issue.sample_call_id && (
          <Link href={`/replay/${issue.sample_call_id}`} className="btn btn-soft">
            Replay call →
          </Link>
        )}
        {issue.status === "open" && (
          <button
            className="btn btn-soft"
            onClick={() => void onResolve()}
            disabled={resolving}
          >
            {resolving ? "Resolving…" : "Mark resolved"}
          </button>
        )}
      </div>

      {/* ── Fix status ── */}
      {issue.last_fix_id && (
        <div className="panel" style={{ marginBottom: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>Fix available</div>
              <div className="mono notif-meta" style={{ fontSize: "0.75rem" }}>
                fix:{issue.last_fix_id}
              </div>
            </div>
            {issue.sample_diagnosis_id ? (
              <Link href={`/diagnoses/${issue.sample_diagnosis_id}`} className="btn btn-soft btn-sm">
                View diagnosis →
              </Link>
            ) : null}
          </div>
        </div>
      )}

      {/* ── Metadata ── */}
      <div className="panel">
        <header className="panel-header">
          <h3>Issue metadata</h3>
        </header>
        <table style={{ width: "100%", fontSize: "0.85rem", borderCollapse: "collapse" }}>
          <tbody>
            {[
              ["Issue ID", issue.id],
              ["Project", issue.project_id],
              ["Failure code", issue.failure_code],
              ["Severity", issue.severity],
              ["Status", issue.status],
              ["Occurrences", String(issue.occurrence_count)],
              ["Blast radius", formatUsd(issue.blast_radius_usd)],
              ["First seen", formatDateTime(issue.first_seen_at)],
              ["Last seen", formatDateTime(issue.last_seen_at)],
              ["Sample call", issue.sample_call_id ?? "—"],
              ["Sample diagnosis", issue.sample_diagnosis_id ?? "—"],
              ["Last fix", issue.last_fix_id ?? "—"],
              ["Resolution source", issue.resolution_source ?? "—"],
            ].map(([label, value]) => (
              <tr key={label} style={{ borderBottom: "1px solid var(--color-border)" }}>
                <td style={{ padding: "0.4rem 0.75rem", color: "var(--color-muted)", whiteSpace: "nowrap" }}>{label}</td>
                <td style={{ padding: "0.4rem 0.75rem" }} className="mono">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
