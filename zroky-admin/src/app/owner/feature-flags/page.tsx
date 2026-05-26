"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Plus, Trash2, X } from "lucide-react";

import {
  createFeatureFlag,
  deleteFeatureFlag,
  listFeatureFlags,
  updateFeatureFlag,
} from "@/lib/api";
import type { FeatureFlag } from "@/lib/types";

export default function FeatureFlagsPage() {
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState("");

  const [newKey, setNewKey] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newEnabled, setNewEnabled] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listFeatureFlags();
      setFlags(res.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load feature flags.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newKey.trim()) return;
    setCreateBusy(true);
    setActionMsg("");
    try {
      const flag = await createFeatureFlag({
        key: newKey.trim(),
        description: newDesc.trim() || undefined,
        enabled_globally: newEnabled,
      });
      setFlags((prev) => [...prev, flag]);
      setNewKey("");
      setNewDesc("");
      setNewEnabled(false);
      setActionMsg("Feature flag created.");
    } catch (e: unknown) {
      setActionMsg(e instanceof Error ? e.message : "Failed to create flag.");
    } finally {
      setCreateBusy(false);
    }
  }

  async function toggleGlobal(flag: FeatureFlag) {
    setActionMsg("");
    try {
      const updated = await updateFeatureFlag(flag.id, {
        enabled_globally: !flag.enabled_globally,
      });
      setFlags((prev) => prev.map((f) => (f.id === updated.id ? updated : f)));
      setActionMsg(`Flag "${updated.key}" updated.`);
    } catch (e: unknown) {
      setActionMsg(e instanceof Error ? e.message : "Failed to update flag.");
    }
  }

  async function removeFlag(flagId: string) {
    if (!window.confirm("Delete this feature flag?")) return;
    setActionMsg("");
    try {
      await deleteFeatureFlag(flagId);
      setFlags((prev) => prev.filter((f) => f.id !== flagId));
      setActionMsg("Feature flag deleted.");
    } catch (e: unknown) {
      setActionMsg(e instanceof Error ? e.message : "Failed to delete flag.");
    }
  }

  return (
    <div className="owner-page">
      <div>
        <h2 className="owner-page-title">Feature Flags</h2>
        <p className="hint">Owner-only feature toggles with per-tenant overrides.</p>
      </div>

      {error && <div className="alert-strip alert-strip-error">{error}</div>}
      {actionMsg && (
        <div className={actionMsg.includes("Failed") || actionMsg.includes("error") ? "alert-strip alert-strip-error" : "alert-strip"}>
          {actionMsg}
        </div>
      )}

      {/* Create form */}
      <section className="panel">
        <header className="panel-header">
          <h3>New Feature Flag</h3>
        </header>
        <form onSubmit={onCreate} className="owner-flag-form">
          <div className="field" style={{ minWidth: 220, flex: 1 }}>
            <label className="field-label">Key</label>
            <input
              className="input"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="e.g. new_dashboard_v2"
              required
            />
          </div>
          <div className="field" style={{ minWidth: 260, flex: 2 }}>
            <label className="field-label">Description</label>
            <input
              className="input"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="What does this flag control?"
            />
          </div>
          <label className="owner-flag-checkbox">
            <input type="checkbox" checked={newEnabled} onChange={(e) => setNewEnabled(e.target.checked)} />
            Enabled globally
          </label>
          <button type="submit" className="btn btn-primary" disabled={createBusy || !newKey.trim()}>
            <Plus size={16} style={{ marginRight: 6 }} /> Create
          </button>
        </form>
      </section>

      {/* List */}
      <section className="panel">
        <header className="panel-header">
          <h3>Existing Flags</h3>
        </header>

        {loading ? (
          <p className="hint">Loading…</p>
        ) : flags.length === 0 ? (
          <p className="hint">No feature flags configured.</p>
        ) : (
          <div className="owner-flag-list">
            {flags.map((flag) => (
              <div key={flag.id} className="owner-flag-item">
                <div className="owner-flag-info">
                  <div className="owner-flag-key">{flag.key}</div>
                  {flag.description && (
                    <div className="hint">{flag.description}</div>
                  )}
                  <div className="owner-flag-meta">
                    {flag.enabled_tenants.length > 0 && <span>On for {flag.enabled_tenants.length} tenants · </span>}
                    {flag.disabled_tenants.length > 0 && <span>Off for {flag.disabled_tenants.length} tenants · </span>}
                    Updated {new Date(flag.updated_at).toLocaleDateString()}
                  </div>
                </div>

                <div className="owner-flag-actions">
                  <button
                    type="button"
                    className={flag.enabled_globally ? "btn btn-primary" : "btn btn-soft"}
                    onClick={() => toggleGlobal(flag)}
                    title={flag.enabled_globally ? "Enabled globally" : "Disabled globally"}
                  >
                    {flag.enabled_globally ? (
                      <><Check size={16} style={{ marginRight: 6 }} /> On</>
                    ) : (
                      <><X size={16} style={{ marginRight: 6 }} /> Off</>
                    )}
                  </button>
                  <button type="button" className="btn btn-danger" onClick={() => removeFlag(flag.id)}>
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
