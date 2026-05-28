"use client";

import { useCallback, useEffect, useState } from "react";

import { useRateLimits, useSetRateLimitOverrides, useClearRateLimitOverrides } from "@/lib/hooks";

interface EditState {
  ingest_soft_limit_rpm: number;
  ingest_burst_limit_rpm: number;
  ingest_rate_limit_window_seconds: number;
  ingest_sustained_breach_threshold: number;
  ingest_backpressure_ttl_seconds: number;
  ingest_enforce_rate_limit: boolean;
}

function ConfigRow({
  label, envValue, editValue, type, onChange, description,
}: {
  label: string;
  envValue: number | boolean;
  editValue: number | boolean;
  type: "number" | "boolean";
  onChange: (value: number | boolean) => void;
  description: string;
}) {
  const hasOverride = editValue !== envValue;
  return (
    <div className="owner-config-row">
      <div>
        <div className="owner-config-label">
          {label}
          {hasOverride && <span className="owner-config-override-badge">overridden</span>}
        </div>
        <div className="hint">{description}</div>
      </div>
      {type === "number" ? (
        <input
          type="number"
          min={0}
          value={editValue as number}
          onChange={(e) => onChange(parseInt(e.target.value) || 0)}
          className={`input owner-config-input${hasOverride ? " owner-config-input-warn" : ""}`}
        />
      ) : (
        <button
          onClick={() => onChange(!(editValue as boolean))}
          className={`owner-bool-btn${editValue ? " owner-bool-btn-on" : ""}`}
        >
          {editValue ? "Enabled" : "Disabled"}
        </button>
      )}
      <div className="hint">
        Env default: <strong>{typeof envValue === "boolean" ? (envValue ? "enabled" : "disabled") : String(envValue)}</strong>
      </div>
    </div>
  );
}

