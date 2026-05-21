"use client";

import { useState } from "react";
import {
  useCalibrationLatest,
  useCalibrationHistory,
  useCalibrationMode,
  useTriggerCalibrationRunNow,
  useCalibrationLabels,
  useCreateCalibrationLabel,
  useDeleteCalibrationLabel,
} from "@/lib/hooks";
import type { CalibrationRunView, CalibrationPerClassMetric, LabelView } from "@/lib/api";

// ── constants ────────────────────────────────────────────────────────────────

const DEFAULT_MODEL = "anthropic/claude-haiku-4";
const VERDICT_LABELS = ["pass", "fail", "inconclusive"];
const VERDICT_COLOURS: Record<string, string> = {
  pass: "var(--color-pass, #22c55e)",
  fail: "var(--color-fail, #ef4444)",
  inconclusive: "var(--color-warn, #f59e0b)",
};

// ── helpers ──────────────────────────────────────────────────────────────────

function pct(n: number) {
  return `${(n * 100).toFixed(1)}%`;
}

function fmtDate(d: string | null | undefined) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

// ── sub-components ────────────────────────────────────────────────────────────

function ModeBadge({ mode }: { mode: string }) {
  const isBlocking = mode === "blocking";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold tracking-wide ${
        isBlocking
          ? "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30"
          : "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30"
      }`}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: isBlocking ? "#22c55e" : "#f59e0b" }}
      />
      {isBlocking ? "Blocking" : "Advisory"}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    complete: "bg-emerald-500/15 text-emerald-400",
    skipped: "bg-slate-500/15 text-slate-400",
    error: "bg-red-500/15 text-red-400",
    running: "bg-blue-500/15 text-blue-400",
  };
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${map[status] ?? "bg-slate-500/15 text-slate-400"}`}>
      {status}
    </span>
  );
}

