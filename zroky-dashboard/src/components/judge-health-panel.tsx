"use client";

import { useEffect, useState } from "react";

import { getJudgeHealth } from "@/lib/api";
import type {
  DimensionDriftView,
  JudgeHealthResponse,
  VerdictDriftView,
} from "@/lib/types";

/**
 * Judge Health panel — exposes the Layer 3 calibration drift signals that
 * previously lived only in process logs and in-memory callbacks. Two views:
 *
 *   1) Verdict drift (judge-vs-truth disagreement rate over the rolling window)
 *   2) Per-dimension drift (older-half vs recent-half mean delta for each
 *      tracked dimension: accuracy / faithfulness / relevance / coherence /
 *      groundedness / completeness)
 *
 * "Breach" badges fire whenever the backend marks a row as breached. The whole
 * panel is read-only — drift state is owned by the backend's calibration
 * window, not the dashboard.
 *
 * Empty-state semantics:
 *   - `enabled === false` → judge engine dormant; render an info banner.
 *   - `verdict_drift` + `dimension_drift` both empty → no samples yet;
 *     render a "no samples yet" message with the configured window length.
 */

interface JudgeHealthPanelProps {
  pollMs?: number; // default 30s — drift moves slowly, polling can be relaxed
}

function formatPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

function formatScore(v: number): string {
  return v.toFixed(3);
}

function VerdictRow({ row }: { row: VerdictDriftView }) {
  return (
    <div className={`judge-health-row${row.breached ? " judge-health-row-breached" : ""}`}>
      <div className="judge-health-row-main">
        <strong className="mono">{row.judge_model}</strong>
        <span className="judge-health-row-sub">
          {row.sample_count} samples · {row.disagreement_count} disagreements
        </span>
      </div>
      <div className="judge-health-row-values">
        <span className="mono">{formatPct(row.disagreement_rate)}</span>
        <span className="judge-health-threshold mono">
          / {formatPct(row.threshold)}
        </span>
        {row.breached && <span className="judge-health-breach-badge">drift</span>}
      </div>
    </div>
  );
}

function DimensionRow({ row }: { row: DimensionDriftView }) {
  const arrow = row.drift > 0 ? "↓" : row.drift < 0 ? "↑" : "→";
  const arrowClass = row.drift > 0 ? "judge-health-arrow-down" : row.drift < 0 ? "judge-health-arrow-up" : "";
  return (
    <div className={`judge-health-row${row.breached ? " judge-health-row-breached" : ""}`}>
      <div className="judge-health-row-main">
        <strong>{row.dimension}</strong>
        <span className="judge-health-row-sub mono">
          {row.judge_model} · {row.sample_count} samples
        </span>
      </div>
      <div className="judge-health-row-values">
        <span className="mono">{formatScore(row.older_mean)}</span>
        <span className={`judge-health-arrow mono ${arrowClass}`}>{arrow}</span>
        <span className="mono">{formatScore(row.recent_mean)}</span>
        <span className="judge-health-threshold mono">
          (Δ {row.drift >= 0 ? "+" : ""}
          {formatScore(row.drift)})
        </span>
        {row.breached && <span className="judge-health-breach-badge">drift</span>}
      </div>
    </div>
  );
}

export function JudgeHealthPanel({ pollMs = 30000 }: JudgeHealthPanelProps) {
  const [data, setData] = useState<JudgeHealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const ctrl = new AbortController();
    let timer: ReturnType<typeof setInterval> | null = null;

    const load = async () => {
      try {
        const fresh = await getJudgeHealth({ signal: ctrl.signal });
        setData(fresh);
        setError(null);
      } catch (err) {
        if ((err as { name?: string })?.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Failed to load judge health.");
      } finally {
        setLoading(false);
      }
    };

    void load();
    timer = setInterval(() => void load(), pollMs);

    return () => {
      ctrl.abort();
      if (timer) clearInterval(timer);
    };
  }, [pollMs]);

  if (loading && !data) {
    return (
      <article className="panel panel-muted">
        <header className="panel-header">
          <div>
            <h3>Judge Health</h3>
            <p>Loading calibration drift…</p>
          </div>
        </header>
        <div className="loading" />
      </article>
    );
  }

  if (error) {
    return (
      <article className="panel panel-muted">
        <header className="panel-header">
          <div>
            <h3>Judge Health</h3>
            <p>Failed to load calibration drift.</p>
          </div>
        </header>
        <div className="empty">{error}</div>
      </article>
    );
  }

  if (!data) return null;

  const hasSamples = data.verdict_drift.length + data.dimension_drift.length > 0;

  return (
    <article
      className={`panel panel-muted judge-health-panel${
        data.any_breached ? " judge-health-panel-breached" : ""
      }`}
    >
      <header className="panel-header">
        <div>
          <h3>
            Judge Health{" "}
            {data.any_breached ? (
              <span className="judge-health-breach-badge judge-health-breach-badge-strong">
                drift detected
              </span>
            ) : data.enabled && hasSamples ? (
              <span className="judge-health-ok-badge">all calibrated</span>
            ) : null}
          </h3>
          <p>
            {data.enabled
              ? `LLM-as-judge drift over the last ${data.window_hours}h.`
              : "Judge engine is disabled — enable JUDGE_ENABLED to populate."}
          </p>
        </div>
        <div className="judge-health-models mono">
          {data.primary_model ?? "no primary"}
          {data.ensemble_models.length > 0 ? ` + ${data.ensemble_models.length} ensemble` : ""}
        </div>
      </header>

      {!data.enabled ? (
        <div className="empty">
          Judge engine is dormant for this project. No calibration data will be recorded
          until <code>JUDGE_ENABLED=true</code> is set in the backend env.
        </div>
      ) : !hasSamples ? (
        <div className="empty">
          No calibration samples recorded in the last {data.window_hours}h. Run a replay
          batch or shadow-judge cycle to populate drift signals.
        </div>
      ) : (
        <>
          {data.verdict_drift.length > 0 && (
            <section className="judge-health-section">
              <h4 className="judge-health-section-title">
                Verdict drift
                <span className="judge-health-section-sub">
                  judge vs deterministic-detector ground truth
                </span>
              </h4>
              <div className="judge-health-list">
                {data.verdict_drift.map((row) => (
                  <VerdictRow key={`v-${row.judge_model}`} row={row} />
                ))}
              </div>
            </section>
          )}

          {data.dimension_drift.length > 0 && (
            <section className="judge-health-section">
              <h4 className="judge-health-section-title">
                Per-dimension drift
                <span className="judge-health-section-sub">
                  rolling mean comparison — Δ &gt; threshold ⇒ quality degraded
                </span>
              </h4>
              <div className="judge-health-list">
                {data.dimension_drift.map((row) => (
                  <DimensionRow
                    key={`d-${row.judge_model}-${row.dimension}`}
                    row={row}
                  />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </article>
  );
}
