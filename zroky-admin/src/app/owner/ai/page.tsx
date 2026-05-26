"use client";

import { useState } from "react";

import { useProviderVerifications, useTestProviderConnection } from "@/lib/hooks";
import type { ProviderVerificationTestResponse } from "@/lib/types";

interface ProviderItem {
  provider: string;
  status: string;
  last_checked_at: string | null;
  last_error: string | null;
  tracked_call_count: number;
}

const STATUS_VAR: Record<string, string> = {
  connected: "var(--status-success)",
  disconnected: "var(--status-error)",
  unknown: "var(--text-secondary)",
  pending: "var(--status-warning)",
};

export default function OwnerAiIntegrationPage() {
  const { data, isLoading, error, refetch } = useProviderVerifications();
  const testMutation = useTestProviderConnection();

  const [testResults, setTestResults] = useState<Record<string, ProviderVerificationTestResponse | string>>({});

  const providers: ProviderItem[] = (data?.items ?? []).map((item) => ({
    provider: item.provider,
    status: item.status,
    last_checked_at: item.last_checked_at,
    last_error: item.last_error,
    tracked_call_count: item.tracked_call_count,
  }));

  const loading = isLoading;
  const errorMessage = error?.message ?? "";

  async function runTest(provider: string) {
    try {
      const result = await testMutation.mutateAsync(provider);
      setTestResults((prev) => ({ ...prev, [provider]: result }));
    } catch (e: unknown) {
      setTestResults((prev) => ({ ...prev, [provider]: (e as Error).message }));
    }
  }

  return (
    <div className="owner-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">AI Integration</h2>
          <p className="hint">Connected LLM providers and model availability.</p>
        </div>
        <button className="btn btn-soft" onClick={() => void refetch()} disabled={loading}>
          Refresh
        </button>
      </div>

      {errorMessage && <div className="alert-strip alert-strip-error">{errorMessage}</div>}
      {loading && <p className="hint">Loading…</p>}

      {!loading && providers.length === 0 && !errorMessage && (
        <div className="alert-strip">No providers configured. Add provider credentials in project settings.</div>
      )}

      {providers.map((p) => {
        const color = STATUS_VAR[p.status] ?? STATUS_VAR.unknown;
        const testResult = testResults[p.provider];
        return (
          <div key={p.provider} className="panel">
            <div className="panel-header" style={{ textTransform: "capitalize" }}>
              {p.provider}
              <span
                className="owner-status-badge"
                style={{ background: `${color}18`, color, border: `1px solid ${color}66`, marginLeft: 10 }}
              >
                {p.status}
              </span>
            </div>

            <div className="owner-provider-meta">
              <span className="hint">
                Tracked calls: <strong style={{ color: "var(--text-primary)" }}>{p.tracked_call_count.toLocaleString()}</strong>
              </span>
              {p.last_error && (
                <span className="owner-provider-error">{p.last_error}</span>
              )}
            </div>

            <div className="owner-provider-actions">
              <button
                className="btn btn-soft"
                onClick={() => runTest(p.provider)}
                disabled={testMutation.isPending && testMutation.variables === p.provider}
              >
                {testMutation.isPending && testMutation.variables === p.provider ? "Testing…" : "Test Connection"}
              </button>
              {p.last_checked_at && (
                <span className="hint">Last checked: {new Date(p.last_checked_at).toLocaleString()}</span>
              )}
            </div>

            {testResult && (
              <div className="owner-test-result">
                {typeof testResult === "string" ? (
                  <span className="owner-test-result-error">{testResult}</span>
                ) : (
                  <div className="owner-test-result-body">
                    <span className={testResult.status === "verified" ? "owner-test-ok" : "owner-test-fail"}>
                      {testResult.status === "verified" ? "Connection Verified" : "Connection Failed"}
                    </span>
                    <span className="hint">{testResult.message}</span>
                    <span className="hint">Checked at: {new Date(testResult.checked_at).toLocaleString()}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