function AccuracyGauge({ value }: { value: number }) {
  const pctVal = Math.min(100, Math.max(0, value * 100));
  const color =
    pctVal >= 93 ? "#22c55e" : pctVal >= 90 ? "#f59e0b" : "#ef4444";
  const circumference = 2 * Math.PI * 44;
  const offset = circumference - (pctVal / 100) * circumference;
  return (
    <div className="relative flex flex-col items-center">
      <svg width="112" height="112" viewBox="0 0 112 112" aria-label={`Accuracy ${pct(value)}`}>
        <circle cx="56" cy="56" r="44" fill="none" stroke="var(--color-border, #1e293b)" strokeWidth="10" />
        <circle
          cx="56"
          cy="56"
          r="44"
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 56 56)"
          style={{ transition: "stroke-dashoffset 0.6s ease" }}
        />
        <text x="56" y="61" textAnchor="middle" fontSize="18" fontWeight="700" fill={color}>
          {pct(value)}
        </text>
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
  const labels = VERDICT_LABELS;
  const maxVal = Math.max(1, ...labels.flatMap((r) => labels.map((c) => matrix[r]?.[c] ?? 0)));
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-slate-300">Confusion Matrix</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-center text-xs">
          <thead>
            <tr>
              <th className="pb-2 pr-2 text-left text-slate-500">Truth ↓ / Judge →</th>
              {labels.map((l) => (
                <th key={l} className="pb-2 px-2 font-medium capitalize" style={{ color: VERDICT_COLOURS[l] }}>
                  {l}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {labels.map((row) => (
              <tr key={row}>
                <td className="py-1 pr-2 text-left font-medium capitalize" style={{ color: VERDICT_COLOURS[row] }}>
                  {row}
                </td>
                {labels.map((col) => {
                  const val = matrix[row]?.[col] ?? 0;
                  const opacity = 0.08 + 0.72 * (val / maxVal);
                  const isDiag = row === col;
                  return (
                    <td
                      key={col}
                      className="py-1 px-2 rounded font-mono"
                      style={{
                        background: isDiag
                          ? `rgba(34,197,94,${opacity})`
                          : val > 0
                          ? `rgba(239,68,68,${opacity})`
                          : "transparent",
                        color: val > 0 ? "#fff" : "var(--color-muted, #64748b)",
                      }}
                    >
                      {val}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PerClassTable({ metrics }: { metrics: CalibrationPerClassMetric[] }) {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-slate-300">Per-Class Metrics</h3>
      <div className="overflow-x-auto">
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
                <td className="py-1.5 pr-4 font-medium capitalize" style={{ color: VERDICT_COLOURS[m.label] }}>
                  {m.label}
                </td>
                <td className="py-1.5 text-right tabular-nums">{pct(m.precision)}</td>
                <td className="py-1.5 text-right tabular-nums">{pct(m.recall)}</td>
                <td className="py-1.5 text-right tabular-nums font-semibold">{pct(m.f1)}</td>
                <td className="py-1.5 text-right tabular-nums text-slate-400">{m.support}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AccuracyHistoryChart({ runs }: { runs: CalibrationRunView[] }) {
  if (runs.length === 0) return null;
  const maxAcc = 1;
  const h = 80;
  const w = 480;
  const pad = { l: 32, r: 8, t: 8, b: 20 };
  const innerW = w - pad.l - pad.r;
  const innerH = h - pad.t - pad.b;
  const points = runs.map((r, i) => {
    const x = pad.l + (i / Math.max(runs.length - 1, 1)) * innerW;
    const y = pad.t + (1 - r.accuracy / maxAcc) * innerH;
    return [x, y] as [number, number];
  });
  const polyline = points.map(([x, y]) => `${x},${y}`).join(" ");
  const area = [
    `M${points[0][0]},${pad.t + innerH}`,
    ...points.map(([x, y]) => `L${x},${y}`),
    `L${points[points.length - 1][0]},${pad.t + innerH}Z`,
  ].join(" ");

  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-slate-300">30-Day Accuracy Trend</h3>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${w} ${h}`}
          width="100%"
          height={h}
          preserveAspectRatio="none"
          className="rounded"
          aria-label="Accuracy trend chart"
        >
          {/* grid lines */}
          {[0.9, 0.93, 1.0].map((v) => {
            const y = pad.t + (1 - v) * innerH;
            return (
              <g key={v}>
                <line x1={pad.l} y1={y} x2={w - pad.r} y2={y} stroke="#1e293b" strokeDasharray="3,3" />
                <text x={pad.l - 3} y={y + 3} fontSize="7" textAnchor="end" fill="#475569">
                  {(v * 100).toFixed(0)}%
                </text>
              </g>
            );
          })}
          {/* area fill */}
          <path d={area} fill="rgba(99,102,241,0.12)" />
          {/* line */}
          <polyline
            points={polyline}
            fill="none"
            stroke="#818cf8"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
          {/* dots */}
          {points.map(([x, y], i) => (
            <circle
              key={i}
              cx={x}
              cy={y}
              r="3"
              fill={runs[i].accuracy >= 0.93 ? "#22c55e" : runs[i].accuracy >= 0.9 ? "#f59e0b" : "#ef4444"}
              stroke="#0f172a"
              strokeWidth="1"
            >
              <title>{`${runs[i].run_date}: ${pct(runs[i].accuracy)}`}</title>
            </circle>
          ))}
        </svg>
      </div>
      <div className="mt-1 flex gap-4 text-xs text-slate-500">
        <span><span className="inline-block w-2 h-2 rounded-full bg-emerald-400 mr-1" />≥93% (blocking restore)</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-amber-400 mr-1" />≥90%</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-red-400 mr-1" />&lt;90% (downgrade)</span>
      </div>
    </div>
  );
}

function RunHistoryTable({ runs }: { runs: CalibrationRunView[] }) {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-slate-300">Run History</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="pb-2 text-left font-medium">Date</th>
              <th className="pb-2 text-right font-medium">Status</th>
              <th className="pb-2 text-right font-medium">Samples</th>
              <th className="pb-2 text-right font-medium">Accuracy</th>
              <th className="pb-2 text-right font-medium">Kappa</th>
              <th className="pb-2 text-right font-medium">Low Conf %</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {[...runs].reverse().map((r) => (
              <tr key={r.id} className="hover:bg-white/[0.02] transition-colors">
                <td className="py-1.5 pr-4 tabular-nums text-slate-300">{r.run_date}</td>
                <td className="py-1.5 text-right"><StatusBadge status={r.status} /></td>
                <td className="py-1.5 text-right tabular-nums">{r.sample_count}</td>
                <td className="py-1.5 text-right tabular-nums font-semibold text-white">
                  {r.status === "complete" ? pct(r.accuracy) : "—"}
                </td>
                <td className="py-1.5 text-right tabular-nums text-slate-300">
                  {r.status === "complete" ? r.kappa.toFixed(3) : "—"}
                </td>
                <td className="py-1.5 text-right tabular-nums text-slate-300">
                  {r.status === "complete" ? pct(r.low_confidence_pct) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── labeling ──────────────────────────────────────────────────────────────────

const VERDICT_OPTIONS = ["pass", "fail", "inconclusive"] as const;

function VerdictPill({ verdict }: { verdict: string }) {
  return (
    <span
      className="inline-block rounded px-2 py-0.5 text-xs font-semibold capitalize"
      style={{
        background:
          verdict === "pass"
            ? "rgba(34,197,94,0.15)"
            : verdict === "fail"
            ? "rgba(239,68,68,0.15)"
            : "rgba(245,158,11,0.15)",
        color: VERDICT_COLOURS[verdict] ?? "#94a3b8",
      }}
    >
      {verdict}
    </span>
  );
}

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
    createLabel.mutate(
      { golden_trace_id: tid, verdict, rationale: rationale.trim() || undefined },
      {
        onSuccess: () => { setTraceId(""); setRationale(""); },
        onError: (err) => setFormError(err.message),
      },
    );
  }

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4 space-y-4">
      <h3 className="text-sm font-semibold text-slate-300">Golden-Set Labels</h3>
      <p className="text-xs text-slate-500">
        Assign a human verdict to a golden trace. The daily calibration run compares these
        ground-truth labels against the LLM judge&apos;s verdicts to compute accuracy and Cohen&apos;s κ.
      </p>

      {/* ── Add form ── */}
      <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-[1fr_auto_1fr_auto]">
        <input
          type="text"
          placeholder="Golden trace ID"
          value={traceId}
          onChange={(e) => setTraceId(e.target.value)}
          className="rounded border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <select
          value={verdict}
          onChange={(e) => setVerdict(e.target.value as typeof verdict)}
          className="rounded border border-white/[0.08] bg-white/[0.04] px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          {VERDICT_OPTIONS.map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Rationale (optional)"
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          className="rounded border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <button
          type="submit"
          disabled={createLabel.isPending}
          className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors whitespace-nowrap"
        >
          {createLabel.isPending ? "Saving…" : "Add Label"}
        </button>
      </form>

      {formError && (
        <p className="text-xs text-red-400">{formError}</p>
      )}

      {/* ── Label list ── */}
      {labelsQuery.isLoading ? (
        <p className="text-xs text-slate-500">Loading labels…</p>
      ) : activeLabels.length === 0 ? (
        <p className="text-xs text-slate-600 italic">No active labels yet. Add one above.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="pb-2 text-left font-medium">Trace ID</th>
                <th className="pb-2 text-left font-medium">Verdict</th>
                <th className="pb-2 text-left font-medium">Rationale</th>
                <th className="pb-2 text-right font-medium">v</th>
                <th className="pb-2 text-right font-medium">Added</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {activeLabels.map((label: LabelView) => (
                <tr key={label.id} className="hover:bg-white/[0.02] transition-colors group">
                  <td className="py-1.5 pr-3 font-mono text-slate-400 max-w-[180px] truncate" title={label.golden_trace_id}>
                    {label.golden_trace_id.slice(0, 8)}…
                  </td>
                  <td className="py-1.5 pr-3">
                    <VerdictPill verdict={label.verdict} />
                  </td>
                  <td className="py-1.5 pr-3 text-slate-400 max-w-[220px] truncate" title={label.rationale ?? ""}>
                    {label.rationale ?? <span className="text-slate-600 italic">—</span>}
                  </td>
                  <td className="py-1.5 text-right tabular-nums text-slate-500">{label.version}</td>
                  <td className="py-1.5 text-right tabular-nums text-slate-500 whitespace-nowrap">
                    {new Date(label.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                  </td>
                  <td className="py-1.5 text-right">
                    <button
                      type="button"
                      title="Deactivate label"
                      disabled={deleteLabel.isPending}
                      onClick={() => deleteLabel.mutate(label.id)}
                      className="opacity-0 group-hover:opacity-100 rounded px-2 py-0.5 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-30 transition-all"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-right text-xs text-slate-600">
        {activeLabels.length} active label{activeLabels.length !== 1 ? "s" : ""}
      </p>
    </div>
  );
}

// ── page ─────────────────────────────────────────────────────────────────────

export default function JudgePage() {
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [days, setDays] = useState(30);

  const latestQuery = useCalibrationLatest();
  const modeQuery = useCalibrationMode(model);
  const historyQuery = useCalibrationHistory(model, days);
  const runNow = useTriggerCalibrationRunNow();

  const latest: CalibrationRunView | null =
    latestQuery.data?.find((r) => r.judge_model === model) ?? latestQuery.data?.[0] ?? null;

  const allModels = Array.from(
    new Set((latestQuery.data ?? []).map((r) => r.judge_model))
  );

  const modeView = modeQuery.data;
  const history = historyQuery.data ?? [];
  const isLoading = latestQuery.isLoading || modeQuery.isLoading;

  return (
    <div className="space-y-6 px-1">
      {/* ── Header row ── */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          {modeView && <ModeBadge mode={modeView.mode} />}
          {modeView?.reason && (
            <span className="text-xs text-slate-500">Reason: {modeView.reason}</span>
          )}
          {modeView?.last_run_date && (
            <span className="text-xs text-slate-500">
              Last run: {fmtDate(modeView.last_run_date)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {allModels.length > 1 && (
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="rounded border border-white/[0.08] bg-white/[0.04] px-2 py-1 text-xs text-slate-200 focus:outline-none"
            >
              {allModels.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          )}
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded border border-white/[0.08] bg-white/[0.04] px-2 py-1 text-xs text-slate-200 focus:outline-none"
          >
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
          <button
            type="button"
            disabled={runNow.isPending}
            onClick={() => runNow.mutate(model)}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
          >
            {runNow.isPending ? "Running…" : "Run Now"}
          </button>
        </div>
      </div>

      {/* ── Run now feedback ── */}
      {runNow.data && (
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-4 py-2 text-xs text-emerald-300">
          {runNow.data.message}
        </div>
      )}
      {runNow.error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2 text-xs text-red-300">
          Run failed: {runNow.error.message}
        </div>
      )}

      {isLoading ? (
        <div className="py-16 text-center text-sm text-slate-500">Loading calibration data…</div>
      ) : !latest ? (
        <div className="space-y-4">
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-6 text-center">
            <p className="text-sm text-slate-400">No calibration runs found for <span className="text-slate-200">{model}</span>.</p>
            <p className="mt-1 text-xs text-slate-500">
              Add human labels below, then click <strong>Run Now</strong> to start calibrating.
            </p>
          </div>
          <LabelingSection />
        </div>
      ) : (
        <>
          {/* ── Labeling ── */}
          <LabelingSection />

          {/* ── KPI strip ── */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="col-span-2 flex items-center justify-center sm:col-span-1">
              <AccuracyGauge value={latest.accuracy} />
            </div>
            <KpiCard
              label="Cohen's Kappa"
              value={latest.kappa.toFixed(3)}
              sub="1.0 = perfect, 0 = chance"
            />
            <KpiCard
              label="Low Confidence"
              value={pct(latest.low_confidence_pct)}
              sub="Verdicts below 0.5 confidence"
            />
            <KpiCard
              label="Samples"
              value={String(latest.sample_count)}
              sub={`${latest.agreement_count} agreements`}
            />
          </div>

          {/* ── Trend chart ── */}
          {history.length > 1 && (
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
              <AccuracyHistoryChart runs={history} />
            </div>
          )}

          {/* ── Matrix + per-class ── */}
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
              <ConfusionMatrix matrix={latest.confusion_matrix} />
            </div>
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
              {latest.per_class_metrics.length > 0 ? (
                <PerClassTable metrics={latest.per_class_metrics} />
              ) : (
                <p className="text-xs text-slate-500">No per-class metrics available.</p>
              )}
            </div>
          </div>

          {/* ── History table ── */}
          {history.length > 0 && (
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
              <RunHistoryTable runs={history} />
            </div>
          )}

          {/* ── Model + last run footer ── */}
          <p className="text-right text-xs text-slate-600">
            Model: <span className="text-slate-400">{latest.judge_model}</span>
            {" · "}Last run: <span className="text-slate-400">{fmtDate(latest.completed_at)}</span>
          </p>
        </>
      )}
    </div>
  );
}
