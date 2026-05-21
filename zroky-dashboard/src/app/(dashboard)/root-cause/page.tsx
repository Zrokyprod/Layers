"use client";

import { useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  GitBranch,
  Loader2,
  RefreshCw,
  Search,
  Shuffle,
  TriangleAlert,
  Zap,
} from "lucide-react";
import { useAblationJob, useAblationJobs, useTriggerAblation } from "@/lib/hooks";
import type { AblationAxisView, AblationJobView } from "@/lib/api";

// ── Determinism class badge ────────────────────────────────────────────────────

function DetClassBadge({ cls }: { cls: string | null }) {
  if (!cls) return <span className="text-gray-400 text-xs">—</span>;
  const map: Record<string, { label: string; color: string; Icon: React.ElementType }> = {
    deterministic: { label: "Deterministic", color: "text-red-400 bg-red-950/40 border-red-800/50", Icon: AlertCircle },
    stochastic: { label: "Stochastic", color: "text-yellow-400 bg-yellow-950/40 border-yellow-800/50", Icon: Shuffle },
    environmental: { label: "Environmental", color: "text-blue-400 bg-blue-950/40 border-blue-800/50", Icon: GitBranch },
    unknown: { label: "Unknown", color: "text-gray-400 bg-gray-800/40 border-gray-700/50", Icon: TriangleAlert },
  };
  const { label, color, Icon } = map[cls] ?? map.unknown;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${color}`}>
      <Icon className="w-3 h-3" /> {label}
    </span>
  );
}

// ── Difficulty badge ────────────────────────────────────────────────────────────

function DiffBadge({ d }: { d: string | null }) {
  if (!d) return null;
  const c = d === "easy" ? "text-green-400" : d === "hard" ? "text-red-400" : "text-yellow-400";
  return <span className={`text-xs font-semibold uppercase ${c}`}>{d}</span>;
}

// ── Status badge ────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  if (status === "done") return <span className="flex items-center gap-1 text-xs text-emerald-400"><CheckCircle2 className="w-3 h-3" /> Done</span>;
  if (status === "running") return <span className="flex items-center gap-1 text-xs text-blue-400"><Loader2 className="w-3 h-3 animate-spin" /> Running</span>;
  if (status === "pending") return <span className="flex items-center gap-1 text-xs text-gray-400"><Clock className="w-3 h-3" /> Pending</span>;
  if (status === "error") return <span className="flex items-center gap-1 text-xs text-red-400"><AlertCircle className="w-3 h-3" /> Error</span>;
  return <span className="text-xs text-gray-400">{status}</span>;
}

// ── Confidence bar ──────────────────────────────────────────────────────────────

function ConfBar({ val }: { val: number }) {
  const pct = Math.round(val * 100);
  const color = val >= 0.7 ? "bg-red-500" : val >= 0.4 ? "bg-yellow-500" : "bg-gray-600";
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="h-1.5 flex-1 rounded-full bg-gray-800 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 tabular-nums w-8 text-right">{pct}%</span>
    </div>
  );
}

// ── Axis row ────────────────────────────────────────────────────────────────────

function AxisRow({ ax }: { ax: AblationAxisView }) {
  const [open, setOpen] = useState(false);
  const evidence = ax.evidence;
  return (
    <div className="border-b border-gray-800/60 last:border-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 py-2.5 px-3 hover:bg-gray-800/30 transition-colors text-left"
      >
        <span className="text-xs font-mono text-indigo-400 w-28 shrink-0 truncate">{ax.axis_type}</span>
        <span className="flex-1 text-sm text-gray-300 truncate">{ax.axis_label}</span>
        <div className="w-36 shrink-0"><ConfBar val={ax.confidence} /></div>
        {open ? <ChevronDown className="w-3.5 h-3.5 text-gray-500" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-500" />}
      </button>
      {open && evidence && (
        <div className="px-4 pb-3 pt-1 bg-gray-900/50">
          <pre className="text-xs text-gray-400 overflow-auto max-h-48 rounded bg-gray-900 p-2 border border-gray-800">
            {JSON.stringify(evidence, null, 2)}
          </pre>
          {ax.failing_value && (
            <p className="mt-2 text-xs text-gray-500">
              <span className="text-gray-400 font-medium">Failing value:</span> {ax.failing_value.slice(0, 200)}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Job detail panel ────────────────────────────────────────────────────────────

function JobPanel({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  const { data: job, isLoading } = useAblationJob(jobId);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400">
        <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading…
      </div>
    );
  }
  if (!job) return null;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="flex items-center justify-between p-4 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <StatusBadge status={job.status} />
          <DetClassBadge cls={job.determinism_class} />
        </div>
        <button onClick={onClose} className="text-xs text-gray-500 hover:text-gray-300 transition-colors">✕ close</button>
      </div>

      <div className="p-4 space-y-4">
        {/* Narrative */}
        {job.root_cause_narrative && (
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-2">Root Cause</h3>
            <p className="text-sm text-gray-200 leading-relaxed">{job.root_cause_narrative}</p>
          </section>
        )}

        {/* Fix */}
        {job.fix_suggestion && (
          <section className="rounded-lg border border-emerald-900/50 bg-emerald-950/20 p-3">
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-xs font-semibold text-emerald-400">Fix</h3>
              <DiffBadge d={job.fix_difficulty} />
            </div>
            <p className="text-sm text-gray-300">{job.fix_suggestion}</p>
            {job.synthesis_confidence != null && (
              <p className="mt-1.5 text-xs text-gray-500">
                Synthesis confidence: {Math.round(job.synthesis_confidence * 100)}%
              </p>
            )}
          </section>
        )}

        {/* Meta */}
        <section className="grid grid-cols-2 gap-2 text-xs text-gray-400">
          <div><span className="text-gray-500">Call ID</span><br /><code className="text-gray-300 font-mono">{job.call_id.slice(0, 24)}…</code></div>
          <div><span className="text-gray-500">Control group</span><br /><span className="text-gray-300">{job.control_group_size} similar traces</span></div>
        </section>

        {/* Axes */}
        {job.axes.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-2">Axis Analysis</h3>
            <div className="rounded-lg border border-gray-800 overflow-hidden">
              {job.axes.map((ax) => <AxisRow key={ax.id} ax={ax} />)}
            </div>
          </section>
        )}

        {job.error_message && (
          <section className="rounded-lg border border-red-900/50 bg-red-950/20 p-3">
            <p className="text-xs text-red-400">{job.error_message}</p>
          </section>
        )}
      </div>
    </div>
  );
}

// ── Job row in list ─────────────────────────────────────────────────────────────

function JobRow({ job, selected, onSelect }: { job: AblationJobView; selected: boolean; onSelect: () => void }) {
  const topAxis = job.axes[0];
  return (
    <button
      onClick={onSelect}
      className={`w-full flex items-center gap-3 px-4 py-3 border-b border-gray-800/60 text-left hover:bg-gray-800/30 transition-colors ${selected ? "bg-gray-800/50 border-l-2 border-l-indigo-500" : ""}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <DetClassBadge cls={job.determinism_class} />
          <StatusBadge status={job.status} />
        </div>
        <p className="text-xs text-gray-400 font-mono truncate">{job.call_id.slice(0, 28)}…</p>
        {topAxis && (
          <p className="text-xs text-gray-500 mt-0.5 truncate">
            Top axis: <span className="text-indigo-400">{topAxis.axis_type}</span> — {Math.round(topAxis.confidence * 100)}% conf.
          </p>
        )}
      </div>
      <time className="text-xs text-gray-600 shrink-0">{new Date(job.created_at).toLocaleDateString()}</time>
    </button>
  );
}

