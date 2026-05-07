"use client";

import { useCallback, useEffect, useState } from "react";

import { listProviderVerifications, testProviderConnection } from "@/lib/api";
import type { ProviderVerificationItem } from "@/lib/types";

const PROVIDER_META: Record<string, { label: string; color: string; description: string }> = {
  openai: {
    label: "OpenAI",
    color: "#10a37f",
    description: "GPT-4, GPT-4o, GPT-3.5 — chat completions and embeddings.",
  },
  anthropic: {
    label: "Anthropic",
    color: "#d4763b",
    description: "Claude 3 Opus, Sonnet, Haiku — reasoning and long context.",
  },
  google: {
    label: "Google Gemini",
    color: "#4285f4",
    description: "Gemini 1.5 Pro / Flash — multimodal and long context.",
  },
};

type TestState = "idle" | "testing" | "ok" | "error";

export default function ProvidersPage() {
  const [items, setItems] = useState<ProviderVerificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testStates, setTestStates] = useState<Record<string, TestState>>({});
  const [testMessages, setTestMessages] = useState<Record<string, string>>({});

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await listProviderVerifications(signal);
      setItems(data.items);
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setError(err instanceof Error ? err.message : "Failed to load providers.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  async function onTest(provider: string) {
    setTestStates((s) => ({ ...s, [provider]: "testing" }));
    setTestMessages((s) => ({ ...s, [provider]: "" }));
    try {
      const res = await testProviderConnection(provider);
      setTestStates((s) => ({ ...s, [provider]: res.status === "verified" ? "ok" : "error" }));
      setTestMessages((s) => ({ ...s, [provider]: res.message }));
      // Reload list to update status
      await load();
    } catch (err) {
      setTestStates((s) => ({ ...s, [provider]: "error" }));
      setTestMessages((s) => ({
        ...s,
        [provider]: err instanceof Error ? err.message : "Test failed.",
      }));
    }
  }

  // Merge backend items with known providers, show unknown providers too
  const allProviders = [
    ...Object.keys(PROVIDER_META),
    ...items.map((i) => i.provider).filter((p) => !PROVIDER_META[p]),
  ];

  function getItem(provider: string): ProviderVerificationItem | undefined {
    return items.find((i) => i.provider === provider);
  }

  return (
    <div className="page-content">
      <section className="panel profile-section-gap">
        <header className="panel-header">
          <h3>Upstream AI Providers</h3>
          <p className="panel-sub">
            Providers your project currently monitors. Test connectivity to verify API key access.
          </p>
        </header>

        {loading && <p className="muted">Loading…</p>}
        {error && <p className="field-error">{error}</p>}

        {!loading && !error && (
          <div className="providers-list">
            {allProviders.map((provider) => {
              const item = getItem(provider);
              const meta = PROVIDER_META[provider];
              const testState = testStates[provider] ?? "idle";
              const testMsg = testMessages[provider] ?? "";
              const status = item?.status ?? "unverified";

              return (
                <div key={provider} className="provider-card">
                  {/* Avatar */}
                  <div
                    className="provider-avatar"
                    style={{ background: meta?.color ?? "#6b7280" }}
                  >
                    {(meta?.label ?? provider).charAt(0).toUpperCase()}
                  </div>

                  {/* Info */}
                  <div className="provider-info">
                    <div className="provider-name-row">
                      <span className="provider-name">{meta?.label ?? provider}</span>
                      <span className={`pill${status === "verified" ? " pill-green" : status === "failed" ? " pill-red" : ""}`}>
                        {status}
                      </span>
                    </div>
                    {meta?.description && (
                      <p className="provider-desc">{meta.description}</p>
                    )}
                    {item && (
                      <p className="provider-meta">
                        {item.tracked_call_count.toLocaleString()} tracked calls
                        {item.last_checked_at && (
                          <> · Last checked {new Date(item.last_checked_at).toLocaleDateString()}</>
                        )}
                      </p>
                    )}
                    {item?.last_error && (
                      <p className="provider-error">{item.last_error}</p>
                    )}
                    {testMsg && (
                      <p className={`provider-test-msg${testState === "ok" ? " ok" : " err"}`}>
                        {testState === "ok" ? "✓" : "✕"} {testMsg}
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="provider-actions">
                    <button
                      type="button"
                      className="btn btn-soft btn-sm"
                      disabled={testState === "testing"}
                      onClick={() => void onTest(provider)}
                    >
                      {testState === "testing" ? "Testing…" : "Test connection"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="panel panel-muted">
        <header className="panel-header">
          <h3>Adding a new provider</h3>
        </header>
        <p className="provider-desc">
          Providers are detected automatically when Zroky ingests your first call from that
          provider. Once detected, use &quot;Test connection&quot; to verify your upstream API key is
          accessible.
        </p>
      </section>
    </div>
  );
}
