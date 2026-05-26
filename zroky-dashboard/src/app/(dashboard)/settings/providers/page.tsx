"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  createProviderKey,
  listProviderKeys,
  listProviderVerifications,
  revokeProviderKey,
  testProviderConnection,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { ProviderKeyResponse, ProviderVerificationItem } from "@/lib/types";

const PROVIDER_META: Record<string, { label: string; color: string; description: string }> = {
  openai: {
    label: "OpenAI",
    color: "#10a37f",
    description: "Chat completions, responses, and embeddings.",
  },
  anthropic: {
    label: "Anthropic",
    color: "#d4763b",
    description: "Claude models for reasoning and long context.",
  },
  gemini: {
    label: "Google Gemini",
    color: "#4285f4",
    description: "Gemini models for multimodal and long-context workflows.",
  },
  openrouter: {
    label: "OpenRouter",
    color: "#111827",
    description: "Multi-provider routing for replay and evaluation workers.",
  },
  azure_openai: {
    label: "Azure OpenAI",
    color: "#2563eb",
    description: "Azure-hosted OpenAI deployments.",
  },
  custom: {
    label: "Custom",
    color: "#6b7280",
    description: "Self-hosted or custom provider endpoint.",
  },
};

const PROVIDER_OPTIONS = [
  "openai",
  "anthropic",
  "gemini",
  "openrouter",
  "azure_openai",
  "vertex",
  "cohere",
  "mistral",
  "deepseek",
  "bedrock",
  "groq",
  "custom",
];

type TestState = "idle" | "testing" | "ok" | "error";

