"use client";

import { useCallback, useEffect, useState } from "react";

import { useOwnerPricing, useUpdateOwnerPricing } from "@/lib/hooks";

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

export default function PricingPage() {
  const pricingQuery = useOwnerPricing();
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

  return (
    <div className="owner-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Pricing Configuration</h2>
          <p className="hint">
            Edit model pricing rates (USD per 1M tokens). Changes are persisted to{" "}
            <code>{filePath || "pricing_config.json"}</code>
          </p>
        </div>
        <div className="owner-page-header-actions">
          {saveMsg && (
            <span className={`owner-save-msg${saveMsg.startsWith("Error") ? " owner-save-msg-error" : ""}`}>
              {saveMsg}
            </span>
          )}
          <button className="btn btn-primary" onClick={handleSave} disabled={updateMutation.isPending || loading}>
            {updateMutation.isPending ? "Saving…" : "Save Changes"}
          </button>
        </div>
      </div>

      {error && <div className="alert-strip alert-strip-error">{error}</div>}
      {loading && !error && <p className="hint">Loading…</p>}

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
                  Pricing page ↗
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
