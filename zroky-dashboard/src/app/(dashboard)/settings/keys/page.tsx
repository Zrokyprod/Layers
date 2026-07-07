"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Copy,
  Database,
  KeyRound,
  LockKeyhole,
  Plug,
  RotateCcw,
  Terminal,
} from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import {
  SettingsHero,
  SettingsScaffold,
} from "@/components/settings-scaffold";
import { StatusPill } from "@/components/status-pill";
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
import { SDK } from "@/lib/sdk";

const defaultKeyName = "Production verified-action key";
const jsSdkInstall = SDK.install;
const pythonSdkInstall = "pip install zroky";

function configuredApiBaseUrl() {
  return (process.env.NEXT_PUBLIC_ZROKY_API_BASE_URL ?? "https://api.zroky.com").replace(/\/+$/, "");
}

function keyStatus(key: ApiKeyResponse): "revoked" | "expired" | "active" {
  if (key.revoked) return "revoked";
  if (key.expired) return "expired";
  return "active";
}

function keyStatusTone(key: ApiKeyResponse): "success" | "danger" | "neutral" {
  const status = keyStatus(key);
  if (status === "active") return "success";
  if (status === "revoked" || status === "expired") return "danger";
  return "neutral";
}

function keyStatusLabel(key: ApiKeyResponse): string {
  const status = keyStatus(key);
  if (status === "active") return "Active";
  if (status === "expired") return "Expired";
  return "Revoked";
}

