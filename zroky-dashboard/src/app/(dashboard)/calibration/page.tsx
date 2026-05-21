"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, Info, RefreshCw } from "lucide-react";
import { useCalibrationLatest, useCalibrationMode } from "@/lib/hooks";
import type { CalibrationRunView } from "@/lib/api";

// ── helpers ───────────────────────────────────────────────────────────────────

function pct(n: number) {
  return `${(n * 100).toFixed(1)}%`;
}

function fmtDate(d: string | null | undefined) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// ── AccuracyRing ──────────────────────────────────────────────────────────────

function AccuracyRing({ value }: { value: number }) {
  const v = Math.min(1, Math.max(0, value));
  const pctVal = v * 100;
  const color = pctVal >= 93 ? "#22c55e" : pctVal >= 90 ? "#f59e0b" : "#ef4444";
  const r = 40;
  const circ = 2 * Math.PI * r;
  const offset = circ - v * circ;
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} fill="none" stroke="#1e293b" strokeWidth="9" />
        <circle
          cx="50" cy="50" r={r} fill="none"
          stroke={color} strokeWidth="9"
          strokeDasharray={circ} strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 50 50)"
          style={{ transition: "stroke-dashoffset 0.5s ease" }}
        />
        <text x="50" y="55" textAnchor="middle" fontSize="17" fontWeight="700" fill={color}>
          {pct(v)}
        </text>
      </svg>
      <p className="text-xs text-gray-500">Accuracy</p>
    </div>
  );
}

// ── ModeBadge ─────────────────────────────────────────────────────────────────

function ModeBadge({ mode }: { mode: string }) {
  const blocking = mode === "blocking";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${
      blocking
        ? "bg-emerald-950/60 text-emerald-300 ring-emerald-700/40"
        : "bg-amber-950/60 text-amber-300 ring-amber-700/40"
    }`}>
      <span className={`h-1.5 w-1.5 rounded-full ${blocking ? "bg-emerald-400" : "bg-amber-400"}`} />
      {blocking ? "Blocking" : "Advisory"}
    </span>
  );
}

// ── StatusDot ─────────────────────────────────────────────────────────────────

function StatusIcon({ accuracy }: { accuracy: number }) {
  const pctVal = accuracy * 100;
  if (pctVal >= 93)
    return <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />;
  if (pctVal >= 90)
    return <Info className="w-4 h-4 text-amber-400 shrink-0" />;
  return <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />;
}

// ── ModelCard ─────────────────────────────────────────────────────────────────

function ModelCard({ run }: { run: CalibrationRunView }) {
  const modeQuery = useCalibrationMode(run.judge_model);
  const mode = modeQuery.data?.mode ?? "advisory";

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-5 flex flex-col gap-4">
      {/* header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <StatusIcon accuracy={run.accuracy} />
          <p className="text-sm font-mono text-gray-200 truncate">{run.judge_model}</p>
        </div>
        <ModeBadge mode={mode} />
      </div>

      {/* gauge + stats */}
      <div className="flex items-center gap-6">
        <AccuracyRing value={run.accuracy} />
        <div className="flex-1 grid grid-cols-2 gap-3">
          <Stat label="Cohen's κ" value={run.kappa.toFixed(3)} />
          <Stat label="Low conf %" value={pct(run.low_confidence_pct)} />
          <Stat label="Samples" value={String(run.sample_count)} />
          <Stat label="Agreements" value={String(run.agreement_count)} />
        </div>
      </div>

      {/* per-class precision bar */}
      {run.per_class_metrics.length > 0 && (
        <div className="space-y-1.5">
          {run.per_class_metrics.map((m) => (
            <div key={m.label} className="flex items-center gap-2 text-xs">
              <span className="w-20 text-gray-400 capitalize">{m.label}</span>
              <div className="flex-1 h-1.5 rounded-full bg-gray-800 overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.round(m.f1 * 100)}%`,
                    background:
                      m.label === "pass" ? "#22c55e"
                      : m.label === "fail" ? "#ef4444"
                      : "#f59e0b",
                  }}
                />
              </div>
              <span className="w-10 text-right tabular-nums text-gray-500">{pct(m.f1)}</span>
            </div>
          ))}
          <p className="text-xs text-gray-600 pt-0.5">F1 score per class</p>
        </div>
      )}

      <p className="text-xs text-gray-600 text-right">
        Last run: <span className="text-gray-400">{fmtDate(run.completed_at ?? run.run_date)}</span>
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-sm font-semibold tabular-nums text-white">{value}</p>
    </div>
  );
}

// ── Legend ────────────────────────────────────────────────────────────────────

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs text-gray-500">
      <span className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-emerald-400" />≥93% — Blocking mode
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-amber-400" />≥90% — Advisory
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-red-400" />&lt;90% — Downgraded
      </span>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CalibrationPage() {
  const { data: runs, isLoading, refetch } = useCalibrationLatest();

  return (
    <div className="flex flex-col gap-6">
      {/* header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-gray-500 mt-0.5">
            Per-model accuracy vs. human labels · Mode switches at 93% (blocking) / 90% (advisory)
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <Legend />

      {isLoading && (
        <div className="py-20 text-center text-sm text-gray-500">
          Loading calibration scores…
        </div>
      )}

      {!isLoading && (!runs || runs.length === 0) && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/30 p-10 text-center">
          <p className="text-sm text-gray-400">No calibration runs found.</p>
          <p className="mt-1 text-xs text-gray-600">
            Add human labels to golden traces and run calibration from{" "}
            <a href="/judge" className="text-indigo-400 hover:underline">Judge Calibration</a>.
          </p>
        </div>
      )}

      {!isLoading && runs && runs.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {runs.map((r) => (
            <ModelCard key={r.id} run={r} />
          ))}
        </div>
      )}
    </div>
  );
}
