"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertTriangle, ArrowRight, BadgeDollarSign, GitBranch, KeyRound, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { OwnerPlanGrantModal } from "@/components/owner-plan-grant-modal";
import {
  useClearProjectRateLimit,
  useOwnerMoneyPathHealth,
  useOwnerProject,
  useProjectMembers,
  useProjectRateLimit,
  useSetProjectRateLimit,
  useSetProjectStatus,
} from "@/lib/hooks";
import type { OwnerMoneyPathTenantRow, OwnerProjectItem } from "@/lib/owner-api";

type Tone = "ok" | "warn" | "danger" | "neutral";

const ACTION_LABELS: Record<string, string> = {
  review_blocked_ci: "Review release block",
  restore_capture: "Restore action intake",
  connect_provider_key: "Connect connector key",
  review_replay_quota: "Review proof quota",
  review_event_quota: "Review event quota",
  restore_replay_worker: "Restore proof worker",
  fix_metering: "Fix metering",
  refresh_pricing: "Refresh pricing",
  fix_billing: "Fix billing",
  review_support: "Review support",
  run_replay: "Run proof check",
  promote_golden: "Promote receipt baseline",
  run_ci_gate: "Run release check",
  continue_triage: "Continue triage",
  monitor: "Monitor",
};

function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="owner-info-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

const usd = (n: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 4 }).format(n);

function fmtCount(value: number): string {
  return value.toLocaleString();
}

function fmtDate(value: string | null): string {
  if (!value) return "No recent action";
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
  if (["pass", "passed", "verified", "configured", "ok", "unlimited", "monitor", "active"].includes(state)) return "ok";
  if (["fail", "failed", "down", "error", "exceeded", "blocked", "missing", "risk", "urgent", "failure", "canceled", "incomplete"].includes(state)) return "danger";
  if (["partial", "running", "near_limit", "disabled", "not_configured", "not_verified", "stale", "fallback", "open", "missing_paid", "past_due"].includes(state)) return "warn";
  return "neutral";
}

function actionTone(action: string): Tone {
  if (["review_blocked_ci", "restore_capture", "restore_replay_worker", "fix_billing", "fix_metering"].includes(action)) return "danger";
  if (["connect_provider_key", "review_replay_quota", "review_event_quota", "review_support", "refresh_pricing", "run_replay", "promote_golden", "run_ci_gate"].includes(action)) return "warn";
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

function breakLabel(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\bprovider\b/gi, "connector")
    .replace(/\breplay\b/gi, "proof")
    .replace(/\bgolden\b/gi, "receipt baseline")
    .replace(/\bci\b/gi, "release");
}

function eventMeteringText(tenant: OwnerMoneyPathTenantRow): string {
  const metering = tenant.event_metering_status;
  if (!metering) return "No event-metering proof";
  if (metering.limit == null) return `${fmtCount(metering.used)} used`;
  return `${fmtCount(metering.used)} / ${fmtCount(metering.limit)}`;
}

function pricingDetail(tenant: OwnerMoneyPathTenantRow): string {
  const pricing = tenant.pricing_cost_status;
  if (!pricing) return "No pricing evidence";
  if (pricing.pricing_age_days == null) return pricing.detail ?? "No pricing age";
  return `${pricing.pricing_age_days}d age - ${pricing.cost_confidence ?? "unknown confidence"}`;
}

function billingDetail(tenant: OwnerMoneyPathTenantRow): string {
  const billing = tenant.billing_status;
  if (!billing) return "No billing row";
  return billing.subscription_status ?? billing.plan_code;
}

