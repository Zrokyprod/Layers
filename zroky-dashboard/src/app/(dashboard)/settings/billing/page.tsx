"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  CheckCircle2,
  CreditCard,
  Gauge,
  LockKeyhole,
  ReceiptText,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { SettingsHero, SettingsScaffold, SettingsSection } from "@/components/settings-scaffold";
import { StatusPill } from "@/components/status-pill";
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
  summary: string;
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
      "1 connector",
      "2 approver seats",
      "7-day evidence retention",
      "Slack approvals",
      "Hard cap",
    ],
    fit: "For the first protected agent and basic evidence collection.",
    summary: "For testing one protected workflow.",
    selfServe: false,
  },
  {
    code: "starter",
    name: "Starter",
    monthlyCostUsd: 49,
    features: [
      "2K protected actions/mo",
      "3 managed agents",
      "3 connectors",
      "Unlimited approver seats",
      "30-day evidence retention",
      "Slack approvals",
      "Scoped policy rules and dry-run",
      "Basic bypass detection",
      "$0.03/action overage",
    ],
    fit: "For the first production workflow without starving the agent during evaluation.",
    summary: "First paid production workflow.",
    selfServe: true,
  },
  {
    code: "team",
    name: "Team",
    monthlyCostUsd: 199,
    features: [
      "10K protected actions/mo",
      "10 managed agents",
      "6 connectors",
      "Unlimited approver seats",
      "90-day evidence retention",
      "Slack approvals",
      "Scoped policy rules and dry-run",
      "Bypass detection",
      "Audit manifest export",
      "$0.025/action overage",
    ],
    fit: "For teams scaling agents that touch money, access, customer state, or production systems.",
    summary: "For teams running multiple agents.",
    selfServe: true,
  },
  {
    code: "scale",
    name: "Scale",
    monthlyCostUsd: 499,
    features: [
      "50K protected actions/mo",
      "Unlimited managed agents",
      "All standard connectors",
      "Unlimited approver seats",
      "180-day evidence retention",
      "Slack approvals",
      "Scoped policy rules and dry-run",
      "Bypass detection",
      "Audit manifest export",
      "$0.015/action overage",
    ],
    fit: "For organizations running high-volume autonomous workflows across many systems of record.",
    summary: "For high-volume autonomous workflows.",
    selfServe: true,
  },
  {
    code: "enterprise",
    name: "Enterprise",
    monthlyCostUsd: null,
    features: [
      "Custom protected action volume",
      "Unlimited or contracted agent and connector capacity",
      "Custom evidence retention",
      "Slack approvals",
      "Scoped policy rules and dry-run",
      "Custom bypass detection",
      "Audit manifest export API",
      "Customer-hosted runner scale-out",
      "SSO, DPA, and private deployment support",
    ],
    fit: "For enterprises rolling out high-risk AI agents across business units.",
    summary: "Custom rollout for business units.",
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

function formatPlanPrice(plan: PlanCatalogItem): string {
  if (plan.monthlyCostUsd == null) {
    return "Custom";
  }
  return `$${plan.monthlyCostUsd.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function formatUsageMeter(meter: BillingUsageMeter | null | undefined): string {
  if (!meter) return "Loading";
  const used = meter.used.toLocaleString();
  if (meter.unlimited || meter.limit == null) return `${used} used`;
  return `${used} / ${meter.limit.toLocaleString()}`;
}

function usageDetail(label: string, meter: BillingUsageMeter | null | undefined): string {
  if (!meter) return `${label} usage is loading.`;
  if (meter.state === "exceeded") {
    const overage = meter.overage ?? 0;
    if (overage > 0) return `${label} limit exceeded by ${overage.toLocaleString()}.`;
    if (!meter.unlimited && meter.limit != null && meter.used >= meter.limit) return `${label} limit reached.`;
    return `${label} is over its plan limit.`;
  }
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

function meterPercentLabel(meter: BillingUsageMeter | null | undefined): string {
  const percent = meterPercent(meter);
  if (percent === 0) return "0% used";
  if (percent < 1) return "<1% used";
  return `${Number(percent.toFixed(1))}% used`;
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
  if ((billing.plan_code ?? "").trim().toLowerCase() === "free") {
    return { label: "Free plan", detail: "No payment method is required on the Free plan." };
  }
  return { label: "Not requested", detail: "Start a paid plan to create a Razorpay checkout order." };
}

function BillingSettingsContent() {
  const searchParams = useSearchParams();

  const [billingMe, setBillingMe] = useState<BillingMeResponse | null>(null);
  const [billingUsage, setBillingUsage] = useState<BillingUsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutPlanCode, setCheckoutPlanCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState("");

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
      setCheckoutPlanCode(planCode);
      const loaded = await loadRazorpayCheckout();
      if (!loaded || !window.Razorpay) {
        setCheckoutPlanCode(null);
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
              setCheckoutPlanCode(null);
            }
          })();
        },
        modal: {
          ondismiss: () => {
            setCheckoutPlanCode(null);
            setActionMsg("Razorpay checkout was closed before payment.");
          },
        },
        theme: {
          color: "#111827",
        },
      });
      checkout.on("payment.failed", (response) => {
        setCheckoutPlanCode(null);
        setActionMsg(response.error?.description || "Razorpay payment failed.");
      });
      setActionMsg(`Opening Razorpay checkout for ${plan.name} (${formatRazorpayAmount(order.amount, order.currency)}).`);
      await load({ quiet: true });
      checkout.open();
    } catch (e: unknown) {
      setActionMsg(e instanceof Error ? e.message : "Failed to update plan.");
      setCheckoutPlanCode(null);
    }
  }

  const checkoutBusy = checkoutPlanCode != null;
  const billingRecordUnavailable = !loading && !billingMe;
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
      label: "SOR connectors",
      detailLabel: "System-of-record connectors",
      icon: <Gauge aria-hidden="true" />,
      meter: billingUsage?.active_connectors,
    },
  ];
  const visiblePlans = PLAN_CATALOG.filter((plan) => {
    if (plan.code === "free") return false;
    return planRank(plan.code) >= planRank(currentCatalogCode);
  });
  const currentCatalogPlan = PLAN_CATALOG.find((plan) => plan.code === currentCatalogCode) ?? PLAN_CATALOG[0];

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
        title="Plan & Billing"
        copy="Review your workspace plan, payment status, and monthly control-plane usage."
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

      {loading && !billingMe ? (
        <div className="loading" />
      ) : billingRecordUnavailable ? (
        <section className="billing-unavailable-state" aria-label="Billing unavailable">
          <CreditCard aria-hidden="true" />
          <div>
            <h2>Billing data unavailable</h2>
            <p>Your current plan and usage could not be confirmed. No fallback plan has been assumed.</p>
          </div>
          <DashboardButton icon={<RefreshCw />} onClick={() => void load()} variant="primary">
            Retry
          </DashboardButton>
        </section>
      ) : (
        <section className="billing-overview-grid" aria-label="Billing overview">
          <article className="billing-current-card">
            <div className="billing-card-head">
              <span>Current plan</span>
              <StatusPill
                value={billingMe?.status ?? "loading"}
                label={billingMe?.status ?? "Loading"}
                tone={billingMe?.status === "active" ? "success" : "neutral"}
              />
            </div>
            <h2>{displayPlanCode(currentPlanCode)}</h2>
            <p>{legacyPlanAliasNote ?? currentCatalogPlan.fit}</p>
            <div className="billing-current-list">
              <div>
                <span>Payment</span>
                <strong>{paymentStatus.label}</strong>
                <small>{paymentStatus.detail}</small>
              </div>
              <div>
                <span>Metering</span>
                <strong>{billingUsage?.metering_health.state ?? "Loading"}</strong>
                <small>{billingUsage?.period_month ? `Usage period ${billingUsage.period_month}` : "Monthly usage period"}</small>
              </div>
              <div>
                <span>Workspace</span>
                <strong>{billingMe?.org_id ?? "Loading"}</strong>
                <small>{billingMe?.current_period_end ? `Renews ${billingMe.current_period_end}` : "Billing record is live"}</small>
              </div>
            </div>
          </article>

          <article className="billing-usage-card">
            <div className="billing-card-head">
              <span>Usage this month</span>
              <StatusPill
                value={billingUsage?.metering_health.state ?? "loading"}
                label={billingUsage?.metering_health.state ?? "Loading"}
                tone={billingUsage?.metering_health.state === "ok" ? "success" : "warning"}
              />
            </div>
            <div className="billing-usage-list" role="region" aria-label="Protected action usage">
              {primaryUsageMeters.map((item) => (
                <div className={`billing-usage-row billing-meter-${meterTone(item.meter)}`} key={item.label}>
                  <span className="billing-usage-icon">{item.icon}</span>
                  <div>
                    <strong>{item.label}</strong>
                    <small>
                      {usageDetail(item.detailLabel, item.meter)}
                      {hasMeterLimit(item.meter) ? (
                        <span className="billing-meter-percent"> · {meterPercentLabel(item.meter)}</span>
                      ) : null}
                    </small>
                  </div>
                  <span className="billing-usage-value">{formatUsageMeter(item.meter)}</span>
                  {hasMeterLimit(item.meter) ? (
                    <div className="billing-meter-progress">
                      <div className="billing-meter-track" aria-hidden="true">
                        <span style={{ width: `${meterPercent(item.meter)}%` }} />
                      </div>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </article>
        </section>
      )}

      <SettingsSection
        id="billing-plan-controls"
        eyebrow="Plan"
        title="Available plans"
        copy="Upgrade when you need more protected actions, connectors, receipts, or retention."
      >
        {loading && !billingMe ? (
          <div className="loading" />
        ) : (
          <div className="billing-plans-grid">
            {visiblePlans.map((plan) => {
              const isCurrent = plan.code === currentCatalogCode;
              const canChangeToPlan = Boolean(billingMe) && !isCurrent && planRank(plan.code) > planRank(currentCatalogCode);
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
                    {formatPlanPrice(plan)}
                    {plan.monthlyCostUsd == null ? null : <span className="billing-plan-period"> / mo</span>}
                  </div>
                  <p className="billing-plan-summary">{plan.summary}</p>
                  <ul className="billing-plan-features">
                    {plan.features.slice(0, 3).map((feature) => (
                      <li key={feature}>
                        <CheckCircle2 aria-hidden="true" />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                  {isCurrent ? (
                    <span className="billing-plan-current-label">Current plan</span>
                  ) : canChangeToPlan && plan.selfServe ? (
                    <DashboardButton
                      type="button"
                      className="billing-plan-btn"
                      variant="primary"
                      onClick={() => void changePlan(plan.code)}
                      disabled={loading || checkoutBusy}
                      loading={checkoutPlanCode === plan.code}
                    >
                      {checkoutPlanCode === plan.code ? "Opening checkout" : `Upgrade to ${plan.name}`}
                    </DashboardButton>
                  ) : canChangeToPlan ? (
                    <DashboardButtonLink
                      className="billing-plan-btn"
                      href="/contact?subject=enterprise-plan"
                      variant="primary"
                    >
                      Contact sales
                    </DashboardButtonLink>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
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
