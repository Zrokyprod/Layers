"use client";

import { useEffect, useState } from "react";

import { clearOwnerToken, getOwnerToken } from "@/lib/owner-api";
import {
  useClearRateLimitOverrides,
  useOwnerProductionReadiness,
  useOwnerRetention,
  useRateLimits,
  useSetRateLimitOverrides,
} from "@/lib/hooks";

function SettingRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="owner-settings-row">
      <span className="owner-settings-label">{label}</span>
      <span className="owner-settings-value">{value}</span>
    </div>
  );
}

const RATE_LIMIT_FIELDS: { key: string; label: string }[] = [
  { key: "ingest_soft_limit_rpm", label: "Action intake soft limit (rpm)" },
  { key: "ingest_burst_limit_rpm", label: "Action intake burst limit (rpm)" },
  { key: "ingest_rate_limit_window_seconds", label: "Rate window (seconds)" },
  { key: "ingest_sustained_breach_threshold", label: "Sustained breach threshold" },
  { key: "ingest_backpressure_ttl_seconds", label: "Backpressure TTL (seconds)" },
];

const READINESS_LABELS: Record<string, string> = {
  provider_key_vault_kek: "Connector key vault KEK",
  replay_real_llm: "Proof worker enabled",
};

const READINESS_DETAILS: Record<string, string> = {
  provider_key_vault_kek: "Connector key vault encryption key is missing, placeholder, or too short.",
  replay_real_llm: "Proof worker environment is not production-ready.",
};

function readinessLabel(code: string, label: string): string {
  return READINESS_LABELS[code] ?? label;
}

function readinessDetail(code: string, detail: string): string {
  return READINESS_DETAILS[code] ?? detail;
}

function readinessBlocker(blocker: string): { label: string; detail: string } {
  const [code, ...rest] = blocker.split(":");
  const detail = rest.join(":").trim();
  return {
    label: READINESS_LABELS[code] ?? code,
    detail: READINESS_DETAILS[code] ?? detail,
  };
}

function PlatformRateLimits() {
  const rateLimitsQuery = useRateLimits();
  const setOverrides = useSetRateLimitOverrides();
  const clearOverrides = useClearRateLimitOverrides();
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [enforce, setEnforce] = useState<boolean>(true);
  const [message, setMessage] = useState("");

  const config = rateLimitsQuery.data ?? null;

  useEffect(() => {
    if (!config) return;
    setDraft(
      RATE_LIMIT_FIELDS.reduce<Record<string, number>>((acc, field) => {
        acc[field.key] = Number((config as unknown as Record<string, unknown>)[field.key] ?? 0);
        return acc;
      }, {}),
    );
    setEnforce(Boolean(config.ingest_enforce_rate_limit));
  }, [config]);

  const busy = setOverrides.isPending || clearOverrides.isPending;

  async function save() {
    setMessage("");
    try {
      await setOverrides.mutateAsync({ ...draft, ingest_enforce_rate_limit: enforce });
      setMessage("Platform rate-limit overrides saved.");
    } catch (error: unknown) {
      setMessage(`Error: ${(error as Error).message}`);
    }
  }

  async function reset() {
    setMessage("");
    try {
      await clearOverrides.mutateAsync();
      setMessage("Overrides cleared — using environment defaults.");
    } catch (error: unknown) {
      setMessage(`Error: ${(error as Error).message}`);
    }
  }

  return (
    <section className="panel" aria-label="Platform rate limits">
      <div className="panel-header">
        Platform Rate Limits
        <span className="panel-header-note">Global protected-action intake caps - per-tenant caps live in tenant detail</span>
      </div>
      {rateLimitsQuery.error ? <div className="alert-strip alert-strip-error">{rateLimitsQuery.error.message}</div> : null}
      {message ? <div className={`alert-strip ${message.startsWith("Error") ? "alert-strip-error" : ""}`}>{message}</div> : null}
      {rateLimitsQuery.isLoading ? (
        <p className="hint owner-settings-loading">Loading rate limits...</p>
      ) : config ? (
        <>
          <div className="owner-ratelimit-grid">
            {RATE_LIMIT_FIELDS.map((field) => (
              <label key={field.key} className="field">
                <span className="field-label">{field.label}</span>
                <input
                  className="input"
                  type="number"
                  min={0}
                  value={draft[field.key] ?? 0}
                  disabled={busy}
                  onChange={(event) => setDraft((prev) => ({ ...prev, [field.key]: Number(event.target.value) }))}
                />
              </label>
            ))}
            <label className="field owner-ratelimit-toggle">
              <span className="field-label">Enforce rate limiting</span>
              <input type="checkbox" checked={enforce} disabled={busy} onChange={(event) => setEnforce(event.target.checked)} />
            </label>
          </div>
          <div className="actions">
            <button className="btn btn-primary" type="button" onClick={save} disabled={busy}>
              {setOverrides.isPending ? "Saving..." : "Save overrides"}
            </button>
            <button className="btn btn-soft" type="button" onClick={reset} disabled={busy}>
              {clearOverrides.isPending ? "Clearing..." : "Reset to defaults"}
            </button>
          </div>
        </>
      ) : (
        <p className="hint owner-settings-loading">Rate-limit config unavailable.</p>
      )}
    </section>
  );
}

