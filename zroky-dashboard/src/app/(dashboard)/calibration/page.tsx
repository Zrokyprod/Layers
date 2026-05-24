"use client";

import { useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Info, RefreshCw } from "lucide-react";
import {
  listGoldenSets, createGoldenSet, listGoldenTraces,
  addGoldenTrace, deleteGoldenTrace, createOrUpdateCalibrationLabel,
  listCalibrationLabels,
  type GoldenSetView, type GoldenTraceView, type LabelView,
  type CalibrationRunView, type CalibrationPerClassMetric,
} from "@/lib/api";
import {
  useCalibrationLatest, useCalibrationMode, useCalibrationHistory,
  useTriggerCalibrationRunNow, useCalibrationLabels,
  useCreateCalibrationLabel, useDeleteCalibrationLabel,
} from "@/lib/hooks";

type Tab = "goldens" | "judge" | "score";

function pct(n: number) { return `${(n * 100).toFixed(1)}%`; }
function fmtDate(d: string | null | undefined) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const VERDICT_COLOURS: Record<string, string> = { pass: "#22c55e", fail: "#ef4444", inconclusive: "#f59e0b" };
const VERDICT_LABELS = ["pass", "fail", "inconclusive"];
const DEFAULT_MODEL = "anthropic/claude-haiku-4";

