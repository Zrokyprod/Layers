"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CreditCard,
  Gauge,
  LockKeyhole,
  ReceiptText,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { SettingsHero, SettingsMetricStrip, SettingsScaffold, SettingsSection } from "@/components/settings-scaffold";
import { StatusPill } from "@/components/status-pill";
import { useBudget, useUpdateBudget } from "@/lib/hooks";
import { budgetSchema, type BudgetFormData } from "@/lib/schemas";
import {
  createRazorpayOrder,
  getBillingMe,
  getBillingUsage,
  verifyRazorpayPayment,
} from "@/lib/api";
import type { BillingMeResponse, BillingUsageMeter, BillingUsageResponse } from "@/lib/types";

type PlanCatalogItem = {
  code: string;
  name: string;
  monthlyCostUsd: number | null;
  features: string[];
  fit: string;
  proof: string;
  selfServe: boolean;
};

type RazorpayPaymentSuccess = {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
};

type RazorpayPaymentFailure = {
  error?: {
    code?: string;
    description?: string;
    reason?: string;
    source?: string;
    step?: string;
  };
};

type RazorpayCheckoutOptions = {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  order_id: string;
  handler: (response: RazorpayPaymentSuccess) => void;
  modal: {
    ondismiss: () => void;
  };
  theme: {
    color: string;
  };
};

type RazorpayCheckout = {
  open: () => void;
  on: (event: "payment.failed", handler: (response: RazorpayPaymentFailure) => void) => void;
};

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayCheckoutOptions) => RazorpayCheckout;
  }
}

const RAZORPAY_CHECKOUT_SCRIPT = "https://checkout.razorpay.com/v1/checkout.js";
let razorpayScriptPromise: Promise<boolean> | null = null;

const PLAN_CATALOG: PlanCatalogItem[] = [
  {
    code: "free",
    name: "Free",
    monthlyCostUsd: 0,
    features: [
      "500 protected actions/mo",
      "1 managed agent",
      "1 system-of-record connector",
      "Signed receipts and bypass watch",
    ],
    fit: "For the first protected agent and basic evidence collection.",
    proof: "Start with quota-backed controls before production rollout.",
    selfServe: false,
  },
  {
    code: "starter",
    name: "Starter",
    monthlyCostUsd: 49,
    features: [
      "2K protected actions/mo",
      "10K policy checks/mo",
      "3 managed agents",
      "3 system-of-record connectors",
      "2K runner executions and receipts/mo",
      "5K verification checks/mo",
      "Scoped policy rules and dry-run",
      "30-day evidence retention",
    ],
    fit: "For the first production workflow without starving the agent during evaluation.",
    proof: "Raises the first control-plane quota while keeping human approvals and receipt proof active.",
    selfServe: true,
  },
  {
    code: "team",
    name: "Team",
    monthlyCostUsd: 199,
    features: [
      "10K protected actions/mo",
      "50K policy checks/mo",
      "10 managed agents",
      "6 system-of-record connectors",
      "10K runner executions and receipts/mo",
      "25K verification checks/mo",
      "Dashboard and Slack approvals",
      "Audit manifest export",
    ],
    fit: "For teams scaling agents that touch money, access, customer state, or production systems.",
    proof: "Raises the control-plane quota while keeping receipt and verifier limits visible.",
    selfServe: true,
  },
  {
    code: "scale",
    name: "Scale",
    monthlyCostUsd: 499,
    features: [
      "50K protected actions/mo",
      "250K policy checks/mo",
      "Unlimited managed agents",
      "All standard connectors",
      "50K runner executions and receipts/mo",
      "125K verification checks/mo",
      "Bypass detection and audit exports",
      "180-day evidence retention",
    ],
    fit: "For organizations running high-volume autonomous workflows across many systems of record.",
    proof: "Expands standard connector and retention capacity without moving to a custom contract.",
    selfServe: true,
  },
  {
    code: "enterprise",
    name: "Enterprise",
    monthlyCostUsd: 2000,
    features: [
      "Custom protected action volume",
      "Contracted policy, runner, receipt, and verification meters",
      "Unlimited or contracted agent and connector capacity",
      "Customer-hosted runner scale-out",
      "SSO, self-hosting, audit, retention, and support controls",
    ],
    fit: "For enterprises rolling out high-risk AI agents across business units.",
    proof: "Contracted limits, audit posture, and deployment support align to your operating model.",
    selfServe: false,
  },
];

