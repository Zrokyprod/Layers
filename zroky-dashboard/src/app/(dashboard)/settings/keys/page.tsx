"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle, Clock3, Copy, KeyRound, RotateCcw, ShieldCheck } from "lucide-react";

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
    defaultValues: { name: "My API Key" },
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
      reset({ name: "My API Key" });
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

  function copyKey(raw: string) {
    navigator.clipboard.writeText(raw).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
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
    <div className="page-content">
      {newKey && (
        <section className="panel keys-newkey-banner">
          <header className="panel-header">
            <div>
              <h3>New API Key Created</h3>
              <p>Copy this key now. It will not be shown again.</p>
            </div>
          </header>
          <div className="share-url-row keys-newkey-row">
            <span className="share-url settings-key-reveal">{newKey.api_key}</span>
            <button type="button" className="btn btn-soft" onClick={() => copyKey(newKey.api_key)}>
              <Copy aria-hidden="true" />
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
          <div className="list">
            <div className="list-row">
              <div className="list-main">
                <strong>Scope</strong>
                <span>{newKey.scopes.join(", ")}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Expires</strong>
                <span>{newKey.expires_at ? formatDateTime(newKey.expires_at) : "Never"}</span>
              </div>
            </div>
          </div>
          <button type="button" className="btn btn-soft" onClick={() => setNewKey(null)}>
            Done
          </button>
        </section>
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
          <small>Rotate unused production keys after rollout.</small>
        </article>
        <article className="panel settings-summary-card">
          <AlertTriangle aria-hidden="true" />
          <span>Expiring soon</span>
          <strong>{expiringSoonKeys}</strong>
          <small>Keys expiring within 14 days need replacement planning.</small>
        </article>
        <article className="panel settings-summary-card">
          <ShieldCheck aria-hidden="true" />
          <span>Scope policy</span>
          <strong>project:member</strong>
          <small>MVP backend accepts one project-scoped role.</small>
        </article>
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Create New API Key</h3>
            <p>Use expiry and rotation so production integrations do not rely on permanent secrets.</p>
          </div>
        </header>

        <form onSubmit={onCreate} className="keys-create-form">
          <div className="field settings-key-field keys-keyname-field">
            <label htmlFor="key-name" className="field-label">Key name</label>
            <input
              id="key-name"
              type="text"
              className="input"
              {...register("name")}
              placeholder="e.g. Production Server"
              disabled={createMutation.isPending || !projectId}
            />
            {errors.name && <span className="field-error">{errors.name.message}</span>}
          </div>
          <div className="field settings-key-field">
            <label htmlFor="key-expiry" className="field-label">Expires in days</label>
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
          <button
            type="submit"
            className="btn btn-primary"
            disabled={createMutation.isPending || !projectId}
          >
            {createMutation.isPending ? "Creating..." : "Create key"}
          </button>
        </form>

        {statusMsg && <p className={statusMsg.includes("failed") || statusMsg.includes("Failed") ? "field-error keys-status-msg" : "field-success keys-status-msg"}>{statusMsg}</p>}
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>API Keys</h3>
            <p>{keys.length} key{keys.length !== 1 ? "s" : ""} for this project.</p>
          </div>
        </header>

        {loading && <div className="loading" />}
        {error && <p className="field-error">{error}</p>}
        {!loading && !error && keys.length === 0 && (
          <div className="empty">No API keys yet. Create one above.</div>
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
                          <button
                            type="button"
                            className="btn btn-danger btn-sm"
                            onClick={() => setRevokeTarget(key)}
                          >
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
                <h3>Revoke API Key</h3>
                <p>
                  This action is irreversible. Requests using <strong>{revokeTarget.name}</strong> will stop working.
                </p>
              </div>
            </header>
            <div className="actions">
              <button
                type="button"
                className="btn btn-danger"
                disabled={revokeMutation.isPending}
                onClick={onRevoke}
              >
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
                <h3>Rotate API Key</h3>
                <p>
                  Zroky will revoke <strong>{rotateTarget.name}</strong> and create a replacement. Copy the replacement before closing the banner.
                </p>
              </div>
            </header>
            <div className="settings-modal-facts">
              <span>Current prefix <strong className="mono">{rotateTarget.key_prefix}...</strong></span>
              <span>Scope <strong>{rotateTarget.scopes?.join(", ") || "project:member"}</strong></span>
            </div>
            <div className="actions">
              <button
                type="button"
                className="btn btn-primary"
                disabled={rotateMutation.isPending}
                onClick={() => void onRotate()}
              >
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
