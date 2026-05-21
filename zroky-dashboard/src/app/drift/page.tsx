"use client";

import { useCallback, useEffect, useState } from "react";

import { getDriftStatus, getDriftHistory, listDriftModels } from "@/lib/api";
import type { DriftModelView, StatusResponse, ModelHistoryResponse, AlertView } from "@/lib/types";

const severityOrder: Record<string, number> = { critical: 0, warn: 1, info: 2 };

function severityBadge(sev: string): string {
  if (sev === "critical") return "badge-critical";
  if (sev === "warn") return "badge-warn";
  return "badge-info";
}

function AlertRow({ alert }: { alert: AlertView }) {
  return (
    <div className="list-row">
      <div className="list-main">
        <strong>{alert.headline}</strong>
        <span>
          {alert.model_id} · {alert.category}
        </span>
      </div>
      <span className={`badge ${severityBadge(alert.severity)}`}>{alert.severity}</span>
    </div>
  );
}

function HistoryChart({ history }: { history: ModelHistoryResponse }) {
  const points = history.points;
  if (points.length === 0) return <div className="empty">No data</div>;

  const rates = points.map((p) => p.judge_pass_rate ?? 0);
  const maxVal = Math.max(1, ...rates);
  const minVal = Math.min(0, ...rates);
  const range = maxVal - minVal || 1;

  return (
    <div className="panel panel-muted">
      <header className="panel-header">
        <div>
          <h4>
            {history.display_name} — {history.category}
          </h4>
          <p>Judge pass rate over last 30 days</p>
        </div>
      </header>
      <div className="chart-bars">
        {points.map((pt, i) => {
          const h = ((pt.judge_pass_rate ?? 0) - minVal) / range;
          return (
            <div key={i} className="chart-bar" title={`${pt.run_date}: ${((pt.judge_pass_rate ?? 0) * 100).toFixed(1)}%`}>
              <div className="chart-bar-fill" style={{ height: `${Math.max(4, h * 100)}%` }} />
              <span className="chart-bar-label">{pt.run_date.slice(5)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function DriftPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [models, setModels] = useState<DriftModelView[]>([]);
  const [histories, setHistories] = useState<ModelHistoryResponse[]>([]);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [statusPayload, modelsPayload] = await Promise.all([
        getDriftStatus(),
        listDriftModels(),
      ]);
      setStatus(statusPayload);
      setModels(modelsPayload);
      if (modelsPayload.length > 0) {
        setSelectedModel(modelsPayload[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load drift data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selectedModel) return;
    let cancelled = false;
    getDriftHistory(selectedModel)
      .then((data) => {
        if (!cancelled) setHistories(data);
      })
      .catch(() => {
        if (!cancelled) setHistories([]);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedModel]);

  const sortedAlerts = status?.alerts
    ? [...status.alerts].sort(
        (a, b) =>
          (severityOrder[a.severity] ?? 99) - (severityOrder[b.severity] ?? 99)
      )
    : [];

  return (
    <main className="page-enter">
      <section className="hero panel">
        <h1>Provider Drift Watch</h1>
        <p>
          Silent-update detector for major LLM providers. Tracks judge pass rates and embedding drift across deterministic prompts.
        </p>
        <div className="hero-footer">
          <div className="actions">
            <a href="/v1/drift/rss" className="btn btn-soft" target="_blank" rel="noopener noreferrer">
              RSS Feed
            </a>
            <a href="/v1/drift/atom" className="btn btn-soft" target="_blank" rel="noopener noreferrer">
              Atom Feed
            </a>
          </div>
        </div>
      </section>

      {error ? (
        <section className="panel">
          <p className="text-red-600">{error}</p>
        </section>
      ) : null}

      {loading ? (
        <section className="kpi-grid">
          <div className="loading" />
          <div className="loading" />
          <div className="loading" />
          <div className="loading" />
        </section>
      ) : (
        <section className="kpi-grid">
          <article className="kpi-card">
            <span className="kpi-label">Tracked Models</span>
            <strong className="kpi-value">{models.length}</strong>
          </article>
          <article className="kpi-card">
            <span className="kpi-label">Total Alerts</span>
            <strong className="kpi-value">{status?.total_alerts ?? 0}</strong>
          </article>
          <article className="kpi-card">
            <span className="kpi-label">Critical</span>
            <strong className="kpi-value text-red-600">{status?.critical_count ?? 0}</strong>
          </article>
          <article className="kpi-card">
            <span className="kpi-label">Warn</span>
            <strong className="kpi-value text-yellow-600">{status?.warn_count ?? 0}</strong>
          </article>
        </section>
      )}

      <section className="grid-two">
        <article className="panel">
          <header className="panel-header">
            <div>
              <h3>Latest Alerts</h3>
              <p>Drift signals from the most recent run.</p>
            </div>
          </header>
          <div className="list">
            {sortedAlerts.length === 0 ? (
              <div className="empty">No drift alerts. All quiet.</div>
            ) : (
              sortedAlerts.map((a) => <AlertRow key={a.id} alert={a} />)
            )}
          </div>
        </article>

        <article className="panel">
          <header className="panel-header">
            <div>
              <h3>Tracked Models</h3>
              <p>Models under active drift surveillance.</p>
            </div>
          </header>
          <div className="list">
            {models.length === 0 ? (
              <div className="empty">No models configured.</div>
            ) : (
              models.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  className={`list-row text-left w-full ${selectedModel === m.id ? "list-row-active" : ""}`}
                  onClick={() => setSelectedModel(m.id)}
                >
                  <div className="list-main">
                    <strong>{m.display_name}</strong>
                    <span>
                      {m.provider} · {m.model_id}
                    </span>
                  </div>
                  {m.active ? <span className="badge badge-green">active</span> : <span className="badge">inactive</span>}
                </button>
              ))
            )}
          </div>
        </article>
      </section>

      {selectedModel && (
        <section className="panel">
          <header className="panel-header">
            <div>
              <h3>History — {models.find((m) => m.id === selectedModel)?.display_name ?? selectedModel}</h3>
              <p>Per-category pass-rate trends over the last 30 days.</p>
            </div>
          </header>
          <div className="grid-two">
            {histories.length === 0 ? (
              <div className="empty">No historical data for this model.</div>
            ) : (
              histories.map((h) => <HistoryChart key={`${h.model_id}-${h.category}`} history={h} />)
            )}
          </div>
        </section>
      )}
    </main>
  );
}