function supportDetail(tenant: OwnerMoneyPathTenantRow): string {
  const support = tenant.support_status;
  if (!support) return "No support status";
  return `${fmtCount(support.open_count)} open / ${fmtCount(support.urgent_count)} urgent`;
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
    { id: "capture", label: "Protected actions", value: `${fmtCount(tenant.captures_24h)} in 24h`, detail: fmtDate(tenant.last_capture_at) },
    { id: "issue", label: "Issue", value: `${fmtCount(tenant.open_issue_count)} open`, detail: tenant.open_issue_count ? "triage required" : "no open issue" },
    { id: "replay", label: "Proof checks", value: `${fmtCount(tenant.replay_run_count_7d)} runs`, detail: `${fmtCount(tenant.verified_replay_count_7d)} verified` },
    { id: "golden", label: "Receipt baseline", value: `${fmtCount(tenant.golden_trace_count)} active`, detail: tenant.golden_trace_count ? "release eligible" : "no baseline yet" },
    { id: "ci", label: "Release checks", value: `${fmtCount(tenant.ci_run_count_7d)} runs`, detail: `${fmtCount(tenant.blocking_ci_failures_7d)} blocked` },
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

function CommercialSignal({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail: string;
  tone?: Tone;
}) {
  return (
    <div className={`owner-project-signal-card owner-project-signal-${tone ?? stateTone(value)}`}>
      <span>{label}</span>
      <strong>{value.replaceAll("_", " ")}</strong>
      <small>{detail}</small>
    </div>
  );
}

function sdkSignal(tenant: OwnerMoneyPathTenantRow | null): { value: string; detail: string; tone: Tone } {
  if (!tenant) return { value: "No health row", detail: "No protected-action row yet.", tone: "warn" };
  if (!tenant.last_capture_at || tenant.captures_24h === 0) {
    return { value: "No actions", detail: fmtDate(tenant.last_capture_at), tone: "danger" };
  }
  return { value: "Active", detail: `${fmtCount(tenant.captures_24h)} protected actions in 24h.`, tone: "ok" };
}

function proofSignal(tenant: OwnerMoneyPathTenantRow | null): { value: string; detail: string; tone: Tone } {
  if (!tenant) return { value: "Proof state missing", detail: "Backend has no proof state.", tone: "warn" };
  if (tenant.verified_replay_count_7d > 0 && tenant.golden_trace_count > 0) {
    return {
      value: "Verified",
      detail: `${fmtCount(tenant.verified_replay_count_7d)} verified, ${fmtCount(tenant.golden_trace_count)} receipt baseline.`,
      tone: "ok",
    };
  }
  if (tenant.blocking_ci_failures_7d > 0) {
    return { value: "Release risk", detail: `${fmtCount(tenant.blocking_ci_failures_7d)} blocking failure(s).`, tone: "danger" };
  }
  return { value: "Proof missing", detail: `${fmtCount(tenant.replay_run_count_7d)} proof check(s).`, tone: tenant.open_issue_count > 0 ? "warn" : "neutral" };
}

function customerStatus(project: OwnerProjectItem, tenant: OwnerMoneyPathTenantRow | null): { value: string; detail: string; tone: Tone } {
  if (!project.is_active) return { value: "Suspended", detail: "Customer access is disabled.", tone: "danger" };
  if (!tenant) return { value: "No health row", detail: "Backend has not reported customer health.", tone: "warn" };
  if (!tenant.last_capture_at || tenant.captures_24h === 0) return { value: "Needs action", detail: "No recent protected actions.", tone: "danger" };
  if (tenant.provider_key_status.state === "missing") return { value: "Needs action", detail: "Connector key missing.", tone: "danger" };
  if (["risk", "missing_paid", "unknown"].includes(tenant.billing_status?.state ?? "")) return { value: "Needs action", detail: "Billing risk.", tone: "danger" };
  if (["near_limit", "exceeded"].includes(tenant.replay_quota_status.state)) return { value: "Needs action", detail: "Proof quota risk.", tone: "warn" };
  if (tenant.open_issue_count > 0 || tenant.blocking_ci_failures_7d > 0) return { value: "Needs action", detail: actionLabel(tenant.next_owner_action), tone: "warn" };
  if (tenant.next_owner_action !== "monitor") return { value: "Review", detail: actionLabel(tenant.next_owner_action), tone: "warn" };
  return { value: "Live", detail: "No owner action queued.", tone: "ok" };
}

function Customer360Summary({
  project,
  tenant,
  memberCount,
}: {
  project: OwnerProjectItem;
  tenant: OwnerMoneyPathTenantRow | null;
  memberCount: number;
}) {
  const status = customerStatus(project, tenant);
  const sdk = sdkSignal(tenant);
  const proof = proofSignal(tenant);
  const connectorValue = tenant?.provider_key_status.state ?? "unknown";
  const connectorDetail = tenant
    ? `${fmtCount(tenant.provider_key_status.active_provider_count)} active connector key(s).`
    : "No connector health row.";
  const quotaValue = tenant?.replay_quota_status.state ?? "unknown";
  const quotaDetail = tenant ? quotaText(tenant) : "No quota row.";
  const planValue = tenant?.plan_code ?? "unknown";
  const planDetail = tenant ? billingDetail(tenant) : "No billing row.";

  return (
    <section className="panel owner-customer-summary-panel">
      <div className="panel-header">
        <div>
          <h3>Customer live state</h3>
          <span className="panel-header-note">Simple status from protected actions, connectors, proof quota, billing, and support rows.</span>
        </div>
        <StatusBadge value={status.value} tone={status.tone} />
      </div>
      <div className="owner-customer-summary-grid">
        <CommercialSignal label="Customer status" value={status.value} detail={status.detail} tone={status.tone} />
        <CommercialSignal label="Plan & subscription" value={planValue} detail={planDetail} tone={stateTone(planValue)} />
        <CommercialSignal label="Action intake" value={sdk.value} detail={sdk.detail} tone={sdk.tone} />
        <CommercialSignal label="Connector health" value={connectorValue} detail={connectorDetail} tone={stateTone(connectorValue)} />
        <CommercialSignal label="Proof quota" value={quotaValue} detail={quotaDetail} tone={stateTone(quotaValue)} />
        <CommercialSignal label="Proof" value={proof.value} detail={proof.detail} tone={proof.tone} />
        <CommercialSignal label="Support" value={tenant?.support_status?.state ?? "none"} detail={tenant ? supportDetail(tenant) : "No support row."} tone={stateTone(tenant?.support_status?.state ?? "none")} />
        <CommercialSignal label="Users" value={fmtCount(memberCount)} detail="Active account members loaded for this tenant." tone={memberCount > 0 ? "ok" : "warn"} />
      </div>
    </section>
  );
}

function TenantProofLedger({
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
          Tenant proof ledger
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
        <div className="panel-header">Tenant proof ledger</div>
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
          Tenant proof ledger
          <span className="panel-header-note">No backend row for this tenant</span>
        </div>
        <div className="owner-project-intel-empty">
          <AlertTriangle size={20} aria-hidden="true" />
          <p>No customer health row exists for this tenant.</p>
          <Link href="/owner/money-path" className="btn btn-soft">
            <GitBranch size={15} aria-hidden="true" />
            Money path
          </Link>
        </div>
      </div>
    );
  }

  const providerValue = `${tenant.provider_key_status.state} (${tenant.provider_key_status.active_provider_count})`;
  const breaks = tenant.money_path_breaks ?? tenant.launch_blockers ?? [];
  const valueStatus = tenant.value_status ?? "unknown";
  const commercialSignals = [
    {
      label: "Connector",
      value: tenant.provider_key_status.state,
      detail: `${fmtCount(tenant.provider_key_status.active_provider_count)} active key(s)`,
    },
    {
      label: "Metering",
      value: tenant.event_metering_status?.state ?? "unknown",
      detail: eventMeteringText(tenant),
    },
    {
      label: "Pricing",
      value: tenant.pricing_cost_status?.state ?? "unknown",
      detail: pricingDetail(tenant),
    },
    {
      label: "Billing",
      value: tenant.billing_status?.state ?? "unknown",
      detail: billingDetail(tenant),
    },
    {
      label: "Support",
      value: tenant.support_status?.state ?? "none",
      detail: supportDetail(tenant),
    },
  ];

  return (
    <div className="panel owner-project-intel-panel">
        <div className="panel-header">
          <div className="owner-project-intel-heading">
            <span>Tenant proof ledger</span>
            <small>Protected actions, proof checks, release checks, connectors, metering, billing, and support evidence for this tenant.</small>
          </div>
        <div className="owner-project-intel-status">
          <StatusBadge value={valueStatus} />
          <StatusBadge value={actionLabel(tenant.next_owner_action)} tone={actionTone(tenant.next_owner_action)} />
        </div>
      </div>
      <div className="owner-project-intel-body">
        <section className={`owner-project-action-card owner-project-action-${actionTone(tenant.next_owner_action)}`}>
          <div>
            <span className="owner-section-label">Next owner action</span>
            <strong>{actionLabel(tenant.next_owner_action)}</strong>
            <p>
              Priority score {tenant.tenant_priority_score == null ? "not reported" : tenant.tenant_priority_score}.
              {breaks.length > 0 ? " Resolve the listed breaks before treating this tenant as launch-ready." : " No money-path breaks reported."}
            </p>
          </div>
          <div className="owner-project-break-list">
            {breaks.length > 0 ? (
              breaks.slice(0, 5).map((item) => <span key={item}>{breakLabel(item)}</span>)
            ) : (
              <span>No breaks reported</span>
            )}
          </div>
        </section>

        <div className="owner-project-intel-grid">
          <div className="owner-project-intel-card">
            <span className="owner-stat-label">Open Issues</span>
            <strong>{fmtCount(tenant.open_issue_count)}</strong>
            <p>{tenant.open_issue_count ? "Open issues still need proof checks." : "No open issue reported by backend."}</p>
          </div>
          <div className="owner-project-intel-card">
            <span className="owner-stat-label">Verified proof</span>
            <strong>{fmtCount(tenant.verified_replay_count_7d)}</strong>
            <p>{fmtCount(tenant.replay_run_count_7d)} total proof check(s) in 7 days.</p>
          </div>
          <div className="owner-project-intel-card">
            <span className="owner-stat-label">Receipt baselines</span>
            <strong>{fmtCount(tenant.golden_trace_count)}</strong>
            <p>{tenant.golden_trace_count ? "Receipt baseline available for release checks." : "No receipt baseline yet."}</p>
          </div>
          <div className="owner-project-intel-card">
            <span className="owner-stat-label">Release checks</span>
            <strong>{fmtCount(tenant.ci_run_count_7d)}</strong>
            <p>{fmtCount(tenant.blocking_ci_failures_7d)} blocking failure(s) in 7 days.</p>
          </div>
        </div>

        <TenantLoopEvidence tenant={tenant} />

        <section className="owner-project-commercial-panel">
          <div className="owner-project-commercial-head">
            <div>
              <span className="owner-section-label">Commercial readiness</span>
              <strong>Paid-path signals</strong>
            </div>
            <BadgeDollarSign size={18} aria-hidden="true" />
          </div>
          <div className="owner-project-commercial-grid">
            {commercialSignals.map((signal) => (
              <CommercialSignal key={signal.label} {...signal} />
            ))}
          </div>
        </section>

        <div className="owner-project-intel-proof">
          <div className="owner-money-proof-grid">
            <EvidenceItem label="Project Plan" value={tenant.plan_code} />
            <EvidenceItem label="Last protected action" value={fmtDate(tenant.last_capture_at)} />
            <EvidenceItem label="Connector keys" value={providerValue} />
            <EvidenceItem label="Proof quota" value={quotaText(tenant)} />
            <EvidenceItem label="Event Metering" value={eventMeteringText(tenant)} />
            <EvidenceItem label="Pricing Evidence" value={pricingDetail(tenant)} />
          </div>
          <div className="owner-project-intel-actions">
            <div className="owner-project-intel-action-copy">
              <KeyRound size={16} aria-hidden="true" />
              <span>
                Connector key is <StatusBadge value={tenant.provider_key_status.state} />, proof quota is{" "}
                <StatusBadge value={tenant.replay_quota_status.state} />, and billing is{" "}
                <StatusBadge value={tenant.billing_status?.state ?? "unknown"} />.
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
              <Link href="/owner/settings" className="btn btn-soft">
                Platform limits
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
  const [grantOpen, setGrantOpen] = useState(false);
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
    return <p className="hint">Loading tenant record...</p>;
  }
  if (error) {
    return <div className="alert-strip alert-strip-error">{error}</div>;
  }
  if (!project) return null;

  return (
    <div className="owner-page owner-project-detail-page">
      <div className="owner-project-breadcrumb">
        <Link href="/owner/projects">Tenants</Link>
        <span>/</span>
        <span>{project.name}</span>
      </div>

      <div className="owner-project-hero">
        <div>
          <span className="owner-section-label">Customer 360</span>
          <h2>{project.name}</h2>
          <p>
            ID: <code>{project.id}</code>
            {tenantHealth ? <> - Plan: <strong>{tenantHealth.plan_code}</strong></> : null}
          </p>
        </div>
        <div className="owner-project-hero-actions">
          <span className={project.is_active ? "pill pill-green" : "pill pill-red"}>
            {project.is_active ? "Active" : "Suspended"}
          </span>
          <button className="btn btn-soft" type="button" onClick={() => setGrantOpen(true)}>
            <BadgeDollarSign size={15} aria-hidden="true" />
            Upgrade / change plan
          </button>
          <button
            className={project.is_active ? "btn btn-danger" : "btn btn-primary"}
            onClick={handleToggleStatus}
            disabled={toggleMutation.isPending}
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

      <Customer360Summary project={project} tenant={tenantHealth} memberCount={members.length} />

      <div className="owner-project-stat-grid">
        {[
          { label: "Protected Actions", value: project.call_count.toLocaleString() },
          { label: "Total Cost (USD)", value: usd(project.total_cost_usd) },
          { label: "Members", value: project.member_count },
        ].map((s) => (
          <div key={s.label} className="owner-project-stat-card">
            <span>{s.label}</span>
            <strong>{s.value}</strong>
          </div>
        ))}
      </div>

      <TenantProofLedger
        tenant={tenantHealth}
        error={moneyPathError}
        loading={moneyPathQuery.isLoading}
      />

      <div className="panel">
        <div className="panel-header">Customer Details</div>
        <div className="owner-info-list">
          <InfoRow label="Project ID" value={<code>{project.id}</code>} />
          <InfoRow label="Name" value={project.name} />
          <InfoRow label="Owner Ref" value={project.owner_ref ?? "-"} />
          <InfoRow label="Status" value={project.is_active ? "Active" : "Suspended"} />
          <InfoRow label="Created" value={new Date(project.created_at).toLocaleString()} />
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          Rate Limit Override
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

      <div className="panel">
        <div className="panel-header">
          <span>Users</span>
          <span className="panel-header-note">
            {members.length} member{members.length !== 1 ? "s" : ""}
          </span>
        </div>
        {members.length === 0 && (
          <p className="owner-panel-empty">No members found.</p>
        )}
        {members.length > 0 && (
          <div className="owner-table-wrap owner-table-wrap-embedded">
            <table className="owner-table">
              <thead>
                <tr>
                  {["User", "Role", "Status", "Joined"].map((h) => (
                    <th key={h} className="owner-th">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.membership_id} className="owner-tr">
                    <td className="owner-td">
                      <Link href={`/owner/users/${m.user_id}`} className="owner-row-link">
                        {m.email ?? m.github_login ?? m.display_name ?? m.user_id}
                      </Link>
                    </td>
                    <td className="owner-td owner-td-secondary">{m.role}</td>
                    <td className="owner-td">
                      <span className={m.is_active ? "pill pill-green" : "pill pill-red"}>
                        {m.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="owner-td owner-td-secondary">
                      {new Date(m.joined_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {grantOpen && (
        <OwnerPlanGrantModal
          orgId={project.id}
          orgLabel={project.name}
          onClose={() => setGrantOpen(false)}
          onGranted={(planCode) => {
            setActionMsg(`Plan grant applied to ${project.name}: ${planCode}.`);
            setGrantOpen(false);
          }}
        />
      )}
    </div>
  );
}
