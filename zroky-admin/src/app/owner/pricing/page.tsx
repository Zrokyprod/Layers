"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  useConfirmOwnerRazorpayPayment,
  useOwnerBillingAccounts,
  useOwnerBillingRecovery,
  useOwnerBillingSummary,
  useOwnerMoneyPathHealth,
  useOwnerPricing,
  useOwnerPricingPlans,
  useRunOwnerBillingRecovery,
  useUpdateOwnerPricing,
} from "@/lib/hooks";
import type {
  OwnerBillingAccountItem,
  OwnerBillingRecoverySummary,
  OwnerBillingSummary,
  OwnerMoneyPathTenantRow,
  OwnerPricingPlan,
} from "@/lib/owner-api";

interface ModelPricing {
  billing_unit: string;
  input: number;
  output: number;
  reasoning: number;
  cache_create: number;
  cache_read: number;
}

interface ProviderConfig {
  pricing_source?: { type: string; url?: string };
  models: Record<string, ModelPricing>;
}

interface PricingConfig {
  meta?: Record<string, unknown>;
  providers?: Record<string, ProviderConfig>;
}

type Tone = "ok" | "warn" | "danger" | "neutral";

const BILLING_RISK_STATUSES = new Set(["past_due", "unpaid", "canceled", "incomplete"]);

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

function fmtCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  if (value === -1) return "Unlimited";
  return value.toLocaleString();
}

function fmtMoney(value: number | null): string {
  if (value === null) return "Custom";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "-";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action.replaceAll("_", " ");
}

function statusCount(summary: OwnerBillingSummary | null, status: string): number | null {
  if (!summary) return null;
  return summary.by_status.find((row) => row.status === status)?.count ?? 0;
}

function planMapFromCatalog(plans: OwnerPricingPlan[], aliases: Record<string, string>) {
  const map = new Map<string, OwnerPricingPlan>();
  for (const plan of plans) map.set(plan.code, plan);
  for (const [alias, canonical] of Object.entries(aliases)) {
    const plan = map.get(canonical);
    if (plan) map.set(alias, plan);
  }
  return map;
}

function boolBadge(value: boolean) {
  return (
    <span className={`owner-money-badge owner-money-badge-${value ? "ok" : "neutral"}`}>
      {value ? "Included" : "Not included"}
    </span>
  );
}

function StatusBadge({ value, tone }: { value: string; tone: Tone }) {
  return <span className={`owner-money-badge owner-money-badge-${tone}`}>{value}</span>;
}

function accountRisk({
  account,
  plan,
  tenant,
  moneyPathReady,
}: {
  account: OwnerBillingAccountItem;
  plan: OwnerPricingPlan | undefined;
  tenant: OwnerMoneyPathTenantRow | undefined;
  moneyPathReady: boolean;
}): { label: string; detail: string; tone: Tone } {
  if (!plan) {
    return { label: "Unknown plan", detail: "No catalog entry matches this billing row.", tone: "danger" };
  }
  if (BILLING_RISK_STATUSES.has(account.status)) {
    return { label: "Billing risk", detail: `Subscription status is ${account.status}.`, tone: "danger" };
  }
  if (!moneyPathReady) {
    return { label: "Control data unavailable", detail: "Protected-action entitlement risk cannot be evaluated.", tone: "warn" };
  }
  if (!tenant) {
    return { label: "No control row", detail: "Tenant has no protected-action health row.", tone: "warn" };
  }
  if (tenant.replay_quota_status.state === "exceeded") {
    return { label: "Proof quota exceeded", detail: "Tenant is above proof-check entitlement.", tone: "danger" };
  }
  if (tenant.replay_quota_status.state === "near_limit") {
    return { label: "Proof quota", detail: "Tenant is near proof-check entitlement.", tone: "warn" };
  }
  if (["risk", "missing_paid", "unknown"].includes(tenant.billing_status?.state ?? "")) {
    return { label: "Billing risk", detail: `Money-path billing status is ${tenant.billing_status?.state}.`, tone: "danger" };
  }
  if (["drift", "missing", "fallback", "stale"].includes(tenant.pricing_cost_status?.state ?? "")) {
    return { label: "Cost metadata", detail: tenant.pricing_cost_status?.detail ?? "Tenant has stale or missing cost metadata.", tone: "warn" };
  }
  if (tenant.provider_key_status.state === "missing" && plan.pricing.connectors !== 0) {
    return { label: "Connector missing", detail: "Protected-action plan has no connector key.", tone: "warn" };
  }
  if (plan.pricing.audit_manifest_export && tenant.golden_trace_count === 0) {
    return { label: "Receipt proof missing", detail: "Audit export is included but no receipt baseline exists.", tone: "warn" };
  }
  return { label: "Monitor", detail: "Billing and control-plane evidence are aligned.", tone: "ok" };
}

