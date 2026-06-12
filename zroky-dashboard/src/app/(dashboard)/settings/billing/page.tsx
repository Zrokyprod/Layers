"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useSearchParams } from "next/navigation";
import { AlertTriangle, CreditCard, Gauge, ReceiptText, ShieldCheck } from "lucide-react";

import { useBudget, useBudgetStatus, useUpdateBudget } from "@/lib/hooks";
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
    features: ["50K events/mo", "7 day retention", "2 seats", "Capture and trace review"],
    selfServe: false,
  },
  {
    code: "pilot",
    name: "Pilot",
    monthlyCostUsd: 29,
    features: ["500K events/mo", "30 day retention", "5 seats", "100 mocked-tool replay runs/mo", "100 Golden traces"],
    selfServe: true,
  },
  {
    code: "pro",
    name: "Pro",
    monthlyCostUsd: 149,
    features: [
      "3M events/mo",
      "90 day retention",
      "10 seats",
      "100 real LLM replay runs/mo",
      "1,000 mocked-tool replay runs/mo",
      "100 live-sandbox replay runs/mo",
      "1,000 Golden traces",
      "CI gates and outcome attribution",
    ],
    selfServe: true,
  },
  {
    code: "enterprise",
    name: "Enterprise",
    monthlyCostUsd: null,
    features: ["Unlimited events and replay limits", "Unlimited seats and projects", "Private replay worker", "SSO, audit logs, custom retention, provider key vault"],
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
  return normalized === "plus" ? "pro" : normalized;
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

function upgradeHintMessage(value: string | null): string | null {
  if (value === "replay.monthly_runs") {
    return "Replay runs are gated by your current plan. Upgrade to unlock more protected replay capacity.";
  }
  if (value === "pilot.goldens_basic") {
    return "Goldens require a plan with release-safety entitlements.";
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
  const budgetStatus = useBudgetStatus();
  const updateBudget = useUpdateBudget();

  const [billingMe, setBillingMe] = useState<BillingMeResponse | null>(null);
  const [billingUsage, setBillingUsage] = useState<BillingUsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState("");
  const [statusMsg, setStatusMsg] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [me, usage] = await Promise.all([getBillingMe(), getBillingUsage()]);
      setBillingMe(me);
      setBillingUsage(usage);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load billing data.");
    } finally {
      setLoading(false);
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
      checkout.open();
    } catch (e: unknown) {
      setActionMsg(e instanceof Error ? e.message : "Failed to update plan.");
      setCheckoutBusy(false);
    }
  }

  const currentPlanCode = billingMe?.plan_code ?? "free";
  const currentCatalogCode = catalogPlanCode(currentPlanCode);
  const legacyPlanAliasNote = currentPlanCode.trim().toLowerCase() === "plus" ? "Legacy Plus maps to Pro entitlements." : null;
  const template = billingMe?.plan_template ?? {};
  const upgradeHint = upgradeHintMessage(searchParams.get("upgrade_hint"));
  const paymentStatus = paymentStatusLabel(billingMe);

  return (
    <div className="page-content">
      {upgradeHint && <div className="alert-strip billing-upgrade-hint">{upgradeHint}</div>}
      {error && <div className="alert-strip alert-strip-error">{error}</div>}
      {actionMsg && (
        <div className={isProblemMessage(actionMsg) ? "alert-strip alert-strip-error" : "alert-strip"}>
          {actionMsg}
        </div>
      )}

      <section className="settings-summary-grid">
        <article className="panel settings-summary-card">
          <CreditCard aria-hidden="true" />
          <span>Current plan</span>
          <strong>{displayPlanCode(currentPlanCode)}</strong>
          <small>{legacyPlanAliasNote ?? billingMe?.status ?? "Loading billing status"}</small>
        </article>
        <article className="panel settings-summary-card">
          <ReceiptText aria-hidden="true" />
          <span>Payment</span>
          <strong>{paymentStatus.label}</strong>
          <small>{paymentStatus.detail}</small>
        </article>
        <article className="panel settings-summary-card">
          <Gauge aria-hidden="true" />
          <span>Event usage</span>
          <strong>{formatUsageMeter(billingUsage?.calls)}</strong>
          <small>{usageDetail("Capture", billingUsage?.calls)}</small>
        </article>
        <article className="panel settings-summary-card">
          <ShieldCheck aria-hidden="true" />
          <span>SLA tier</span>
          <strong>{billingMe?.sla_tier ?? "standard"}</strong>
          <small>Entitlements are read from backend plan state.</small>
        </article>
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Plan &amp; Pricing</h3>
            <p>Your current plan and Razorpay checkout upgrades.</p>
          </div>
        </header>

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
            {PLAN_CATALOG.map((plan) => {
              const isCurrent = plan.code === currentCatalogCode;
              return (
                <div key={plan.code} className={`billing-plan-card${isCurrent ? " billing-plan-current" : ""}`}>
                  {isCurrent && <span className="pill pill-green billing-plan-badge">Current</span>}
                  <div className="billing-plan-name">{plan.name}</div>
                  <div className="billing-plan-price">
                    {plan.monthlyCostUsd == null ? "Custom" : `$${plan.monthlyCostUsd.toFixed(2)}`}{" "}
                    <span className="billing-plan-period">/ mo</span>
                  </div>
                  <ul className="billing-plan-features">
                    {plan.features.map((feature) => (
                      <li key={feature}>✓ {feature}</li>
                    ))}
                  </ul>
                  {!isCurrent && (
                    <button
                      type="button"
                      className="btn btn-primary billing-plan-btn"
                      onClick={() => void changePlan(plan.code)}
                      disabled={loading || checkoutBusy}
                    >
                      {plan.selfServe ? (checkoutBusy ? "Opening checkout..." : `Pay with Razorpay for ${plan.name}`) : `Contact us for ${plan.name}`}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {billingMe && (
        <section className="panel">
          <header className="panel-header">
            <h3>Usage &amp; Entitlements</h3>
            <p>
              {billingMe.status} plan for org {billingMe.org_id}
            </p>
          </header>

          <div className="kpi-grid billing-usage-kpis">
            <div className="kpi-card">
              <div className="kpi-value">{formatUsageMeter(billingUsage?.calls)}</div>
              <div className="kpi-label">Capture events</div>
              <small>{usageDetail("Capture", billingUsage?.calls)}</small>
            </div>
            <div className="kpi-card">
              <div className="kpi-value">{formatUsageMeter(billingUsage?.replay)}</div>
              <div className="kpi-label">Replay runs</div>
              <small>{usageDetail("Replay", billingUsage?.replay)}</small>
            </div>
            <div className="kpi-card">
              <div className="kpi-value">{formatUsageMeter(billingUsage?.goldens)}</div>
              <div className="kpi-label">Golden traces</div>
              <small>{usageDetail("Goldens", billingUsage?.goldens)}</small>
            </div>
            <div className="kpi-card">
              <div className="kpi-value">{billingUsage?.metering_health.state ?? "loading"}</div>
              <div className="kpi-label">Metering health</div>
              <small>{billingUsage?.metering_health.detail ?? `Policy: ${billingUsage?.metering_health.failure_policy ?? "unknown"}`}</small>
            </div>
          </div>

          <div className="kpi-grid billing-usage-kpis">
            <div className="kpi-card">
              <div className="kpi-value">{formatEntitlement(template["events.monthly_quota"])}</div>
              <div className="kpi-label">Plan event limit</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-value">{formatEntitlement(template["replay.monthly_runs"])}</div>
              <div className="kpi-label">Plan replay limit</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-value">{formatEntitlement(template["seats.included"])}</div>
              <div className="kpi-label">Included seats</div>
            </div>
          </div>
        </section>
      )}

      <section className="panel">
        <header className="panel-header">
          <h3>Spend Limits</h3>
          <p>Saved monthly AI spend controls used by the backend budget guard and alerting flow.</p>
        </header>

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
            <button type="submit" className="btn btn-primary" disabled={updateBudget.isPending}>
              {updateBudget.isPending ? "Saving..." : "Save limits"}
            </button>
          </div>
        </form>
      </section>

      <section className="panel">
        <header className="panel-header">
          <h3>Invoices</h3>
          <p>Razorpay is the self-serve payment surface; Zroky verifies paid plans into entitlements.</p>
        </header>
        <div className="actions billing-invoices-empty">
          <span className="hint">Razorpay payment receipts are confirmed immediately after checkout verification.</span>
          {!billingMe?.payment_request_ref && !billingMe?.payment_subscription_ref && (
            <span className="hint">Start a paid plan to create a Razorpay payment reference.</span>
          )}
        </div>
      </section>
    </div>
  );
}

export default function BillingPage() {
  return (
    <Suspense fallback={<div className="page-content"><section className="panel"><div className="loading" /></section></div>}>
      <BillingSettingsContent />
    </Suspense>
  );
}
