"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { formatDateTime } from "@/lib/format";
import type { ApiKeyCreateResponse, ApiKeyResponse } from "@/lib/types";
import {
  useProjectSettings,
  useListProjectApiKeys,
  useCreateProjectApiKey,
  useRevokeProjectApiKey,
} from "@/lib/hooks";
import { apiKeySchema, type ApiKeyFormData } from "@/lib/schemas";

export default function ApiKeysPage() {
  const projectQuery = useProjectSettings();
  const projectId = projectQuery.data?.project_id ?? "";
  const keysQuery = useListProjectApiKeys(projectId);

  const createMutation = useCreateProjectApiKey();
  const revokeMutation = useRevokeProjectApiKey();

  const [newKey, setNewKey] = useState<ApiKeyCreateResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");

  // Revoke confirmation
  const [revokeTarget, setRevokeTarget] = useState<ApiKeyResponse | null>(null);

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
      const created = await createMutation.mutateAsync({ projectId, name: data.name.trim() });
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
      setRevokeTarget(null);
      setStatusMsg(`Key "${revokeTarget.name}" revoked.`);
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : "Revoke failed.");
      setRevokeTarget(null);
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

  return (
    <div className="page-content">
      {/* New key reveal banner */}
      {newKey && (
        <section className="panel keys-newkey-banner">
          <header className="panel-header">
            <div>
              <h3>New API Key Created</h3>
              <p>Copy this key now — it will not be shown again.</p>
            </div>
          </header>
          <div className="share-url-row keys-newkey-row">
            <span className="share-url settings-key-reveal">{newKey.api_key}</span>
            <button type="button" className="btn btn-soft" onClick={() => copyKey(newKey.api_key)}>
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
          <button type="button" className="btn btn-soft" onClick={() => setNewKey(null)}>
            Done
          </button>
        </section>
      )}

      {/* Create Key */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Create New API Key</h3>
            <p>Give it a descriptive name to identify where it&apos;s used.</p>
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
          <button
            type="submit"
            className="btn btn-primary"
            disabled={createMutation.isPending || !projectId}
          >
            {createMutation.isPending ? "Creating…" : "Create key"}
          </button>
        </form>

        {statusMsg && <p className="field-error keys-status-msg">{statusMsg}</p>}
      </section>

      {/* Keys Table */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>API Keys</h3>
            <p>{keys.length} key{keys.length !== 1 ? "s" : ""} — active keys can make requests on behalf of this project.</p>
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
                  <th>Created</th>
                  <th>Last used</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.key_id} className={k.revoked ? "keys-row-revoked" : ""}>
                    <td>{k.name}</td>
                    <td className="mono">{k.key_prefix}…</td>
                    <td>{formatDateTime(k.created_at)}</td>
                    <td>{k.last_used_at ? formatDateTime(k.last_used_at) : "Never"}</td>
                    <td>
                      {k.revoked
                        ? <span className="pill pill-red">Revoked</span>
                        : <span className="pill pill-green">Active</span>}
                    </td>
                    <td>
                      {!k.revoked && (
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          onClick={() => setRevokeTarget(k)}
                        >
                          Revoke
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

      {/* Revoke Confirmation Modal */}
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
            onClick={(e) => e.stopPropagation()}
          >
            <header className="panel-header">
              <div>
                <h3>Revoke API Key</h3>
                <p>
                  This action is irreversible. Any requests using{" "}
                  <strong>{revokeTarget.name}</strong> will immediately stop working.
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
                {revokeMutation.isPending ? "Revoking…" : "Yes, revoke key"}
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
    </div>
  );
}