export default function OwnerSettingsPage() {
  const retentionQuery = useOwnerRetention();
  const readinessQuery = useOwnerProductionReadiness();
  const [tokenPresent, setTokenPresent] = useState(() => Boolean(getOwnerToken()));

  const token = getOwnerToken();
  const sessionLabel = tokenPresent && token
    ? "Active HttpOnly owner session"
    : "No owner token stored";

  function signOut() {
    clearOwnerToken();
    setTokenPresent(false);
    window.location.href = "/owner";
  }

  const retention = retentionQuery.data ?? null;
  const readiness = readinessQuery.data ?? null;
  const readinessFailures = readiness?.checks.filter((check) => check.status === "fail").length ?? null;

  return (
    <div className="owner-page owner-settings-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Settings</h2>
          <p className="hint">Admin session, environment visibility, protected-action limits, and dangerous-operation guardrails.</p>
        </div>
        <button className="btn btn-danger" onClick={signOut}>Sign out</button>
      </div>

      {retentionQuery.error ? <div className="alert-strip alert-strip-error">{retentionQuery.error.message}</div> : null}

      <section className="panel">
        <div className="panel-header">Admin Session</div>
        <div className="owner-settings-list">
          <SettingRow label="Auth model" value="Provisioning token" />
          <SettingRow label="Storage" value="HttpOnly cookie plus non-sensitive session marker" />
          <SettingRow label="Current token" value={sessionLabel} />
          <SettingRow label="Backend header" value={<code>x-zroky-admin-token</code>} />
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">Environment</div>
        <div className="owner-settings-list">
          <SettingRow label="Admin app mode" value={process.env.NODE_ENV} />
          <SettingRow label="API proxy" value={<code>/api/zroky/*</code>} />
          <SettingRow label="Production backend requirement" value="ZROKY_API_BASE_URL must be non-localhost in production" />
          <SettingRow label="Proxy credential policy" value="Converts HttpOnly owner cookie to backend owner header" />
          <SettingRow label="Customer dashboard routes" value="Not present in admin build" />
        </div>
      </section>

      <PlatformRateLimits />

      <section className="panel" aria-label="Production readiness">
        <div className="panel-header">Production Readiness</div>
        {readinessQuery.error ? <div className="alert-strip alert-strip-error">{readinessQuery.error.message}</div> : null}
        {readinessQuery.isLoading ? (
          <p className="hint owner-settings-loading">Loading production readiness...</p>
        ) : readiness ? (
          <div className="owner-settings-list">
            <SettingRow
              label="Overall"
              value={
                <span className={`status-pill status-${readiness.overall_status}`}>
                  {readiness.overall_status}
                </span>
              }
            />
            <SettingRow label="Environment" value={readiness.app_env} />
            <SettingRow label="Production profile" value={readiness.production_profile ? "enabled" : "not enabled"} />
            <SettingRow label="Failed launch gates" value={readinessFailures ?? 0} />
            {readiness.hard_blockers.length > 0 ? (
              <div className="owner-settings-rules">
                {readiness.hard_blockers.slice(0, 6).map((blocker) => {
                  const formatted = readinessBlocker(blocker);
                  return (
                    <div key={blocker}>
                      <strong>{formatted.label}</strong>
                      <span>{formatted.detail}</span>
                    </div>
                  );
                })}
              </div>
            ) : null}
            <div className="owner-settings-rules">
              {readiness.checks.slice(0, 8).map((check) => (
                <div key={check.code}>
                  <strong>{readinessLabel(check.code, check.label)}</strong>
                  <span>
                    <span className={`status-pill status-${check.status}`}>{check.status}</span>{" "}
                    {readinessDetail(check.code, check.detail)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="hint owner-settings-loading">Production readiness unavailable.</p>
        )}
      </section>

      <section className="panel">
        <div className="panel-header">Data Retention</div>
        <div className="owner-settings-list">
          {retentionQuery.isLoading ? (
            <p className="hint owner-settings-loading">Loading retention policy...</p>
          ) : retention ? (
            <>
              <SettingRow label="Protected action records" value={retention.call_retention_days ?? "not configured"} />
              <SettingRow label="Decision records" value={retention.diagnosis_retention_days ?? "not configured"} />
              <SettingRow label="Audit logs" value={retention.audit_log_retention_days ?? "not configured"} />
              <SettingRow label="Notifications" value={retention.notification_retention_days ?? "not configured"} />
              <SettingRow label="Note" value={retention.note} />
            </>
          ) : (
            <p className="hint owner-settings-loading">Retention policy unavailable.</p>
          )}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">Dangerous Operation Rules</div>
        <div className="owner-settings-rules">
          <div>
            <strong>User deletion</strong>
            <span>Requires browser confirmation plus backend confirm=DELETE_CONFIRMED.</span>
          </div>
          <div>
            <strong>User anonymization</strong>
            <span>Preserves audit trail while removing identifying fields.</span>
          </div>
          <div>
            <strong>Maintenance mode</strong>
            <span>Requires owner token and leaves an audit event.</span>
          </div>
          <div>
            <strong>Queue purge and task revoke</strong>
            <span>Backend rate limits and allowlists protect infrastructure actions.</span>
          </div>
        </div>
      </section>
    </div>
  );
}