function ModeBadge({ mode }: { mode: string }) {
  const b = mode === "blocking";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold tracking-wide ${b ? "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30" : "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30"}`}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: b ? "#22c55e" : "#f59e0b" }} />
      {b ? "Blocking" : "Advisory"}
    </span>
  );
}

function VerdictBadge({ verdict }: { verdict: string }) {
  return (
    <span className="inline-block rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
      style={{ background: `${VERDICT_COLOURS[verdict] ?? "#64748b"}22`, color: VERDICT_COLOURS[verdict] ?? "#64748b" }}>
      {verdict}
    </span>
  );
}

function VerdictPill({ verdict }: { verdict: string }) {
  return (
    <span className="inline-block rounded px-2 py-0.5 text-xs font-semibold capitalize"
      style={{ background: verdict === "pass" ? "rgba(34,197,94,0.15)" : verdict === "fail" ? "rgba(239,68,68,0.15)" : "rgba(245,158,11,0.15)", color: VERDICT_COLOURS[verdict] ?? "#94a3b8" }}>
      {verdict}
    </span>
  );
}

function AccuracyGauge({ value }: { value: number }) {
  const v = Math.min(100, Math.max(0, value * 100));
  const color = v >= 93 ? "#22c55e" : v >= 90 ? "#f59e0b" : "#ef4444";
  const circ = 2 * Math.PI * 44;
  const offset = circ - (v / 100) * circ;
  return (
    <div className="flex flex-col items-center">
      <svg width="112" height="112" viewBox="0 0 112 112" aria-label={`Accuracy ${pct(value)}`}>
        <circle cx="56" cy="56" r="44" fill="none" stroke="#1e293b" strokeWidth="10" />
        <circle cx="56" cy="56" r="44" fill="none" stroke={color} strokeWidth="10"
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
          transform="rotate(-90 56 56)" style={{ transition: "stroke-dashoffset 0.6s ease" }} />
        <text x="56" y="61" textAnchor="middle" fontSize="18" fontWeight="700" fill={color}>{pct(value)}</text>
      </svg>
      <p className="mt-1 text-xs text-slate-400">Accuracy</p>
    </div>
  );
}

function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-white">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

function ConfusionMatrix({ matrix }: { matrix: Record<string, Record<string, number>> }) {
  const maxVal = Math.max(1, ...VERDICT_LABELS.flatMap((r) => VERDICT_LABELS.map((c) => matrix[r]?.[c] ?? 0)));
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-slate-300">Confusion Matrix</h3>
      <table className="w-full text-center text-xs">
        <thead>
          <tr>
            <th className="pb-2 pr-2 text-left text-slate-500">Truth / Judge</th>
            {VERDICT_LABELS.map((l) => <th key={l} className="pb-2 px-2 font-medium capitalize" style={{ color: VERDICT_COLOURS[l] }}>{l}</th>)}
          </tr>
        </thead>
        <tbody>
          {VERDICT_LABELS.map((row) => (
            <tr key={row}>
              <td className="py-1 pr-2 text-left font-medium capitalize" style={{ color: VERDICT_COLOURS[row] }}>{row}</td>
              {VERDICT_LABELS.map((col) => {
                const val = matrix[row]?.[col] ?? 0;
                const opacity = 0.08 + 0.72 * (val / maxVal);
                return <td key={col} className="py-1 px-2 rounded font-mono" style={{ background: row === col ? `rgba(34,197,94,${opacity})` : val > 0 ? `rgba(239,68,68,${opacity})` : "transparent", color: val > 0 ? "#fff" : "#64748b" }}>{val}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PerClassTable({ metrics }: { metrics: CalibrationPerClassMetric[] }) {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-slate-300">Per-Class Metrics</h3>
      <table className="w-full text-xs">
        <thead className="text-slate-500">
          <tr>
            <th className="pb-2 text-left font-medium">Class</th>
            <th className="pb-2 text-right font-medium">Precision</th>
            <th className="pb-2 text-right font-medium">Recall</th>
            <th className="pb-2 text-right font-medium">F1</th>
            <th className="pb-2 text-right font-medium">Support</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/[0.04]">
          {metrics.map((m) => (
            <tr key={m.label}>
              <td className="py-1.5 pr-4 font-medium capitalize" style={{ color: VERDICT_COLOURS[m.label] }}>{m.label}</td>
              <td className="py-1.5 text-right tabular-nums">{pct(m.precision)}</td>
              <td className="py-1.5 text-right tabular-nums">{pct(m.recall)}</td>
              <td className="py-1.5 text-right tabular-nums font-semibold">{pct(m.f1)}</td>
              <td className="py-1.5 text-right tabular-nums text-slate-400">{m.support}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AccuracyHistoryChart({ runs }: { runs: CalibrationRunView[] }) {
  if (runs.length < 2) return null;
  const w = 480; const h = 80; const pad = { l: 32, r: 8, t: 8, b: 20 };
  const iW = w - pad.l - pad.r; const iH = h - pad.t - pad.b;
  const pts = runs.map((r, i) => [pad.l + (i / (runs.length - 1)) * iW, pad.t + (1 - r.accuracy) * iH] as [number, number]);
  const area = [`M${pts[0][0]},${pad.t + iH}`, ...pts.map(([x, y]) => `L${x},${y}`), `L${pts[pts.length - 1][0]},${pad.t + iH}Z`].join(" ");
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-slate-300">30-Day Accuracy Trend</h3>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="none">
        {[0.9, 0.93, 1.0].map((v) => { const y = pad.t + (1 - v) * iH; return <g key={v}><line x1={pad.l} y1={y} x2={w - pad.r} y2={y} stroke="#1e293b" strokeDasharray="3,3" /><text x={pad.l - 3} y={y + 3} fontSize="7" textAnchor="end" fill="#475569">{(v * 100).toFixed(0)}%</text></g>; })}
        <path d={area} fill="rgba(99,102,241,0.12)" />
        <polyline points={pts.map(([x, y]) => `${x},${y}`).join(" ")} fill="none" stroke="#818cf8" strokeWidth="1.5" strokeLinejoin="round" />
        {pts.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="3" fill={runs[i].accuracy >= 0.93 ? "#22c55e" : runs[i].accuracy >= 0.9 ? "#f59e0b" : "#ef4444"} stroke="#0f172a" strokeWidth="1"><title>{`${runs[i].run_date}: ${pct(runs[i].accuracy)}`}</title></circle>)}
      </svg>
    </div>
  );
}

function RunHistoryTable({ runs }: { runs: CalibrationRunView[] }) {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-slate-300">Run History</h3>
      <table className="w-full text-xs">
        <thead className="text-slate-500">
          <tr>
            <th className="pb-2 text-left font-medium">Date</th>
            <th className="pb-2 text-right font-medium">Status</th>
            <th className="pb-2 text-right font-medium">Samples</th>
            <th className="pb-2 text-right font-medium">Accuracy</th>
            <th className="pb-2 text-right font-medium">Kappa</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/[0.04]">
          {[...runs].reverse().map((r) => (
            <tr key={r.id} className="hover:bg-white/[0.02]">
              <td className="py-1.5 pr-4 tabular-nums text-slate-300">{r.run_date}</td>
              <td className="py-1.5 text-right"><span className={`rounded px-2 py-0.5 text-xs font-medium ${r.status === "complete" ? "bg-emerald-500/15 text-emerald-400" : r.status === "error" ? "bg-red-500/15 text-red-400" : "bg-slate-500/15 text-slate-400"}`}>{r.status}</span></td>
              <td className="py-1.5 text-right tabular-nums">{r.sample_count}</td>
              <td className="py-1.5 text-right tabular-nums font-semibold text-white">{r.status === "complete" ? pct(r.accuracy) : "—"}</td>
              <td className="py-1.5 text-right tabular-nums text-slate-300">{r.status === "complete" ? r.kappa.toFixed(3) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type StepState = "done" | "current" | "pending";
function StepCircle({ state, num }: { state: StepState; num: number }) {
  if (state === "done") return <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-500/20 ring-1 ring-emerald-500/40"><CheckCircle2 className="h-4 w-4 text-emerald-400" /></div>;
  if (state === "current") return <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-500/20 ring-1 ring-indigo-500/40 animate-pulse"><span className="text-xs font-bold text-indigo-400">{num}</span></div>;
  return <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/[0.04] ring-1 ring-white/[0.08]"><span className="text-xs font-medium text-slate-600">{num}</span></div>;
}

function WorkflowStepper({ traceCount, labelCount, runCount, accuracy }: { traceCount: number; labelCount: number; runCount: number; accuracy: number | null }) {
  const steps = [
    { num: 1, label: "Add Traces", sub: traceCount > 0 ? `${traceCount} trace${traceCount !== 1 ? "s" : ""}` : "Pick calls from Calls page", done: traceCount > 0 },
    { num: 2, label: "Label Them", sub: labelCount > 0 ? `${labelCount} labeled` : "Mark each pass / fail / inconclusive", done: labelCount > 0 },
    { num: 3, label: "Run Calibration", sub: runCount > 0 ? `${runCount} run${runCount !== 1 ? "s" : ""}` : "Click Run Now in Judge tab", done: runCount > 0 },
    { num: 4, label: "Score >=90%", sub: accuracy !== null ? (accuracy >= 0.9 ? `✓ ${pct(accuracy)} reliable` : `${pct(accuracy)} needs labels`) : "Waiting for first run", done: accuracy !== null && accuracy >= 0.9 },
  ];
  const firstPending = steps.findIndex((s) => !s.done);
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-5 py-4">
      <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-slate-500">Setup workflow</p>
      <div className="flex flex-wrap gap-5">
        {steps.map((step, idx) => {
          const state: StepState = step.done ? "done" : idx === firstPending ? "current" : "pending";
          return (
            <div key={step.num} className="flex items-start gap-2 min-w-[150px]">
              <StepCircle state={state} num={step.num} />
              <div>
                <p className={`text-xs font-semibold ${state === "done" ? "text-emerald-400" : state === "current" ? "text-indigo-300" : "text-slate-500"}`}>{step.label}</p>
                <p className="text-[10px] text-slate-600 mt-0.5">{step.sub}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TraceRow({ trace, goldenSetId, existingLabel }: { trace: GoldenTraceView; goldenSetId: string; existingLabel: LabelView | null }) {
  const qc = useQueryClient();
  const [showLabeler, setShowLabeler] = useState(false);
  const [verdict, setVerdict] = useState<"pass" | "fail" | "inconclusive">("pass");
  const [rationale, setRationale] = useState("");
  const labelMutation = useMutation({
    mutationFn: (vars: { verdict: "pass" | "fail" | "inconclusive"; rationale: string }) =>
      createOrUpdateCalibrationLabel({ golden_trace_id: trace.id, verdict: vars.verdict, rationale: vars.rationale || undefined }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["calibration-labels"] }); setShowLabeler(false); setRationale(""); },
  });
  const removeMutation = useMutation({
    mutationFn: () => deleteGoldenTrace(goldenSetId, trace.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["golden-traces", goldenSetId] }),
  });
  return (
    <div className="group rounded-lg border border-white/[0.05] bg-white/[0.02] p-3 hover:border-white/[0.12] transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <code className="text-xs text-slate-400 font-mono">{trace.id.slice(0, 12)}…</code>
            {trace.call_id && <span className="text-[10px] text-slate-600">call: {trace.call_id.slice(0, 8)}…</span>}
            {existingLabel && <VerdictBadge verdict={existingLabel.verdict} />}
          </div>
          {trace.expected_output_text && <p className="mt-1.5 text-xs text-slate-500 line-clamp-2">{trace.expected_output_text}</p>}
          {trace.criteria_json && <p className="mt-1 text-[10px] text-slate-600 font-mono truncate">criteria: {trace.criteria_json.slice(0, 80)}…</p>}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {!existingLabel && <button type="button" onClick={() => setShowLabeler(!showLabeler)} className="rounded px-2.5 py-1 text-[10px] font-semibold bg-indigo-600/80 text-white hover:bg-indigo-500 transition-colors">Label</button>}
          {existingLabel && !showLabeler && <button type="button" onClick={() => setShowLabeler(true)} className="rounded px-2 py-1 text-[10px] text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors">Re-label</button>}
          <button type="button" onClick={() => removeMutation.mutate()} disabled={removeMutation.isPending} className="opacity-0 group-hover:opacity-100 rounded px-2 py-1 text-[10px] text-red-400 hover:bg-red-500/10 disabled:opacity-30 transition-all">×</button>
        </div>
      </div>
      {showLabeler && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/[0.06] pt-3">
          <div className="flex items-center gap-1">
            {(["pass", "fail", "inconclusive"] as const).map((v) => (
              <button key={v} type="button" onClick={() => setVerdict(v)} className="rounded px-2.5 py-1 text-[10px] font-semibold capitalize transition-all"
                style={{ background: verdict === v ? `${VERDICT_COLOURS[v]}33` : "transparent", color: verdict === v ? VERDICT_COLOURS[v] : "#94a3b8", border: `1px solid ${verdict === v ? `${VERDICT_COLOURS[v]}55` : "transparent"}` }}>
                {v}
              </button>
            ))}
          </div>
          <input type="text" placeholder="Rationale (optional)" value={rationale} onChange={(e) => setRationale(e.target.value)} className="flex-1 min-w-[120px] rounded border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
          <button type="button" disabled={labelMutation.isPending} onClick={() => labelMutation.mutate({ verdict, rationale })} className="rounded bg-indigo-600 px-3 py-1 text-[10px] font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors">{labelMutation.isPending ? "…" : "Save"}</button>
          <button type="button" onClick={() => setShowLabeler(false)} className="rounded px-2 py-1 text-[10px] text-slate-500 hover:text-slate-300">Cancel</button>
        </div>
      )}
    </div>
  );
}

function SetDetail({ set }: { set: GoldenSetView }) {
  const qc = useQueryClient();
  const [callId, setCallId] = useState("");
  const [expectedOutput, setExpectedOutput] = useState("");
  const tracesQuery = useQuery({ queryKey: ["golden-traces", set.id], queryFn: ({ signal }) => listGoldenTraces(set.id, { limit: 100 }, signal) });
  const labelsQuery = useQuery({ queryKey: ["calibration-labels"], queryFn: ({ signal }) => listCalibrationLabels(undefined, signal) });
  const addTraceMutation = useMutation({
    mutationFn: () => addGoldenTrace(set.id, { call_id: callId.trim() || undefined, expected_output_text: expectedOutput.trim() || undefined }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["golden-traces", set.id] }); qc.invalidateQueries({ queryKey: ["golden-sets"] }); setCallId(""); setExpectedOutput(""); },
  });
  const traces = tracesQuery.data?.items ?? [];
  const labels: LabelView[] = labelsQuery.data ?? [];
  const getLabelForTrace = (id: string) => labels.find((l) => l.golden_trace_id === id && l.active) ?? null;
  const labeledCount = traces.filter((t) => getLabelForTrace(t.id)).length;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-white">{set.name}</h3>
          {set.description && <p className="mt-0.5 text-xs text-slate-500">{set.description}</p>}
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span>{traces.length} traces</span>
          <span className="text-emerald-400">{labeledCount} labeled</span>
          {traces.length - labeledCount > 0 && <span className="text-amber-400">{traces.length - labeledCount} unlabeled</span>}
        </div>
      </div>
      <div className="rounded-lg border border-white/[0.06] bg-white/[0.03] p-3">
        <p className="text-xs text-slate-400 mb-2">Add trace to this set</p>
        <div className="flex flex-wrap items-center gap-2">
          <input type="text" placeholder="Call ID (paste from Calls page)" value={callId} onChange={(e) => setCallId(e.target.value)} className="flex-1 min-w-[180px] rounded border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
          <input type="text" placeholder="Expected output (optional)" value={expectedOutput} onChange={(e) => setExpectedOutput(e.target.value)} className="flex-1 min-w-[180px] rounded border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
          <button type="button" disabled={addTraceMutation.isPending || (!callId.trim() && !expectedOutput.trim())} onClick={() => addTraceMutation.mutate()} className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors">{addTraceMutation.isPending ? "Adding…" : "Add Trace"}</button>
        </div>
      </div>
      {tracesQuery.isLoading ? <p className="text-xs text-slate-500 py-4 text-center">Loading traces…</p>
        : traces.length === 0 ? <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-8 text-center"><p className="text-sm text-slate-400">No traces yet.</p><p className="mt-1 text-xs text-slate-500">Paste a call ID from the Calls page.</p></div>
        : <div className="space-y-2">{traces.map((trace) => <TraceRow key={trace.id} trace={trace} goldenSetId={set.id} existingLabel={getLabelForTrace(trace.id)} />)}</div>}
    </div>
  );
}

function GoldenSetsTab() {
  const qc = useQueryClient();
  const [selectedSetId, setSelectedSetId] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const setsQuery = useQuery({ queryKey: ["golden-sets"], queryFn: ({ signal }) => listGoldenSets({ limit: 50 }, signal) });
  const createMutation = useMutation({
    mutationFn: () => createGoldenSet({ name: newName.trim(), description: newDesc.trim() || undefined }),
    onSuccess: (data) => { qc.invalidateQueries({ queryKey: ["golden-sets"] }); setSelectedSetId(data.id); setNewName(""); setNewDesc(""); setShowCreate(false); },
  });
  const sets: GoldenSetView[] = setsQuery.data?.items ?? [];
  const selectedSet = sets.find((s) => s.id === selectedSetId) ?? null;
  return (
    <div className="flex gap-6 min-h-[50vh]">
      <div className="w-64 shrink-0 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-300">Golden Sets</h2>
          <button type="button" onClick={() => setShowCreate(!showCreate)} className="rounded px-2 py-0.5 text-xs text-indigo-400 hover:bg-indigo-500/10 transition-colors">+ New</button>
        </div>
        {showCreate && (
          <div className="rounded-lg border border-indigo-500/20 bg-indigo-500/5 p-3 space-y-2">
            <input type="text" placeholder="Set name" value={newName} onChange={(e) => setNewName(e.target.value)} className="w-full rounded border border-white/[0.08] bg-white/[0.04] px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
            <input type="text" placeholder="Description (optional)" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} className="w-full rounded border border-white/[0.08] bg-white/[0.04] px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
            <button type="button" disabled={!newName.trim() || createMutation.isPending} onClick={() => createMutation.mutate()} className="w-full rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors">{createMutation.isPending ? "Creating…" : "Create Set"}</button>
          </div>
        )}
        {setsQuery.isLoading ? <p className="text-xs text-slate-500 py-4">Loading…</p>
          : sets.length === 0 ? <p className="text-xs text-slate-600 italic py-4">No golden sets yet.</p>
          : <div className="space-y-1">{sets.map((s) => <button key={s.id} type="button" onClick={() => setSelectedSetId(s.id)} className={`w-full rounded-lg px-3 py-2.5 text-left transition-colors ${selectedSetId === s.id ? "bg-indigo-600/15 border border-indigo-500/30" : "hover:bg-white/[0.04] border border-transparent"}`}><p className={`text-xs font-medium ${selectedSetId === s.id ? "text-indigo-300" : "text-slate-300"}`}>{s.name}</p><p className="text-[10px] text-slate-500 mt-0.5">{s.trace_count} traces · {timeAgo(s.updated_at)}</p></button>)}</div>}
      </div>
      <div className="flex-1 min-w-0">
        {selectedSet ? <SetDetail set={selectedSet} /> : <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-8 text-center"><p className="text-sm text-slate-400">Select a golden set to view and label traces.</p><p className="mt-1 text-xs text-slate-500">Golden sets are curated production traces used to calibrate your LLM judge.</p></div>}
      </div>
    </div>
  );
}

const VERDICT_OPTIONS_JUDGE = ["pass", "fail", "inconclusive"] as const;

function LabelingSection() {
  const labelsQuery = useCalibrationLabels();
  const createLabel = useCreateCalibrationLabel();
  const deleteLabel = useDeleteCalibrationLabel();
  const [traceId, setTraceId] = useState("");
  const [verdict, setVerdict] = useState<"pass" | "fail" | "inconclusive">("pass");
  const [rationale, setRationale] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const activeLabels = (labelsQuery.data ?? []).filter((l: LabelView) => l.active);
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const tid = traceId.trim();
    if (!tid) { setFormError("Golden trace ID is required."); return; }
    setFormError(null);
    createLabel.mutate({ golden_trace_id: tid, verdict, rationale: rationale.trim() || undefined },
      { onSuccess: () => { setTraceId(""); setRationale(""); }, onError: (err: Error) => setFormError(err.message) });
  }
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4 space-y-4">
      <h3 className="text-sm font-semibold text-slate-300">Golden-Set Labels</h3>
      <p className="text-xs text-slate-500">Assign a human verdict to a golden trace. Calibration runs compare these against the judge to compute accuracy and Cohen&apos;s κ.</p>
      <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-[1fr_auto_1fr_auto]">
        <input type="text" placeholder="Golden trace ID" value={traceId} onChange={(e) => setTraceId(e.target.value)} className="rounded border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
        <select value={verdict} onChange={(e) => setVerdict(e.target.value as typeof verdict)} className="rounded border border-white/[0.08] bg-white/[0.04] px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500">
          {VERDICT_OPTIONS_JUDGE.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
        <input type="text" placeholder="Rationale (optional)" value={rationale} onChange={(e) => setRationale(e.target.value)} className="rounded border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
        <button type="submit" disabled={createLabel.isPending} className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors whitespace-nowrap">{createLabel.isPending ? "Saving…" : "Add Label"}</button>
      </form>
      {formError && <p className="text-xs text-red-400">{formError}</p>}
      {activeLabels.length > 0 && (
        <table className="w-full text-xs">
          <thead className="text-slate-500"><tr><th className="pb-2 text-left font-medium">Trace ID</th><th className="pb-2 text-left font-medium">Verdict</th><th className="pb-2 text-left font-medium">Rationale</th><th className="pb-2 text-right font-medium">Added</th><th className="pb-2" /></tr></thead>
          <tbody className="divide-y divide-white/[0.04]">
            {activeLabels.map((label: LabelView) => (
              <tr key={label.id} className="hover:bg-white/[0.02] group">
                <td className="py-1.5 pr-3 font-mono text-slate-400 max-w-[180px] truncate" title={label.golden_trace_id}>{label.golden_trace_id.slice(0, 8)}…</td>
                <td className="py-1.5 pr-3"><VerdictPill verdict={label.verdict} /></td>
                <td className="py-1.5 pr-3 text-slate-400 max-w-[220px] truncate">{label.rationale ?? "—"}</td>
                <td className="py-1.5 text-right tabular-nums text-slate-500">{new Date(label.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</td>
                <td className="py-1.5 text-right"><button type="button" disabled={deleteLabel.isPending} onClick={() => deleteLabel.mutate(label.id)} className="opacity-0 group-hover:opacity-100 rounded px-2 py-0.5 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-30 transition-all">Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-right text-xs text-slate-600">{activeLabels.length} active label{activeLabels.length !== 1 ? "s" : ""}</p>
    </div>
  );
}

function JudgeResultsTab() {
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [days, setDays] = useState(30);
  const latestQuery = useCalibrationLatest();
  const modeQuery = useCalibrationMode(model);
  const historyQuery = useCalibrationHistory(model, days);
  const runNow = useTriggerCalibrationRunNow();
  const latest: CalibrationRunView | null = latestQuery.data?.find((r) => r.judge_model === model) ?? latestQuery.data?.[0] ?? null;
  const allModels = Array.from(new Set((latestQuery.data ?? []).map((r) => r.judge_model)));
  const modeView = modeQuery.data;
  const history = historyQuery.data ?? [];
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          {modeView && <ModeBadge mode={modeView.mode} />}
          {modeView?.reason && <span className="text-xs text-slate-500">Reason: {modeView.reason}</span>}
          {modeView?.last_run_date && <span className="text-xs text-slate-500">Last run: {fmtDate(modeView.last_run_date)}</span>}
        </div>
        <div className="flex items-center gap-2">
          {allModels.length > 1 && <select value={model} onChange={(e) => setModel(e.target.value)} className="rounded border border-white/[0.08] bg-white/[0.04] px-2 py-1 text-xs text-slate-200 focus:outline-none">{allModels.map((m) => <option key={m} value={m}>{m}</option>)}</select>}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded border border-white/[0.08] bg-white/[0.04] px-2 py-1 text-xs text-slate-200 focus:outline-none">
            <option value={7}>7 days</option><option value={14}>14 days</option><option value={30}>30 days</option><option value={90}>90 days</option>
          </select>
          <button type="button" disabled={runNow.isPending} onClick={() => runNow.mutate(model)} className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors">{runNow.isPending ? "Running…" : "Run Now"}</button>
        </div>
      </div>
      {runNow.data && <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-4 py-2 text-xs text-emerald-300">{runNow.data.message}</div>}
      {runNow.error && <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2 text-xs text-red-300">Run failed: {(runNow.error as Error).message}</div>}
      <LabelingSection />
      {latestQuery.isLoading ? <div className="py-16 text-center text-sm text-slate-500">Loading calibration data…</div>
        : !latest ? <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-6 text-center"><p className="text-sm text-slate-400">No calibration runs for <span className="text-slate-200">{model}</span>.</p><p className="mt-1 text-xs text-slate-500">Add labels above then click Run Now.</p></div>
        : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="col-span-2 flex items-center justify-center sm:col-span-1"><AccuracyGauge value={latest.accuracy} /></div>
              <KpiCard label="Cohen's Kappa" value={latest.kappa.toFixed(3)} sub="1.0 = perfect, 0 = chance" />
              <KpiCard label="Low Confidence" value={pct(latest.low_confidence_pct)} sub="Verdicts below 0.5 confidence" />
              <KpiCard label="Samples" value={String(latest.sample_count)} sub={`${latest.agreement_count} agreements`} />
            </div>
            {history.length > 1 && <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4"><AccuracyHistoryChart runs={history} /></div>}
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4"><ConfusionMatrix matrix={latest.confusion_matrix} /></div>
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">{latest.per_class_metrics.length > 0 ? <PerClassTable metrics={latest.per_class_metrics} /> : <p className="text-xs text-slate-500">No per-class metrics.</p>}</div>
            </div>
            {history.length > 0 && <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4"><RunHistoryTable runs={history} /></div>}
          </>
        )}
    </div>
  );
}

function ScoreModelCard({ run }: { run: CalibrationRunView }) {
  const modeQuery = useCalibrationMode(run.judge_model);
  const mode = modeQuery.data?.mode ?? "advisory";
  const v = run.accuracy * 100;
  const color = v >= 93 ? "#22c55e" : v >= 90 ? "#f59e0b" : "#ef4444";
  const r = 40; const circ = 2 * Math.PI * r; const offset = circ - (v / 100) * circ;
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-5 flex flex-col gap-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {v >= 93 ? <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" /> : v >= 90 ? <Info className="w-4 h-4 text-amber-400 shrink-0" /> : <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />}
          <p className="text-sm font-mono text-gray-200 truncate">{run.judge_model}</p>
        </div>
        <ModeBadge mode={mode} />
      </div>
      <div className="flex items-center gap-6">
        <div className="flex flex-col items-center gap-1">
          <svg width="100" height="100" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r={r} fill="none" stroke="#1e293b" strokeWidth="9" />
            <circle cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="9" strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" transform="rotate(-90 50 50)" style={{ transition: "stroke-dashoffset 0.5s ease" }} />
            <text x="50" y="55" textAnchor="middle" fontSize="17" fontWeight="700" fill={color}>{pct(run.accuracy)}</text>
          </svg>
          <p className="text-xs text-gray-500">Accuracy</p>
        </div>
        <div className="flex-1 grid grid-cols-2 gap-3">
          {([["Cohen's κ", run.kappa.toFixed(3)], ["Low conf %", pct(run.low_confidence_pct)], ["Samples", String(run.sample_count)], ["Agreements", String(run.agreement_count)]] as [string, string][]).map(([lbl, val]) => (
            <div key={lbl}><p className="text-xs text-gray-500">{lbl}</p><p className="text-sm font-semibold tabular-nums text-white">{val}</p></div>
          ))}
        </div>
      </div>
      {run.per_class_metrics.length > 0 && (
        <div className="space-y-1.5">
          {run.per_class_metrics.map((m) => (
            <div key={m.label} className="flex items-center gap-2 text-xs">
              <span className="w-20 text-gray-400 capitalize">{m.label}</span>
              <div className="flex-1 h-1.5 rounded-full bg-gray-800 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${Math.round(m.f1 * 100)}%`, background: m.label === "pass" ? "#22c55e" : m.label === "fail" ? "#ef4444" : "#f59e0b" }} /></div>
              <span className="w-10 text-right tabular-nums text-gray-500">{pct(m.f1)}</span>
            </div>
          ))}
          <p className="text-xs text-gray-600 pt-0.5">F1 score per class</p>
        </div>
      )}
      <p className="text-xs text-gray-600 text-right">Last run: <span className="text-gray-400">{fmtDate(run.completed_at ?? run.run_date)}</span></p>
    </div>
  );
}

