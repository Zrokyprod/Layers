"use client";

import Script from "next/script";
import { useCallback, useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { useBudget, useUpdateBudget } from "@/lib/hooks";
import { budgetSchema, type BudgetFormData } from "@/lib/schemas";
import {
  createBillingPortal,
  createRazorpayOrder,
  getBillingMe,
  verifyRazorpayPayment,
} from "@/lib/api";
import type { BillingMeResponse } from "@/lib/types";

type PlanCatalogItem = {
  code: string;
  name: string;
  monthlyCostUsd: number | null;
  features: string[];
  selfServe: boolean;
};

const PLAN_CATALOG: PlanCatalogItem[] = [
  {
    code: "free",
    name: "Free",
    monthlyCostUsd: 0,
    features: ["50K events/mo", "7 day retention", "2 seats"],
    selfServe: false,
  },
  {
    code: "pro",
    name: "Pro",
    monthlyCostUsd: 29,
    features: ["500K events/mo", "30 day retention", "5 seats", "100 replay runs/mo"],
    selfServe: true,
  },
  {
    code: "plus",
    name: "Plus",
    monthlyCostUsd: 99,
    features: ["3M events/mo", "90 day retention", "10 seats", "Real LLM replay"],
    selfServe: true,
  },
  {
    code: "enterprise",
    name: "Enterprise",
    monthlyCostUsd: null,
    features: ["Unlimited scale", "Dedicated rollout", "SSO", "SLA tier"],
    selfServe: false,
  },
];

type RazorpaySuccessResponse = {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
};

type RazorpayFailureResponse = {
  error?: {
    code?: string;
    description?: string;
    reason?: string;
  };
};

type RazorpayOptions = {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  order_id: string;
  handler: (response: RazorpaySuccessResponse) => void;
  notes?: Record<string, string>;
  theme?: {
    color?: string;
  };
  modal?: {
    ondismiss?: () => void;
  };
};

type RazorpayInstance = {
  open: () => void;
  on: (event: "payment.failed", callback: (response: RazorpayFailureResponse) => void) => void;
};

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayOptions) => RazorpayInstance;
  }
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

