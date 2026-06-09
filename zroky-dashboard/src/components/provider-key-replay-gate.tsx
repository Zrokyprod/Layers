"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";
import { KeyRound, ShieldCheck } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { createProviderKey } from "@/lib/api";
import { PROVIDER_KEY_OPTIONS, PROVIDER_KEY_QUERY_KEY } from "@/lib/provider-key-gate";

type ProviderKeyReplayGateProps = {
  onClose?: () => void;
  onSavedAndRun: () => void | Promise<void>;
  onUseStub?: () => void;
  showUseStub?: boolean;
};

export function ProviderKeyReplayGate({
  onClose,
  onSavedAndRun,
  onUseStub,
  showUseStub = true,
}: ProviderKeyReplayGateProps) {
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState("openai");
  const [label, setLabel] = useState("production");
  const [plaintextKey, setPlaintextKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await createProviderKey({
        provider,
        plaintext_key: plaintextKey,
        label: label.trim() || null,
      });
      setPlaintextKey("");
      await queryClient.invalidateQueries({ queryKey: PROVIDER_KEY_QUERY_KEY });
      await onSavedAndRun();
      onClose?.();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Failed to save provider key.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel provider-key-replay-gate" role="dialog" aria-label="Connect provider key">
      <header className="panel-header">
        <div>
          <div className="provider-key-gate-eyebrow">
            <KeyRound aria-hidden="true" />
            BYOK replay
          </div>
          <h3>Connect your provider key to run verified replay.</h3>
          <p>Capture works without a key. Verified replay uses your provider account so model spend stays visible.</p>
        </div>
        {onClose ? (
          <button type="button" className="btn btn-soft btn-sm" onClick={onClose} disabled={saving}>
            Dismiss
          </button>
        ) : null}
      </header>

      <form className="provider-key-gate-form" onSubmit={onSubmit}>
        <label className="detail-field">
          <span className="detail-field-label">Provider</span>
          <select className="input" value={provider} onChange={(event) => setProvider(event.target.value)} disabled={saving}>
            {PROVIDER_KEY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="detail-field">
          <span className="detail-field-label">Label</span>
          <input className="input" value={label} onChange={(event) => setLabel(event.target.value)} placeholder="production" disabled={saving} />
        </label>
        <label className="detail-field provider-key-gate-key-field">
          <span className="detail-field-label">API key</span>
          <input
            className="input"
            type="password"
            value={plaintextKey}
            onChange={(event) => setPlaintextKey(event.target.value)}
            placeholder="Paste provider API key"
            disabled={saving}
          />
        </label>

        {error ? <p className="field-error provider-key-gate-error">{error}</p> : null}

        <div className="provider-key-gate-actions">
          <button type="submit" className="btn btn-primary" disabled={saving || plaintextKey.trim().length < 8}>
            <ShieldCheck aria-hidden="true" />
            {saving ? "Saving..." : "Save key and run replay"}
          </button>
          {showUseStub && onUseStub ? (
            <button type="button" className="btn btn-soft" onClick={onUseStub} disabled={saving}>
              Use stub replay
            </button>
          ) : null}
          <Link href="/settings/providers" className="btn btn-soft">
            Open provider settings
          </Link>
        </div>
      </form>
    </section>
  );
}