function ModelRow({
  provider, model, data, onUpdate,
}: {
  provider: string;
  model: string;
  data: ModelPricing;
  onUpdate: (provider: string, model: string, field: keyof ModelPricing, value: number | string) => void;
}) {
  const fields: Array<keyof ModelPricing> = ["input", "output", "reasoning", "cache_create", "cache_read"];
  return (
    <tr className="owner-tr">
      <td className="owner-td owner-td-model">{model}</td>
      {fields.map((f) => (
        <td key={f} className="owner-td">
          <input
            type="number"
            step="0.0001"
            min="0"
            value={data[f] as number}
            onChange={(e) => onUpdate(provider, model, f, parseFloat(e.target.value) || 0)}
            className="owner-price-input"
          />
        </td>
      ))}
    </tr>
  );
}

function BillingAccountRow({
  account,
  plan,
  tenant,
  moneyPathReady,
}: {
  account: OwnerBillingAccountItem;
  plan: OwnerPricingPlan | undefined;
  tenant: OwnerMoneyPathTenantRow | undefined;
  moneyPathReady: boolean;
}) {
  const risk = accountRisk({ account, plan, tenant, moneyPathReady });
  return (
    <tr className="owner-tr">
      <td className="owner-td">
        <strong>{account.project_name ?? account.org_id}</strong>
        <div className="hint"><code>{account.org_id}</code></div>
      </td>
      <td className="owner-td">
        <span className="pill">{account.plan_code}</span>
      </td>
      <td className="owner-td">
        <span className={`status-pill status-${account.status}`}>{account.status}</span>
      </td>
      <td className="owner-td">{account.sla_tier}</td>
      <td className="owner-td">
        <div>{tenant ? fmtCount(tenant.replay_quota_status.used) : "-"}</div>
        <span className="owner-td-secondary">
          {tenant ? `${fmtCount(tenant.golden_trace_count)} receipt baseline` : "No control row"}
        </span>
      </td>
      <td className="owner-td">
        <StatusBadge value={risk.label} tone={risk.tone} />
        <div className="owner-user-id">{risk.detail}</div>
      </td>
      <td className="owner-td owner-td-ts">
        {account.current_period_end ? new Date(account.current_period_end).toLocaleDateString() : "-"}
      </td>
      <td className="owner-td owner-td-truncate">
        <div>{account.payment_subscription_ref ?? account.payment_request_ref ?? "-"}</div>
        <span className="owner-td-secondary">{account.payment_provider || "manual"}</span>
      </td>
      <td className="owner-td">
        <div className="owner-billing-links">
          {account.payment_dashboard_url ? (
            <a className="owner-row-link" href={account.payment_dashboard_url} target="_blank" rel="noopener noreferrer">
              Razorpay
            </a>
          ) : null}
          {!account.payment_dashboard_url ? (
            <span className="hint">No payment link</span>
          ) : null}
        </div>
      </td>
    </tr>
  );
}

