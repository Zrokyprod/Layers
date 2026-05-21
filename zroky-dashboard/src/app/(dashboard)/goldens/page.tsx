"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listGoldenSets,
  createGoldenSet,
  listGoldenTraces,
  addGoldenTrace,
  deleteGoldenTrace,
  createOrUpdateCalibrationLabel,
  listCalibrationLabels,
  type GoldenSetView,
  type GoldenTraceView,
  type LabelView,
} from "@/lib/api";

// ── helpers ──────────────────────────────────────────────────────────────────

function timeAgo(iso: string) {
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const VERDICT_COLOURS: Record<string, string> = {
  pass: "#22c55e",
  fail: "#ef4444",
  inconclusive: "#f59e0b",
};

// ── sub-components ───────────────────────────────────────────────────────────

function VerdictBadge({ verdict }: { verdict: string }) {
  return (
    <span
      className="inline-block rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
      style={{
        background: `${VERDICT_COLOURS[verdict] ?? "#64748b"}22`,
        color: VERDICT_COLOURS[verdict] ?? "#64748b",
      }}
    >
      {verdict}
    </span>
  );
}

function EmptyState({ text, sub }: { text: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-8 text-center">
      <p className="text-sm text-slate-400">{text}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

// ── Trace row with inline labeling ───────────────────────────────────────────

function TraceRow({
  trace,
  goldenSetId,
  existingLabel,
}: {
  trace: GoldenTraceView;
  goldenSetId: string;
  existingLabel: LabelView | null;
}) {
  const qc = useQueryClient();
  const [showLabeler, setShowLabeler] = useState(false);
  const [verdict, setVerdict] = useState<"pass" | "fail" | "inconclusive">("pass");
  const [rationale, setRationale] = useState("");

  const labelMutation = useMutation({
    mutationFn: (vars: { verdict: "pass" | "fail" | "inconclusive"; rationale: string }) =>
      createOrUpdateCalibrationLabel({
        golden_trace_id: trace.id,
        verdict: vars.verdict,
        rationale: vars.rationale || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["calibration-labels"] });
      setShowLabeler(false);
      setRationale("");
    },
  });

  const removeMutation = useMutation({
    mutationFn: () => deleteGoldenTrace(goldenSetId, trace.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["golden-traces", goldenSetId] }),
  });

  return (
    <div className="group rounded-lg border border-white/[0.05] bg-white/[0.02] p-3 hover:border-white/[0.12] transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <code className="text-xs text-slate-400 font-mono">{trace.id.slice(0, 12)}…</code>
            {trace.call_id && (
              <span className="text-[10px] text-slate-600">
                call: {trace.call_id.slice(0, 8)}…
              </span>
            )}
            {existingLabel && <VerdictBadge verdict={existingLabel.verdict} />}
          </div>
          {trace.expected_output_text && (
            <p className="mt-1.5 text-xs text-slate-500 line-clamp-2">
              {trace.expected_output_text}
            </p>
          )}
          {trace.criteria_json && (
            <p className="mt-1 text-[10px] text-slate-600 font-mono truncate">
              criteria: {trace.criteria_json.slice(0, 80)}…
            </p>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {!existingLabel && (
            <button
              type="button"
              onClick={() => setShowLabeler(!showLabeler)}
              className="rounded px-2.5 py-1 text-[10px] font-semibold bg-indigo-600/80 text-white hover:bg-indigo-500 transition-colors"
            >
              Label
            </button>
          )}
          {existingLabel && !showLabeler && (
            <button
              type="button"
              onClick={() => setShowLabeler(true)}
              className="rounded px-2 py-1 text-[10px] text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
            >
              Re-label
            </button>
          )}
          <button
            type="button"
            onClick={() => removeMutation.mutate()}
            disabled={removeMutation.isPending}
            className="opacity-0 group-hover:opacity-100 rounded px-2 py-1 text-[10px] text-red-400 hover:bg-red-500/10 disabled:opacity-30 transition-all"
          >
            ×
          </button>
        </div>
      </div>

      {/* Inline labeling form */}
      {showLabeler && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/[0.06] pt-3">
          <div className="flex items-center gap-1">
            {(["pass", "fail", "inconclusive"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setVerdict(v)}
                className="rounded px-2.5 py-1 text-[10px] font-semibold capitalize transition-all"
                style={{
                  background: verdict === v ? `${VERDICT_COLOURS[v]}33` : "transparent",
                  color: verdict === v ? VERDICT_COLOURS[v] : "#94a3b8",
                  border: `1px solid ${verdict === v ? VERDICT_COLOURS[v] + "55" : "transparent"}`,
                }}
              >
                {v}
              </button>
            ))}
          </div>
          <input
            type="text"
            placeholder="Rationale (optional)"
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            className="flex-1 min-w-[120px] rounded border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <button
            type="button"
            disabled={labelMutation.isPending}
            onClick={() => labelMutation.mutate({ verdict, rationale })}
            className="rounded bg-indigo-600 px-3 py-1 text-[10px] font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
          >
            {labelMutation.isPending ? "…" : "Save"}
          </button>
          <button
            type="button"
            onClick={() => setShowLabeler(false)}
            className="rounded px-2 py-1 text-[10px] text-slate-500 hover:text-slate-300"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

// ── Golden Set detail panel ──────────────────────────────────────────────────

function SetDetail({ set }: { set: GoldenSetView }) {
  const qc = useQueryClient();
  const [callId, setCallId] = useState("");
  const [expectedOutput, setExpectedOutput] = useState("");

  const tracesQuery = useQuery({
    queryKey: ["golden-traces", set.id],
    queryFn: ({ signal }) => listGoldenTraces(set.id, { limit: 100 }, signal),
  });

  const labelsQuery = useQuery({
    queryKey: ["calibration-labels"],
    queryFn: ({ signal }) => listCalibrationLabels(undefined, signal),
  });

  const addTraceMutation = useMutation({
    mutationFn: () =>
      addGoldenTrace(set.id, {
        call_id: callId.trim() || undefined,
        expected_output_text: expectedOutput.trim() || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["golden-traces", set.id] });
      qc.invalidateQueries({ queryKey: ["golden-sets"] });
      setCallId("");
      setExpectedOutput("");
    },
  });

  const traces = tracesQuery.data?.items ?? [];
  const labels = labelsQuery.data ?? [];

  function getLabelForTrace(traceId: string): LabelView | null {
    return labels.find((l) => l.golden_trace_id === traceId && l.active) ?? null;
  }

  const labeledCount = traces.filter((t) => getLabelForTrace(t.id)).length;
  const unlabeledCount = traces.length - labeledCount;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-white">{set.name}</h3>
          {set.description && <p className="mt-0.5 text-xs text-slate-500">{set.description}</p>}
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span>{traces.length} traces</span>
          <span className="text-emerald-400">{labeledCount} labeled</span>
          {unlabeledCount > 0 && (
            <span className="text-amber-400">{unlabeledCount} unlabeled</span>
          )}
        </div>
      </div>

      {/* Add trace form */}
      <div className="rounded-lg border border-white/[0.06] bg-white/[0.03] p-3">
        <p className="text-xs text-slate-400 mb-2">Add trace to this set</p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            placeholder="Call ID (paste from Calls page)"
            value={callId}
            onChange={(e) => setCallId(e.target.value)}
            className="flex-1 min-w-[180px] rounded border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <input
            type="text"
            placeholder="Expected output (optional)"
            value={expectedOutput}
            onChange={(e) => setExpectedOutput(e.target.value)}
            className="flex-1 min-w-[180px] rounded border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <button
            type="button"
            disabled={addTraceMutation.isPending || (!callId.trim() && !expectedOutput.trim())}
            onClick={() => addTraceMutation.mutate()}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
          >
            {addTraceMutation.isPending ? "Adding…" : "Add Trace"}
          </button>
        </div>
      </div>

      {/* Traces list with inline labeling */}
      {tracesQuery.isLoading ? (
        <p className="text-xs text-slate-500 py-4 text-center">Loading traces…</p>
      ) : traces.length === 0 ? (
        <EmptyState
          text="No traces in this set yet."
          sub="Add a call ID from the Calls page to start building your golden set."
        />
      ) : (
        <div className="space-y-2">
          {traces.map((trace) => (
            <TraceRow
              key={trace.id}
              trace={trace}
              goldenSetId={set.id}
              existingLabel={getLabelForTrace(trace.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function GoldensPage() {
  const qc = useQueryClient();
  const [selectedSetId, setSelectedSetId] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  const setsQuery = useQuery({
    queryKey: ["golden-sets"],
    queryFn: ({ signal }) => listGoldenSets({ limit: 50 }, signal),
  });

  const createMutation = useMutation({
    mutationFn: () => createGoldenSet({ name: newName.trim(), description: newDesc.trim() || undefined }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["golden-sets"] });
      setSelectedSetId(data.id);
      setNewName("");
      setNewDesc("");
      setShowCreate(false);
    },
  });

  const sets = setsQuery.data?.items ?? [];
  const selectedSet = sets.find((s) => s.id === selectedSetId) ?? null;

  return (
    <div className="flex gap-6 min-h-[60vh]">
      {/* Left panel — set list */}
      <div className="w-72 shrink-0 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-300">Golden Sets</h2>
          <button
            type="button"
            onClick={() => setShowCreate(!showCreate)}
            className="rounded px-2 py-0.5 text-xs text-indigo-400 hover:bg-indigo-500/10 transition-colors"
          >
            + New
          </button>
        </div>

        {showCreate && (
          <div className="rounded-lg border border-indigo-500/20 bg-indigo-500/5 p-3 space-y-2">
            <input
              type="text"
              placeholder="Set name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="w-full rounded border border-white/[0.08] bg-white/[0.04] px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <input
              type="text"
              placeholder="Description (optional)"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              className="w-full rounded border border-white/[0.08] bg-white/[0.04] px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <button
              type="button"
              disabled={!newName.trim() || createMutation.isPending}
              onClick={() => createMutation.mutate()}
              className="w-full rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
            >
              {createMutation.isPending ? "Creating…" : "Create Set"}
            </button>
          </div>
        )}

        {setsQuery.isLoading ? (
          <p className="text-xs text-slate-500 py-4">Loading…</p>
        ) : sets.length === 0 ? (
          <p className="text-xs text-slate-600 italic py-4">No golden sets yet.</p>
        ) : (
          <div className="space-y-1">
            {sets.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => setSelectedSetId(s.id)}
                className={`w-full rounded-lg px-3 py-2.5 text-left transition-colors ${
                  selectedSetId === s.id
                    ? "bg-indigo-600/15 border border-indigo-500/30"
                    : "hover:bg-white/[0.04] border border-transparent"
                }`}
              >
                <p className={`text-xs font-medium ${selectedSetId === s.id ? "text-indigo-300" : "text-slate-300"}`}>
                  {s.name}
                </p>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  {s.trace_count} traces · {timeAgo(s.updated_at)}
                </p>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Right panel — detail + annotation */}
      <div className="flex-1 min-w-0">
        {selectedSet ? (
          <SetDetail set={selectedSet} />
        ) : (
          <EmptyState
            text="Select a golden set to view and label traces."
            sub="Golden sets are curated collections of production traces used to calibrate your LLM judge."
          />
        )}
      </div>
    </div>
  );
}
