"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  GitBranch,
  History,
  Loader2,
  PlayCircle,
  Plus,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

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

function GoldenMetric({ label, value, helper }: { label: string; value: string; helper: string }) {
  return (
    <div className="metric-card golden-metric-card">
      <div className="notif-meta">{label}</div>
      <strong>{value}</strong>
      <span>{helper}</span>
    </div>
  );
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
    <section className="panel golden-create-panel">
      <header className="panel-header">
        <div>
          <h3>Create Golden Set</h3>
          <p>Group production traces into reusable regression memory.</p>
        </div>
      </header>
      <div className="golden-create-grid">
        <label>
          <span className="notif-meta">Name</span>
          <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Checkout agent regressions" />
        </label>
        <label>
          <span className="notif-meta">Description</span>
          <input className="input" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Critical production memory" />
        </label>
        <button type="button" className="btn btn-primary" disabled={!name.trim() || createMutation.isPending} onClick={() => createMutation.mutate()}>
          {createMutation.isPending ? <Loader2 aria-hidden="true" /> : <Plus aria-hidden="true" />}
          {createMutation.isPending ? "Creating..." : "Create set"}
        </button>
      </div>
      {createMutation.error && <p className="notif-error">{createMutation.error.message}</p>}
    </section>
  );
}

function AddTracePanel({ set }: { set: GoldenSetView }) {
  const qc = useQueryClient();
  const [callId, setCallId] = useState("");
  const [expectedOutput, setExpectedOutput] = useState("");
  const addMutation = useMutation({
    mutationFn: () =>
      addGoldenTrace(set.id, {
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
    <div className="golden-add-trace">
      <input className="input input-sm" value={callId} onChange={(event) => setCallId(event.target.value)} placeholder="Source call ID" />
      <input className="input input-sm" value={expectedOutput} onChange={(event) => setExpectedOutput(event.target.value)} placeholder="Expected output text" />
      <button type="button" className="btn btn-soft btn-sm" disabled={(!callId.trim() && !expectedOutput.trim()) || addMutation.isPending} onClick={() => addMutation.mutate()}>
        {addMutation.isPending ? "Adding..." : "Add trace"}
      </button>
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

  if (set.trace_count === 0) {
    return <p className="golden-empty-traces">No traces yet. Add a source call or promote a replay.</p>;
  }

  if (tracesQuery.isLoading) {
    return <p className="notif-meta">Loading traces...</p>;
  }

  return (
    <div className="golden-trace-list">
      {traces.map((trace: GoldenTraceView) => (
        <div key={trace.id} className="golden-trace-row">
          <div>
            <strong className="mono">{trace.call_id ?? trace.id}</strong>
            <span>{trace.expected_output_text ? trace.expected_output_text.slice(0, 120) : "No expected output text captured"}</span>
          </div>
          {trace.call_id && (
            <Link href={`/calls/${trace.call_id}`} className="btn btn-soft btn-sm">
              Call
            </Link>
          )}
        </div>
      ))}
    </div>
  );
}

function GoldenSetCard({ set }: { set: GoldenSetView }) {
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
    <article className="panel golden-set-card">
      <div className="golden-set-grid">
        <div className="golden-set-main">
          <div className="golden-set-badges">
            <h3>{set.name}</h3>
            <span className={`alert-cat-badge ${set.blocks_ci ? "badge-red" : "badge-gray"}`}>
              {set.blocks_ci ? "Blocking" : "Advisory"}
            </span>
            <span className={`alert-cat-badge ${set.is_flaky ? "badge-yellow" : "badge-green"}`}>
              {set.is_flaky ? "Flaky" : "Stable"}
            </span>
            {latestRun && <span className={`alert-cat-badge ${statusClass(latestRun.status)}`}>{latestRun.status}</span>}
          </div>

          {set.description && <p className="golden-description">{set.description}</p>}

          <div className="golden-set-meta">
            <span>{set.trace_count} trace{set.trace_count === 1 ? "" : "s"}</span>
            <span>Last run: {timeAgo(latestRun?.created_at)}</span>
            <span>{passFailLabel(latestRun)}</span>
            <span>Updated {formatDateTime(set.updated_at)}</span>
          </div>

          <TracePreview set={set} />
          <AddTracePanel set={set} />
        </div>

        <div className="golden-action-rail">
          <button type="button" className="btn btn-primary btn-sm" onClick={() => runMutation.mutate()} disabled={set.trace_count === 0 || runMutation.isPending}>
            {runMutation.isPending ? <Loader2 aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
            {runMutation.isPending ? "Running..." : "Run set"}
          </button>
          <button
            type="button"
            className="btn btn-soft btn-sm"
            onClick={() => updateMutation.mutate({ is_flaky: !set.is_flaky })}
            disabled={updateMutation.isPending}
          >
            <TriangleAlert aria-hidden="true" />
            {set.is_flaky ? "Clear flaky" : "Mark flaky"}
          </button>
          <button
            type="button"
            className="btn btn-soft btn-sm"
            onClick={() => updateMutation.mutate({ blocks_ci: !set.blocks_ci })}
            disabled={updateMutation.isPending}
          >
            <ShieldCheck aria-hidden="true" />
            {set.blocks_ci ? "Mark advisory" : "Mark blocking"}
          </button>
          <Link href={`/replay?golden_set_id=${encodeURIComponent(set.id)}`} className="btn btn-soft btn-sm">
            <History aria-hidden="true" />
            Replay history
          </Link>
          <Link href="/settings/evaluation" className="btn btn-soft btn-sm">
            <GitBranch aria-hidden="true" />
            Evaluation settings
          </Link>
        </div>
      </div>

      {runMutation.error && <p className="notif-error">{runMutation.error.message}</p>}
      {updateMutation.error && <p className="notif-error">{updateMutation.error.message}</p>}
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
  const stableCount = sets.filter((set) => !set.is_flaky).length;

  return (
    <div className="goldens-workspace">
      <section className="module-hero golden-hero">
        <div className="module-hero-header">
          <div>
            <div className="module-eyebrow">
              <BookOpen aria-hidden="true" />
              Production regression memory
            </div>
            <h1>Goldens</h1>
            <p>Pinned production traces that make replays reusable, CI blocking possible, and fixes measurable over time.</p>
          </div>
          <Link href="/replay" className="btn btn-primary">
            Replay history
            <ArrowRight aria-hidden="true" />
          </Link>
        </div>
      </section>

      <section className="metric-strip" aria-label="Golden set summary">
        <GoldenMetric label="Golden sets" value={sets.length.toLocaleString()} helper={`${stableCount.toLocaleString()} stable sets`} />
        <GoldenMetric label="Golden traces" value={totalTraces.toLocaleString()} helper="Pinned source calls" />
        <GoldenMetric label="Blocking sets" value={blockingCount.toLocaleString()} helper="Can block CI once wired" />
        <GoldenMetric label="Flaky sets" value={flakyCount.toLocaleString()} helper="Needs review before blocking" />
      </section>

      <CreateSetPanel />

      {setsQuery.isLoading ? (
        <section className="panel issue-loading-panel" aria-label="Loading golden sets">
          <Loader2 aria-hidden="true" />
          <div>
            <strong>Loading goldens</strong>
            <p className="notif-meta">Reading golden sets and trace counts.</p>
          </div>
        </section>
      ) : sets.length === 0 ? (
        <section className="empty golden-empty">
          <BookOpen aria-hidden="true" />
          <strong>No golden sets yet.</strong>
          <span>Create one, add traces, then run it as production regression memory.</span>
        </section>
      ) : (
        <section className="golden-set-list" aria-label="Golden sets">
          {sets.map((set) => (
            <GoldenSetCard key={set.id} set={set} />
          ))}
        </section>
      )}

      <section className="panel panel-muted golden-ci-panel">
        <div>
          <CheckCircle2 aria-hidden="true" />
          <strong>Golden rule</strong>
        </div>
        <p>Passing replays become reusable production memory only when they come from honest non-stub comparisons. Flaky sets should stay advisory until stable.</p>
      </section>
    </div>
  );
}