function PaymentRecoveryPanel({
  recovery,
  isLoading,
  isRunning,
  message,
  onRun,
}: {
  recovery: OwnerBillingRecoverySummary | null;
  isLoading: boolean;
  isRunning: boolean;
  message: string;
  onRun: () => void;
}) {
  const latest = recovery?.recent_reconciled?.[0] ?? null;
  return (
    <section className="panel">
      <div className="panel-header">
        Payment Recovery
        <span className="panel-header-note">Webhook fallback, pending orders, and manual reconciliation.</span>
      </div>
      {message ? (
        <div className={`alert-strip${message.startsWith("Error") ? " alert-strip-error" : ""}`}>
          {message}
        </div>
      ) : null}
      <div className="owner-stat-grid owner-stat-grid-embedded">
        <div className={`owner-stat-card ${(recovery?.pending_count ?? 0) === 0 ? "owner-stat-card-accent" : ""}`}>
          <span className="owner-stat-label">Pending Razorpay Orders</span>
          <span className="owner-stat-value">{isLoading ? "-" : fmtCount(recovery?.pending_count)}</span>
          <span className="owner-stat-sub">checkout orders without active payment refs</span>
        </div>
        <div className={`owner-stat-card ${(recovery?.stale_pending_count ?? 0) > 0 ? "owner-stat-card-danger" : ""}`}>
          <span className="owner-stat-label">Stale Pending</span>
          <span className="owner-stat-value">{isLoading ? "-" : fmtCount(recovery?.stale_pending_count)}</span>
          <span className="owner-stat-sub">older than {fmtDuration(recovery?.stale_after_seconds)}</span>
        </div>
        <div className="owner-stat-card">
          <span className="owner-stat-label">Oldest Pending Age</span>
          <span className="owner-stat-value">{isLoading ? "-" : fmtDuration(recovery?.oldest_pending_age_seconds)}</span>
          <span className="owner-stat-sub">time since local checkout request update</span>
        </div>
        <div className="owner-stat-card">
          <span className="owner-stat-label">Latest Recovered</span>
          <span className="owner-stat-value">{latest?.plan_code ?? "-"}</span>
          <span className="owner-stat-sub">{latest?.payment_id ?? recovery?.last_reconciled_at ?? "No recovered payment yet"}</span>
        </div>
      </div>
      <div className="owner-panel-filter owner-panel-filter-embedded">
        <div className="owner-filter-row">
          <button className="btn btn-primary" onClick={onRun} disabled={isRunning}>
            {isRunning ? "Reconciling..." : "Run reconciliation now"}
          </button>
          <span className="hint">Uses Razorpay order/payment verification before activating entitlements.</span>
        </div>
      </div>
      <div className="owner-table-wrap owner-table-wrap-embedded">
        <table className="owner-table">
          <thead>
            <tr>
              {["Account", "Requested plan", "Age", "State", "Order", "Updated"].map((header) => (
                <th key={header} className="owner-th">{header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={6} className="owner-td owner-td-empty">Loading payment recovery state...</td></tr>
            ) : (recovery?.pending_items ?? []).length === 0 ? (
              <tr><td colSpan={6} className="owner-td owner-td-empty">No pending Razorpay orders.</td></tr>
            ) : (
              recovery?.pending_items.map((item) => (
                <tr key={`${item.org_id}:${item.payment_request_ref}`} className="owner-tr">
                  <td className="owner-td">
                    <strong>{item.project_name ?? item.org_id}</strong>
                    <div className="hint"><code>{item.org_id}</code></div>
                  </td>
                  <td className="owner-td">
                    <span className="pill">{item.requested_plan_code ?? item.plan_code}</span>
                  </td>
                  <td className="owner-td">{fmtDuration(item.age_seconds)}</td>
                  <td className="owner-td">
                    <StatusBadge value={item.stale ? "stale pending" : "pending"} tone={item.stale ? "danger" : "warn"} />
                    <div className="owner-user-id">{item.subscription_status}</div>
                  </td>
                  <td className="owner-td owner-td-truncate">{item.order_id ?? item.payment_request_ref}</td>
                  <td className="owner-td owner-td-ts">{item.updated_at ? new Date(item.updated_at).toLocaleString() : "-"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function PricingPage() {
  const pricingQuery = useOwnerPricing();
  const pricingPlansQuery = useOwnerPricingPlans();
  const summaryQuery = useOwnerBillingSummary();
  const recoveryQuery = useOwnerBillingRecovery();
  const moneyPathQuery = useOwnerMoneyPathHealth();
  const [accountStatus, setAccountStatus] = useState("");
  const [planCode, setPlanCode] = useState("");
  const accountsQuery = useOwnerBillingAccounts({
    status: accountStatus || undefined,
    plan_code: planCode || undefined,
    limit: 100,
  });
  const updateMutation = useUpdateOwnerPricing();
  const confirmPaymentMutation = useConfirmOwnerRazorpayPayment();
  const runRecoveryMutation = useRunOwnerBillingRecovery();

  const [config, setConfig] = useState<PricingConfig | null>(null);
  const [saveMsg, setSaveMsg] = useState("");
  const [confirmMsg, setConfirmMsg] = useState("");
  const [recoveryMsg, setRecoveryMsg] = useState("");
  const [confirmOrgId, setConfirmOrgId] = useState("");
  const [confirmPlanCode, setConfirmPlanCode] = useState("pro");
  const [confirmPaymentRef, setConfirmPaymentRef] = useState("");
  const [confirmCustomerRef, setConfirmCustomerRef] = useState("");
  const [confirmPaymentRequestRef, setConfirmPaymentRequestRef] = useState("");
  const [confirmPeriodEnd, setConfirmPeriodEnd] = useState("");
  const [confirmSeats, setConfirmSeats] = useState("10");

  const loading = pricingQuery.isLoading;
  const error = pricingQuery.error?.message ?? "";
  const filePath = pricingQuery.data?.path ?? "";

  useEffect(() => {
    if (pricingQuery.data?.config) {
      setConfig(pricingQuery.data.config as PricingConfig);
    }
  }, [pricingQuery.data]);

  const handleUpdate = useCallback(
    (provider: string, model: string, field: keyof ModelPricing, value: number | string) => {
      setConfig((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          providers: {
            ...prev.providers,
            [provider]: {
              ...prev.providers?.[provider],
              models: {
                ...prev.providers?.[provider]?.models,
                [model]: {
                  ...prev.providers?.[provider]?.models?.[model],
                  [field]: value,
                },
              },
            },
          },
        } as PricingConfig;
      });
    },
    [],
  );

  const handleSave = useCallback(async () => {
    if (!config) return;
    setSaveMsg("");
    try {
      await updateMutation.mutateAsync(config as Record<string, unknown>);
      setSaveMsg("Pricing config saved successfully.");
    } catch (e: unknown) {
      setSaveMsg(`Error: ${(e as Error).message}`);
    }
  }, [config, updateMutation]);

  const handleConfirmPayment = useCallback(async () => {
    setConfirmMsg("");
    try {
      const parsedSeats = confirmSeats.trim() ? Number(confirmSeats) : null;
      await confirmPaymentMutation.mutateAsync({
        org_id: confirmOrgId.trim(),
        plan_code: confirmPlanCode.trim(),
        payment_ref: confirmPaymentRef.trim(),
        customer_ref: confirmCustomerRef.trim() || null,
        payment_request_ref: confirmPaymentRequestRef.trim() || null,
        current_period_end: confirmPeriodEnd.trim() ? new Date(confirmPeriodEnd).toISOString() : null,
        seats: parsedSeats !== null && Number.isFinite(parsedSeats) ? parsedSeats : null,
      });
      setConfirmMsg("Razorpay payment confirmed and entitlements activated.");
      setConfirmPaymentRef("");
      setConfirmPaymentRequestRef("");
    } catch (e: unknown) {
      setConfirmMsg(`Error: ${(e as Error).message}`);
    }
  }, [
    confirmCustomerRef,
    confirmOrgId,
    confirmPaymentMutation,
    confirmPaymentRef,
    confirmPaymentRequestRef,
    confirmPeriodEnd,
    confirmPlanCode,
    confirmSeats,
  ]);

  const handleRunRecovery = useCallback(async () => {
    setRecoveryMsg("");
    try {
      const result = await runRecoveryMutation.mutateAsync(50);
      setRecoveryMsg(
        `Reconciliation complete: ${result.activated} activated, ${result.skipped} skipped, ${result.failed} failed.`,
      );
    } catch (e: unknown) {
      setRecoveryMsg(`Error: ${(e as Error).message}`);
    }
  }, [runRecoveryMutation]);

  const fieldLabels = ["Input ($/1M)", "Output ($/1M)", "Reasoning ($/1M)", "Cache Create ($/1M)", "Cache Read ($/1M)"];
  const summary = summaryQuery.data ?? null;
  const accounts = accountsQuery.data?.items ?? [];
  const planCatalog = pricingPlansQuery.data ?? null;
  const plans = useMemo(() => planCatalog?.plans ?? [], [planCatalog]);
  const aliases = useMemo(() => planCatalog?.aliases ?? {}, [planCatalog]);
  const plansByCode = useMemo(() => planMapFromCatalog(plans, aliases), [aliases, plans]);
  const moneyPathTenantsByProject = useMemo(() => {
    const map = new Map<string, OwnerMoneyPathTenantRow>();
    for (const tenant of moneyPathQuery.data?.tenants ?? []) map.set(tenant.project_id, tenant);
    return map;
  }, [moneyPathQuery.data?.tenants]);
  const activeAccounts = (statusCount(summary, "active") ?? 0) + (statusCount(summary, "trialing") ?? 0);
  const driftCount = planCatalog?.drift.length ?? null;
  const providerGaps = moneyPathQuery.data?.platform.tenants_missing_provider_key ?? null;
  const quotaRisk = moneyPathQuery.data?.platform.tenants_near_replay_quota ?? null;
  const costMetadataRisk = moneyPathQuery.data?.platform.tenants_with_stale_pricing ?? null;
  const billingRisk = moneyPathQuery.data?.platform.tenants_with_billing_risk ?? null;
  const meteringRisk = moneyPathQuery.data?.platform.metering_failure_tenants ?? null;
  const providerVerification = moneyPathQuery.data?.platform.billing_provider_verification ?? null;
  const pricingRiskTenants = (moneyPathQuery.data?.tenants ?? []).filter((tenant) =>
    ["drift", "missing", "fallback", "stale", "degraded"].includes(tenant.pricing_cost_status?.state ?? ""),
  );
  const moneyPathReady = Boolean(moneyPathQuery.data && !moneyPathQuery.error);

  return (
    <div className="owner-page owner-pricing-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Revenue & Entitlements</h2>
          <p className="hint">
            Plan contract, billing accounts, proof quota risk, and model pricing controls.
          </p>
        </div>
        <div className="owner-page-header-actions">
          {saveMsg && (
            <span className={`owner-save-msg${saveMsg.startsWith("Error") ? " owner-save-msg-error" : ""}`}>
              {saveMsg}
            </span>
          )}
          <button className="btn btn-primary" onClick={handleSave} disabled={updateMutation.isPending || loading}>
            {updateMutation.isPending ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>

      {error && <div className="alert-strip alert-strip-error">{error}</div>}
      {pricingPlansQuery.error && <div className="alert-strip alert-strip-error">{pricingPlansQuery.error.message}</div>}
      {summaryQuery.error && <div className="alert-strip alert-strip-error">{summaryQuery.error.message}</div>}
      {accountsQuery.error && <div className="alert-strip alert-strip-error">{accountsQuery.error.message}</div>}
      {recoveryQuery.error && <div className="alert-strip alert-strip-error">{recoveryQuery.error.message}</div>}
      {moneyPathQuery.error && <div className="alert-strip alert-strip-error">{moneyPathQuery.error.message}</div>}
      {loading && !error && <p className="hint">Loading...</p>}

      <section className="owner-pricing-contract-grid">
        <div className={`owner-stat-card ${driftCount === 0 ? "owner-stat-card-accent" : ""}`}>
          <span className="owner-stat-label">Plan Contract</span>
          <span className="owner-stat-value">{driftCount === null ? "-" : driftCount === 0 ? "In sync" : `${driftCount} drift`}</span>
          <span className="owner-stat-sub">{planCatalog?.source_of_truth ?? "Backend pricing contract"}</span>
        </div>
        <div className="owner-stat-card">
          <span className="owner-stat-label">Active + Trialing</span>
          <span className="owner-stat-value">{summary ? activeAccounts.toLocaleString() : "-"}</span>
          <span className="owner-stat-sub">billing rows in sellable state</span>
        </div>
        <div className="owner-stat-card">
          <span className="owner-stat-label">Proof Quota Risk</span>
          <span className="owner-stat-value">{fmtCount(quotaRisk)}</span>
          <span className="owner-stat-sub">tenants near or above proof-check credits</span>
        </div>
        <div className="owner-stat-card">
          <span className="owner-stat-label">Connector Gaps</span>
          <span className="owner-stat-value">{fmtCount(providerGaps)}</span>
          <span className="owner-stat-sub">tenants blocked from connector-backed protected actions</span>
        </div>
        <div className="owner-stat-card">
          <span className="owner-stat-label">Cost Metadata Risk</span>
          <span className="owner-stat-value">{fmtCount(costMetadataRisk)}</span>
          <span className="owner-stat-sub">stale, fallback, drifted, or missing pricing evidence</span>
        </div>
        <div className="owner-stat-card">
          <span className="owner-stat-label">Billing Risk</span>
          <span className="owner-stat-value">{fmtCount(billingRisk)}</span>
          <span className="owner-stat-sub">subscription rows breaking the paid path</span>
        </div>
        <div className="owner-stat-card">
          <span className="owner-stat-label">Metering Failures</span>
          <span className="owner-stat-value">{fmtCount(meteringRisk)}</span>
          <span className="owner-stat-sub">{fmtCount(moneyPathQuery.data?.platform.event_counter_failure_count ?? null)} counter failure(s)</span>
        </div>
        <div className="owner-stat-card">
          <span className="owner-stat-label">Payment Verification</span>
          <span className="owner-stat-value">{providerVerification?.state ?? "-"}</span>
          <span className="owner-stat-sub">{providerVerification?.detail ?? "No payment proof reported"}</span>
        </div>
      </section>

      <PaymentRecoveryPanel
        recovery={recoveryQuery.data ?? null}
        isLoading={recoveryQuery.isLoading}
        isRunning={runRecoveryMutation.isPending}
        message={recoveryMsg}
        onRun={() => void handleRunRecovery()}
      />

      <section className="panel">
        <div className="panel-header">
          Plan Entitlement Matrix
          <span className="panel-header-note">
            {planCatalog ? `${planCatalog.currency}, unlimited=${planCatalog.unlimited}` : "Backend contract loading"}
          </span>
        </div>
        {pricingPlansQuery.isLoading ? <p className="hint owner-panel-padding">Loading plan entitlement contract...</p> : null}
        {!pricingPlansQuery.isLoading && plans.length === 0 ? (
          <div className="alert-strip">No pricing plans returned by backend.</div>
        ) : null}
        {planCatalog?.drift.length ? (
          <div className="alert-strip alert-strip-error">
            Pricing contract drift: {planCatalog.drift.join(", ")}
          </div>
        ) : null}
        {plans.length > 0 ? (
          <div className="owner-table-wrap owner-table-wrap-embedded">
            <table className="owner-table owner-pricing-matrix">
              <thead>
                <tr>
                  {[
                    "Plan",
                    "Price",
                    "Protected actions/mo",
                    "Agents",
                    "Connectors",
                    "Approvers",
                    "Retention",
                    "Bypass",
                    "Audit export",
                    "Overage",
                  ].map((header) => (
                    <th key={header} className="owner-th">{header}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {plans.map((plan) => (
                  <tr key={plan.code} className="owner-tr">
                    <td className="owner-td">
                      <strong>{plan.name}</strong>
                      <div className="hint"><code>{plan.code}</code></div>
                    </td>
                    <td className="owner-td">{fmtMoney(plan.price.monthly_usd)}{plan.price.period}</td>
                    <td className="owner-td">{fmtCount(plan.pricing.protected_actions_per_month)}</td>
                    <td className="owner-td">{fmtCount(plan.pricing.managed_agents)}</td>
                    <td className="owner-td">{fmtCount(plan.pricing.connectors)}</td>
                    <td className="owner-td">{fmtCount(plan.pricing.approver_seats)}</td>
                    <td className="owner-td">{fmtCount(plan.pricing.evidence_retention_days)} days</td>
                    <td className="owner-td">{plan.pricing.bypass_detection}</td>
                    <td className="owner-td">{boolBadge(plan.pricing.audit_manifest_export)}</td>
                    <td className="owner-td">
                      {plan.pricing.overage_policy === "hard_cap"
                        ? "Hard cap"
                        : plan.pricing.overage_policy === "custom"
                          ? "Custom"
                          : `$${plan.pricing.overage_per_action_usd?.toFixed(3)}/action`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="owner-stat-grid">
        <div className="owner-stat-card owner-stat-card-accent">
          <span className="owner-stat-label">Subscriptions</span>
          <span className="owner-stat-value">{summary?.total_subscriptions.toLocaleString() ?? "-"}</span>
          <span className="owner-stat-sub">tenant subscriptions</span>
        </div>
        <div className="owner-stat-card">
          <span className="owner-stat-label">Overdue</span>
          <span className="owner-stat-value">{summary?.overdue.toLocaleString() ?? "-"}</span>
          <span className="owner-stat-sub">past due accounts</span>
        </div>
        <div className="owner-stat-card">
          <span className="owner-stat-label">Canceled</span>
          <span className="owner-stat-value">{summary?.canceled.toLocaleString() ?? "-"}</span>
          <span className="owner-stat-sub">canceled accounts</span>
        </div>
        <div className="owner-stat-card">
          <span className="owner-stat-label">Billing accounts</span>
          <span className="owner-stat-value">{accountsQuery.data?.total.toLocaleString() ?? "-"}</span>
          <span className="owner-stat-sub">payment-backed billing rows</span>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          Stale Pricing &amp; Cost Metadata
          <span className="panel-header-note">From protected-action health and latest pricing evidence.</span>
        </div>
        {!moneyPathReady ? (
          <div className="alert-strip">Control-plane health is unavailable, so stale tenant cost evidence cannot be evaluated.</div>
        ) : pricingRiskTenants.length === 0 ? (
          <p className="hint owner-panel-padding">No tenants have stale, fallback, missing, or drifted pricing metadata.</p>
        ) : (
          <div className="owner-table-wrap owner-table-wrap-embedded">
            <table className="owner-table">
              <thead>
                <tr>
                  {["Tenant", "Pricing status", "Version", "Source", "Age", "Next action"].map((header) => (
                    <th key={header} className="owner-th">{header}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pricingRiskTenants.map((tenant) => (
                  <tr key={tenant.project_id} className="owner-tr">
                    <td className="owner-td">
                      <strong>{tenant.project_name}</strong>
                      <div className="hint"><code>{tenant.project_id}</code></div>
                    </td>
                    <td className="owner-td">
                      <StatusBadge value={tenant.pricing_cost_status?.state ?? "unknown"} tone={["drift", "missing", "fallback", "stale"].includes(tenant.pricing_cost_status?.state ?? "") ? "warn" : "neutral"} />
                      <div className="owner-user-id">{tenant.pricing_cost_status?.detail ?? "No detail"}</div>
                    </td>
                    <td className="owner-td">{tenant.pricing_cost_status?.pricing_version ?? "-"}</td>
                    <td className="owner-td">{tenant.pricing_cost_status?.pricing_source ?? "-"}</td>
                    <td className="owner-td">{tenant.pricing_cost_status?.pricing_age_days ?? "-"} days</td>
                    <td className="owner-td">{actionLabel(tenant.next_owner_action)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="owner-ops-grid">
        <section className="panel">
          <div className="panel-header">Plan Breakdown</div>
          <div className="owner-ops-list">
            {(summary?.by_plan ?? []).length === 0 ? <p className="hint">No plan data found.</p> : null}
            {(summary?.by_plan ?? []).map((plan) => (
              <div key={plan.slug} className="owner-billing-breakdown-row">
                <span>{plan.plan}</span>
                <strong>{plan.tenant_count.toLocaleString()}</strong>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">Status Breakdown</div>
          <div className="owner-ops-list">
            {(summary?.by_status ?? []).length === 0 ? <p className="hint">No status data found.</p> : null}
            {(summary?.by_status ?? []).map((row) => (
              <div key={row.status} className="owner-billing-breakdown-row">
                <span>{row.status || "unknown"}</span>
                <strong>{row.count.toLocaleString()}</strong>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="panel">
        <div className="panel-header">
          Confirm Razorpay Payment
          <span className="panel-header-note">Marks a received Razorpay payment as active and seeds plan entitlements.</span>
        </div>
        {confirmMsg && (
          <div className={`alert-strip${confirmMsg.startsWith("Error") ? " alert-strip-error" : ""}`}>
            {confirmMsg}
          </div>
        )}
        <div className="owner-panel-filter owner-panel-filter-embedded">
          <div className="owner-filter-row">
            <label className="owner-filter-group">
              <span className="owner-filter-label">Org ID</span>
              <input className="input" value={confirmOrgId} onChange={(event) => setConfirmOrgId(event.target.value)} placeholder="project/org id" />
            </label>
            <label className="owner-filter-group">
              <span className="owner-filter-label">Plan</span>
              <select className="owner-select" value={confirmPlanCode} onChange={(event) => setConfirmPlanCode(event.target.value)}>
                <option value="starter">starter</option>
                <option value="pro">pro</option>
                <option value="enterprise">enterprise</option>
              </select>
            </label>
            <label className="owner-filter-group">
              <span className="owner-filter-label">Payment ref</span>
              <input className="input" value={confirmPaymentRef} onChange={(event) => setConfirmPaymentRef(event.target.value)} placeholder="Razorpay payment id" />
            </label>
            <label className="owner-filter-group">
              <span className="owner-filter-label">Request ref</span>
              <input className="input" value={confirmPaymentRequestRef} onChange={(event) => setConfirmPaymentRequestRef(event.target.value)} placeholder="order_..." />
            </label>
            <label className="owner-filter-group">
              <span className="owner-filter-label">Customer ref</span>
              <input className="input" value={confirmCustomerRef} onChange={(event) => setConfirmCustomerRef(event.target.value)} placeholder="email/client id" />
            </label>
            <label className="owner-filter-group">
              <span className="owner-filter-label">Period end</span>
              <input className="input" type="datetime-local" value={confirmPeriodEnd} onChange={(event) => setConfirmPeriodEnd(event.target.value)} />
            </label>
            <label className="owner-filter-group">
              <span className="owner-filter-label">Seats</span>
              <input className="input" type="number" min="1" value={confirmSeats} onChange={(event) => setConfirmSeats(event.target.value)} />
            </label>
            <button
              className="btn btn-primary"
              onClick={() => void handleConfirmPayment()}
              disabled={confirmPaymentMutation.isPending || !confirmOrgId.trim() || !confirmPaymentRef.trim()}
            >
              {confirmPaymentMutation.isPending ? "Confirming..." : "Confirm payment"}
            </button>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          Razorpay Billing Accounts
          <span className="panel-header-note">Shows subscription rows with payment references and control-plane readiness.</span>
        </div>
        <div className="owner-panel-filter owner-panel-filter-embedded">
          <div className="owner-filter-row">
            <label className="owner-filter-group">
              <span className="owner-filter-label">Status</span>
              <select className="owner-select" value={accountStatus} onChange={(event) => setAccountStatus(event.target.value)}>
                <option value="">All statuses</option>
                {["trialing", "active", "past_due", "canceled", "unpaid", "incomplete"].map((status) => (
                  <option key={status} value={status}>{status}</option>
                ))}
              </select>
            </label>
            <label className="owner-filter-group">
              <span className="owner-filter-label">Plan</span>
              <input
                className="input"
                value={planCode}
                onChange={(event) => setPlanCode(event.target.value)}
                placeholder="free, starter, pro"
              />
            </label>
            <button className="btn btn-soft" onClick={() => accountsQuery.refetch()} disabled={accountsQuery.isFetching}>
              Refresh accounts
            </button>
          </div>
        </div>
        <div className="owner-table-wrap owner-table-wrap-embedded">
          <table className="owner-table">
            <thead>
              <tr>
                {["Account", "Plan", "Status", "SLA", "Control plane", "Risk", "Period End", "Payment Ref", "Links"].map((header) => (
                  <th key={header} className="owner-th">{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {accountsQuery.isLoading ? (
                <tr><td colSpan={9} className="owner-td owner-td-empty">Loading accounts...</td></tr>
              ) : accounts.length === 0 ? (
                <tr><td colSpan={9} className="owner-td owner-td-empty">No billing accounts found.</td></tr>
              ) : (
                accounts.map((account) => (
                  <BillingAccountRow
                    key={account.org_id}
                    account={account}
                    plan={plansByCode.get(account.plan_code)}
                    tenant={moneyPathTenantsByProject.get(account.org_id)}
                    moneyPathReady={moneyPathReady}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          Model Pricing Configuration
          <span className="panel-header-note">
            Persisted to <code>{filePath || "pricing_config.json"}</code>
          </span>
        </div>
      </section>

      {!loading && config && !config.providers && (
        <div className="alert-strip">No model providers found in pricing config.</div>
      )}

      {config?.providers &&
        Object.entries(config.providers).map(([provider, provConfig]) => (
          <div key={provider} className="panel">
            <div className="panel-header" style={{ textTransform: "capitalize" }}>
              {provider}
              {provConfig.pricing_source?.url && (
                <a href={provConfig.pricing_source.url} target="_blank" rel="noopener noreferrer" className="owner-row-link" style={{ marginLeft: 10 }}>
                  Open pricing page
                </a>
              )}
            </div>

            <div className="owner-table-wrap">
              <table className="owner-table">
                <thead>
                  <tr>
                    <th className="owner-th">Model</th>
                    {fieldLabels.map((h) => <th key={h} className="owner-th">{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(provConfig.models ?? {}).map(([model, modelData]) => (
                    <ModelRow key={model} provider={provider} model={model} data={modelData} onUpdate={handleUpdate} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
    </div>
  );
}