// ── Trigger ablation form ───────────────────────────────────────────────────────

function TriggerForm({ onTriggered }: { onTriggered: (jobId: string) => void }) {
  const [callId, setCallId] = useState("");
  const { mutate, isPending, error } = useTriggerAblation();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!callId.trim()) return;
    mutate({ call_id: callId.trim() }, { onSuccess: (r) => onTriggered(r.job_id) });
  };

  return (
    <form onSubmit={submit} className="flex items-center gap-2">
      <input
        type="text"
        value={callId}
        onChange={(e) => setCallId(e.target.value)}
        placeholder="Paste failing call ID…"
        className="flex-1 text-sm bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
      />
      <button
        type="submit"
        disabled={isPending || !callId.trim()}
        className="flex items-center gap-1.5 text-sm px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg transition-colors"
      >
        {isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
        Analyse
      </button>
      {error && <p className="text-xs text-red-400">{error.message}</p>}
    </form>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────────

export default function RootCausePage() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const { data: jobs, isLoading, refetch } = useAblationJobs(statusFilter, 50);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
        <div>
          <h1 className="text-base font-semibold text-white">Root-Cause Ablation</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Statistical causal analysis — identify which axis explains each failure
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={statusFilter ?? ""}
            onChange={(e) => setStatusFilter(e.target.value || undefined)}
            className="text-xs bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-gray-300 focus:outline-none focus:border-indigo-500"
          >
            <option value="">All statuses</option>
            <option value="done">Done</option>
            <option value="running">Running</option>
            <option value="pending">Pending</option>
            <option value="error">Error</option>
            <option value="insufficient_data">Insufficient data</option>
          </select>
          <button onClick={() => refetch()} className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Trigger form */}
      <div className="px-6 py-3 border-b border-gray-800 bg-gray-900/30">
        <TriggerForm onTriggered={(id) => setSelectedJobId(id)} />
      </div>

      {/* Two-pane layout */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left: job list */}
        <div className="w-80 border-r border-gray-800 overflow-y-auto shrink-0">
          {isLoading && (
            <div className="flex items-center justify-center h-32 text-gray-500">
              <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading…
            </div>
          )}
          {!isLoading && (!jobs || jobs.length === 0) && (
            <div className="flex flex-col items-center justify-center h-48 text-gray-500 gap-2">
              <Search className="w-8 h-8 text-gray-700" />
              <p className="text-sm">No ablation jobs yet</p>
              <p className="text-xs text-gray-600">Paste a failing call ID above to start</p>
            </div>
          )}
          {jobs?.map((j) => (
            <JobRow
              key={j.id}
              job={j}
              selected={j.id === selectedJobId}
              onSelect={() => setSelectedJobId(j.id)}
            />
          ))}
        </div>

        {/* Right: detail or empty state */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {selectedJobId ? (
            <JobPanel jobId={selectedJobId} onClose={() => setSelectedJobId(null)} />
          ) : (
            <div className="flex flex-col items-center justify-center flex-1 gap-3 text-gray-600">
              <GitBranch className="w-10 h-10 text-gray-800" />
              <p className="text-sm">Select a job to see the root-cause analysis</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
