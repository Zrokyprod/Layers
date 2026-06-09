"use client";

import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Code2,
  Copy,
  KeyRound,
  Plug,
  RotateCcw,
  Route,
  ShieldCheck,
  Terminal,
} from "lucide-react";

import { formatDateTime } from "@/lib/format";
import type { ApiKeyCreateResponse, ApiKeyResponse } from "@/lib/types";
import {
  useProjectSettings,
  useListProjectApiKeys,
  useCreateProjectApiKey,
  useRevokeProjectApiKey,
  useRotateProjectApiKey,
} from "@/lib/hooks";
import { apiKeySchema, type ApiKeyFormData } from "@/lib/schemas";

const defaultKeyName = "Production capture key";
const capturePath = ["Project key", "SDK/Gateway capture", "First trace", "Stub replay", "Verified replay"];

export default function ApiKeysPage() {
  const projectQuery = useProjectSettings();
  const projectId = projectQuery.data?.project_id ?? "";
  const keysQuery = useListProjectApiKeys(projectId);

  const createMutation = useCreateProjectApiKey();
  const revokeMutation = useRevokeProjectApiKey();
  const rotateMutation = useRotateProjectApiKey();

  const [newKey, setNewKey] = useState<ApiKeyCreateResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [expiresInDays, setExpiresInDays] = useState("90");
  const [revokeTarget, setRevokeTarget] = useState<ApiKeyResponse | null>(null);
  const [rotateTarget, setRotateTarget] = useState<ApiKeyResponse | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ApiKeyFormData>({
    resolver: zodResolver(apiKeySchema),
    defaultValues: { name: defaultKeyName },
  });

  const onCreate = handleSubmit(async (data) => {
    if (!projectId) return;
    setStatusMsg("");
    setNewKey(null);
    try {
      const parsedExpiry = expiresInDays.trim() === "" ? null : Number(expiresInDays);
      const created = await createMutation.mutateAsync({
        projectId,
        name: data.name.trim(),
        expires_in_days: Number.isFinite(parsedExpiry ?? 0) ? parsedExpiry : null,
        scopes: ["project:member"],
      });
      setNewKey(created);
      reset({ name: defaultKeyName });
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : "Failed to create key.");
    }
  });

  async function onRevoke() {
    if (!revokeTarget || !projectId) return;
    try {
      await revokeMutation.mutateAsync({ projectId, keyId: revokeTarget.key_id });
      setStatusMsg(`Key "${revokeTarget.name}" revoked.`);
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : "Revoke failed.");
    } finally {
      setRevokeTarget(null);
    }
  }

  async function onRotate() {
    if (!projectId || !rotateTarget) return;
    try {
      const rotated = await rotateMutation.mutateAsync({ projectId, keyId: rotateTarget.key_id });
      setNewKey(rotated);
      setStatusMsg(`Key "${rotateTarget.name}" rotated. Copy the replacement key now.`);
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : "Rotation failed.");
    } finally {
      setRotateTarget(null);
    }
  }

  async function copyKey(raw: string) {
    try {
      await navigator.clipboard.writeText(raw);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setStatusMsg("Copy failed. Select the key and copy it manually.");
    }
  }

  const keys = keysQuery.data ?? [];
  const loading = projectQuery.isLoading || keysQuery.isLoading;
  const error = projectQuery.error?.message ?? keysQuery.error?.message ?? null;
  const activeKeys = keys.filter((key) => !key.revoked && !key.expired);
  const neverUsedKeys = activeKeys.filter((key) => !key.last_used_at).length;
  const expiringSoonKeys = activeKeys.filter((key) => {
    if (!key.expires_at) return false;
    const expiresAt = new Date(key.expires_at).getTime();
    return Number.isFinite(expiresAt) && expiresAt - Date.now() < 14 * 24 * 60 * 60 * 1000;
  }).length;

  return (
    <div className="page-content keys-setup-page">
      <section className="panel keys-setup-hero">
        <div className="keys-hero-copy">
          <span className="settings-section-kicker">
            <KeyRound aria-hidden="true" />
            Capture setup
          </span>
          <h1>Create a project key. Capture your first agent call.</h1>
          <p>
            Project keys send production evidence to Zroky. Provider keys are separate and only used when verified
            replay runs.
          </p>
        </div>
        <div className="keys-hero-actions">
          <Link href="/trace" className="btn btn-primary">
            Confirm first trace
            <ArrowRight aria-hidden="true" />
          </Link>
          <Link href="/settings/providers" className="btn btn-soft">
            Provider keys
          </Link>
        </div>
        <div className="keys-capture-path" aria-label="Project key to verified replay path">
          {capturePath.map((step, index) => (
            <span key={step} className={index === 0 ? "is-current" : undefined}>
              {String(index + 1).padStart(2, "0")}
              <strong>{step}</strong>
            </span>
          ))}
        </div>
      </section>

      {newKey && (
        <section className="panel keys-newkey-banner" aria-label="One-time project key">
          <div className="keys-copy-head">
            <span className="keys-copy-icon">
              <Copy aria-hidden="true" />
            </span>
            <div>
              <h2>Copy this project key now.</h2>
              <p>This secret is shown once. Save it in your runtime environment before closing this panel.</p>
            </div>
          </div>
          <div className="share-url-row keys-newkey-row">
            <span className="share-url settings-key-reveal">{newKey.api_key}</span>
            <button type="button" className="btn btn-primary" onClick={() => void copyKey(newKey.api_key)}>
              <Copy aria-hidden="true" />
              {copied ? "Copied" : "Copy key"}
            </button>
          </div>
          <div className="keys-next-grid">
            <div>
              <span>Scope</span>
              <strong>{newKey.scopes.join(", ")}</strong>
            </div>
            <div>
              <span>Expires</span>
              <strong>{newKey.expires_at ? formatDateTime(newKey.expires_at) : "Never"}</strong>
            </div>
            <div>
              <span>Next step</span>
              <strong>Install SDK or route Gateway traffic.</strong>
            </div>
          </div>
          <div className="keys-copy-actions">
            <Link href="/trace" className="btn btn-soft">
              Confirm first trace
            </Link>
            <button type="button" className="btn btn-soft" onClick={() => setNewKey(null)}>
              Done
            </button>
          </div>
        </section>
      )}

      {statusMsg && (
        <p className={statusMsg.toLowerCase().includes("failed") ? "field-error keys-status-msg" : "field-success keys-status-msg"}>
          {statusMsg}
        </p>
      )}

      <section className="settings-summary-grid">
        <article className="panel settings-summary-card">
          <KeyRound aria-hidden="true" />
          <span>Active keys</span>
          <strong>{activeKeys.length}</strong>
          <small>{keys.length} total including revoked or expired keys.</small>
        </article>
        <article className="panel settings-summary-card">
          <Clock3 aria-hidden="true" />
          <span>Never used</span>
          <strong>{neverUsedKeys}</strong>
          <small>Unused capture keys should be rotated after rollout.</small>
        </article>
        <article className="panel settings-summary-card">
          <AlertTriangle aria-hidden="true" />
          <span>Expiring soon</span>
          <strong>{expiringSoonKeys}</strong>
          <small>Keys expiring within 14 days need replacement planning.</small>
        </article>
        <article className="panel settings-summary-card">
          <ShieldCheck aria-hidden="true" />
          <span>Capture scope</span>
          <strong>project:member</strong>
          <small>Project-scoped evidence capture for SDK and Gateway traffic.</small>
        </article>
      </section>

      <section className="keys-primary-grid">
        <article className="panel keys-create-panel">
          <header className="panel-header">
            <div>
              <h2>Create capture key</h2>
              <p>Use this key in the SDK or Gateway. It does not grant model-provider access.</p>
            </div>
          </header>

          <form onSubmit={onCreate} className="keys-create-form">
            <div className="field settings-key-field keys-keyname-field">
              <label htmlFor="key-name" className="field-label">
                Key name
              </label>
              <input
                id="key-name"
                type="text"
                className="input"
                {...register("name")}
                placeholder="Production capture key"
                disabled={createMutation.isPending || !projectId}
              />
              {errors.name && <span className="field-error">{errors.name.message}</span>}
            </div>
            <div className="field settings-key-field">
              <label htmlFor="key-expiry" className="field-label">
                Expires in days
              </label>
              <input
                id="key-expiry"
                type="number"
                className="input"
                min="1"
                max="3650"
                value={expiresInDays}
                onChange={(event) => setExpiresInDays(event.target.value)}
                placeholder="90"
                disabled={createMutation.isPending || !projectId}
              />
              <span className="field-hint">Leave blank for no automatic expiry. Scope is project:member.</span>
            </div>
            <button type="submit" className="btn btn-primary" disabled={createMutation.isPending || !projectId}>
              {createMutation.isPending ? "Creating..." : "Create project key"}
            </button>
          </form>

          <div className="keys-provider-note">
            <Plug aria-hidden="true" />
            <div>
              <strong>Do not add provider keys for capture.</strong>
              <span>Connect provider keys only for verified replay.</span>
            </div>
            <Link href="/settings/providers" className="btn btn-soft btn-sm">
              Open provider settings
            </Link>
          </div>
        </article>

        <aside className="panel keys-setup-card">
          <span className="settings-section-kicker">
            <Terminal aria-hidden="true" />
            First run
          </span>
          <h2>Start with evidence, not replay.</h2>
          <p>
            Once one call is captured, Zroky can diagnose the issue, run stub replay, and later ask for a provider key
            only when verified replay is needed.
          </p>
          <ol className="keys-checklist">
            {["Create project key", "Install SDK or Gateway", "Run one agent call", "Confirm trace", "Use stub replay"].map((step) => (
              <li key={step}>
                <CheckCircle2 aria-hidden="true" />
                {step}
              </li>
            ))}
          </ol>
        </aside>
      </section>

      <section className="keys-snippet-grid" aria-label="Capture setup snippets">
        <article className="panel keys-snippet-card">
          <div className="keys-snippet-head">
            <Code2 aria-hidden="true" />
            <div>
              <h2>SDK capture</h2>
              <p>Use when you can wrap the model/tool call in application code.</p>
            </div>
          </div>
          <div className="keys-code-grid">
            <pre aria-label="Python SDK project key snippet">
              <code>{`pip install zroky
export ZROKY_API_KEY=zk_live_...

zroky.init()
zroky.call("checkout-agent", input=payload)`}</code>
            </pre>
            <pre aria-label="TypeScript SDK project key snippet">
              <code>{`npm install @zroky/sdk
export ZROKY_API_KEY=zk_live_...

init()
const client = wrap(new OpenAI())`}</code>
            </pre>
          </div>
        </article>

        <article className="panel keys-snippet-card">
          <div className="keys-snippet-head">
            <Route aria-hidden="true" />
            <div>
              <h2>Gateway capture</h2>
              <p>Use when you need evidence without changing agent code first.</p>
            </div>
          </div>
          <pre aria-label="Gateway project key snippet">
            <code>{`docker run -p 8090:8090 \\
  -e ZROKY_API_KEY=zk_live_... \\
  ghcr.io/zroky-ai/zroky-gateway:latest

export OPENAI_BASE_URL=http://localhost:8090/v1`}</code>
          </pre>
        </article>
      </section>

      <section className="panel keys-table-panel">
        <header className="panel-header">
          <div>
            <h2>Project keys</h2>
            <p>{keys.length} key{keys.length !== 1 ? "s" : ""} for this project.</p>
          </div>
        </header>

        {loading && <div className="loading" />}
        {error && <p className="field-error">{error}</p>}
        {!loading && !error && keys.length === 0 && (
          <div className="empty">No project keys yet. Create one to start capturing calls.</div>
        )}

        {!loading && !error && keys.length > 0 && (
          <div className="table-wrap">
            <table className="settings-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Prefix</th>
                  <th>Scope</th>
                  <th>Expires</th>
                  <th>Created</th>
                  <th>Last used</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => (
                  <tr key={key.key_id} className={key.revoked ? "keys-row-revoked" : ""}>
                    <td>{key.name}</td>
                    <td className="mono">{key.key_prefix}...</td>
                    <td>{key.scopes?.join(", ") || "project:member"}</td>
                    <td>{key.expires_at ? formatDateTime(key.expires_at) : "Never"}</td>
                    <td>{formatDateTime(key.created_at)}</td>
                    <td>{key.last_used_at ? formatDateTime(key.last_used_at) : "Never"}</td>
                    <td>
                      {key.revoked ? (
                        <span className="pill pill-red">Revoked</span>
                      ) : key.expired ? (
                        <span className="pill pill-red">Expired</span>
                      ) : (
                        <span className="pill pill-green">Active</span>
                      )}
                    </td>
                    <td>
                      {!key.revoked && !key.expired && (
                        <div className="actions">
                          <button
                            type="button"
                            className="btn btn-soft btn-sm"
                            disabled={rotateMutation.isPending}
                            onClick={() => setRotateTarget(key)}
                          >
                            <RotateCcw aria-hidden="true" />
                            Rotate
                          </button>
                          <button type="button" className="btn btn-danger btn-sm" onClick={() => setRevokeTarget(key)}>
                            Revoke
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {revokeTarget && (
        <div
          className="fix-modal-backdrop"
          role="presentation"
          onClick={() => !revokeMutation.isPending && setRevokeTarget(null)}
        >
          <section
            className="panel keys-revoke-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Revoke API key"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="panel-header">
              <div>
                <h2>Revoke project key</h2>
                <p>
                  This action is irreversible. Requests using <strong>{revokeTarget.name}</strong> will stop working.
                </p>
              </div>
            </header>
            <div className="actions">
              <button type="button" className="btn btn-danger" disabled={revokeMutation.isPending} onClick={onRevoke}>
                {revokeMutation.isPending ? "Revoking..." : "Yes, revoke key"}
              </button>
              <button
                type="button"
                className="btn btn-soft"
                disabled={revokeMutation.isPending}
                onClick={() => setRevokeTarget(null)}
              >
                Cancel
              </button>
            </div>
          </section>
        </div>
      )}

      {rotateTarget && (
        <div
          className="fix-modal-backdrop"
          role="presentation"
          onClick={() => !rotateMutation.isPending && setRotateTarget(null)}
        >
          <section
            className="panel keys-revoke-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Rotate API key"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="panel-header">
              <div>
                <h2>Rotate project key</h2>
                <p>
                  Zroky will revoke <strong>{rotateTarget.name}</strong> and create a replacement. Copy the
                  replacement before closing the banner.
                </p>
              </div>
            </header>
            <div className="settings-modal-facts">
              <span>
                Current prefix <strong className="mono">{rotateTarget.key_prefix}...</strong>
              </span>
              <span>
                Scope <strong>{rotateTarget.scopes?.join(", ") || "project:member"}</strong>
              </span>
            </div>
            <div className="actions">
              <button type="button" className="btn btn-primary" disabled={rotateMutation.isPending} onClick={() => void onRotate()}>
                {rotateMutation.isPending ? "Rotating..." : "Rotate and show replacement"}
              </button>
              <button
                type="button"
                className="btn btn-soft"
                disabled={rotateMutation.isPending}
                onClick={() => setRotateTarget(null)}
              >
                Cancel
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