export default function BillingPage() {
  const budget = useBudget();
  const updateBudget = useUpdateBudget();

  const [billingMe, setBillingMe] = useState<BillingMeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState("");
  const [statusMsg, setStatusMsg] = useState("");
  const [checkoutPlanCode, setCheckoutPlanCode] = useState<string | null>(null);
  const [razorpayReady, setRazorpayReady] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setBillingMe(await getBillingMe());
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
        setActionMsg("Free is the default plan. Contact support to cancel an active paid subscription.");
        return;
      }
      if (!plan?.selfServe) {
        setActionMsg(`${plan?.name ?? "This plan"} is sales-led. Contact the Zroky team to activate it.`);
        return;
      }
      const key = process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID?.trim();
      if (!key) {
        setActionMsg("Razorpay checkout is not configured for this dashboard.");
        return;
      }
      if (!razorpayReady || !window.Razorpay) {
        setActionMsg("Razorpay checkout is still loading. Try again in a moment.");
        return;
      }

      setCheckoutPlanCode(planCode);
      const order = await createRazorpayOrder({ plan_code: planCode });
      let paymentCompleted = false;
      const checkout = new window.Razorpay({
        key,
        amount: order.amount,
        currency: order.currency,
        name: "Zroky",
        description: `${plan.name} monthly plan`,
        order_id: order.order_id,
        notes: {
          org_id: order.org_id,
          plan_code: order.plan_code ?? planCode,
        },
        theme: {
          color: "#111827",
        },
        modal: {
          ondismiss: () => {
            if (!paymentCompleted) {
              setCheckoutPlanCode(null);
              setActionMsg("Checkout cancelled before payment.");
            }
          },
        },
        handler: async (response) => {
          paymentCompleted = true;
          try {
            await verifyRazorpayPayment(response);
            setActionMsg("Payment verified successfully. Your plan is active.");
            await load();
          } catch (e: unknown) {
            setActionMsg(e instanceof Error ? e.message : "Payment verification failed.");
          } finally {
            setCheckoutPlanCode(null);
          }
        },
      });

      checkout.on("payment.failed", (response) => {
        paymentCompleted = true;
        setCheckoutPlanCode(null);
        setActionMsg(response.error?.description ?? "Payment failed. No plan change was applied.");
      });
      checkout.open();
    } catch (e: unknown) {
      setActionMsg(e instanceof Error ? e.message : "Failed to update plan.");
      setCheckoutPlanCode(null);
    }
  }

  async function openBillingPortal() {
    setActionMsg("");
    try {
      const portal = await createBillingPortal();
      window.open(portal.portal_url, "_self");
    } catch (e: unknown) {
      setActionMsg(e instanceof Error ? e.message : "Failed to open billing portal.");
    }
  }

  const currentPlanCode = billingMe?.plan_code ?? "free";
  const template = billingMe?.plan_template ?? {};
  const razorpayConfigured = Boolean(process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID?.trim());

  return (
    <div className="page-content">
      <Script
        src="https://checkout.razorpay.com/v1/checkout.js"
        strategy="afterInteractive"
        onLoad={() => setRazorpayReady(true)}
        onError={() => setActionMsg("Razorpay checkout script failed to load.")}
      />

      {error && <div className="alert-strip alert-strip-error">{error}</div>}
      {actionMsg && (
        <div className={actionMsg.includes("success") ? "alert-strip" : "alert-strip alert-strip-error"}>
          {actionMsg}
        </div>
      )}

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Plan &amp; Pricing</h3>
            <p>Your current plan and self-serve upgrades.</p>
          </div>
          {!razorpayConfigured && (
            <button
              type="button"
              className="btn btn-soft"
              onClick={() => void openBillingPortal()}
              disabled={loading || !billingMe?.stripe_customer_id}
              title={!billingMe?.stripe_customer_id ? "Start checkout first to create a Stripe customer." : undefined}
            >
              Manage in Stripe
            </button>
          )}
        </header>

        {loading && !billingMe ? (
          <div className="loading" />
        ) : (
          <div className="billing-plans-grid">
            {PLAN_CATALOG.map((plan) => {
              const isCurrent = plan.code === currentPlanCode;
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
                      disabled={loading || checkoutPlanCode != null}
                    >
                      {checkoutPlanCode === plan.code
                        ? "Opening Razorpay..."
                        : plan.selfServe
                          ? `Checkout for ${plan.name}`
                          : `Contact us for ${plan.name}`}
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
            <h3>Current Plan Entitlements</h3>
            <p>
              {billingMe.status} plan for org {billingMe.org_id}
            </p>
          </header>

          <div className="kpi-grid billing-usage-kpis">
            <div className="kpi-card">
              <div className="kpi-value">{formatEntitlement(template["events.monthly_quota"])}</div>
              <div className="kpi-label">Events / month</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-value">{formatEntitlement(template["replay.monthly_runs"])}</div>
              <div className="kpi-label">Replay runs / month</div>
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
          <p>Hard cap on monthly AI cost. Requests are blocked when the limit is reached.</p>
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
          <h3>Receipts</h3>
          <p>
            {razorpayConfigured
              ? "Razorpay confirms payments after checkout and Zroky verifies the payment signature before activating a plan."
              : "Stripe is the source of truth for invoices, payment methods, and receipts."}
          </p>
        </header>
        <div className="actions billing-invoices-empty">
          {!razorpayConfigured && (
            <button
              type="button"
              className="btn btn-soft"
              onClick={() => void openBillingPortal()}
              disabled={!billingMe?.stripe_customer_id}
            >
              Open invoice portal
            </button>
          )}
          {razorpayConfigured ? (
            <span className="hint">Razorpay payment receipts are available after a successful checkout.</span>
          ) : (
            !billingMe?.stripe_customer_id && (
              <span className="hint">Create a paid checkout session before opening the Stripe customer portal.</span>
            )
          )}
        </div>
      </section>
    </div>
  );
}
