"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { useOwnerUser, useUserMemberships, useSetUserStatus } from "@/lib/hooks";

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

  const [actionMsg, setActionMsg] = useState("");

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

  if (loading) {
    return <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>Loading…</p>;
  }
  if (error) {
    return <div className="alert-strip alert-strip-error">{error}</div>;
  }
  if (!user) return null;

  const provider = user.github_login ? "GitHub" : user.email ? "Email" : "Unknown";

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
            disabled={toggleMutation.isPending}
            style={{ fontSize: "0.82rem", padding: "7px 16px" }}
          >
            {toggleMutation.isPending ? "Working…" : user.is_active ? "Suspend User" : "Activate User"}
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
        <InfoRow label="Email" value={user.email ?? "—"} />
        <InfoRow label="GitHub Login" value={user.github_login ?? "—"} />
        <InfoRow label="Display Name" value={user.display_name ?? "—"} />
        <InfoRow label="Auth Provider" value={provider} />
        <InfoRow label="Projects" value={user.project_count} />
        <InfoRow
          label="Joined"
          value={new Date(user.created_at).toLocaleString()}
        />
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
                {["Project", "Role", "Status", "Joined"].map((h) => (
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
                  <td style={{ padding: "9px 10px", color: "var(--text-secondary)" }}>{m.role}</td>
                  <td style={{ padding: "9px 10px" }}>
                    <span className={m.is_active ? "pill pill-green" : "pill pill-red"} style={{ fontSize: "0.68rem" }}>
                      {m.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td style={{ padding: "9px 10px", color: "var(--text-secondary)" }}>
                    {new Date(m.joined_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