export default function RateLimitsPage() {
  const rateLimitsQuery = useRateLimits();
  const setOverridesMutation = useSetRateLimitOverrides();
  const clearOverridesMutation = useClearRateLimitOverrides();

  const config = rateLimitsQuery.data ?? null;
  const [edit, setEdit] = useState<EditState | null>(null);
  const [msg, setMsg] = useState("");

  const loading = rateLimitsQuery.isLoading;
  const error = rateLimitsQuery.error?.message ?? "";
  const isMutating = setOverridesMutation.isPending || clearOverridesMutation.isPending;

  useEffect(() => {
    if (config) {
      setEdit({
        ingest_soft_limit_rpm: config.ingest_soft_limit_rpm,
        ingest_burst_limit_rpm: config.ingest_burst_limit_rpm,
        ingest_rate_limit_window_seconds: config.ingest_rate_limit_window_seconds,
        ingest_sustained_breach_threshold: config.ingest_sustained_breach_threshold,
        ingest_backpressure_ttl_seconds: config.ingest_backpressure_ttl_seconds,
        ingest_enforce_rate_limit: config.ingest_enforce_rate_limit,
      });
    }
  }, [config]);

  const handleSave = useCallback(async () => {
    if (!edit || !config) return;
    setMsg("");
    try {
      await setOverridesMutation.mutateAsync(edit as unknown as Record<string, unknown>);
      setMsg("Rate limit overrides saved. Takes effect on next ingest request.");
    } catch (e: unknown) {
      setMsg(`Error: ${(e as Error).message}`);
    }
  }, [edit, config, setOverridesMutation]);

  const handleClear = useCallback(async () => {
    setMsg("");
    try {
      await clearOverridesMutation.mutateAsync();
      setMsg("All overrides cleared. Settings revert to environment defaults.");
    } catch (e: unknown) {
      setMsg(`Error: ${(e as Error).message}`);
    }
  }, [clearOverridesMutation]);

  const setField = useCallback(<K extends keyof EditState>(key: K, value: EditState[K]) => {
    setEdit((prev) => prev ? { ...prev, [key]: value } : prev);
  }, []);

  const hasOverrides = config && Object.keys(config.overrides).length > 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            Rate Limits & Protection
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.82rem", marginTop: 4 }}>
            Configure ingest rate limits. Overrides are stored in Redis and take effect immediately without redeployment.
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          {msg && (
            <span style={{ fontSize: "0.78rem", color: msg.startsWith("Error") ? "var(--status-error)" : "var(--status-success)", maxWidth: 300 }}>
              {msg}
            </span>
          )}
          {hasOverrides && (
            <button
              className="btn btn-danger"
              onClick={handleClear}
              disabled={isMutating}
              style={{ fontSize: "0.78rem", padding: "6px 14px" }}
            >
              Clear Overrides
            </button>
          )}
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={isMutating || loading}
            style={{ fontSize: "0.82rem", padding: "7px 18px" }}
          >
            {isMutating ? "Saving..." : "Save Overrides"}
          </button>
        </div>
      </div>

      {error && <div className="alert-strip alert-strip-error">{error}</div>}
      {loading && !error && <p className="hint">Loading...</p>}

      {hasOverrides && (
        <div className="alert-strip">
          Active overrides: {Object.keys(config.overrides).join(", ")}
        </div>
      )}

      {edit && config && (
        <div className="panel">
          <div className="panel-header">Ingest Rate Limiting</div>

          <ConfigRow
            label="Enforce Rate Limit"
            envValue={config.ingest_enforce_rate_limit}
            editValue={edit.ingest_enforce_rate_limit}
            type="boolean"
            onChange={(v) => setField("ingest_enforce_rate_limit", v as boolean)}
            description="Master switch - disable to allow unlimited ingest"
          />
          <ConfigRow
            label="Soft Limit (RPM)"
            envValue={config.ingest_soft_limit_rpm}
            editValue={edit.ingest_soft_limit_rpm}
            type="number"
            onChange={(v) => setField("ingest_soft_limit_rpm", v as number)}
            description="Normal sustained request limit per project per minute"
          />
          <ConfigRow
            label="Burst Limit (RPM)"
            envValue={config.ingest_burst_limit_rpm}
            editValue={edit.ingest_burst_limit_rpm}
            type="number"
            onChange={(v) => setField("ingest_burst_limit_rpm", v as number)}
            description="Max allowed during normal operation (above soft triggers backpressure)"
          />
          <ConfigRow
            label="Window (seconds)"
            envValue={config.ingest_rate_limit_window_seconds}
            editValue={edit.ingest_rate_limit_window_seconds}
            type="number"
            onChange={(v) => setField("ingest_rate_limit_window_seconds", v as number)}
            description="Rolling window size for rate limit counting"
          />
          <ConfigRow
            label="Sustained Breach Threshold"
            envValue={config.ingest_sustained_breach_threshold}
            editValue={edit.ingest_sustained_breach_threshold}
            type="number"
            onChange={(v) => setField("ingest_sustained_breach_threshold", v as number)}
            description="Consecutive over-burst windows before activating backpressure"
          />
          <ConfigRow
            label="Backpressure TTL (seconds)"
            envValue={config.ingest_backpressure_ttl_seconds}
            editValue={edit.ingest_backpressure_ttl_seconds}
            type="number"
            onChange={(v) => setField("ingest_backpressure_ttl_seconds", v as number)}
            description="How long to enforce reduced limits after sustained breach"
          />
        </div>
      )}

      {/* Note about runtime effect */}
      <div className="panel">
        <div className="panel-header">How Overrides Work</div>
        <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
          Overrides are stored as a JSON object in Redis under the key{" "}
          <code style={{ fontFamily: "monospace", fontSize: "0.75rem" }}>zroky:owner:rate_limit_overrides</code>.
          The ingest service reads these on every request and merges them over the environment-default settings.
          Clearing overrides reverts to the environment defaults configured at deploy time.
        </p>
        <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.6, marginTop: 8 }}>
          <strong>Note:</strong> Ingest enforcement reads this Redis override key during rate-limit evaluation, so
          owner changes take effect without restarting the API while Redis is available.
        </p>
      </div>
    </div>
  );
}
