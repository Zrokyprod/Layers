"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { addGoldenTrace, createGoldenSet, listGoldenSets } from "@/lib/api";
import type { GoldenSetView, ReplayRunDetailItem, ReplayRunTraceItem } from "@/lib/api";
import { useReplayRunDetail } from "@/lib/hooks";
import { formatDateTime, formatUsd } from "@/lib/format";
import { replayModeLabel, replayModeProof, replayVerificationLabel, replayVerifiedFix } from "@/lib/replay-mode";

const STATUS_CLASS: Record<string, string> = {
  pending: "badge-yellow",
  running: "badge-yellow",
  pass: "badge-green",
  fail: "badge-red",
  error: "badge-red",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  running: "Running",
  pass: "Pass",
  fail: "Fail",
  error: "Error",
};

function boolLabel(value: boolean | null | undefined) {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return "Unknown";
}

function formatMs(value: number | null | undefined) {
  if (value == null) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value} ms`;
}

function JsonPreview({ value }: { value: Record<string, unknown> | null | undefined }) {
  if (!value) return <span className="notif-meta">No difference data captured.</span>;
  return (
    <pre className="mono" style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: "0.75rem", margin: 0 }}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function promotionCriteria(run: ReplayRunDetailItem, trace: ReplayRunTraceItem): string {
  return JSON.stringify({
    source: "replay_promotion",
    source_replay_run_id: run.id,
    source_replay_trace_id: trace.id,
    source_golden_trace_id: trace.golden_trace_id,
    replay_mode: run.replay_mode,
    executor_replay_mode: run.executor_replay_mode,
    replay_status: run.status,
    replay_trace_status: trace.status,
    verification_status: run.summary.verification_status,
    verified_fix: replayVerifiedFix(run.replay_mode, run.summary.verified_fix),
    diff_metric: trace.diff_metric,
    cost_delta_usd: trace.cost_delta_usd,
    latency_delta_ms: trace.latency_delta_ms,
    output_diff: trace.output_diff,
    tool_behavior_diff: trace.tool_behavior_diff,
    promoted_at: new Date().toISOString(),
  });
}

function PromoteToGoldenPanel({ run, isVerifiedFix }: { run: ReplayRunDetailItem; isVerifiedFix: boolean }) {
  const queryClient = useQueryClient();
  const [selectedSetId, setSelectedSetId] = useState("");
  const [newSetName, setNewSetName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const goldenSetsQuery = useQuery({
    queryKey: ["golden-sets", "promote-replay"],
    queryFn: ({ signal }) => listGoldenSets({ limit: 100 }, signal),
  });
  const promotableTraces = useMemo(
    () => run.traces.filter((trace) => trace.status === "pass" && Boolean(trace.call_id_replayed)),
    [run.traces],
  );
  const canPromote = run.status === "pass" && !run.replay_mode_warning && !run.replay_mode.startsWith("stub") && promotableTraces.length > 0;
  const promoteMutation = useMutation({
    mutationFn: async () => {
      setMessage(null);
      let targetSet: GoldenSetView | null = goldenSetsQuery.data?.items.find((set) => set.id === selectedSetId) ?? null;
      const name = newSetName.trim();
      if (!targetSet) {
        if (!name) {
          throw new Error("Select a Golden Set or create a new one.");
        }
        targetSet = await createGoldenSet({
          name,
          description: `Promoted from replay ${run.id}`,
        });
      }
      const created = [];
      for (const trace of promotableTraces) {
        if (!trace.call_id_replayed) continue;
        created.push(await addGoldenTrace(targetSet.id, {
          call_id: trace.call_id_replayed,
          expected_output_text: trace.output_text ?? undefined,
          criteria_json: promotionCriteria(run, trace),
          weight: 1,
        }));
      }
      return { targetSet, createdCount: created.length };
    },
    onSuccess: ({ targetSet, createdCount }) => {
      setSelectedSetId(targetSet.id);
      setNewSetName("");
      setMessage(`${createdCount} replay trace${createdCount === 1 ? "" : "s"} promoted to ${targetSet.name}.`);
      void queryClient.invalidateQueries({ queryKey: ["golden-sets"] });
      void queryClient.invalidateQueries({ queryKey: ["golden-traces", targetSet.id] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "Promotion failed."),
  });

  return (
    <section className="panel" style={{ marginBottom: "1rem" }}>
      <header className="panel-header">
        <div>
          <h3>Promote Replay to Golden</h3>
          <p>Passing replay traces become reusable production memory for future CI regression checks.</p>
        </div>
        <span className={`alert-cat-badge ${canPromote ? "badge-green" : "badge-yellow"}`}>
          {canPromote ? "Ready" : "Needs passing non-stub replay"}
        </span>
      </header>

      <div style={{ display: "grid", gap: "0.75rem" }}>
        {!isVerifiedFix && (
          <p className="notif-meta">Only honest non-stub passing replays should be promoted. Stub replay is a sanity check, not a verified fix.</p>
        )}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "0.75rem", alignItems: "end" }}>
          <label style={{ display: "grid", gap: "0.35rem" }}>
            <span className="notif-meta">Select Golden Set</span>
            <select className="input" value={selectedSetId} onChange={(event) => setSelectedSetId(event.target.value)} disabled={goldenSetsQuery.isLoading}>
              <option value="">Create a new set</option>
              {(goldenSetsQuery.data?.items ?? []).map((set) => (
                <option key={set.id} value={set.id}>{set.name} - {set.trace_count} traces</option>
              ))}
            </select>
          </label>
          <label style={{ display: "grid", gap: "0.35rem" }}>
            <span className="notif-meta">New Golden Set name</span>
            <input className="input" value={newSetName} onChange={(event) => setNewSetName(event.target.value)} placeholder="Production memory" disabled={Boolean(selectedSetId)} />
          </label>
          <button type="button" className="btn btn-primary" onClick={() => promoteMutation.mutate()} disabled={!canPromote || promoteMutation.isPending}>
            {promoteMutation.isPending ? "Promoting..." : "Promote to Golden"}
          </button>
        </div>
        <div className="notif-meta">
          Source call/replay metadata is stored in each golden trace criteria JSON for CI use later.
          {" "}<strong>{promotableTraces.length}</strong> passing source trace{promotableTraces.length === 1 ? "" : "s"} available.
        </div>
        {message && <p className={promoteMutation.isError ? "notif-error" : "notif-meta"}>{message}</p>}
      </div>
    </section>
  );
}

export default function ReplayRunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const runQuery = useReplayRunDetail(id);
  const run = runQuery.data ?? null;

  if (runQuery.isLoading) {
    return (
      <section className="panel">
        <div className="loading" />
      </section>
    );
  }

  if (runQuery.error || !run) {
    return (
      <section className="panel">
        <p className="notif-error">{runQuery.error?.message ?? "Replay run unavailable."}</p>
        <Link href="/replay" className="btn btn-soft" style={{ marginTop: "1rem" }}>
          Back to replay runs
        </Link>
      </section>
    );
  }

  const summary = run.summary;
  const isStub = run.replay_mode === "stub";
  const isVerifiedFix = replayVerifiedFix(run.replay_mode, summary.verified_fix);
  const verificationLabel = replayVerificationLabel(run.replay_mode, summary.verified_fix, summary.verification_status);

  return (
    <div>
      <div style={{ marginBottom: "1rem", fontSize: "0.85rem" }}>
        <Link href="/replay" className="notif-action-link">Back to replay runs</Link>
      </div>

      <section className="panel" style={{ marginBottom: "1rem" }}>
        <header className="panel-header">
          <div>
            <h2 style={{ margin: 0 }}>Replay run</h2>
            <p className="mono notif-meta" style={{ marginTop: "0.35rem" }}>{run.id}</p>
          </div>
          <span className={`alert-cat-badge ${STATUS_CLASS[run.status] ?? "badge-gray"}`}>
            {STATUS_LABEL[run.status] ?? run.status}
          </span>
        </header>

        {(run.replay_mode_warning || isStub) && (
          <div style={{ marginTop: "1rem", padding: "0.75rem 1rem", borderRadius: 8, border: "1px solid #f59e0b", background: "rgba(245,158,11,0.1)" }}>
            <strong>{isStub ? "Stub replay is a sanity check, not a verified fix." : "Replay mode warning"}</strong>
            <p style={{ marginTop: "0.35rem", fontSize: "0.85rem" }}>{isStub ? "Stub replay is a sanity check, not a verified fix." : run.replay_mode_warning}</p>
          </div>
        )}
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.75rem", marginBottom: "1rem" }}>
        <ProofCard title="Mode" value={replayModeLabel(run.replay_mode)} />
        <ProofCard title="Proof badge" value={replayModeProof(run.replay_mode)} tone={isStub ? "warn" : "neutral"} />
        <ProofCard title="Original failure reproduced" value={boolLabel(summary.reproduced_original_failure)} />
        <ProofCard title="Fix passed" value={boolLabel(summary.fix_passed)} />
        <ProofCard title="Verification" value={verificationLabel} tone={isVerifiedFix ? "good" : isStub ? "warn" : "neutral"} />
        <ProofCard title="Replay cost" value={summary.replay_cost_usd == null ? "-" : formatUsd(summary.replay_cost_usd)} />
        <ProofCard title="Cost delta" value={summary.cost_delta_usd == null ? "-" : formatUsd(summary.cost_delta_usd)} />
        <ProofCard title="Latency delta" value={formatMs(summary.latency_delta_ms)} />
        <ProofCard title="Traces" value={`${summary.trace_count_executed}/${summary.trace_count_at_dispatch}`} />
      </section>

      <PromoteToGoldenPanel run={run} isVerifiedFix={isVerifiedFix} />

      <section className="panel" style={{ marginBottom: "1rem" }}>
        <header className="panel-header">
          <h3>Run metadata</h3>
        </header>
        <table style={{ width: "100%", fontSize: "0.85rem", borderCollapse: "collapse" }}>
          <tbody>
            {[
              ["Golden set", run.golden_set_id],
              ["Git SHA", run.git_sha ?? "-"],
              ["Trigger", run.trigger],
              ["Executor mode", run.executor_replay_mode],
              ["Created", formatDateTime(run.created_at)],
              ["Started", run.started_at ? formatDateTime(run.started_at) : "-"],
              ["Completed", run.completed_at ? formatDateTime(run.completed_at) : "-"],
            ].map(([label, value]) => (
              <tr key={label} style={{ borderBottom: "1px solid var(--color-border)" }}>
                <td style={{ padding: "0.45rem 0.75rem", color: "var(--color-muted)", whiteSpace: "nowrap" }}>{label}</td>
                <td style={{ padding: "0.45rem 0.75rem" }} className="mono">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1rem", marginBottom: "1rem" }}>
        <article className="panel">
          <header className="panel-header"><h3>Output differences</h3></header>
          <JsonPreview value={summary.output_diff} />
        </article>
        <article className="panel">
          <header className="panel-header"><h3>Tool behavior differences</h3></header>
          <JsonPreview value={summary.tool_behavior_diff} />
        </article>
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Trace results</h3>
            <p>{run.traces.length} trace{run.traces.length === 1 ? "" : "s"} in this replay run.</p>
          </div>
        </header>
        {run.traces.length === 0 ? (
          <div className="empty">No trace rows have been written yet.</div>
        ) : (
          <div className="list">
            {run.traces.map((trace) => (
              <div key={trace.id} className="list-row" style={{ alignItems: "flex-start" }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                    <span className={`alert-cat-badge ${STATUS_CLASS[trace.status] ?? "badge-gray"}`}>{trace.status}</span>
                    {trace.call_id_replayed && <Link href={`/calls/${trace.call_id_replayed}`} className="mono notif-action-link">{trace.call_id_replayed}</Link>}
                  </div>
                  {trace.output_text && <p className="mono" style={{ marginTop: "0.5rem", fontSize: "0.78rem", whiteSpace: "pre-wrap" }}>{trace.output_text.slice(0, 600)}</p>}
                </div>
                <div style={{ textAlign: "right", fontSize: "0.78rem" }}>
                  <div>Diff: {trace.diff_metric == null ? "-" : trace.diff_metric.toFixed(4)}</div>
                  <div>Cost: {trace.cost_delta_usd == null ? "-" : formatUsd(trace.cost_delta_usd)}</div>
                  <div>Latency: {formatMs(trace.latency_delta_ms)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ProofCard({ title, value, tone = "neutral" }: { title: string; value: string; tone?: "good" | "warn" | "neutral" }) {
  const color = tone === "good" ? "var(--color-green)" : tone === "warn" ? "#f59e0b" : "inherit";
  return (
    <article className="panel" style={{ padding: "0.85rem 1rem" }}>
      <div className="notif-meta" style={{ fontSize: "0.72rem" }}>{title}</div>
      <div style={{ marginTop: "0.35rem", fontWeight: 700, color }}>{value}</div>
    </article>
  );
}
