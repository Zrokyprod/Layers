"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { createReplayJob, getReplayJob } from "@/lib/api";
import type { ReplayJobResponse } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const STATUS_CLASS: Record<string, string> = {
  pending: "badge-yellow",
  running: "badge-yellow",
  pass: "badge-green",
  fail: "badge-red",
  error: "badge-red",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  running: "Running…",
  pass: "Pass ✓",
  fail: "Fail ✗",
  error: "Error",
};

export default function ReplayPage() {
  const { id: callId } = useParams<{ id: string }>();
  const [job, setJob] = useState<ReplayJobResponse | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  useEffect(() => () => stopPolling(), []);

  function startPolling(replayId: string) {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const updated = await getReplayJob(replayId);
        setJob(updated);
        if (updated.status !== "pending" && updated.status !== "running") {
          stopPolling();
        }
      } catch {
        stopPolling();
      }
    }, 3000);
  }

  async function onTrigger() {
    if (!callId) return;
    setTriggering(true);
    setError(null);
    try {
      const created = await createReplayJob({ call_id: callId });
      setJob(created);
      if (created.status === "pending" || created.status === "running") {
        startPolling(created.id);
      }
    } catch (e: unknown) {
      setError((e as { message?: string }).message ?? "Failed to create replay job.");
    } finally {
      setTriggering(false);
    }
  }

  const isTerminal = job && job.status !== "pending" && job.status !== "running";
  const isActive = job && (job.status === "pending" || job.status === "running");

  return (
    <div>
      <div style={{ marginBottom: "1rem", fontSize: "0.85rem" }}>
        <Link href="/issues" className="notif-action-link">← Issues</Link>
      </div>

      {/* ── Header ── */}
      <div className="panel" style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <h2 style={{ margin: 0, marginBottom: "0.25rem" }}>Replay sandbox</h2>
            <div className="mono notif-meta" style={{ fontSize: "0.8rem" }}>
              call: {callId}
            </div>
          </div>

          <button
            className="btn btn-soft"
            onClick={() => void onTrigger()}
            disabled={triggering || !!isActive}
          >
            {triggering ? "Submitting…" : isActive ? "Running…" : job ? "Re-run replay" : "Trigger replay"}
          </button>
        </div>

        {error && <p className="notif-error" style={{ marginTop: "0.75rem" }}>{error}</p>}
      </div>

      {/* ── Job status ── */}
      {job && (
        <div className="panel" style={{ marginBottom: "1rem" }}>
          <header className="panel-header">
            <h3>Replay job</h3>
            <span className={`alert-cat-badge ${STATUS_CLASS[job.status] ?? "badge-gray"}`}>
              {STATUS_LABEL[job.status] ?? job.status}
            </span>
          </header>

          <div style={{ marginTop: "0.75rem" }}>
            <table style={{ width: "100%", fontSize: "0.85rem", borderCollapse: "collapse" }}>
              <tbody>
                {[
                  ["Job ID", job.id],
                  ["Status", STATUS_LABEL[job.status] ?? job.status],
                  ["Created", formatDateTime(job.created_at)],
                  ["Completed", job.completed_at ? formatDateTime(job.completed_at) : "—"],
                  ["Diff metric", job.diff_metric !== null ? String(job.diff_metric.toFixed(4)) : "—"],
                  ["PR ID", job.pr_id ?? "—"],
                ].map(([label, value]) => (
                  <tr key={label} style={{ borderBottom: "1px solid var(--color-border)" }}>
                    <td style={{ padding: "0.4rem 0.75rem", color: "var(--color-muted)", whiteSpace: "nowrap" }}>{label}</td>
                    <td style={{ padding: "0.4rem 0.75rem" }} className="mono">{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* ── Verdict ── */}
          {isTerminal && (
            <div
              style={{
                marginTop: "1rem",
                padding: "0.75rem 1rem",
                borderRadius: "6px",
                background: job.status === "pass" ? "var(--color-green-bg, #f0fdf4)" : "var(--color-red-bg, #fef2f2)",
                border: `1px solid ${job.status === "pass" ? "var(--color-green)" : "var(--color-red)"}`,
              }}
            >
              {job.status === "pass" ? (
                <strong>✓ Replay passed — fix is safe to ship.</strong>
              ) : job.status === "fail" ? (
                <strong>✗ Replay failed — the fix does not resolve the original failure.</strong>
              ) : (
                <strong>⚠ Replay errored — check worker logs.</strong>
              )}
              {job.diff_metric !== null && (
                <p style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
                  Diff metric: <span className="mono">{job.diff_metric.toFixed(4)}</span>
                  {" "}(1.0 = identical to expected output)
                </p>
              )}
            </div>
          )}

          {/* ── Worker output ── */}
          {job.stdout_tail && (
            <div style={{ marginTop: "1rem" }}>
              <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "0.25rem" }}>Worker output</div>
              <pre
                className="mono"
                style={{
                  padding: "0.75rem",
                  background: "var(--color-code-bg, #1e1e1e)",
                  color: "var(--color-code-fg, #d4d4d4)",
                  borderRadius: "6px",
                  fontSize: "0.75rem",
                  overflowX: "auto",
                  maxHeight: "300px",
                  overflowY: "auto",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                {job.stdout_tail}
              </pre>
            </div>
          )}

          {job.error_message && (
            <div style={{ marginTop: "0.75rem" }}>
              <p className="notif-error">{job.error_message}</p>
            </div>
          )}
        </div>
      )}

      {/* ── Explanation ── */}
      {!job && (
        <div className="panel" style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}>
          <p>
            The replay sandbox re-runs the original failing call against the candidate fix diff
            and reports whether the fix resolves the problem.
          </p>
          <p style={{ marginTop: "0.5rem" }}>
            Requires the <strong>Zroky Replay Worker</strong> to be running in your environment.
            Set <span className="mono">REPLAY_WORKER_TOKEN</span> in both the worker and control plane.
          </p>
        </div>
      )}
    </div>
  );
}