function ScoreOverviewTab() {
  const { data: runs, isLoading, refetch } = useCalibrationLatest();
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex flex-wrap items-center gap-4 text-xs text-gray-500">
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-400" />≥93% — Blocking</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-amber-400" />≥90% — Advisory</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-red-400" />&lt;90% — Downgraded</span>
        </div>
        <button onClick={() => refetch()} className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors"><RefreshCw className="w-4 h-4" /></button>
      </div>
      {isLoading && <div className="py-20 text-center text-sm text-gray-500">Loading calibration scores…</div>}
      {!isLoading && (!runs || runs.length === 0) && <div className="rounded-xl border border-gray-800 bg-gray-900/30 p-10 text-center"><p className="text-sm text-gray-400">No calibration runs found.</p><p className="mt-1 text-xs text-gray-600">Add labels in the Golden Sets tab, then click Run Now in the Judge Results tab.</p></div>}
      {!isLoading && runs && runs.length > 0 && <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{runs.map((r) => <ScoreModelCard key={r.id} run={r} />)}</div>}
    </div>
  );
}

const TABS: { id: Tab; label: string }[] = [
  { id: "goldens", label: "Golden Sets" },
  { id: "judge", label: "Judge Results" },
  { id: "score", label: "Score Overview" },
];

function CalibrationPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const tabParam = searchParams.get("tab") as Tab | null;
  const activeTab: Tab = tabParam === "judge" || tabParam === "score" ? tabParam : "goldens";
  function setTab(tab: Tab) { router.push(`/calibration?tab=${tab}`, { scroll: false }); }
  const setsQuery = useQuery({ queryKey: ["golden-sets"], queryFn: ({ signal }) => listGoldenSets({ limit: 50 }, signal) });
  const labelsQuery = useQuery({ queryKey: ["calibration-labels"], queryFn: ({ signal }) => listCalibrationLabels(undefined, signal) });
  const { data: runsData } = useCalibrationLatest();
  const traceCount = (setsQuery.data?.items ?? []).reduce((sum: number, s: GoldenSetView) => sum + (s.trace_count ?? 0), 0);
  const labelCount = (labelsQuery.data ?? []).filter((l: LabelView) => l.active).length;
  const runs = runsData ?? [];
  const accuracy = runs[0]?.accuracy ?? null;
  return (
    <div className="space-y-5">
      <WorkflowStepper traceCount={traceCount} labelCount={labelCount} runCount={runs.length} accuracy={accuracy} />
      <div className="flex border-b border-white/[0.06]">
        {TABS.map((tab) => (
          <button key={tab.id} type="button" onClick={() => setTab(tab.id)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${activeTab === tab.id ? "border-indigo-500 text-indigo-300" : "border-transparent text-slate-500 hover:text-slate-300"}`}>
            {tab.label}
          </button>
        ))}
      </div>
      <div className="pt-1">
        {activeTab === "goldens" && <GoldenSetsTab />}
        {activeTab === "judge" && <JudgeResultsTab />}
        {activeTab === "score" && <ScoreOverviewTab />}
      </div>
    </div>
  );
}

export default function CalibrationPage() {
  return (
    <Suspense fallback={<div className="py-16 text-center text-sm text-slate-500">Loading…</div>}>
      <CalibrationPageInner />
    </Suspense>
  );
}