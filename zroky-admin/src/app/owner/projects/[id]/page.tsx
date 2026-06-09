"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertTriangle, ArrowRight, GitBranch, KeyRound, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  useClearProjectRateLimit,
  useOwnerMoneyPathHealth,
  useOwnerProject,
  useProjectMembers,
  useProjectRateLimit,
  useSetProjectRateLimit,
  useSetProjectStatus,
} from "@/lib/hooks";
import type { OwnerMoneyPathTenantRow } from "@/lib/owner-api";

type Tone = "ok" | "warn" | "danger" | "neutral";

const ACTION_LABELS: Record<string, string> = {
  review_blocked_ci: "Review blocked CI",
  restore_capture: "Restore capture",
  connect_provider_key: "Connect provider key",
  review_replay_quota: "Review replay quota",
  run_replay: "Run replay",
  promote_golden: "Promote Golden",
  run_ci_gate: "Run CI gate",
  continue_triage: "Continue triage",
  monitor: "Monitor",
};

function InfoRow({ label, value }: { label: string; value: ReactNode }) {
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

function fmtCount(value: number): string {
  return value.toLocaleString();
}

function fmtDate(value: string | null): string {
  if (!value) return "No recent capture";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Invalid timestamp";
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action.replaceAll("_", " ");
}

function stateTone(state: string): Tone {
  if (["passed", "configured", "ok", "unlimited", "monitor"].includes(state)) return "ok";
  if (["failed", "down", "error", "exceeded", "blocked", "missing"].includes(state)) return "danger";
  if (["partial", "running", "near_limit", "disabled", "not_configured"].includes(state)) return "warn";
  return "neutral";
}

function actionTone(action: string): Tone {
  if (["review_blocked_ci", "restore_capture"].includes(action)) return "danger";
  if (["connect_provider_key", "review_replay_quota", "run_replay", "promote_golden", "run_ci_gate"].includes(action)) return "warn";
  if (action === "monitor") return "ok";
  return "neutral";
}

function loopTone(tenant: OwnerMoneyPathTenantRow, step: string): Tone {
  if (step === "capture") return tenant.captures_24h > 0 ? "ok" : "danger";
  if (step === "issue") return tenant.open_issue_count > 0 ? "danger" : "ok";
  if (step === "replay") {
    if (tenant.verified_replay_count_7d > 0) return "ok";
    if (tenant.replay_run_count_7d > 0) return "warn";
    return tenant.open_issue_count > 0 ? "danger" : "neutral";
  }
  if (step === "golden") {
    if (tenant.golden_trace_count > 0) return "ok";
    return tenant.verified_replay_count_7d > 0 ? "warn" : "neutral";
  }
  if (step === "ci") {
    if (tenant.blocking_ci_failures_7d > 0) return "danger";
    if (tenant.ci_run_count_7d > 0) return "ok";
    return tenant.golden_trace_count > 0 ? "warn" : "neutral";
  }
  return "neutral";
}

function quotaText(tenant: OwnerMoneyPathTenantRow): string {
  if (tenant.replay_quota_status.limit === -1) return `${fmtCount(tenant.replay_quota_status.used)} used`;
  return `${fmtCount(tenant.replay_quota_status.used)} / ${fmtCount(tenant.replay_quota_status.limit)}`;
}

function StatusBadge({ value, tone }: { value: string; tone?: Tone }) {
  const resolved = tone ?? stateTone(value);
  return <span className={`owner-money-badge owner-money-badge-${resolved}`}>{value.replaceAll("_", " ")}</span>;
}

function EvidenceItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="owner-money-proof-item">
      <span>{label}</span>
      <code>{value}</code>
    </div>
  );
}

function TenantLoopEvidence({ tenant }: { tenant: OwnerMoneyPathTenantRow }) {
  const steps = [
    { id: "capture", label: "Capture", value: `${fmtCount(tenant.captures_24h)} in 24h`, detail: fmtDate(tenant.last_capture_at) },
    { id: "issue", label: "Issue", value: `${fmtCount(tenant.open_issue_count)} open`, detail: tenant.open_issue_count ? "triage required" : "no open issue" },
    { id: "replay", label: "Replay", value: `${fmtCount(tenant.replay_run_count_7d)} runs`, detail: `${fmtCount(tenant.verified_replay_count_7d)} verified` },
    { id: "golden", label: "Golden", value: `${fmtCount(tenant.golden_trace_count)} active`, detail: tenant.golden_trace_count ? "CI eligible" : "no active trace" },
    { id: "ci", label: "CI Gate", value: `${fmtCount(tenant.ci_run_count_7d)} runs`, detail: `${fmtCount(tenant.blocking_ci_failures_7d)} blocked` },
  ];

  return (
    <div className="owner-money-tenant-loop">
      {steps.map((step) => (
        <div key={step.id} className={`owner-money-tenant-step owner-money-badge-${loopTone(tenant, step.id)}`}>
          <span>{step.label}</span>
          <strong>{step.value}</strong>
          <small>{step.detail}</small>
        </div>
      ))}
    </div>
  );
}

