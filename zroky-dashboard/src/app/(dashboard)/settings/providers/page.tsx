"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  KeyRound,
  LockKeyhole,
  Plug,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import {
  createProviderKey,
  listProviderKeys,
  listProviderVerifications,
  revokeProviderKey,
  testProviderConnection,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { ProviderKeyResponse, ProviderVerificationItem } from "@/lib/types";

const PROVIDER_META: Record<string, { label: string; description: string }> = {
  openai: {
    label: "OpenAI",
    description: "Chat completions, responses, and embeddings.",
  },
  anthropic: {
    label: "Anthropic",
    description: "Claude models for reasoning and long context.",
  },
  gemini: {
    label: "Google Gemini",
    description: "Gemini models for multimodal and long-context workflows.",
  },
  openrouter: {
    label: "OpenRouter",
    description: "Multi-provider routing for replay and evaluation workers.",
  },
  azure_openai: {
    label: "Azure OpenAI",
    description: "Azure-hosted OpenAI deployments.",
  },
  custom: {
    label: "Custom",
    description: "Private or custom provider endpoint.",
  },
};

const PRIMARY_PROVIDERS = ["openai", "anthropic", "gemini", "openrouter"];

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

const replayProviderFlow = [
  "Capture without key",
  "Stub replay",
  "Connect provider key",
  "Verified replay",
  "CI gate",
];

type TestState = "idle" | "testing" | "ok" | "error";

function keyFingerprint(key: ProviderKeyResponse): string {
  return `${key.key_fingerprint.slice(0, 8)}...${key.key_last4 ?? "----"}`;
}

function isConfigProblem(message: string | null): boolean {
  if (!message) return false;
  const normalized = message.toLowerCase();
  return normalized.includes("not configured") || normalized.includes("unavailable") || normalized.includes("503") || normalized.includes("vault");
}

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
  const [revokeTarget, setRevokeTarget] = useState<ProviderKeyResponse | null>(null);

  const loadProviders = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await listProviderVerifications(signal);
      setItems(data.items);
      setError(null);
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
      setStatusMessage(`${labelForProvider(providerInput)} key saved. Verified replay can now run with your provider account.`);
      await loadKeys();
    } catch (err) {
      setKeyError(err instanceof Error ? err.message : "Failed to save provider key.");
    } finally {
      setSavingKey(false);
    }
  }

  async function onRevokeProviderKey() {
    if (!revokeTarget) return;
    const key = revokeTarget;
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
      setRevokeTarget(null);
    }
  }

  const allProviders = useMemo(() => {
    return Array.from(new Set([...PRIMARY_PROVIDERS, ...PROVIDER_OPTIONS, ...items.map((item) => item.provider)]));
  }, [items]);

  function getItem(provider: string): ProviderVerificationItem | undefined {
    return items.find((item) => item.provider === provider);
  }

  function labelForProvider(provider: string): string {
    return PROVIDER_META[provider]?.label ?? provider;
  }

  function activeKeyForProvider(provider: string): ProviderKeyResponse | undefined {
    return providerKeys.find((key) => key.provider === provider && key.is_active);
  }

  const activeProviderKeys = providerKeys.filter((key) => key.is_active);
  const detectedProviders = items.filter((item) => item.tracked_call_count > 0).length;
  const verifiedProviders = items.filter((item) => item.status === "verified").length;
  const vaultConfigProblem = isConfigProblem(keyError);
  const secondaryProviders = allProviders.filter((provider) => !PRIMARY_PROVIDERS.includes(provider));

  function renderProviderCard(provider: string, variant: "primary" | "secondary") {
    const item = getItem(provider);
    const activeKey = activeKeyForProvider(provider);
    const meta = PROVIDER_META[provider];
    const testState = testStates[provider] ?? "idle";
    const testMsg = testMessages[provider] ?? "";
    const status = item?.status ?? "unverified";

    return (
      <article key={provider} className={`provider-card provider-status-card provider-${variant}`}>
        <div className="provider-avatar">
          {(meta?.label ?? provider).charAt(0).toUpperCase()}
        </div>
        <div className="provider-info">
          <div className="provider-name-row">
            <span className="provider-name">{meta?.label ?? provider}</span>
            <span className={`pill${activeKey ? " pill-green" : ""}`}>{activeKey ? "Active key" : "No key"}</span>
            <span className={`pill${status === "verified" ? " pill-green" : status === "failed" ? " pill-red" : ""}`}>
              {status}
            </span>
          </div>
          <p className="provider-desc">{meta?.description ?? "Provider is available for verified replay when a key is saved."}</p>
          <div className="provider-card-meta">
            <span>{item ? `${item.tracked_call_count.toLocaleString()} tracked calls` : "No captured traffic yet"}</span>
            <span>{item?.last_checked_at ? `Last checked ${formatDateTime(item.last_checked_at)}` : "Not checked yet"}</span>
            <span>{activeKey ? `Vault ${keyFingerprint(activeKey)}` : "Vault key not connected"}</span>
          </div>
          {item?.last_error ? <p className="provider-error">{item.last_error}</p> : null}
          {testMsg ? (
            <p className={`provider-test-msg${testState === "ok" ? " ok" : " err"}`}>
              {testState === "ok" ? "OK" : "Failed"}: {testMsg}
            </p>
          ) : null}
        </div>
        <div className="provider-actions">
          <button
            type="button"
            className="btn btn-soft btn-sm"
            disabled={testState === "testing"}
            onClick={() => void onTest(provider)}
          >
            <RefreshCw aria-hidden="true" />
            {testState === "testing" ? "Testing..." : "Test connection"}
          </button>
        </div>
      </article>
    );
  }

  return (
    <div className="page-content providers-setup-page">
      <section className="panel providers-setup-hero">
        <div className="providers-hero-copy">
          <span className="settings-section-kicker">
            <KeyRound aria-hidden="true" />
            BYOK replay
          </span>
          <h1>Connect provider keys only when verified replay needs them.</h1>
          <p>Capture stays keyless. Verified replay uses your provider account so model spend stays visible.</p>
        </div>
        <div className="providers-hero-actions">
          <Link href="/replay" className="btn btn-primary">
            Open Replay Lab
            <ArrowRight aria-hidden="true" />
          </Link>
          <Link href="/settings/keys" className="btn btn-soft">
            Project keys
          </Link>
        </div>
        <div className="providers-flow-rail" aria-label="Capture to verified replay provider key flow">
          {replayProviderFlow.map((step, index) => (
            <span key={step} className={index === 2 ? "is-current" : undefined}>
              {String(index + 1).padStart(2, "0")}
              <strong>{step}</strong>
            </span>
          ))}
        </div>
      </section>

      {statusMessage ? <div className="alert-strip providers-status-message">{statusMessage}</div> : null}

      <section className="settings-summary-grid">
        <article className="panel settings-summary-card">
          <KeyRound aria-hidden="true" />
          <span>Active vault keys</span>
          <strong>{activeProviderKeys.length}</strong>
          <small>{providerKeys.length} total key records loaded.</small>
        </article>
        <article className="panel settings-summary-card">
          <Plug aria-hidden="true" />
          <span>Detected providers</span>
          <strong>{detectedProviders}</strong>
          <small>From captured production or replay traffic.</small>
        </article>
        <article className="panel settings-summary-card">
          <CheckCircle2 aria-hidden="true" />
          <span>Verified</span>
          <strong>{verifiedProviders}</strong>
          <small>Connectivity tests that passed recently.</small>
        </article>
        <article className="panel settings-summary-card">
          <ShieldAlert aria-hidden="true" />
          <span>Vault state</span>
          <strong>{vaultConfigProblem ? "Needs config" : "Reachable"}</strong>
          <small>{vaultConfigProblem ? "Set backend provider key encryption before saving." : "Key list endpoint responded."}</small>
        </article>
      </section>

      <section className="providers-primary-grid">
        <article className="panel providers-save-panel">
          <header className="panel-header">
            <div>
              <h2>Save provider key for verified replay</h2>
              <p>Capture, traces, issues, and stub replay work without this key. Connect it only when real replay proof is needed.</p>
            </div>
          </header>

          {vaultConfigProblem ? (
            <div className="settings-config-warning" role="status">
              <AlertTriangle aria-hidden="true" />
              <div>
                <strong>Provider vault is not ready in this environment.</strong>
                <span>{keyError}</span>
              </div>
            </div>
          ) : null}

          <form className="providers-save-form" onSubmit={onSaveProviderKey}>
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
            <div className="field providers-key-field">
              <label htmlFor="providerKeyPlaintext">API key</label>
              <input
                id="providerKeyPlaintext"
                type="password"
                value={plaintextInput}
                onChange={(event) => setPlaintextInput(event.target.value)}
                placeholder="Paste provider API key"
                disabled={savingKey}
              />
              <span className="field-hint">Plaintext is submitted once, encrypted by the vault, then cleared from this form.</span>
            </div>
            <button type="submit" className="btn btn-primary" disabled={savingKey || plaintextInput.trim().length < 8}>
              <ShieldCheck aria-hidden="true" />
              {savingKey ? "Saving..." : "Save provider key"}
            </button>
          </form>

          {keyError && !vaultConfigProblem ? <p className="field-error">{keyError}</p> : null}
        </article>

        <aside className="panel providers-rule-card">
          <span className="settings-section-kicker">
            <LockKeyhole aria-hidden="true" />
            Key rule
          </span>
          <h2>Do not add provider keys for capture.</h2>
          <p>Provider keys are only used by verified replay, CI replay, and evaluation workers. Your normal capture path remains project-key based.</p>
          <div className="providers-rule-list">
            {["Signup and login", "SDK/Gateway capture", "Trace and issue browsing", "Stub replay"].map((item) => (
              <span key={item}>
                <CheckCircle2 aria-hidden="true" />
                {item}
              </span>
            ))}
          </div>
        </aside>
      </section>

      <section className="panel providers-card-section">
        <header className="panel-header">
          <div>
            <h2>Priority providers</h2>
            <p>Connect the provider your agent already uses, then run a connection test before verified replay.</p>
          </div>
        </header>

        {loading ? <p className="muted">Loading providers...</p> : null}
        {error ? <p className="field-error">{error}</p> : null}
        {!loading && !error ? (
          <div className="providers-card-grid">
            {PRIMARY_PROVIDERS.map((provider) => renderProviderCard(provider, "primary"))}
          </div>
        ) : null}
      </section>

      <section className="panel providers-vault-panel">
        <header className="panel-header">
          <div>
            <h2>Provider key vault</h2>
            <p>Active and revoked provider keys. A new active key rotates out the previous active key for that provider.</p>
          </div>
          <label className="providers-toggle" htmlFor="includeRevokedProviderKeys">
            <span>Show revoked keys</span>
            <input
              id="includeRevokedProviderKeys"
              type="checkbox"
              checked={includeRevoked}
              onChange={(event) => setIncludeRevoked(event.target.checked)}
            />
          </label>
        </header>

        {keysLoading ? (
          <div className="loading" />
        ) : providerKeys.length === 0 ? (
          <div className="empty">No provider keys saved yet. Capture still works; connect a key when verified replay is needed.</div>
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
                    <td className="mono">{keyFingerprint(key)}</td>
                    <td>{key.last_used_at ? formatDateTime(key.last_used_at) : "Never"}</td>
                    <td>
                      {key.is_active ? (
                        <span className="pill pill-green">Active</span>
                      ) : (
                        <span className="pill pill-red">Revoked</span>
                      )}
                    </td>
                    <td>
                      {key.is_active ? (
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          disabled={revokingKeyId === key.id}
                          onClick={() => setRevokeTarget(key)}
                        >
                          {revokingKeyId === key.id ? "Revoking..." : "Revoke"}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {!loading && !error && secondaryProviders.length > 0 ? (
        <section className="panel providers-card-section providers-secondary-section">
          <header className="panel-header">
            <div>
              <h2>Other provider checks</h2>
              <p>These providers remain available for teams with custom routing or less common model stacks.</p>
            </div>
          </header>
          <div className="providers-list">
            {secondaryProviders.map((provider) => renderProviderCard(provider, "secondary"))}
          </div>
        </section>
      ) : null}

      {revokeTarget ? (
        <div
          className="fix-modal-backdrop"
          role="presentation"
          onClick={() => !revokingKeyId && setRevokeTarget(null)}
        >
          <section
            className="panel keys-revoke-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Revoke provider key"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="panel-header">
              <div>
                <h2>Revoke provider key</h2>
                <p>
                  Replay, evaluation, and provider verification jobs using <strong>{labelForProvider(revokeTarget.provider)}</strong> may stop working until another active key exists.
                </p>
              </div>
            </header>
            <div className="settings-modal-facts">
              <span>Label <strong>{revokeTarget.label ?? "production"}</strong></span>
              <span>Fingerprint <strong className="mono">{keyFingerprint(revokeTarget)}</strong></span>
            </div>
            <div className="actions">
              <button
                type="button"
                className="btn btn-danger"
                disabled={revokingKeyId === revokeTarget.id}
                onClick={() => void onRevokeProviderKey()}
              >
                {revokingKeyId === revokeTarget.id ? "Revoking..." : "Yes, revoke key"}
              </button>
              <button
                type="button"
                className="btn btn-soft"
                disabled={revokingKeyId === revokeTarget.id}
                onClick={() => setRevokeTarget(null)}
              >
                Cancel
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