function loadRazorpayCheckout(): Promise<boolean> {
  if (typeof window === "undefined") {
    return Promise.resolve(false);
  }
  if (window.Razorpay) {
    return Promise.resolve(true);
  }
  if (razorpayScriptPromise) {
    return razorpayScriptPromise;
  }

  razorpayScriptPromise = new Promise((resolve) => {
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${RAZORPAY_CHECKOUT_SCRIPT}"]`,
    );
    if (existing) {
      existing.addEventListener("load", () => resolve(Boolean(window.Razorpay)), { once: true });
      existing.addEventListener("error", () => resolve(false), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.src = RAZORPAY_CHECKOUT_SCRIPT;
    script.async = true;
    script.onload = () => resolve(Boolean(window.Razorpay));
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
  return razorpayScriptPromise;
}

function formatRazorpayAmount(amount: number, currency: string): string {
  const majorUnits = amount / 100;
  return `${currency.toUpperCase()} ${majorUnits.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function catalogPlanCode(planCode: string | null | undefined): string {
  const normalized = (planCode ?? "").trim().toLowerCase();
  if (!normalized) {
    return "free";
  }
  if (normalized === "pilot") return "starter";
  if (normalized === "pro") return "team";
  if (normalized === "plus") return "scale";
  return normalized;
}

function planRank(planCode: string | null | undefined): number {
  const code = catalogPlanCode(planCode);
  if (code === "enterprise") return 4;
  if (code === "scale") return 3;
  if (code === "team") return 2;
  if (code === "starter") return 1;
  return 0;
}

function displayPlanCode(planCode: string | null | undefined): string {
  const normalized = (planCode ?? "").trim();
  return normalized ? normalized.toUpperCase() : "FREE";
}

function formatEntitlement(value: unknown): string {
  if (typeof value === "number") {
    return value < 0 ? "Unlimited" : value.toLocaleString();
  }
  if (typeof value === "boolean") {
    return value ? "Enabled" : "Disabled";
  }
  return value == null ? "Not configured" : String(value);
}

function formatUsageMeter(meter: BillingUsageMeter | null | undefined): string {
  if (!meter) return "Loading";
  const used = meter.used.toLocaleString();
  if (meter.unlimited || meter.limit == null) return `${used} used`;
  return `${used} / ${meter.limit.toLocaleString()}`;
}

function usageDetail(label: string, meter: BillingUsageMeter | null | undefined): string {
  if (!meter) return `${label} usage is loading.`;
  if (meter.state === "exceeded") return `${label} limit exceeded by ${(meter.overage ?? 0).toLocaleString()}.`;
  if (meter.state === "near_limit") return `${label} is near its plan limit.`;
  if (meter.state === "blocked") return `${label} is blocked on this plan.`;
  if (meter.unlimited) return `${label} is unlimited on this plan.`;
  return meter.resets_at ? `Resets ${meter.resets_at}.` : "Current plan allocation.";
}

function meterTone(meter: BillingUsageMeter | null | undefined): "success" | "warning" | "danger" | "neutral" {
  if (!meter) return "neutral";
  if (meter.state === "exceeded" || meter.state === "blocked") return "danger";
  if (meter.state === "near_limit") return "warning";
  return "success";
}

function meterPercent(meter: BillingUsageMeter | null | undefined): number {
  if (!meter || meter.unlimited || meter.limit == null || meter.limit <= 0) return 0;
  return Math.min(100, Math.max(0, (meter.used / meter.limit) * 100));
}

function hasMeterLimit(meter: BillingUsageMeter | null | undefined): boolean {
  return Boolean(meter && !meter.unlimited && meter.limit != null && meter.limit > 0);
}

function upgradeHintMessage(value: string | null): string | null {
  if (value === "actions.protected.monthly_quota" || value === "protected_actions") {
    return "Protected action volume is gated by your current plan. Upgrade to raise the monthly control-plane limit.";
  }
  if (value === "actions.receipts.monthly_quota" || value === "action_receipts") {
    return "Signed receipt volume is gated by your current plan. Upgrade to export more audit-grade proof.";
  }
  if (value === "connectors.system_of_record.max" || value === "active_connectors") {
    return "System-of-record connector capacity is gated by your current plan. Upgrade to verify more systems.";
  }
  if (value === "replay.monthly_runs") {
    return "That legacy quota is gated by your current plan. Billing now centers on protected actions, receipts, verification, and connectors.";
  }
  if (value === "pilot.goldens_basic") {
    return "That legacy entitlement needs a higher plan. Current plans are enforced through protected-action control-plane meters.";
  }
  if (value) {
    return "This feature needs a higher plan or an enabled entitlement.";
  }
  return null;
}

function isProblemMessage(value: string): boolean {
  const text = value.toLowerCase();
  return text.includes("failed") || text.includes("unavailable") || text.includes("not configured") || text.includes("disabled");
}

function paymentStatusLabel(billing: BillingMeResponse | null): { label: string; detail: string } {
  if (!billing) {
    return { label: "Loading", detail: "Billing status is loading." };
  }
  if (billing?.payment_provider === "manual" && billing.status === "active") {
    return { label: "Manual activation", detail: "Plan access is active through a Zroky-administered billing record." };
  }
  if (billing?.payment_subscription_ref) {
    return { label: "Confirmed", detail: "Razorpay payment is active for this billing period." };
  }
  if (billing?.payment_request_ref) {
    return { label: "Pending", detail: "Razorpay payment request is waiting for confirmation." };
  }
  return { label: "Not requested", detail: "Start a paid plan to create a Razorpay checkout order." };
}

function BillingSettingsContent() {
  const searchParams = useSearchParams();
  const budget = useBudget();
  const updateBudget = useUpdateBudget();

  const [billingMe, setBillingMe] = useState<BillingMeResponse | null>(null);
  const [billingUsage, setBillingUsage] = useState<BillingUsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState("");
  const [statusMsg, setStatusMsg] = useState("");

  const load = useCallback(async (options?: { quiet?: boolean }) => {
    const quiet = options?.quiet === true;
    if (!quiet) {
      setLoading(true);
    }
    setError(null);
    try {
      const [me, usage] = await Promise.all([getBillingMe(), getBillingUsage()]);
      setBillingMe(me);
      setBillingUsage(usage);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load billing data.");
    } finally {
      if (!quiet) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    control,
  } = useForm<BudgetFormData>({
    resolver: zodResolver(budgetSchema),
    defaultValues: {
      monthlyLimit: budget.data?.monthly_limit_usd != null ? String(budget.data.monthly_limit_usd) : "",
      threshold: String(budget.data?.threshold_percentage ?? "80"),
    },
  });

  useEffect(() => {
    if (budget.data) {
      reset({
        monthlyLimit: budget.data.monthly_limit_usd != null ? String(budget.data.monthly_limit_usd) : "",
        threshold: String(budget.data.threshold_percentage ?? "80"),
      });
    }
  }, [budget.data, reset]);

  const thresholdValue = useWatch({ name: "threshold", control });

  const onSaveBudget = handleSubmit((data: BudgetFormData) => {
    const parsedLimit = data.monthlyLimit.trim() === "" ? null : Number(data.monthlyLimit);
    const parsedThreshold = Number(data.threshold);
    setStatusMsg("");
    updateBudget.mutate(
      {
        monthly_limit_usd: Number.isFinite(parsedLimit ?? 0) ? parsedLimit : null,
        threshold_percentage: parsedThreshold,
      },
      {
        onSuccess: () => setStatusMsg("Spend limits saved."),
        onError: (err) => setStatusMsg(err instanceof Error ? err.message : "Save failed."),
      }
    );
  });

  async function changePlan(planCode: string) {
    setActionMsg("");
    try {
      const plan = PLAN_CATALOG.find((item) => item.code === planCode);
      if (planCode === "free") {
        setActionMsg("Free is the default plan. Ask Zroky support to cancel an active paid plan.");
        return;
      }
      if (!plan?.selfServe) {
        setActionMsg(`${plan?.name ?? "This plan"} is sales-led. Contact the Zroky team to activate it.`);
        return;
      }
      const key = process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID?.trim();
      if (!key) {
        setActionMsg("Razorpay key is not configured for this dashboard environment.");
        return;
      }
      setCheckoutBusy(true);
      const loaded = await loadRazorpayCheckout();
      if (!loaded || !window.Razorpay) {
        setCheckoutBusy(false);
        setActionMsg("Razorpay checkout script failed to load.");
        return;
      }

      const order = await createRazorpayOrder({ plan_code: planCode });
      const checkout = new window.Razorpay({
        key,
        amount: order.amount,
        currency: order.currency,
        name: "Zroky",
        description: `${plan.name} monthly plan`,
        order_id: order.order_id,
        handler: (response) => {
          void (async () => {
            try {
              await verifyRazorpayPayment(response);
              setActionMsg(`Payment verified for ${plan.name}. Your plan is active.`);
              await load();
            } catch (e: unknown) {
              setActionMsg(e instanceof Error ? e.message : "Payment verification failed.");
            } finally {
              setCheckoutBusy(false);
            }
          })();
        },
        modal: {
          ondismiss: () => {
            setCheckoutBusy(false);
            setActionMsg("Razorpay checkout was closed before payment.");
          },
        },
        theme: {
          color: "#111827",
        },
      });
      checkout.on("payment.failed", (response) => {
        setCheckoutBusy(false);
        setActionMsg(response.error?.description || "Razorpay payment failed.");
      });
      setActionMsg(`Opening Razorpay checkout for ${plan.name} (${formatRazorpayAmount(order.amount, order.currency)}).`);
      await load({ quiet: true });
      checkout.open();
    } catch (e: unknown) {
      setActionMsg(e instanceof Error ? e.message : "Failed to update plan.");
      setCheckoutBusy(false);
    }
  }

  const currentPlanCode = billingMe?.plan_code ?? "free";
  const currentCatalogCode = catalogPlanCode(currentPlanCode);
  const currentPlanAlias = currentPlanCode.trim().toLowerCase();
  const legacyPlanAliasNote =
    currentPlanAlias === "plus"
      ? "Legacy Plus maps to Scale entitlements."
      : currentPlanAlias === "pro"
        ? "Legacy Pro maps to Team entitlements."
      : currentPlanAlias === "pilot"
        ? "Legacy Pilot maps to grandfathered Starter entitlements. Team is the featured self-serve upgrade."
        : currentPlanAlias === "starter"
          ? "Starter is the first paid launch plan. Team is the featured self-serve upgrade."
          : null;
  const template = billingMe?.plan_template ?? {};
  const upgradeHint = upgradeHintMessage(searchParams.get("upgrade_hint"));
  const paymentStatus = paymentStatusLabel(billingMe);
  const pendingPaymentConfirmation = Boolean(billingMe?.payment_request_ref && !billingMe?.payment_subscription_ref);
  const billingTone = error ? "danger" : pendingPaymentConfirmation ? "warning" : billingMe?.status === "active" ? "success" : "neutral";
  const primaryUsageMeters = [
    {
      label: "Protected actions",
      detailLabel: "Protected actions",
      icon: <ShieldCheck aria-hidden="true" />,
      meter: billingUsage?.protected_actions,
    },
    {
      label: "Receipts",
      detailLabel: "Action receipts",
      icon: <ReceiptText aria-hidden="true" />,
      meter: billingUsage?.action_receipts,
    },
    {
      label: "Verification checks",
      detailLabel: "Verification checks",
      icon: <LockKeyhole aria-hidden="true" />,
      meter: billingUsage?.verification_checks,
    },
    {
      label: "Source mutations",
      detailLabel: "Source mutations",
      icon: <Gauge aria-hidden="true" />,
      meter: billingUsage?.source_mutations,
    },
    {
      label: "SOR connectors",
      detailLabel: "System-of-record connectors",
      icon: <CreditCard aria-hidden="true" />,
      meter: billingUsage?.active_connectors,
    },
  ];
  const advancedUsageMeters = [
    {
      label: "Policy checks",
      detailLabel: "Policy checks",
      meter: billingUsage?.policy_checks,
    },
    {
      label: "Runner executions",
      detailLabel: "Runner executions",
      meter: billingUsage?.runner_executions,
    },
    {
      label: "Source mutations",
      detailLabel: "Source mutations",
      meter: billingUsage?.source_mutations,
    },
  ];
  const entitlementCards = [
    {
      label: "Agent limit",
      value: formatEntitlement(template["agents.max"]),
      helper: "Managed AgentProfile capacity",
    },
    {
      label: "SOR connectors",
      value: formatEntitlement(template["connectors.system_of_record.max"]),
      helper: "Verification connectors included",
    },
    {
      label: "Protected actions",
      value: formatEntitlement(template["actions.protected.monthly_quota"]),
      helper: "Monthly held/controlled actions",
    },
    {
      label: "Receipts",
      value: formatEntitlement(template["actions.receipts.monthly_quota"]),
      helper: "Signed action receipts included",
    },
    {
      label: "Verification checks",
      value: formatEntitlement(template["actions.verifications.monthly_quota"]),
      helper: "System-of-record verification checks",
    },
    {
      label: "Retention",
      value: formatEntitlement(template["retention.days"]),
      helper: "Evidence retention days",
    },
  ];
  const visiblePlans = PLAN_CATALOG.filter((plan) => {
    if (plan.code === "free") return false;
    return planRank(plan.code) >= planRank(currentCatalogCode);
  });
  const heroTitle = billingMe ? `${displayPlanCode(currentPlanCode)} plan` : "Plan & Billing";
  const currentCatalogPlan = PLAN_CATALOG.find((plan) => plan.code === currentCatalogCode) ?? PLAN_CATALOG[0];
  const commandMeters = primaryUsageMeters.filter((item) =>
    ["Protected actions", "Receipts", "SOR connectors"].includes(item.label),
  );

  useEffect(() => {
    if (!pendingPaymentConfirmation) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      void load({ quiet: true });
    }, 5_000);
    return () => window.clearInterval(intervalId);
  }, [load, pendingPaymentConfirmation]);

  return (
    <SettingsScaffold className="billing-settings-page" aria-labelledby="billing-settings-title">
      <SettingsHero
        ariaLabel="Plan and billing settings"
        eyebrow="Plan & Billing"
        icon={<CreditCard aria-hidden="true" />}
        title={heroTitle}
        copy="Plan status, protected-action quotas, connector capacity, and spend limits for this workspace."
        tone={billingTone}
        pill={paymentStatus.label}
        updatedLabel={loading ? "Loading" : "Settings live"}
        notices={
          <>
            {upgradeHint ? <div className="alert-strip billing-upgrade-hint">{upgradeHint}</div> : null}
            {error ? <div className="alert-strip alert-strip-error">{error}</div> : null}
            {actionMsg ? (
              <div className={isProblemMessage(actionMsg) ? "alert-strip alert-strip-error" : "alert-strip"}>
                {actionMsg}
              </div>
            ) : null}
          </>
        }
        actions={
          <DashboardButton icon={<RefreshCw />} onClick={() => void load()} disabled={loading || checkoutBusy} variant="soft">
            Refresh
          </DashboardButton>
        }
      />

      <SettingsMetricStrip
        ariaLabel="Plan and billing summary"
        metrics={[
          {
            id: "current-plan",
            label: "Current plan",
            value: billingMe ? displayPlanCode(currentPlanCode) : "Loading",
            helper: legacyPlanAliasNote ?? billingMe?.status ?? "Loading billing status",
            tone: billingMe?.status === "active" ? "success" : "neutral",
            icon: <CreditCard aria-hidden="true" />,
          },
          {
            id: "payment",
            label: "Payment",
            value: paymentStatus.label,
            helper: paymentStatus.detail,
            tone: pendingPaymentConfirmation ? "warning" : billingMe?.payment_subscription_ref || billingMe?.payment_provider === "manual" ? "success" : "neutral",
            icon: <ReceiptText aria-hidden="true" />,
          },
          {
            id: "protected-actions",
            label: "Protected actions",
            value: formatUsageMeter(billingUsage?.protected_actions),
            helper: usageDetail("Protected actions", billingUsage?.protected_actions),
            tone: meterTone(billingUsage?.protected_actions),
            icon: <ShieldCheck aria-hidden="true" />,
          },
          {
            id: "connectors",
            label: "SOR connectors",
            value: formatUsageMeter(billingUsage?.active_connectors),
            helper: usageDetail("System-of-record connectors", billingUsage?.active_connectors),
            tone: meterTone(billingUsage?.active_connectors),
            icon: <Gauge aria-hidden="true" />,
          },
        ]}
      />

      <section className="billing-command-card" aria-label="Subscription status">
        <div className="billing-command-main">
          <span className="billing-command-kicker">Subscription control plane</span>
          <h2>Run protected agents on the {displayPlanCode(currentPlanCode)} plan.</h2>
          <p>
            Quota, payment status, and evidence limits stay attached to this workspace before agent actions reach
            runners, systems of record, or signed receipts.
          </p>
          <div className="billing-command-pills" aria-label="Billing posture">
            <span>
              <ShieldCheck aria-hidden="true" />
              {billingMe?.status ?? "loading"}
            </span>
            <span>
              <ReceiptText aria-hidden="true" />
              {paymentStatus.label}
            </span>
            <span>
              <Gauge aria-hidden="true" />
              {billingUsage?.metering_health.state ?? "metering"}
            </span>
          </div>
        </div>
        <div className="billing-command-panel">
          <div className="billing-command-panel-head">
            <span>Current package</span>
            <strong>{currentCatalogPlan?.name ?? displayPlanCode(currentPlanCode)}</strong>
          </div>
          <p>{currentCatalogPlan?.fit}</p>
          <div className="billing-command-meter-list">
            {commandMeters.map((item) => (
              <div className="billing-command-meter" key={item.label}>
                <div>
                  <span>{item.label}</span>
                  <strong>{formatUsageMeter(item.meter)}</strong>
                </div>
                {hasMeterLimit(item.meter) ? (
                  <div className="billing-command-meter-track" aria-hidden="true">
                    <span style={{ width: `${meterPercent(item.meter)}%` }} />
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </section>

      <SettingsSection
        id="billing-plan-controls"
        eyebrow="Plan"
        title="Upgrade path"
        copy="Choose the next subscription level for protected actions, receipts, verifiers, and system-of-record connectors."
      >

        {isProblemMessage(actionMsg) ? (
          <div className="settings-config-warning" role="status">
            <AlertTriangle aria-hidden="true" />
            <div>
              <strong>Billing action is not ready in this environment.</strong>
              <span>{actionMsg}</span>
            </div>
          </div>
        ) : null}

        {loading && !billingMe ? (
          <div className="loading" />
        ) : (
          <div className="billing-plans-grid">
            {visiblePlans.map((plan) => {
              const isCurrent = plan.code === currentCatalogCode;
              const canChangeToPlan = !isCurrent && planRank(plan.code) > planRank(currentCatalogCode);
              return (
                <div
                  key={plan.code}
                  className={`billing-plan-card${isCurrent ? " billing-plan-current" : ""}`}
                  role="article"
                  aria-label={`${plan.name} plan`}
                >
                  <div className="billing-plan-topline">
                    <span>{plan.selfServe ? "Self serve" : "Contract"}</span>
                    {isCurrent && <span className="pill pill-green billing-plan-badge">Current</span>}
                  </div>
                  <div className="billing-plan-name">{plan.name}</div>
                  <div className="billing-plan-price">
                    {plan.monthlyCostUsd == null ? "Custom" : `$${plan.monthlyCostUsd.toFixed(2)}`}{" "}
                    <span className="billing-plan-period">/ mo</span>
                  </div>
                  <p className="billing-plan-fit">{plan.fit}</p>
                  <div className="billing-plan-proof">
                    <LockKeyhole aria-hidden="true" />
                    <span>{plan.proof}</span>
                  </div>
                  <ul className="billing-plan-features">
                    {plan.features.map((feature) => (
                      <li key={feature}>
                        <CheckCircle2 aria-hidden="true" />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                  {canChangeToPlan && (
                    <DashboardButton
                      type="button"
                      className="billing-plan-btn"
                      variant="primary"
                      onClick={() => void changePlan(plan.code)}
                      disabled={loading || checkoutBusy}
                    >
                      {plan.selfServe ? (checkoutBusy ? "Opening checkout..." : `Pay with Razorpay for ${plan.name}`) : `Contact Zroky for ${plan.name}`}
                      <ArrowRight aria-hidden="true" />
                    </DashboardButton>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </SettingsSection>

      {billingMe && (
        <SettingsSection
          id="billing-usage-entitlements"
          eyebrow="Usage"
          title="Usage and entitlements"
          copy={`${billingMe.status} plan for org ${billingMe.org_id}. These meters are hard plan gates until overage billing is explicitly enabled.`}
          actions={
            <StatusPill
              value={billingUsage?.metering_health.state ?? "loading"}
              label={billingUsage?.metering_health.state ?? "Loading"}
              tone={billingUsage?.metering_health.state === "ok" ? "success" : "warning"}
            />
          }
        >

          <div className="billing-usage-layout">
            <div className="billing-meter-grid billing-usage-kpis" role="region" aria-label="Protected action usage">
              {primaryUsageMeters.map((item) => (
                <div className={`billing-meter-card billing-meter-${meterTone(item.meter)}`} key={item.label}>
                  <div className="billing-meter-card-head">
                    <span>{item.icon}</span>
                    <strong>{item.label}</strong>
                  </div>
                  <div className="billing-meter-value">{formatUsageMeter(item.meter)}</div>
                  {hasMeterLimit(item.meter) ? (
                    <div className="billing-meter-track" aria-label={`${Math.round(meterPercent(item.meter))}% used`}>
                      <span style={{ width: `${meterPercent(item.meter)}%` }} />
                    </div>
                  ) : null}
                  <small>{usageDetail(item.detailLabel, item.meter)}</small>
                </div>
              ))}
            </div>

            <aside className="billing-entitlement-panel" aria-label="Plan entitlements">
              <h3>Plan limits</h3>
              <div className="billing-entitlement-list">
                {entitlementCards.map((item) => (
                  <div key={item.label}>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                    <small>{item.helper}</small>
                  </div>
                ))}
              </div>
            </aside>
          </div>

          <div className="actions billing-control-links">
            <DashboardButtonLink href="/actions" variant="primary">
              Open Actions
            </DashboardButtonLink>
            <DashboardButtonLink href="/outcomes" variant="soft">
              Open bypass risk
            </DashboardButtonLink>
            <DashboardButtonLink href="/evidence" variant="soft">
              Open Evidence
            </DashboardButtonLink>
          </div>

          <details className="billing-advanced-meters">
            <summary>Advanced metering</summary>
            <div className="kpi-grid billing-usage-kpis">
              {advancedUsageMeters.map((item) => (
                <div className="kpi-card" key={item.label}>
                  <div className="kpi-value">{formatUsageMeter(item.meter)}</div>
                  <div className="kpi-label">{item.label}</div>
                  <small>{usageDetail(item.detailLabel, item.meter)}</small>
                </div>
              ))}
            </div>
          </details>
        </SettingsSection>
      )}

      <SettingsSection
        id="billing-spend-limits"
        eyebrow="Spend guard"
        title="Spend limits"
        copy="Saved monthly AI spend controls used by the backend budget guard and alerting flow."
      >

        <form onSubmit={onSaveBudget} className="billing-budget-form">
          <div className="field">
            <label htmlFor="spend-limit" className="field-label">
              Monthly limit (USD) - leave blank for no limit
            </label>
            <input
              id="spend-limit"
              type="number"
              className="input"
              step="0.01"
              placeholder="e.g. 100"
              {...register("monthlyLimit")}
              disabled={updateBudget.isPending}
            />
            {errors.monthlyLimit && <span className="field-error">{errors.monthlyLimit.message}</span>}
          </div>

          <div className="field">
            <label htmlFor="alert-threshold" className="field-label">
              Alert threshold (% of limit)
            </label>
            <input
              id="alert-threshold"
              type="number"
              className="input"
              {...register("threshold")}
              disabled={updateBudget.isPending}
            />
            {errors.threshold && <span className="field-error">{errors.threshold.message}</span>}
            <p className="field-hint">
              You&apos;ll receive an alert when you reach {thresholdValue || "-"}% of your limit.
            </p>
          </div>

          {statusMsg && (
            <p className={statusMsg.includes("saved") ? "field-success" : "field-error"}>
              {statusMsg}
            </p>
          )}

          <div className="actions">
            <DashboardButton type="submit" variant="primary" loading={updateBudget.isPending} disabled={updateBudget.isPending}>
              {updateBudget.isPending ? "Saving..." : "Save limits"}
            </DashboardButton>
          </div>
        </form>
      </SettingsSection>

    </SettingsScaffold>
  );
}

export default function BillingPage() {
  return (
    <Suspense fallback={<SettingsScaffold className="billing-settings-page"><SettingsSection title="Plan & Billing"><div className="loading" /></SettingsSection></SettingsScaffold>}>
      <BillingSettingsContent />
    </Suspense>
  );
}
