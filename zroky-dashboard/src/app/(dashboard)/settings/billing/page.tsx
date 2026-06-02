"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useSearchParams } from "next/navigation";
import { AlertTriangle, CreditCard, Gauge, ReceiptText, ShieldCheck } from "lucide-react";

import { useBudget, useBudgetStatus, useUpdateBudget } from "@/lib/hooks";
import { budgetSchema, type BudgetFormData } from "@/lib/schemas";
import {
  createBillingCheckout,
  createBillingPortal,
  getBillingMe,
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

function formatEntitlement(value: unknown): string {
  if (typeof value === "number") {
    return value < 0 ? "Unlimited" : value.toLocaleString();
  }
  if (typeof value === "boolean") {
    return value ? "Enabled" : "Disabled";
  }
  return value == null ? "Not configured" : String(value);
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

function BillingSettingsContent() {
  const searchParams = useSearchParams();
  const budget = useBudget();
  const budgetStatus = useBudgetStatus();
  const updateBudget = useUpdateBudget();

  const [billingMe, setBillingMe] = useState<BillingMeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState("");
  const [statusMsg, setStatusMsg] = useState("");

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
        setActionMsg("Free is the default plan. Use Stripe portal to cancel an active paid subscription.");
        return;
      }
      if (!plan?.selfServe) {
        setActionMsg(`${plan?.name ?? "This plan"} is sales-led. Contact the Zroky team to activate it.`);
        return;
      }
      const checkout = await createBillingCheckout({ plan_code: planCode });
      window.open(checkout.checkout_url, "_self");
    } catch (e: unknown) {
      setActionMsg(e instanceof Error ? e.message : "Failed to update plan.");
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
  const upgradeHint = upgradeHintMessage(searchParams.get("upgrade_hint"));

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
          <strong>{currentPlanCode.toUpperCase()}</strong>
          <small>{billingMe?.status ?? "Loading billing status"}</small>
        </article>
        <article className="panel settings-summary-card">
          <ReceiptText aria-hidden="true" />
          <span>Stripe portal</span>
          <strong>{billingMe?.stripe_customer_id ? "Ready" : "Not created"}</strong>
          <small>{billingMe?.stripe_customer_id ? "Customer portal can open." : "Checkout must create a customer first."}</small>
        </article>
        <article className="panel settings-summary-card">
          <Gauge aria-hidden="true" />
          <span>Budget status</span>
          <strong>{budgetStatus.data?.status ?? "Unknown"}</strong>
          <small>{budgetStatus.data?.limit_usd == null ? "No hard monthly limit saved." : `$${budgetStatus.data.spent_usd.toFixed(2)} spent this period.`}</small>
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
            <p>Your current plan and Stripe-managed upgrades.</p>
          </div>
          <button
            type="button"
            className="btn btn-soft"
            onClick={() => void openBillingPortal()}
            disabled={loading || !billingMe?.stripe_customer_id}
            title={!billingMe?.stripe_customer_id ? "Start checkout first to create a Stripe customer." : undefined}
          >
            Manage in Stripe
          </button>
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
                      disabled={loading}
                    >
                      {plan.selfServe ? `Checkout for ${plan.name}` : `Contact us for ${plan.name}`}
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
          <p>Stripe is the source of truth for invoices, payment methods, and receipts.</p>
        </header>
        <div className="actions billing-invoices-empty">
          <button
            type="button"
            className="btn btn-soft"
            onClick={() => void openBillingPortal()}
            disabled={!billingMe?.stripe_customer_id}
          >
            Open invoice portal
          </button>
          {!billingMe?.stripe_customer_id && (
            <span className="hint">Create a paid checkout session before opening the Stripe customer portal.</span>
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