function ProductIntelligencePanel({
  tenant,
  error,
  loading,
}: {
  tenant: OwnerMoneyPathTenantRow | null;
  error: string;
  loading: boolean;
}) {
  if (error) {
    return (
      <div className="panel owner-project-intel-panel">
        <div className="panel-header">
          Regression Firewall
          <span className="panel-header-note">Backend money-path health unavailable</span>
        </div>
        <div className="owner-project-intel-body">
          <div className="alert-strip alert-strip-error">{error}</div>
        </div>
      </div>
    );
  }

  if (loading && !tenant) {
    return (
      <div className="panel owner-project-intel-panel">
        <div className="panel-header">Regression Firewall</div>
        <div className="owner-project-intel-empty">
          <ShieldCheck size={20} aria-hidden="true" />
          <p>Loading tenant money-path evidence...</p>
        </div>
      </div>
    );
  }

  if (!tenant) {
    return (
      <div className="panel owner-project-intel-panel">
        <div className="panel-header">
          Regression Firewall
          <span className="panel-header-note">No backend row for this tenant</span>
        </div>
        <div className="owner-project-intel-empty">
          <AlertTriangle size={20} aria-hidden="true" />
          <p>No regression-firewall health row exists for this tenant.</p>
          <Link href="/owner/money-path" className="btn btn-soft">
            <GitBranch size={15} aria-hidden="true" />
            Money path
          </Link>
        </div>
      </div>
    );
  }

  const providerValue = `${tenant.provider_key_status.state} (${tenant.provider_key_status.active_provider_count})`;

  return (
    <div className="panel owner-project-intel-panel">
      <div className="panel-header">
        <span>Regression Firewall</span>
        <StatusBadge value={actionLabel(tenant.next_owner_action)} tone={actionTone(tenant.next_owner_action)} />
      </div>
      <div className="owner-project-intel-body">
        <div className="owner-project-intel-grid">
          <div className="owner-project-intel-card">
            <span className="owner-stat-label">Open Issues</span>
            <strong>{fmtCount(tenant.open_issue_count)}</strong>
            <p>{tenant.open_issue_count ? "Failure groups still need replay proof." : "No open issue reported by backend."}</p>
          </div>
          <div className="owner-project-intel-card">
            <span className="owner-stat-label">Verified Replay</span>
            <strong>{fmtCount(tenant.verified_replay_count_7d)}</strong>
            <p>{fmtCount(tenant.replay_run_count_7d)} total replay run(s) in 7 days.</p>
          </div>
          <div className="owner-project-intel-card">
            <span className="owner-stat-label">Goldens</span>
            <strong>{fmtCount(tenant.golden_trace_count)}</strong>
            <p>{tenant.golden_trace_count ? "Active Golden trace available for CI." : "No active Golden trace yet."}</p>
          </div>
          <div className="owner-project-intel-card">
            <span className="owner-stat-label">CI Gate</span>
            <strong>{fmtCount(tenant.ci_run_count_7d)}</strong>
            <p>{fmtCount(tenant.blocking_ci_failures_7d)} blocking failure(s) in 7 days.</p>
          </div>
        </div>

        <TenantLoopEvidence tenant={tenant} />

        <div className="owner-project-intel-proof">
          <div className="owner-money-proof-grid">
            <EvidenceItem label="Project Plan" value={tenant.plan_code} />
            <EvidenceItem label="Last Capture" value={fmtDate(tenant.last_capture_at)} />
            <EvidenceItem label="Provider Keys" value={providerValue} />
            <EvidenceItem label="Replay Quota" value={quotaText(tenant)} />
          </div>
          <div className="owner-project-intel-actions">
            <div className="owner-project-intel-action-copy">
              <KeyRound size={16} aria-hidden="true" />
              <span>
                Provider key is <StatusBadge value={tenant.provider_key_status.state} /> and replay quota is{" "}
                <StatusBadge value={tenant.replay_quota_status.state} />.
              </span>
            </div>
            <div className="owner-project-intel-action-links">
              <Link href="/owner/money-path" className="btn btn-soft">
                <GitBranch size={15} aria-hidden="true" />
                Money path
              </Link>
              <Link href="/owner/pricing" className="btn btn-soft">
                Entitlements
              </Link>
              <Link href="/owner/rate-limits" className="btn btn-soft">
                Rate limits
                <ArrowRight size={14} aria-hidden="true" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const projectQuery = useOwnerProject(id);
  const membersQuery = useProjectMembers(id);
  const rateLimitQuery = useProjectRateLimit(id);
  const moneyPathQuery = useOwnerMoneyPathHealth();
  const toggleMutation = useSetProjectStatus();
  const setRateLimitMutation = useSetProjectRateLimit(id);
  const clearRateLimitMutation = useClearProjectRateLimit(id);

  const [actionMsg, setActionMsg] = useState("");
  const [softLimit, setSoftLimit] = useState("");
  const [burstLimit, setBurstLimit] = useState("");
  const [enforceLimit, setEnforceLimit] = useState(false);

  const project = projectQuery.data ?? null;
  const members = membersQuery.data?.members ?? [];
  const tenantHealth = useMemo(
    () => moneyPathQuery.data?.tenants.find((tenant) => tenant.project_id === id) ?? null,
    [id, moneyPathQuery.data?.tenants],
  );
  const loading = projectQuery.isLoading || membersQuery.isLoading;
  const error = projectQuery.error?.message ?? membersQuery.error?.message ?? "";
  const moneyPathError = moneyPathQuery.error?.message ?? "";

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
    <div className="owner-page owner-project-detail-page">
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

      <ProductIntelligencePanel
        tenant={tenantHealth}
        error={moneyPathError}
        loading={moneyPathQuery.isLoading}
      />

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
