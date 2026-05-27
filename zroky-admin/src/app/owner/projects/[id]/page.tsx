"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  useClearProjectRateLimit,
  useOwnerProject,
  useProjectMembers,
  useProjectRateLimit,
  useSetProjectRateLimit,
  useSetProjectStatus,
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
      <span style={{ width: 180, flexShrink: 0, fontSize: "0.8rem", color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ fontSize: "0.82rem", color: "var(--text-primary)", wordBreak: "break-all" }}>{value}</span>
    </div>
  );
}

const usd = (n: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 4 }).format(n);

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const projectQuery = useOwnerProject(id);
  const membersQuery = useProjectMembers(id);
  const rateLimitQuery = useProjectRateLimit(id);
  const toggleMutation = useSetProjectStatus();
  const setRateLimitMutation = useSetProjectRateLimit(id);
  const clearRateLimitMutation = useClearProjectRateLimit(id);

  const [actionMsg, setActionMsg] = useState("");
  const [softLimit, setSoftLimit] = useState("");
  const [burstLimit, setBurstLimit] = useState("");
  const [enforceLimit, setEnforceLimit] = useState(false);

  const project = projectQuery.data ?? null;
  const members = membersQuery.data?.members ?? [];
  const loading = projectQuery.isLoading || membersQuery.isLoading;
  const error = projectQuery.error?.message ?? membersQuery.error?.message ?? "";

  useEffect(() => {
    const overrides = rateLimitQuery.data?.overrides;
    if (!overrides) return;
    setSoftLimit(String(overrides.ingest_soft_limit_rpm ?? ""));
    setBurstLimit(String(overrides.ingest_burst_limit_rpm ?? ""));
    setEnforceLimit(Boolean(overrides.ingest_enforce_rate_limit));
  }, [rateLimitQuery.data?.overrides]);

  async function handleToggleStatus() {
    if (!project) return;
    setActionMsg("");
    try {
      await toggleMutation.mutateAsync({ projectId: project.id, isActive: !project.is_active });
      setActionMsg(`Project ${!project.is_active ? "activated" : "suspended"} successfully.`);
    } catch (e: unknown) {
      setActionMsg(`Error: ${(e as Error).message}`);
    }
  }

  async function handleSaveRateLimit() {
    setActionMsg("");
    try {
      await setRateLimitMutation.mutateAsync({
        ingest_soft_limit_rpm: softLimit.trim() ? Number(softLimit) : undefined,
        ingest_burst_limit_rpm: burstLimit.trim() ? Number(burstLimit) : undefined,
        ingest_enforce_rate_limit: enforceLimit,
      });
      setActionMsg("Project rate limit saved.");
    } catch (e: unknown) {
      setActionMsg(`Error: ${(e as Error).message}`);
    }
  }

  async function handleClearRateLimit() {
    if (!window.confirm("Clear project-specific rate limit overrides?")) return;
    setActionMsg("");
    try {
      await clearRateLimitMutation.mutateAsync();
      setSoftLimit("");
      setBurstLimit("");
      setEnforceLimit(false);
      setActionMsg("Project rate limit override cleared.");
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
  if (!project) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.78rem", color: "var(--text-secondary)" }}>
        <Link href="/owner/projects" style={{ color: "var(--accent)", textDecoration: "none" }}>Projects</Link>
        <span>/</span>
        <span>{project.name}</span>
      </div>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            {project.name}
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.82rem", marginTop: 4 }}>
            ID: <code style={{ fontFamily: "monospace", fontSize: "0.78rem" }}>{project.id}</code>
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span className={project.is_active ? "pill pill-green" : "pill pill-red"}>
            {project.is_active ? "Active" : "Suspended"}
          </span>
          <button
            className={project.is_active ? "btn btn-danger" : "btn btn-primary"}
            onClick={handleToggleStatus}
            disabled={toggleMutation.isPending}
            style={{ fontSize: "0.82rem", padding: "7px 16px" }}
          >
            {toggleMutation.isPending ? "Working..." : project.is_active ? "Suspend Project" : "Activate Project"}
          </button>
        </div>
      </div>

      {actionMsg && (
        <div className={`alert-strip ${actionMsg.startsWith("Error") ? "alert-strip-error" : ""}`}>
          {actionMsg}
        </div>
      )}

      {/* Stats */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
          gap: 14,
        }}
      >
        {[
          { label: "Total Calls", value: project.call_count.toLocaleString() },
          { label: "Total Cost (USD)", value: usd(project.total_cost_usd) },
          { label: "Members", value: project.member_count },
        ].map((s) => (
          <div
            key={s.label}
            style={{
              background: "var(--bg-panel)",
              border: "1px solid var(--line-soft)",
              borderRadius: "var(--radius-md)",
              padding: "16px 18px",
              display: "flex",
              flexDirection: "column",
              gap: 4,
            }}
          >
            <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
              {s.label}
            </span>
            <span style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--text-primary)", lineHeight: 1.2 }}>
              {s.value}
            </span>
          </div>
        ))}
      </div>

      {/* Project Info */}
      <div className="panel">
        <div className="panel-header">Project Details</div>
        <InfoRow label="Project ID" value={<code style={{ fontFamily: "monospace", fontSize: "0.78rem" }}>{project.id}</code>} />
        <InfoRow label="Name" value={project.name} />
        <InfoRow label="Owner Ref" value={project.owner_ref ?? "-"} />
        <InfoRow label="Status" value={project.is_active ? "Active" : "Suspended"} />
        <InfoRow label="Created" value={new Date(project.created_at).toLocaleString()} />
      </div>

      <div className="panel">
        <div className="panel-header">
          Project Rate Limits
          <span className="panel-header-note">
            {rateLimitQuery.data?.has_override ? "Override active" : "Using global defaults"}
          </span>
        </div>
        <div className="owner-project-rate-grid">
          <label className="field">
            <span className="field-label">Soft RPM</span>
            <input
              className="input"
              inputMode="numeric"
              value={softLimit}
              onChange={(event) => setSoftLimit(event.target.value)}
              placeholder="global default"
            />
          </label>
          <label className="field">
            <span className="field-label">Burst RPM</span>
            <input
              className="input"
              inputMode="numeric"
              value={burstLimit}
              onChange={(event) => setBurstLimit(event.target.value)}
              placeholder="global default"
            />
          </label>
          <label className="owner-flag-checkbox">
            <input
              type="checkbox"
              checked={enforceLimit}
              onChange={(event) => setEnforceLimit(event.target.checked)}
            />
            Enforce project limit
          </label>
          <div className="owner-project-rate-actions">
            <button className="btn btn-primary" onClick={handleSaveRateLimit} disabled={setRateLimitMutation.isPending}>
              {setRateLimitMutation.isPending ? "Saving..." : "Save override"}
            </button>
            <button className="btn btn-soft" onClick={handleClearRateLimit} disabled={clearRateLimitMutation.isPending}>
              {clearRateLimitMutation.isPending ? "Clearing..." : "Clear override"}
            </button>
          </div>
        </div>
      </div>

      {/* Members */}
      <div className="panel">
        <div className="panel-header">
          Members
          <span style={{ fontWeight: 400, color: "var(--text-secondary)", marginLeft: 8, fontSize: "0.78rem" }}>
            {members.length} member{members.length !== 1 ? "s" : ""}
          </span>
        </div>
        {members.length === 0 && (
          <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", padding: "12px 0" }}>No members found.</p>
        )}
        {members.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
            <thead>
              <tr>
                {["User", "Role", "Status", "Joined"].map((h) => (
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
              {members.map((m) => (
                <tr key={m.membership_id} style={{ borderBottom: "1px solid var(--line-subtle)" }}>
                  <td style={{ padding: "9px 10px" }}>
                    <Link href={`/owner/users/${m.user_id}`} style={{ color: "var(--accent)", textDecoration: "none" }}>
                      {m.email ?? m.github_login ?? m.display_name ?? m.user_id}
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
