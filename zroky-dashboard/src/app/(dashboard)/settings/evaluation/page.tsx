"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { getEvaluationSettings, updateEvaluationSettings } from "@/lib/api";
import type { EvaluationSettingsResponse } from "@/lib/types";
import { formatDateTime } from "@/lib/format";

export default function EvaluationSettingsPage() {
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
            <p>Persisted judge and calibration defaults used by replay, goldens, and CI checks.</p>
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

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Evaluation Workspaces</h3>
            <p>Open detailed calibration and judge diagnostics when tuning quality gates.</p>
          </div>
        </header>
        <div className="grid gap-3 md:grid-cols-2">
          <Link href="/settings/evaluation?workspace=calibration" className="panel panel-muted" style={{ textDecoration: "none" }}>
            <div className="panel-header">
              <div>
                <h3>Calibration</h3>
                <p>Golden sets, judge accuracy, calibration runs, and score overview.</p>
              </div>
            </div>
          </Link>
          <Link href="/settings/evaluation?workspace=judge" className="panel panel-muted" style={{ textDecoration: "none" }}>
            <div className="panel-header">
              <div>
                <h3>Judge Diagnostics</h3>
                <p>Inspect judge health and evaluation diagnostics when tuning quality gates.</p>
              </div>
            </div>
          </Link>
        </div>
      </section>
    </div>
  );
}
