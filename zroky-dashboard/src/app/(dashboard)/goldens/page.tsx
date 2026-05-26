"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addGoldenTrace,
  createGoldenSet,
  listGoldenSets,
  listGoldenTraces,
  listReplayRuns,
  runGoldenSet,
  updateGoldenSet,
  type GoldenSetView,
  type GoldenTraceView,
  type ReplayRunItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

function timeAgo(iso: string | null | undefined) {
  if (!iso) return "Never";
  const secs = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

function statusClass(status: string) {
  if (status === "pass") return "badge-green";
  if (status === "fail" || status === "error") return "badge-red";
  if (status === "running" || status === "pending") return "badge-yellow";
  return "badge-gray";
}

function passFailLabel(run: ReplayRunItem | null) {
  if (!run) return "No runs yet";
  const summary = run.summary;
  return `${summary.pass_count} pass / ${summary.fail_count} fail${summary.error_count ? ` / ${summary.error_count} error` : ""}`;
}

function CreateSetPanel() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const createMutation = useMutation({
    mutationFn: () => createGoldenSet({ name: name.trim(), description: description.trim() || undefined }),
    onSuccess: () => {
      setName("");
      setDescription("");
      void qc.invalidateQueries({ queryKey: ["golden-sets"] });
    },
  });
  return (
    <section className="panel">
      <header className="panel-header">
        <div>
          <h3>Create Golden Set</h3>
          <p>Group production traces into reusable regression memory.</p>
        </div>
      </header>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "0.75rem", alignItems: "end" }}>
        <label style={{ display: "grid", gap: "0.35rem" }}>
          <span className="notif-meta">Name</span>
          <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Checkout agent regressions" />
        </label>
        <label style={{ display: "grid", gap: "0.35rem" }}>
          <span className="notif-meta">Description</span>
          <input className="input" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Critical production memory" />
        </label>
        <button type="button" className="btn btn-primary" disabled={!name.trim() || createMutation.isPending} onClick={() => createMutation.mutate()}>
          {createMutation.isPending ? "Creating..." : "Create set"}
        </button>
      </div>
      {createMutation.error && <p className="notif-error" style={{ marginTop: "0.75rem" }}>{createMutation.error.message}</p>}
    </section>
  );
}

