"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
import { FlaskConical, GitBranch, PlayCircle, RefreshCw, ShieldCheck } from "lucide-react";

import { getEvaluationSettings, updateEvaluationSettings } from "@/lib/api";
import { useCalibrationLatest, useJudgeHealth, useTriggerCalibrationRunNow } from "@/lib/hooks";
import type { EvaluationSettingsResponse } from "@/lib/types";
import { formatDateTime, formatUsd } from "@/lib/format";

type EvaluationWorkspace = "overview" | "calibration" | "judge";

function workspaceFromParam(value: string | null): EvaluationWorkspace {
  if (value === "calibration" || value === "judge") return value;
  return "overview";
}

function pct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function signedPctPoints(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(1)}pp`;
}

function WorkspaceCard({
  active,
  href,
  title,
  description,
}: {
  active: boolean;
  href: string;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className={`panel panel-muted settings-workspace-card${active ? " border-primary" : ""}`}
    >
      <div className="panel-header">
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
        {active ? <span className="pill pill-green">Open</span> : null}
      </div>
    </Link>
  );
}

function CalibrationWorkspace() {
  const latestQuery = useCalibrationLatest();
  const triggerCalibration = useTriggerCalibrationRunNow();
  const [runMessage, setRunMessage] = useState("");
  const runs = latestQuery.data ?? [];

  function runCalibrationNow() {
    setRunMessage("");
    triggerCalibration.mutate(undefined, {
      onSuccess: (response) => setRunMessage(response.message || "Calibration run started."),
      onError: (error) => setRunMessage(error instanceof Error ? error.message : "Calibration run failed."),
    });
  }

  return (
    <section className="panel">
      <header className="panel-header">
        <div>
          <h3>Calibration Workspace</h3>
          <p>Latest judge calibration runs, agreement quality, and calibration costs.</p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={runCalibrationNow}
          disabled={triggerCalibration.isPending}
        >
          {triggerCalibration.isPending ? "Starting..." : "Run calibration now"}
        </button>
      </header>

      {runMessage ? (
        <p className={runMessage.toLowerCase().includes("fail") ? "field-error" : "field-success"}>{runMessage}</p>
      ) : null}
      {latestQuery.error ? <p className="field-error">{latestQuery.error.message}</p> : null}
      {latestQuery.isLoading ? <div className="loading" /> : null}

      {!latestQuery.isLoading && !latestQuery.error && runs.length === 0 ? (
        <div className="empty">No calibration runs have been recorded yet.</div>
      ) : null}

      {runs.length > 0 ? (
        <div className="table-wrap">
          <table className="settings-table">
            <thead>
              <tr>
                <th>Judge model</th>
                <th>Status</th>
                <th>Samples</th>
                <th>Accuracy</th>
                <th>Kappa</th>
                <th>Low confidence</th>
                <th>Cost</th>
                <th>Completed</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td className="mono">{run.judge_model}</td>
                  <td><span className="pill">{run.status}</span></td>
                  <td>{run.sample_count.toLocaleString()}</td>
                  <td>{pct(run.accuracy)}</td>
                  <td>{run.kappa.toFixed(2)}</td>
                  <td>{pct(run.low_confidence_pct)}</td>
                  <td className="mono">{formatUsd(run.cost_usd)}</td>
                  <td>{run.completed_at ? formatDateTime(run.completed_at) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function JudgeWorkspace() {
  const judgeQuery = useJudgeHealth(true);
  const health = judgeQuery.data;
  const judgePending = judgeQuery.isLoading || judgeQuery.isFetching;

  return (
    <section className="panel">
      <header className="panel-header">
        <div>
          <h3>Judge Diagnostics</h3>
          <p>Judge health, ensemble coverage, verdict drift, and score-dimension drift.</p>
        </div>
        {health ? <span className={health.any_breached ? "pill pill-red" : "pill pill-green"}>{health.any_breached ? "Drift breached" : "Healthy"}</span> : null}
      </header>

      {judgeQuery.error ? (
        <div className="field-error field-error-row">
          <span>Judge diagnostics are taking longer than expected. {judgeQuery.error.message}</span>
          <button type="button" className="btn btn-soft" onClick={() => void judgeQuery.refetch()}>
            <RefreshCw aria-hidden="true" />
            Retry
          </button>
        </div>
      ) : null}
      {judgePending ? <div className="loading" /> : null}

      {health ? (
        <div className="grid gap-4">
          <div className="kpi-grid">
            <div className="kpi-card">
              <div className="kpi-value">{health.enabled ? "On" : "Off"}</div>
              <div className="kpi-label">Judge enabled</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-value mono">{health.primary_model ?? "auto"}</div>
              <div className="kpi-label">Primary judge</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-value">{health.ensemble_models.length}</div>
              <div className="kpi-label">Ensemble models</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-value">{health.window_hours}h</div>
              <div className="kpi-label">Window</div>
            </div>
          </div>

          <section className="panel panel-muted">
            <header className="panel-header">
              <h3>Verdict drift</h3>
              <p>{health.verdict_drift.length} judge model rows.</p>
            </header>
            {health.verdict_drift.length === 0 ? (
              <div className="empty">No verdict drift rows in the current window.</div>
            ) : (
              <div className="list">
                {health.verdict_drift.map((row) => (
                  <div key={row.judge_model} className="list-row">
                    <div className="list-main">
                      <strong>{row.judge_model}</strong>
                      <span>{row.disagreement_count} disagreements across {row.sample_count} samples.</span>
                    </div>
                    <span className={row.breached ? "pill pill-red" : "pill pill-green"}>
                      {pct(row.disagreement_rate)} / max {pct(row.threshold)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="panel panel-muted">
            <header className="panel-header">
              <h3>Dimension drift</h3>
              <p>{health.dimension_drift.length} score dimensions.</p>
            </header>
            {health.dimension_drift.length === 0 ? (
              <div className="empty">No score dimension drift rows in the current window.</div>
            ) : (
              <div className="list">
                {health.dimension_drift.map((row) => (
                  <div key={`${row.judge_model}-${row.dimension}`} className="list-row">
                    <div className="list-main">
                      <strong>{row.dimension}</strong>
                      <span>{row.judge_model} - {row.sample_count} samples - {pct(row.older_mean)} baseline to {pct(row.recent_mean)} recent.</span>
                    </div>
                    <span className={row.breached ? "pill pill-red" : "pill pill-green"}>
                      {signedPctPoints(row.drift)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      ) : null}
    </section>
  );
}

function EvaluationSettingsContent() {
  const searchParams = useSearchParams();
  const activeWorkspace = workspaceFromParam(searchParams.get("workspace"));
  const [settings, setSettings] = useState<EvaluationSettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [judgeMode, setJudgeMode] = useState<"fast" | "standard" | "strict">("standard");
  const [defaultJudgeModel, setDefaultJudgeModel] = useState("auto");
  const [minimumConfidence, setMinimumConfidence] = useState("0.75");
  const [autoCalibrationEnabled, setAutoCalibrationEnabled] = useState(true);
  const [recordReplayCalibration, setRecordReplayCalibration] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      const response = await getEvaluationSettings();
      setSettings(response);
      setJudgeMode(response.judge_mode);
      setDefaultJudgeModel(response.default_judge_model);
      setMinimumConfidence(String(response.minimum_confidence));
      setAutoCalibrationEnabled(response.auto_calibration_enabled);
      setRecordReplayCalibration(response.record_replay_calibration);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to load evaluation settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      const confidence = Number(minimumConfidence);
      const updated = await updateEvaluationSettings({
        judge_mode: judgeMode,
        default_judge_model: defaultJudgeModel.trim() || "auto",
        minimum_confidence: Number.isFinite(confidence) ? confidence : 0.75,
        auto_calibration_enabled: autoCalibrationEnabled,
        record_replay_calibration: recordReplayCalibration,
      });
      setSettings(updated);
      setMessage("Evaluation settings saved.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save evaluation settings.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-4">
      {message && <div className={message.includes("saved") ? "alert-strip" : "alert-strip alert-strip-error"}>{message}</div>}

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Evaluation Controls</h3>
            <p>Persisted judge and calibration defaults used by replay, Contracts, and CI checks.</p>
          </div>
          {settings?.updated_at && <span className="hint">Updated {formatDateTime(settings.updated_at)}</span>}
        </header>

        {loading ? (
          <div className="loading" />
        ) : (
          <form className="grid gap-3" onSubmit={onSave}>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="field">
                <label htmlFor="judgeMode">Judge mode</label>
                <select
                  id="judgeMode"
                  value={judgeMode}
                  onChange={(event) => setJudgeMode(event.target.value as "fast" | "standard" | "strict")}
                  disabled={saving}
                >
                  <option value="fast">Fast</option>
                  <option value="standard">Standard</option>
                  <option value="strict">Strict</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="defaultJudgeModel">Default judge model</label>
                <input
                  id="defaultJudgeModel"
                  value={defaultJudgeModel}
                  onChange={(event) => setDefaultJudgeModel(event.target.value)}
                  placeholder="auto"
                  disabled={saving}
                />
              </div>
              <div className="field">
                <label htmlFor="minimumConfidence">Minimum confidence</label>
                <input
                  id="minimumConfidence"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={minimumConfidence}
                  onChange={(event) => setMinimumConfidence(event.target.value)}
                  disabled={saving}
                />
              </div>
              <label className="list-row" htmlFor="autoCalibrationEnabled">
                <span>Auto calibration</span>
                <input
                  id="autoCalibrationEnabled"
                  type="checkbox"
                  checked={autoCalibrationEnabled}
                  onChange={(event) => setAutoCalibrationEnabled(event.target.checked)}
                  disabled={saving}
                />
              </label>
              <label className="list-row" htmlFor="recordReplayCalibration">
                <span>Record replay calibration samples</span>
                <input
                  id="recordReplayCalibration"
                  type="checkbox"
                  checked={recordReplayCalibration}
                  onChange={(event) => setRecordReplayCalibration(event.target.checked)}
                  disabled={saving}
                />
              </label>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? "Saving..." : "Save evaluation settings"}
              </button>
            </div>
          </form>
        )}
      </section>

      <section className="panel settings-control-panel">
        <header className="panel-header">
          <div>
            <h3>Where These Controls Apply</h3>
            <p>Evaluation settings are reused across the reliability path instead of living as isolated preferences.</p>
          </div>
        </header>
        <div className="settings-gate-map">
          <div className="settings-gate-map-item">
            <PlayCircle aria-hidden="true" />
            <strong>Replay</strong>
            <span>Judge mode and confidence threshold score replay candidate outputs.</span>
          </div>
          <div className="settings-gate-map-item">
            <FlaskConical aria-hidden="true" />
            <strong>Contracts</strong>
            <span>Replay calibration samples can promote trustworthy traces into fixture-backed Contracts.</span>
          </div>
          <div className="settings-gate-map-item">
            <GitBranch aria-hidden="true" />
            <strong>CI Gates</strong>
            <span>Strict judge behavior increases release-blocking confidence for regressions.</span>
          </div>
          <div className="settings-gate-map-item">
            <ShieldCheck aria-hidden="true" />
            <strong>Cost Impact</strong>
            <span>Low-confidence runs should not be used as business proof without review.</span>
          </div>
        </div>
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Evaluation Workspaces</h3>
            <p>Open detailed calibration and judge diagnostics when tuning quality gates.</p>
          </div>
          {activeWorkspace !== "overview" ? <Link href="/settings/evaluation" className="btn btn-soft">Back to overview</Link> : null}
        </header>
        <div className="grid gap-3 md:grid-cols-2">
          <WorkspaceCard
            active={activeWorkspace === "calibration"}
            href="/settings/evaluation?workspace=calibration"
            title="Calibration"
            description="Fixture sets, judge accuracy, calibration runs, and score overview."
          />
          <WorkspaceCard
            active={activeWorkspace === "judge"}
            href="/settings/evaluation?workspace=judge"
            title="Judge Diagnostics"
            description="Inspect judge health and evaluation diagnostics when tuning quality gates."
          />
        </div>
      </section>

      {activeWorkspace === "calibration" ? <CalibrationWorkspace /> : null}
      {activeWorkspace === "judge" ? <JudgeWorkspace /> : null}
    </div>
  );
}

export default function EvaluationSettingsPage() {
  return (
    <Suspense fallback={<div className="grid gap-4"><section className="panel"><div className="loading" /></section></div>}>
      <EvaluationSettingsContent />
    </Suspense>
  );
}