export default function ProvidersPage() {
  const [items, setItems] = useState<ProviderVerificationItem[]>([]);
  const [providerKeys, setProviderKeys] = useState<ProviderKeyResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [keysLoading, setKeysLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [keyError, setKeyError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [testStates, setTestStates] = useState<Record<string, TestState>>({});
  const [testMessages, setTestMessages] = useState<Record<string, string>>({});
  const [providerInput, setProviderInput] = useState("openai");
  const [labelInput, setLabelInput] = useState("production");
  const [plaintextInput, setPlaintextInput] = useState("");
  const [includeRevoked, setIncludeRevoked] = useState(false);
  const [savingKey, setSavingKey] = useState(false);
  const [revokingKeyId, setRevokingKeyId] = useState<string | null>(null);

  const loadProviders = useCallback(async (signal?: AbortSignal) => {
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

  const loadKeys = useCallback(async (signal?: AbortSignal) => {
    try {
      setKeysLoading(true);
      const data = await listProviderKeys({ include_revoked: includeRevoked }, signal);
      setProviderKeys(data.items);
      setKeyError(null);
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setKeyError(err instanceof Error ? err.message : "Failed to load provider keys.");
      }
    } finally {
      setKeysLoading(false);
    }
  }, [includeRevoked]);

  useEffect(() => {
    const controller = new AbortController();
    void loadProviders(controller.signal);
    return () => controller.abort();
  }, [loadProviders]);

  useEffect(() => {
    const controller = new AbortController();
    void loadKeys(controller.signal);
    return () => controller.abort();
  }, [loadKeys]);

  async function onTest(provider: string) {
    setTestStates((state) => ({ ...state, [provider]: "testing" }));
    setTestMessages((state) => ({ ...state, [provider]: "" }));
    try {
      const response = await testProviderConnection(provider);
      setTestStates((state) => ({ ...state, [provider]: response.status === "verified" ? "ok" : "error" }));
      setTestMessages((state) => ({ ...state, [provider]: response.message }));
      await loadProviders();
    } catch (err) {
      setTestStates((state) => ({ ...state, [provider]: "error" }));
      setTestMessages((state) => ({
        ...state,
        [provider]: err instanceof Error ? err.message : "Test failed.",
      }));
    }
  }

  async function onSaveProviderKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSavingKey(true);
    setStatusMessage("");
    setKeyError(null);
    try {
      await createProviderKey({
        provider: providerInput,
        plaintext_key: plaintextInput,
        label: labelInput.trim() || null,
      });
      setPlaintextInput("");
      setStatusMessage(`${labelForProvider(providerInput)} key saved and previous active key rotated out.`);
      await loadKeys();
    } catch (err) {
      setKeyError(err instanceof Error ? err.message : "Failed to save provider key.");
    } finally {
      setSavingKey(false);
    }
  }

  async function onRevokeProviderKey(key: ProviderKeyResponse) {
    setRevokingKeyId(key.id);
    setStatusMessage("");
    setKeyError(null);
    try {
      await revokeProviderKey(key.id);
      setStatusMessage(`${labelForProvider(key.provider)} key revoked.`);
      await loadKeys();
    } catch (err) {
      setKeyError(err instanceof Error ? err.message : "Failed to revoke provider key.");
    } finally {
      setRevokingKeyId(null);
    }
  }

  const allProviders = useMemo(() => {
    return [
      ...PROVIDER_OPTIONS,
      ...items.map((item) => item.provider).filter((provider) => !PROVIDER_OPTIONS.includes(provider)),
    ];
  }, [items]);

  function getItem(provider: string): ProviderVerificationItem | undefined {
    return items.find((item) => item.provider === provider);
  }

  function labelForProvider(provider: string): string {
    return PROVIDER_META[provider]?.label ?? provider;
  }

  return (
    <div className="page-content">
      {statusMessage && <div className="alert-strip">{statusMessage}</div>}

      <section className="panel profile-section-gap">
        <header className="panel-header">
          <div>
            <h3>Provider Key Vault</h3>
            <p>Encrypted provider keys used by replay and evaluation workers. Plaintext is never shown again after save.</p>
          </div>
          <label className="list-row" htmlFor="includeRevokedProviderKeys">
            <span>Show revoked keys</span>
            <input
              id="includeRevokedProviderKeys"
              type="checkbox"
              checked={includeRevoked}
              onChange={(event) => setIncludeRevoked(event.target.checked)}
            />
          </label>
        </header>

        <form className="grid-two" onSubmit={onSaveProviderKey}>
          <div className="field">
            <label htmlFor="providerKeyProvider">Provider</label>
            <select
              id="providerKeyProvider"
              value={providerInput}
              onChange={(event) => setProviderInput(event.target.value)}
              disabled={savingKey}
            >
              {PROVIDER_OPTIONS.map((provider) => (
                <option key={provider} value={provider}>{labelForProvider(provider)}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="providerKeyLabel">Label</label>
            <input
              id="providerKeyLabel"
              value={labelInput}
              onChange={(event) => setLabelInput(event.target.value)}
              placeholder="production"
              disabled={savingKey}
            />
          </div>
          <div className="field settings-grid-full">
            <label htmlFor="providerKeyPlaintext">API key</label>
            <input
              id="providerKeyPlaintext"
              type="password"
              value={plaintextInput}
              onChange={(event) => setPlaintextInput(event.target.value)}
              placeholder="Paste provider API key"
              disabled={savingKey}
            />
            <span className="field-hint">Saving a new active key for a provider revokes the previous active key for that provider.</span>
          </div>
          <div className="actions settings-grid-full">
            <button type="submit" className="btn btn-primary" disabled={savingKey || plaintextInput.trim().length < 8}>
              {savingKey ? "Saving..." : "Save provider key"}
            </button>
          </div>
        </form>

        {keyError && <p className="field-error">{keyError}</p>}

        {keysLoading ? (
          <div className="loading" />
        ) : providerKeys.length === 0 ? (
          <div className="empty">No provider keys saved yet.</div>
        ) : (
          <div className="table-wrap">
            <table className="settings-table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Label</th>
                  <th>Key</th>
                  <th>Last used</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {providerKeys.map((key) => (
                  <tr key={key.id}>
                    <td>{labelForProvider(key.provider)}</td>
                    <td>{key.label ?? "-"}</td>
                    <td className="mono">{key.key_fingerprint.slice(0, 8)}...{key.key_last4 ?? "----"}</td>
                    <td>{key.last_used_at ? formatDateTime(key.last_used_at) : "Never"}</td>
                    <td>
                      {key.is_active ? (
                        <span className="pill pill-green">Active</span>
                      ) : (
                        <span className="pill pill-red">Revoked</span>
                      )}
                    </td>
                    <td>
                      {key.is_active && (
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          disabled={revokingKeyId === key.id}
                          onClick={() => void onRevokeProviderKey(key)}
                        >
                          {revokingKeyId === key.id ? "Revoking..." : "Revoke"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel profile-section-gap">
        <header className="panel-header">
          <h3>Upstream AI Providers</h3>
          <p className="panel-sub">Providers detected from captured traffic. Test connectivity after saving vault keys or configuring environment keys.</p>
        </header>

        {loading && <p className="muted">Loading...</p>}
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
                  <div className="provider-avatar" style={{ background: meta?.color ?? "#6b7280" }}>
                    {(meta?.label ?? provider).charAt(0).toUpperCase()}
                  </div>
                  <div className="provider-info">
                    <div className="provider-name-row">
                      <span className="provider-name">{meta?.label ?? provider}</span>
                      <span className={`pill${status === "verified" ? " pill-green" : status === "failed" ? " pill-red" : ""}`}>
                        {status}
                      </span>
                    </div>
                    {meta?.description && <p className="provider-desc">{meta.description}</p>}
                    {item && (
                      <p className="provider-meta">
                        {item.tracked_call_count.toLocaleString()} tracked calls
                        {item.last_checked_at && <> - Last checked {new Date(item.last_checked_at).toLocaleDateString()}</>}
                      </p>
                    )}
                    {item?.last_error && <p className="provider-error">{item.last_error}</p>}
                    {testMsg && (
                      <p className={`provider-test-msg${testState === "ok" ? " ok" : " err"}`}>
                        {testState === "ok" ? "OK" : "Failed"}: {testMsg}
                      </p>
                    )}
                  </div>
                  <div className="provider-actions">
                    <button
                      type="button"
                      className="btn btn-soft btn-sm"
                      disabled={testState === "testing"}
                      onClick={() => void onTest(provider)}
                    >
                      {testState === "testing" ? "Testing..." : "Test connection"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
