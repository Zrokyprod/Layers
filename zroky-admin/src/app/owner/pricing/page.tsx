"use client";

import { useCallback, useEffect, useState } from "react";

import {
  useOwnerBillingAccounts,
  useOwnerBillingSummary,
  useOwnerPricing,
  useUpdateOwnerPricing,
} from "@/lib/hooks";
import type { OwnerBillingAccountItem } from "@/lib/owner-api";

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

function BillingAccountRow({ account }: { account: OwnerBillingAccountItem }) {
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
      <td className="owner-td owner-td-ts">
        {account.current_period_end ? new Date(account.current_period_end).toLocaleDateString() : "-"}
      </td>
      <td className="owner-td owner-td-truncate">{account.stripe_customer_id ?? "-"}</td>
      <td className="owner-td">
        <div className="owner-billing-links">
          {account.stripe_customer_url ? (
            <a className="owner-row-link" href={account.stripe_customer_url} target="_blank" rel="noopener noreferrer">
              Customer
            </a>
          ) : null}
          {account.stripe_subscription_url ? (
            <a className="owner-row-link" href={account.stripe_subscription_url} target="_blank" rel="noopener noreferrer">
              Subscription
            </a>
          ) : null}
          {!account.stripe_customer_url && !account.stripe_subscription_url ? <span className="hint">No Stripe link</span> : null}
        </div>
      </td>
    </tr>
  );
}

export default function PricingPage() {
  const pricingQuery = useOwnerPricing();
  const summaryQuery = useOwnerBillingSummary();
  const [accountStatus, setAccountStatus] = useState("");
  const [planCode, setPlanCode] = useState("");
  const accountsQuery = useOwnerBillingAccounts({
    status: accountStatus || undefined,
    plan_code: planCode || undefined,
    limit: 100,
  });
  const updateMutation = useUpdateOwnerPricing();

  const [config, setConfig] = useState<PricingConfig | null>(null);
  const [saveMsg, setSaveMsg] = useState("");

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

  const fieldLabels = ["Input ($/1M)", "Output ($/1M)", "Reasoning ($/1M)", "Cache Create ($/1M)", "Cache Read ($/1M)"];
  const summary = summaryQuery.data ?? null;
  const accounts = accountsQuery.data?.items ?? [];

  return (
    <div className="owner-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Billing</h2>
          <p className="hint">
            Plan/status breakdown, Stripe-linked accounts and model pricing controls.
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
      {summaryQuery.error && <div className="alert-strip alert-strip-error">{summaryQuery.error.message}</div>}
      {accountsQuery.error && <div className="alert-strip alert-strip-error">{accountsQuery.error.message}</div>}
      {loading && !error && <p className="hint">Loading...</p>}

      <section className="owner-stat-grid">
        <div className="owner-stat-card owner-stat-card-accent">
          <span className="owner-stat-label">Subscriptions</span>
          <span className="owner-stat-value">{summary?.total_subscriptions.toLocaleString() ?? "-"}</span>
          <span className="owner-stat-sub">legacy tenant subscriptions</span>
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
          <span className="owner-stat-label">Stripe accounts</span>
          <span className="owner-stat-value">{accountsQuery.data?.total.toLocaleString() ?? "-"}</span>
          <span className="owner-stat-sub">new billing rows</span>
        </div>
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
          Stripe-linked Accounts
          <span className="panel-header-note">Shows new subscription rows with direct Stripe dashboard links.</span>
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
                {["Account", "Plan", "Status", "SLA", "Period End", "Stripe Customer", "Links"].map((header) => (
                  <th key={header} className="owner-th">{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {accountsQuery.isLoading ? (
                <tr><td colSpan={7} className="owner-td owner-td-empty">Loading accounts...</td></tr>
              ) : accounts.length === 0 ? (
                <tr><td colSpan={7} className="owner-td owner-td-empty">No Stripe-linked billing accounts found.</td></tr>
              ) : (
                accounts.map((account) => <BillingAccountRow key={account.org_id} account={account} />)
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
        <div className="alert-strip">No providers found in pricing config.</div>
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
