"use client";

import { useState } from "react";
import { useJudgeHealth } from "@/lib/hooks";
import type { VerdictDriftView, DimensionDriftView } from "@/lib/api";

// ── helpers ───────────────────────────────────────────────────────────────────

function pct(n: number) {
  return `${(n * 100).toFixed(1)}%`;
}

function BreachedBadge() {
  return (
    <span className="inline-flex items-center rounded-full bg-red-900/60 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-300">
      Breached
    </span>
  );
}

function OkBadge() {
  return (
    <span className="inline-flex items-center rounded-full bg-emerald-900/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-400">
      OK
    </span>
  );
}

// ── sub-components ────────────────────────────────────────────────────────────

function VerdictDriftRow({ row }: { row: VerdictDriftView }) {
  const barWidth = Math.min(100, row.disagreement_rate * 100);
  const thresholdLeft = Math.min(100, row.threshold * 100);

  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-slate-300">{row.judge_model}</p>
          <p className="text-[10px] text-slate-500 mt-0.5">
            {row.disagreement_count} disagreements / {row.sample_count} samples
          </p>
        </div>
        {row.breached ? <BreachedBadge /> : <OkBadge />}
      </div>

      {/* Bar */}
      <div className="relative h-2 rounded-full bg-white/[0.06] overflow-visible">
        <div
          className={`h-2 rounded-full transition-all ${row.breached ? "bg-red-500" : "bg-emerald-500"}`}
          style={{ width: `${barWidth}%` }}
        />
        {/* threshold marker */}
        <div
          className="absolute top-0 h-2 w-0.5 bg-amber-400 rounded-full"
          style={{ left: `${thresholdLeft}%` }}
          title={`Threshold: ${pct(row.threshold)}`}
        />
      </div>

      <div className="flex items-center justify-between text-[10px] text-slate-500">
        <span>Disagreement rate: <span className={row.breached ? "text-red-400" : "text-slate-300"}>{pct(row.disagreement_rate)}</span></span>
        <span>Threshold: <span className="text-amber-400">{pct(row.threshold)}</span></span>
      </div>
    </div>
  );
}

const DIMENSION_ORDER = ["accuracy", "faithfulness", "relevance", "coherence", "groundedness", "completeness"];

function DimensionCard({ row }: { row: DimensionDriftView }) {
  const driftAbs = Math.abs(row.drift);
  const degraded = row.drift > 0; // positive drift = older_mean > recent_mean

  return (
    <div className={`rounded-lg border p-4 space-y-2 ${row.breached ? "border-red-500/30 bg-red-900/10" : "border-white/[0.06] bg-white/[0.02]"}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold capitalize text-slate-300">{row.dimension}</p>
        {row.breached ? <BreachedBadge /> : <OkBadge />}
      </div>
      <p className="text-[10px] text-slate-500">{row.judge_model}</p>

      <div className="flex items-center gap-2 text-xs">
        <span className="text-slate-400">{pct(row.older_mean)}</span>
        <span className="text-slate-600">→</span>
        <span className={degraded ? "text-red-400" : "text-emerald-400"}>{pct(row.recent_mean)}</span>
        <span className={`ml-auto text-[10px] font-semibold ${degraded ? "text-red-400" : "text-emerald-400"}`}>
          {degraded ? "−" : "+"}{pct(driftAbs)}
        </span>
      </div>

      <div className="flex items-center justify-between text-[10px] text-slate-600">
        <span>{row.sample_count} samples</span>
        <span>threshold {pct(row.threshold)}</span>
      </div>
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function DriftPage() {
  const [showZero, setShowZero] = useState(false);
  const query = useJudgeHealth(showZero);
  const data = query.data;

  const verdictDrift = data?.verdict_drift ?? [];
  const dimensionDrift = data?.dimension_drift ?? [];

  // Sort dimensions in canonical order
  const sortedDims = [...dimensionDrift].sort((a, b) => {
    const ai = DIMENSION_ORDER.indexOf(a.dimension);
    const bi = DIMENSION_ORDER.indexOf(b.dimension);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-white">Judge Health &amp; Drift</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            {data
              ? `Window: ${data.window_hours}h · Primary model: ${data.primary_model ?? "none"}`
              : "Monitor verdict consistency and dimension score drift over time."}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showZero}
              onChange={(e) => setShowZero(e.target.checked)}
              className="rounded border-white/20 bg-white/10 text-indigo-500 focus:ring-indigo-500/30"
            />
            Show zero-sample dims
          </label>
        </div>
      </div>

      {/* Breach banner */}
      {data?.any_breached && (
        <div className="rounded-xl border border-red-500/30 bg-red-900/10 px-4 py-3 flex items-center gap-3">
          <span className="text-red-400 text-lg">⚠</span>
          <div>
            <p className="text-sm font-semibold text-red-300">Drift threshold breached</p>
            <p className="text-xs text-red-400/80">One or more judge metrics have exceeded their drift threshold. Review below and consider re-calibration.</p>
          </div>
        </div>
      )}

      {query.isLoading && (
        <p className="py-12 text-center text-sm text-slate-500">Loading judge health…</p>
      )}

      {!query.isLoading && data && !data.enabled && (
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-10 text-center">
          <p className="text-sm text-slate-400">Judge health monitoring is not enabled for this project.</p>
          <p className="mt-1 text-xs text-slate-600">
            Enable it from the Judge Calibration page and run at least one calibration.
          </p>
        </div>
      )}

      {/* Verdict drift */}
      {verdictDrift.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-300">Verdict Drift</h2>
          <p className="text-xs text-slate-500">
            Rate at which the judge disagrees with itself across time windows.
          </p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {verdictDrift.map((row) => (
              <VerdictDriftRow key={`${row.judge_model}`} row={row} />
            ))}
          </div>
        </section>
      )}

      {/* Dimension drift */}
      {sortedDims.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-300">Dimension Drift</h2>
          <p className="text-xs text-slate-500">
            Per-dimension mean score shift between older and recent evaluation windows.
          </p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {sortedDims.map((row) => (
              <DimensionCard key={`${row.judge_model}-${row.dimension}`} row={row} />
            ))}
          </div>
        </section>
      )}

      {!query.isLoading && data?.enabled && verdictDrift.length === 0 && sortedDims.length === 0 && (
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-10 text-center">
          <p className="text-sm text-slate-400">No drift data yet.</p>
          <p className="mt-1 text-xs text-slate-600">
            Run calibration with enough golden-set traces to populate drift metrics.
          </p>
        </div>
      )}

      {/* Ensemble info */}
      {data && data.ensemble_models.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Ensemble Models</h2>
          <div className="flex flex-wrap gap-2">
            {data.ensemble_models.map((m) => (
              <span key={m} className="rounded bg-white/[0.04] border border-white/[0.06] px-2 py-0.5 text-xs text-slate-400">
                {m}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
