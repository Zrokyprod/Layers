"use client";

import { useState } from "react";

import { clearOwnerToken, getOwnerToken } from "@/lib/owner-api";
import { useOwnerRetention } from "@/lib/hooks";

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
  const [tokenPresent, setTokenPresent] = useState(() => Boolean(getOwnerToken()));

  const token = getOwnerToken();
  const sessionLabel = tokenPresent && token
    ? `Stored in this browser session (${token.length} chars)`
    : "No owner token stored";

  function signOut() {
    clearOwnerToken();
    setTokenPresent(false);
    window.location.href = "/owner";
  }

  const retention = retentionQuery.data ?? null;

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
          <SettingRow label="Storage" value="sessionStorage only" />
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
          <SettingRow label="Customer dashboard routes" value="Not present in admin build" />
        </div>
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
