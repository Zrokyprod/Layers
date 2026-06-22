"use client";

import { useState } from "react";

import { clearOwnerToken, getOwnerToken } from "@/lib/owner-api";
import { useOwnerProductionReadiness, useOwnerRetention } from "@/lib/hooks";

function SettingRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="owner-settings-row">
      <span className="owner-settings-label">{label}</span>
      <span className="owner-settings-value">{value}</span>
    </div>
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
          <p className="hint">Admin session, environment visibility and dangerous-operation guardrails.</p>
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
                {readiness.hard_blockers.slice(0, 6).map((blocker) => (
                  <div key={blocker}>
                    <strong>{blocker.split(":")[0]}</strong>
                    <span>{blocker.split(":").slice(1).join(":")}</span>
                  </div>
                ))}
              </div>
            ) : null}
            <div className="owner-settings-rules">
              {readiness.checks.slice(0, 8).map((check) => (
                <div key={check.code}>
                  <strong>{check.label}</strong>
                  <span>
                    <span className={`status-pill status-${check.status}`}>{check.status}</span>{" "}
                    {check.detail}
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
              <SettingRow label="Calls" value={retention.call_retention_days ?? "not configured"} />
              <SettingRow label="Diagnoses" value={retention.diagnosis_retention_days ?? "not configured"} />
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