function AddTracePanel({ set }: { set: GoldenSetView }) {
  const qc = useQueryClient();
  const [callId, setCallId] = useState("");
  const [expectedOutput, setExpectedOutput] = useState("");
  const addMutation = useMutation({
    mutationFn: () => addGoldenTrace(set.id, {
      call_id: callId.trim() || undefined,
      expected_output_text: expectedOutput.trim() || undefined,
      criteria_json: JSON.stringify({ source: "manual_goldens_page", added_at: new Date().toISOString() }),
      weight: 1,
    }),
    onSuccess: () => {
      setCallId("");
      setExpectedOutput("");
      void qc.invalidateQueries({ queryKey: ["golden-sets"] });
      void qc.invalidateQueries({ queryKey: ["golden-traces", set.id] });
    },
  });
  return (
    <div style={{ display: "grid", gap: "0.5rem", marginTop: "0.75rem" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.5rem" }}>
        <input className="input" value={callId} onChange={(event) => setCallId(event.target.value)} placeholder="Source call ID" />
        <input className="input" value={expectedOutput} onChange={(event) => setExpectedOutput(event.target.value)} placeholder="Expected output text" />
        <button type="button" className="btn btn-soft" disabled={(!callId.trim() && !expectedOutput.trim()) || addMutation.isPending} onClick={() => addMutation.mutate()}>
          {addMutation.isPending ? "Adding..." : "Add trace"}
        </button>
      </div>
      {addMutation.error && <p className="notif-error">{addMutation.error.message}</p>}
    </div>
  );
}

function TracePreview({ set }: { set: GoldenSetView }) {
  const tracesQuery = useQuery({
    queryKey: ["golden-traces", set.id],
    queryFn: ({ signal }) => listGoldenTraces(set.id, { limit: 5 }, signal),
    enabled: set.trace_count > 0,
  });
  const traces = tracesQuery.data?.items ?? [];
  if (set.trace_count === 0) return <p className="notif-meta">No traces yet. Add a source call or promote a replay.</p>;
  return (
    <div className="list" style={{ marginTop: "0.75rem" }}>
      {traces.map((trace: GoldenTraceView) => (
        <div key={trace.id} className="list-row">
          <div className="list-main">
            <strong className="mono">{trace.call_id ?? trace.id}</strong>
            <span>{trace.expected_output_text ? trace.expected_output_text.slice(0, 120) : "No expected output text captured"}</span>
          </div>
          {trace.call_id && <Link href={`/calls/${trace.call_id}`} className="btn btn-soft btn-sm">Call</Link>}
        </div>
      ))}
    </div>
  );
}

function GoldenSetCard({
  set,
}: {
  set: GoldenSetView;
}) {
  const qc = useQueryClient();
  const runsQuery = useQuery({
    queryKey: ["replay-runs", { golden_set_id: set.id, limit: 5 }],
    queryFn: ({ signal }) => listReplayRuns({ golden_set_id: set.id, limit: 5 }, signal),
  });
  const latestRun = runsQuery.data?.items[0] ?? null;
  const runMutation = useMutation({
    mutationFn: () => runGoldenSet(set.id, { trigger: "manual", replay_mode: "real_llm" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["replay-runs"] });
    },
  });
  const updateMutation = useMutation({
    mutationFn: (body: { is_flaky?: boolean; blocks_ci?: boolean }) => updateGoldenSet(set.id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["golden-sets"] });
    },
  });

  return (
    <article className="panel">
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: "1rem", alignItems: "start" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
            <h3 style={{ margin: 0 }}>{set.name}</h3>
            <span className={`alert-cat-badge ${set.blocks_ci ? "badge-red" : "badge-gray"}`}>{set.blocks_ci ? "Blocking" : "Advisory"}</span>
            <span className={`alert-cat-badge ${set.is_flaky ? "badge-yellow" : "badge-green"}`}>{set.is_flaky ? "Flaky" : "Stable"}</span>
            {latestRun && <span className={`alert-cat-badge ${statusClass(latestRun.status)}`}>{latestRun.status}</span>}
          </div>
          {set.description && <p className="notif-meta" style={{ marginTop: "0.35rem" }}>{set.description}</p>}
          <div className="notif-meta" style={{ display: "flex", gap: "0.9rem", flexWrap: "wrap", marginTop: "0.65rem" }}>
            <span>{set.trace_count} trace{set.trace_count === 1 ? "" : "s"}</span>
            <span>Last run: {timeAgo(latestRun?.created_at)}</span>
            <span>{passFailLabel(latestRun)}</span>
            <span>Updated {formatDateTime(set.updated_at)}</span>
          </div>
          <TracePreview set={set} />
          <AddTracePanel set={set} />
        </div>
        <div style={{ display: "grid", gap: "0.45rem", minWidth: 150 }}>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => runMutation.mutate()} disabled={set.trace_count === 0 || runMutation.isPending}>
            {runMutation.isPending ? "Running..." : "Run set"}
          </button>
          <button
            type="button"
            className="btn btn-soft btn-sm"
            onClick={() => updateMutation.mutate({ is_flaky: !set.is_flaky })}
            disabled={updateMutation.isPending}
          >
            {set.is_flaky ? "Clear flaky" : "Mark flaky"}
          </button>
          <button
            type="button"
            className="btn btn-soft btn-sm"
            onClick={() => updateMutation.mutate({ blocks_ci: !set.blocks_ci })}
            disabled={updateMutation.isPending}
          >
            {set.blocks_ci ? "Mark advisory" : "Mark blocking"}
          </button>
          <Link href={`/replay?golden_set_id=${encodeURIComponent(set.id)}`} className="btn btn-soft btn-sm">Open replay history</Link>
          <Link href={`/calibration?tab=goldens`} className="btn btn-soft btn-sm">Open labels</Link>
        </div>
      </div>
      {runMutation.error && <p className="notif-error" style={{ marginTop: "0.75rem" }}>{runMutation.error.message}</p>}
      {updateMutation.error && <p className="notif-error" style={{ marginTop: "0.75rem" }}>{updateMutation.error.message}</p>}
    </article>
  );
}

export default function GoldensPage() {
  const setsQuery = useQuery({
    queryKey: ["golden-sets"],
    queryFn: ({ signal }) => listGoldenSets({ limit: 100 }, signal),
  });
  const sets = useMemo(() => setsQuery.data?.items ?? [], [setsQuery.data?.items]);
  const totalTraces = useMemo(() => sets.reduce((sum, set) => sum + set.trace_count, 0), [sets]);
  const blockingCount = sets.filter((set) => set.blocks_ci).length;
  const flakyCount = sets.filter((set) => set.is_flaky).length;

  return (
    <div className="grid gap-4">
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Goldens</h3>
            <p>Production regression memory: pinned traces, replay health, and CI-ready golden sets.</p>
          </div>
          <Link href="/replay" className="btn btn-soft">Replay history</Link>
        </header>
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.75rem" }}>
        <div className="panel panel-muted"><div className="notif-meta">Golden sets</div><strong style={{ fontSize: "1.4rem" }}>{sets.length}</strong></div>
        <div className="panel panel-muted"><div className="notif-meta">Golden traces</div><strong style={{ fontSize: "1.4rem" }}>{totalTraces}</strong></div>
        <div className="panel panel-muted"><div className="notif-meta">Blocking sets</div><strong style={{ fontSize: "1.4rem" }}>{blockingCount}</strong></div>
        <div className="panel panel-muted"><div className="notif-meta">Flaky sets</div><strong style={{ fontSize: "1.4rem" }}>{flakyCount}</strong></div>
      </section>

      <CreateSetPanel />

      {setsQuery.isLoading ? (
        <div className="loading" />
      ) : sets.length === 0 ? (
        <div className="empty">No golden sets yet. Create one, add traces, then run it as production regression memory.</div>
      ) : (
        <section style={{ display: "grid", gap: "0.75rem" }}>
          {sets.map((set) => (
            <GoldenSetCard
              key={set.id}
              set={set}
            />
          ))}
        </section>
      )}
    </div>
  );
}
