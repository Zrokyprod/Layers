"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { OwnerPlanGrantModal } from "@/components/owner-plan-grant-modal";
import {
  useAnonymizeOwnerUser,
  useDeleteOwnerUser,
  useOwnerBillingAccounts,
  useOwnerUser,
  useSetUserStatus,
  useUserMemberships,
} from "@/lib/hooks";

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        padding: "9px 0",
        borderBottom: "1px solid var(--line-subtle)",
        alignItems: "flex-start",
      }}
    >
      <span style={{ width: 160, flexShrink: 0, fontSize: "0.8rem", color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ fontSize: "0.82rem", color: "var(--text-primary)", wordBreak: "break-all" }}>{value}</span>
    </div>
  );
}

export default function UserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const userQuery = useOwnerUser(id);
  const membershipsQuery = useUserMemberships(id);
  const toggleMutation = useSetUserStatus();
  const anonymizeMutation = useAnonymizeOwnerUser();
  const deleteMutation = useDeleteOwnerUser();

  const [actionMsg, setActionMsg] = useState("");
  const [grantTarget, setGrantTarget] = useState<{ orgId: string; orgLabel: string } | null>(null);

  const billingQuery = useOwnerBillingAccounts({ limit: 200 });
  const planByOrg = new Map(
    (billingQuery.data?.items ?? []).map((account) => [account.org_id, account]),
  );

  const user = userQuery.data ?? null;
  const memberships = membershipsQuery.data?.memberships ?? [];
  const loading = userQuery.isLoading || membershipsQuery.isLoading;
  const error = userQuery.error?.message ?? membershipsQuery.error?.message ?? "";

  async function handleToggleStatus() {
    if (!user) return;
    setActionMsg("");
    try {
      await toggleMutation.mutateAsync({ userId: user.id, isActive: !user.is_active });
      setActionMsg(`User ${!user.is_active ? "activated" : "suspended"} successfully.`);
    } catch (e: unknown) {
      setActionMsg(`Error: ${(e as Error).message}`);
    }
  }

  async function handleAnonymize() {
    if (!user) return;
    const confirmed = window.prompt(`Type ANONYMIZE ${user.id} to anonymize this user.`);
    if (confirmed !== `ANONYMIZE ${user.id}`) return;
    setActionMsg("");
    try {
      await anonymizeMutation.mutateAsync(user.id);
      setActionMsg("User anonymized successfully.");
    } catch (e: unknown) {
      setActionMsg(`Error: ${(e as Error).message}`);
    }
  }

  async function handleHardDelete() {
    if (!user) return;
    const confirmed = window.prompt(`Type DELETE ${user.id} to hard-delete this user.`);
    if (confirmed !== `DELETE ${user.id}`) return;
    setActionMsg("");
    try {
      await deleteMutation.mutateAsync(user.id);
      window.location.href = "/owner/users";
    } catch (e: unknown) {
      setActionMsg(`Error: ${(e as Error).message}`);
    }
  }

  if (loading) {
    return <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>Loading...</p>;
  }
  if (error) {
    return <div className="alert-strip alert-strip-error">{error}</div>;
  }
  if (!user) return null;

  const loginMethod = user.github_login ? "GitHub" : user.email ? "Email" : "Unknown";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.78rem", color: "var(--text-secondary)" }}>
        <Link href="/owner/users" style={{ color: "var(--accent)", textDecoration: "none" }}>Users</Link>
        <span>/</span>
        <span>{user.email ?? user.github_login ?? user.id}</span>
      </div>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            {user.display_name ?? user.email ?? user.github_login ?? "User"}
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.82rem", marginTop: 4 }}>
            ID: <code style={{ fontFamily: "monospace", fontSize: "0.78rem" }}>{user.id}</code>
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span
            className={user.is_active ? "pill pill-green" : "pill pill-red"}
          >
            {user.is_active ? "Active" : "Suspended"}
          </span>
          <button
            className={user.is_active ? "btn btn-danger" : "btn btn-primary"}
            onClick={handleToggleStatus}
            disabled={toggleMutation.isPending || anonymizeMutation.isPending || deleteMutation.isPending}
            style={{ fontSize: "0.82rem", padding: "7px 16px" }}
          >
            {toggleMutation.isPending ? "Working..." : user.is_active ? "Suspend User" : "Activate User"}
          </button>
        </div>
      </div>

      {actionMsg && (
        <div className={`alert-strip ${actionMsg.startsWith("Error") ? "alert-strip-error" : ""}`}>
          {actionMsg}
        </div>
      )}

      {/* Profile Info */}
      <div className="panel">
        <div className="panel-header">Profile</div>
        <InfoRow label="Email" value={user.email ?? "-"} />
        <InfoRow label="GitHub Login" value={user.github_login ?? "-"} />
        <InfoRow label="Display Name" value={user.display_name ?? "-"} />
        <InfoRow label="Login Method" value={loginMethod} />
        <InfoRow label="Projects" value={user.project_count} />
        <InfoRow
          label="Joined"
          value={new Date(user.created_at).toLocaleString()}
        />
      </div>

      <div className="panel">
        <div className="panel-header">Danger Zone</div>
        <div className="owner-danger-actions">
          <div>
            <strong>Anonymize user</strong>
            <p className="hint">Removes personal identifiers and keeps the audit trail intact.</p>
          </div>
          <button className="btn btn-danger" onClick={handleAnonymize} disabled={anonymizeMutation.isPending || deleteMutation.isPending}>
            {anonymizeMutation.isPending ? "Anonymizing..." : "Anonymize"}
          </button>
          <div>
            <strong>Hard delete user</strong>
            <p className="hint">Deletes the user row after explicit confirmation. Prefer anonymize unless legally required.</p>
          </div>
          <button className="btn btn-danger" onClick={handleHardDelete} disabled={anonymizeMutation.isPending || deleteMutation.isPending}>
            {deleteMutation.isPending ? "Deleting..." : "Hard delete"}
          </button>
        </div>
      </div>

      {/* Memberships */}
      <div className="panel">
        <div className="panel-header">
          Project Memberships
          <span style={{ fontWeight: 400, color: "var(--text-secondary)", marginLeft: 8, fontSize: "0.78rem" }}>
            {memberships.length} project{memberships.length !== 1 ? "s" : ""}
          </span>
        </div>
        {memberships.length === 0 && (
          <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", padding: "12px 0" }}>No project memberships.</p>
        )}
        {memberships.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
            <thead>
              <tr>
                {["Project", "Plan", "Role", "Status", "Joined", "Actions"].map((h) => (
                  <th
                    key={h}
                    style={{
                      textAlign: "left",
                      padding: "8px 10px",
                      borderBottom: "1px solid var(--line-soft)",
                      fontSize: "0.72rem",
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                      color: "var(--text-secondary)",
                      fontWeight: 600,
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {memberships.map((m) => (
                <tr key={m.project_id} style={{ borderBottom: "1px solid var(--line-subtle)" }}>
                  <td style={{ padding: "9px 10px" }}>
                    <Link href={`/owner/projects/${m.project_id}`} style={{ color: "var(--accent)", textDecoration: "none" }}>
                      {m.project_name}
                    </Link>
                  </td>
                  <td style={{ padding: "9px 10px" }}>
                    {(() => {
                      const account = planByOrg.get(m.project_id);
                      if (billingQuery.isLoading) return <span className="owner-cell-muted">…</span>;
                      if (!account) return <span style={{ color: "var(--text-secondary)" }}>—</span>;
                      return (
                        <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                          <span className="owner-money-badge owner-money-badge-neutral" style={{ textTransform: "capitalize" }}>{account.plan_code}</span>
                          <span className={`owner-money-badge owner-money-badge-${account.status === "active" ? "ok" : account.status === "past_due" || account.status === "unpaid" ? "danger" : "warn"}`}>{account.status}</span>
                        </span>
                      );
                    })()}
                  </td>
                  <td style={{ padding: "9px 10px", color: "var(--text-secondary)" }}>{m.role}</td>
                  <td style={{ padding: "9px 10px" }}>
                    <span className={m.is_active ? "pill pill-green" : "pill pill-red"} style={{ fontSize: "0.68rem" }}>
                      {m.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td style={{ padding: "9px 10px", color: "var(--text-secondary)" }}>
                    {new Date(m.joined_at).toLocaleDateString()}
                  </td>
                  <td style={{ padding: "9px 10px" }}>
                    <button
                      className="btn btn-soft"
                      type="button"
                      onClick={() => setGrantTarget({ orgId: m.project_id, orgLabel: m.project_name })}
                      style={{ fontSize: "0.78rem", minHeight: 30, padding: "6px 10px" }}
                    >
                      Change subscription
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {grantTarget && (
        <OwnerPlanGrantModal
          orgId={grantTarget.orgId}
          orgLabel={grantTarget.orgLabel}
          onClose={() => setGrantTarget(null)}
          onGranted={(planCode) => {
            setActionMsg(`Subscription changed for ${grantTarget.orgLabel}: ${planCode}.`);
            setGrantTarget(null);
            void billingQuery.refetch();
          }}
        />
      )}
    </div>
  );
}