function ApiKeysContent() {
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
      const expiryValue = expiresInDays.trim();
      let parsedExpiry: number | null = null;
      if (expiryValue !== "") {
        const numericExpiry = Number(expiryValue);
        if (!Number.isInteger(numericExpiry) || numericExpiry < 1 || numericExpiry > 3650) {
          setStatusMsg("Failed to create key: expiry must be blank or a whole number between 1 and 3650 days.");
          return;
        }
        parsedExpiry = numericExpiry;
      }
      const created = await createMutation.mutateAsync({
        projectId,
        name: data.name.trim(),
        expires_in_days: parsedExpiry,
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
  const revokedKeys = keys.filter((key) => key.revoked);
  const expiredKeys = keys.filter((key) => key.expired);
  const hasActiveKey = activeKeys.length > 0 || newKey !== null;
  const snippetProjectId = projectId || "proj_...";
  const apiBaseUrl = configuredApiBaseUrl();
  const jsSetupSnippet = `${jsSdkInstall}
export ZROKY_PROJECT_ID="${snippetProjectId}"
export ZROKY_API_KEY="${newKey?.api_key ?? "zk_live_..."}"
export ZROKY_API_URL="${apiBaseUrl}"`;
  const pythonSetupSnippet = `${pythonSdkInstall}
export ZROKY_PROJECT_ID="${snippetProjectId}"
export ZROKY_API_KEY="${newKey?.api_key ?? "zk_live_..."}"
export ZROKY_API_URL="${apiBaseUrl}"`;
  const heroTone: "success" | "danger" | "setup" = error ? "danger" : hasActiveKey ? "success" : "setup";
  const runtimePosture = error ? "Needs refresh" : hasActiveKey ? "Runtime ready" : "Setup required";

  const keyTableSection = (
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
        <div className="empty">No project keys yet. Create one to run your first verified action.</div>
      )}

      {!loading && !error && keys.length > 0 && (
        <div className="keys-card-list">
          {keys.map((key) => (
            <article key={key.key_id} className={`keys-card-row is-${keyStatus(key)}`}>
              <div className="keys-card-icon" aria-hidden="true">
                {keyStatus(key) === "active" ? <CheckCircle2 /> : <AlertTriangle />}
              </div>

              <div className="keys-card-main">
                <div className="keys-card-title-row">
                  <strong>{key.name}</strong>
                  <StatusPill value={keyStatus(key)} label={keyStatusLabel(key)} tone={keyStatusTone(key)} />
                </div>
                <div className="keys-card-meta">
                  <span className="mono">{key.key_prefix}...</span>
                  <span>{key.scopes?.join(", ") || "project:member"}</span>
                  <span>Created {formatDateTime(key.created_at)}</span>
                </div>
              </div>

              <div className="keys-card-facts" aria-label={`${key.name} timing`}>
                <span>
                  <small>Expires</small>
                  <strong>{key.expires_at ? formatDateTime(key.expires_at) : "Never"}</strong>
                </span>
                <span>
                  <small>Last used</small>
                  <strong>{key.last_used_at ? formatDateTime(key.last_used_at) : "Never"}</strong>
                </span>
              </div>

              {!key.revoked && !key.expired ? (
                <div className="keys-card-actions">
                  <DashboardButton
                    type="button"
                    size="sm"
                    variant="soft"
                    icon={<RotateCcw />}
                    disabled={rotateMutation.isPending}
                    onClick={() => setRotateTarget(key)}
                  >
                    Rotate
                  </DashboardButton>
                  <DashboardButton type="button" size="sm" variant="danger" onClick={() => setRevokeTarget(key)}>
                    Revoke
                  </DashboardButton>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </section>
  );

  return (
    <SettingsScaffold className="keys-setup-page">
      <SettingsHero
        ariaLabel="API key setup"
        eyebrow="API Keys"
        icon={<KeyRound aria-hidden="true" />}
        title={error ? "API key visibility unavailable" : "Project API keys"}
        copy={
          error
            ? "Project key data did not refresh cleanly. Retry before rotating or revoking keys."
            : "Create and manage project keys for SDK, Gateway, and verified-action calls. Keys do not grant model-provider access."
        }
        tone={heroTone}
        pill={hasActiveKey ? `${activeKeys.length || 1} active` : "No active key"}
        updatedLabel={loading ? "Loading" : "Settings live"}
      />

      <section className="keys-command-card" aria-label="Runtime access command center">
        <div className="keys-command-main">
          <span className="keys-command-kicker">
            <LockKeyhole aria-hidden="true" />
            Runtime access command center
          </span>
          <h2>Project keys let agents reach Zroky without widening human authority.</h2>
          <p>
            Create short-lived runtime credentials, copy the secret once, and rotate or revoke active keys when a runner changes.
          </p>
          <div className="keys-command-rail" aria-label="Runtime key guarantees">
            <span>
              <Terminal aria-hidden="true" />
              SDK runtime only
            </span>
            <span>
              <Database aria-hidden="true" />
              Prefix display only
            </span>
            <span>
              <RotateCcw aria-hidden="true" />
              Rotate without changing project ID
            </span>
          </div>
        </div>

        <aside className="keys-posture-card" aria-label="API key posture">
          <div className="keys-posture-head">
            <span>Key posture</span>
            <strong>{runtimePosture}</strong>
          </div>
          <div className="keys-posture-grid">
            <div>
              <Activity aria-hidden="true" />
              <span>
                <small>Active keys</small>
                <strong>{activeKeys.length}</strong>
              </span>
            </div>
            <div>
              <Clock3 aria-hidden="true" />
              <span>
                <small>Expired keys</small>
                <strong>{expiredKeys.length}</strong>
              </span>
            </div>
            <div>
              <AlertTriangle aria-hidden="true" />
              <span>
                <small>Revoked keys</small>
                <strong>{revokedKeys.length}</strong>
              </span>
            </div>
          </div>
        </aside>
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
            <DashboardButton type="button" variant="primary" icon={<Copy />} onClick={() => void copyKey(newKey.api_key)}>
              {copied ? "Copied" : "Copy key"}
            </DashboardButton>
          </div>
          <div className="keys-next-grid">
            <div>
              <span>Project</span>
              <strong>{newKey.project_id}</strong>
            </div>
            <div>
              <span>Expires</span>
              <strong>{newKey.expires_at ? formatDateTime(newKey.expires_at) : "Never"}</strong>
            </div>
            <div>
              <span>Scope</span>
              <strong>{newKey.scopes.join(", ")}</strong>
            </div>
          </div>
          <div className="keys-command-grid" aria-label="One-time setup commands">
            <pre aria-label="Node SDK environment setup">
              <code>{jsSetupSnippet}</code>
            </pre>
            <pre aria-label="Python SDK environment setup">
              <code>{pythonSetupSnippet}</code>
            </pre>
          </div>
          <div className="keys-copy-actions">
            <DashboardButton type="button" variant="soft" icon={<Copy />} onClick={() => void copyKey(jsSetupSnippet)}>
              Copy Node setup
            </DashboardButton>
            <DashboardButton type="button" variant="soft" icon={<Copy />} onClick={() => void copyKey(pythonSetupSnippet)}>
              Copy Python setup
            </DashboardButton>
            <DashboardButton type="button" variant="soft" onClick={() => setNewKey(null)}>
              Done
            </DashboardButton>
          </div>
        </section>
      )}

      {statusMsg && (
        <p className={statusMsg.toLowerCase().includes("failed") ? "field-error keys-status-msg" : "field-success keys-status-msg"}>
          {statusMsg}
        </p>
      )}

      {hasActiveKey ? keyTableSection : null}

      <section className="keys-primary-grid">
        <article className="panel keys-create-panel" id="create-project-key">
          <header className="panel-header">
            <div>
              <h2>Create project key</h2>
              <p>Use it for the SDK, Gateway, and verified-action calls. It does not grant model-provider access.</p>
            </div>
          </header>

          <form onSubmit={onCreate} className="keys-create-form" noValidate>
            <div className="field settings-key-field keys-keyname-field">
              <label htmlFor="key-name" className="field-label">
                Key name
              </label>
              <input
                id="key-name"
                type="text"
                className="input"
                {...register("name")}
                placeholder="Production verified-action key"
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
            <DashboardButton type="submit" variant="primary" loading={createMutation.isPending} disabled={!projectId}>
              {createMutation.isPending ? "Creating..." : "Create project key"}
            </DashboardButton>
          </form>

          <div className="keys-provider-note">
            <Plug aria-hidden="true" />
            <div>
              <strong>Runtime access only.</strong>
              <span>This key authenticates runtime requests; it does not change policies, verifiers, or model-provider access.</span>
            </div>
          </div>
        </article>

        <aside className="panel keys-setup-card">
          <span className="settings-section-kicker">
            <KeyRound aria-hidden="true" />
            Key rules
          </span>
          <h2>Keep it simple</h2>
          <p>Create a key, copy the secret once, then store it in the agent runtime environment.</p>
          <ul className="keys-compact-list">
            <li>Full secrets are shown once.</li>
            <li>Only prefixes are stored for display.</li>
            <li>Rotate or revoke active keys from the table.</li>
          </ul>
        </aside>
      </section>

      {!hasActiveKey ? keyTableSection : null}

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
              <DashboardButton type="button" variant="danger" loading={revokeMutation.isPending} onClick={onRevoke}>
                {revokeMutation.isPending ? "Revoking..." : "Yes, revoke key"}
              </DashboardButton>
              <DashboardButton
                type="button"
                variant="soft"
                disabled={revokeMutation.isPending}
                onClick={() => setRevokeTarget(null)}
              >
                Cancel
              </DashboardButton>
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
              <DashboardButton type="button" variant="primary" loading={rotateMutation.isPending} onClick={() => void onRotate()}>
                {rotateMutation.isPending ? "Rotating..." : "Rotate and show replacement"}
              </DashboardButton>
              <DashboardButton
                type="button"
                variant="soft"
                disabled={rotateMutation.isPending}
                onClick={() => setRotateTarget(null)}
              >
                Cancel
              </DashboardButton>
            </div>
          </section>
        </div>
      )}
    </SettingsScaffold>
  );
}

export default function ApiKeysPage() {
  return <ApiKeysContent />;
}
