"use client";

import { useCallback, useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { useBudget, useUpdateBudget } from "@/lib/hooks";
import { budgetSchema, type BudgetFormData } from "@/lib/schemas";
import {
  createBillingCheckout,
  createBillingPortal,
  getBillingUsageSummary,
  getBillingMe,
  getTenantSubscription,
  listSubscriptionPlans,
  updateTenantSubscription,
} from "@/lib/api";
import type { BillingMeResponse, BillingUsageSummary, SubscriptionPlan, TenantSubscription } from "@/lib/types";

export default function BillingPage() {
  const budget = useBudget();
  const updateBudget = useUpdateBudget();

  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [subscription, setSubscription] = useState<TenantSubscription | null>(null);
  const [billingMe, setBillingMe] = useState<BillingMeResponse | null>(null);
  const [usage, setUsage] = useState<BillingUsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState("");
  const [statusMsg, setStatusMsg] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [plansRes, subRes, usageRes] = await Promise.all([
        listSubscriptionPlans(),
        getTenantSubscription(),
        getBillingUsageSummary(),
      ]);
      const meRes = await getBillingMe().catch(() => null);
      setPlans(plansRes.plans);
      setSubscription(subRes);
      setBillingMe(meRes);
      setUsage(usageRes);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to load billing data.";
      setError(msg);
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

  async function changePlan(planId: string) {
    setActionMsg("");
    try {
      const plan = plans.find((item) => item.id === planId || item.slug === planId);
      const planCode = plan?.slug ?? planId;
      if (planCode === "free") {
        const updated = await updateTenantSubscription({ plan_id: planId });
        setSubscription(updated);
        setActionMsg("Plan updated successfully.");
        await load();
        return;
      }
      if (planCode === "enterprise") {
        setActionMsg("Enterprise is sales-led. Contact the Zroky team to activate this plan.");
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

  const currentPlanId = subscription?.plan?.id;

  return (
    <div className="page-content">
      {error && <div className="alert-strip alert-strip-error">{error}</div>}
      {actionMsg && (
        <div className={actionMsg.includes("success") ? "alert-strip" : "alert-strip alert-strip-error"}>
          {actionMsg}
        </div>
      )}

      {/* Plans */}
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

        {loading && !plans.length ? (
          <div className="loading" />
        ) : (
          <div className="billing-plans-grid">
            {plans.map((plan) => {
              const isCurrent = plan.id === currentPlanId;
              return (
                <div key={plan.id} className={`billing-plan-card${isCurrent ? " billing-plan-current" : ""}`}>
                  {isCurrent && (
                    <span className="pill pill-green billing-plan-badge">Current</span>
                  )}
                  <div className="billing-plan-name">{plan.name}</div>
                  <div className="billing-plan-price">
                    ${plan.monthly_cost_usd.toFixed(2)} <span className="billing-plan-period">/ mo</span>
                  </div>
                  <ul className="billing-plan-features">
                    {plan.features.map((f) => (
                      <li key={f}>✓ {f}</li>
                    ))}
                    {plan.max_calls_per_month != null && (
                      <li>✓ Up to {plan.max_calls_per_month.toLocaleString()} calls/mo</li>
                    )}
                    {plan.max_members_per_project > 0 && (
                      <li>✓ Up to {plan.max_members_per_project} members</li>
                    )}
                  </ul>
                  {!isCurrent && (
                    <button
                      type="button"
                      className="btn btn-primary billing-plan-btn"
                      onClick={() => changePlan(plan.id)}
                      disabled={loading}
                    >
                      {plan.slug === "free" ? `Switch to ${plan.name}` : `Checkout for ${plan.name}`}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Usage summary */}
      {usage && (
        <section className="panel">
          <header className="panel-header">
            <h3>Current Period Usage</h3>
            <p>
              {new Date(usage.period_start).toLocaleDateString()} →{" "}
              {new Date(usage.period_end).toLocaleDateString()}
            </p>
          </header>

          <div className="kpi-grid billing-usage-kpis">
            <div className="kpi-card">
              <div className="kpi-value">{usage.total_calls.toLocaleString()}</div>
              <div className="kpi-label">Calls</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-value">{usage.total_tokens.toLocaleString()}</div>
              <div className="kpi-label">Tokens</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-value">${usage.total_cost_usd.toFixed(4)}</div>
              <div className="kpi-label">Cost</div>
            </div>
          </div>

          {usage.plan_limit_calls != null && (
            <div className="billing-quota-row">
              <div className="billing-quota-label">
                Calls: {usage.total_calls.toLocaleString()} / {usage.plan_limit_calls.toLocaleString()}
              </div>
              <div className="billing-progress-track">
                <div
                  className={`billing-progress-fill${usage.overage_calls ? " billing-progress-over" : ""}`}
                  style={{ width: `${Math.min(100, (usage.total_calls / usage.plan_limit_calls) * 100)}%` }}
                />
              </div>
              {usage.overage_calls != null && (
                <div className="billing-overage">Over by {usage.overage_calls.toLocaleString()} calls</div>
              )}
            </div>
          )}

          {usage.plan_limit_tokens != null && (
            <div className="billing-quota-row">
              <div className="billing-quota-label">
                Tokens: {usage.total_tokens.toLocaleString()} / {usage.plan_limit_tokens.toLocaleString()}
              </div>
              <div className="billing-progress-track">
                <div
                  className={`billing-progress-fill${usage.overage_tokens ? " billing-progress-over" : ""}`}
                  style={{ width: `${Math.min(100, (usage.total_tokens / usage.plan_limit_tokens) * 100)}%` }}
                />
              </div>
              {usage.overage_tokens != null && (
                <div className="billing-overage">Over by {usage.overage_tokens.toLocaleString()} tokens</div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Spend Limits */}
      <section className="panel">
        <header className="panel-header">
          <h3>Spend Limits</h3>
          <p>Hard cap on monthly AI cost. Requests are blocked when the limit is reached.</p>
        </header>

        <form onSubmit={onSaveBudget} className="billing-budget-form">
          <div className="field">
            <label htmlFor="spend-limit" className="field-label">
              Monthly limit (USD) — leave blank for no limit
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
            {errors.monthlyLimit && (
              <span className="field-error">{errors.monthlyLimit.message}</span>
            )}
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
            {errors.threshold && (
              <span className="field-error">{errors.threshold.message}</span>
            )}
            <p className="field-hint">
              You&apos;ll receive an alert when you reach {thresholdValue || "–"}% of your limit.
            </p>
          </div>

          {statusMsg && (
            <p className={statusMsg.includes("saved") ? "field-success" : "field-error"}>
              {statusMsg}
            </p>
          )}

          <div className="actions">
            <button type="submit" className="btn btn-primary" disabled={updateBudget.isPending}>
              {updateBudget.isPending ? "Saving…" : "Save limits"}
            </button>
          </div>
        </form>
      </section>

      {/* Invoices */}
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
