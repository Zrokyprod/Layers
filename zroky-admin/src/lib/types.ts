export interface PlatformLlmUsageItem {
  id: string;
  purpose: string;
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number | null;
  tenant_id: string | null;
  diagnosis_id: string | null;
  created_at: string;
}

export interface PlatformLlmUsageSummaryResponse {
  total_calls: number;
  total_cost_usd: number;
  total_tokens: number;
  avg_latency_ms: number;
  by_purpose: Record<string, { calls: number; cost_usd: number; tokens: number }>;
  by_model: Record<string, { calls: number; cost_usd: number; tokens: number }>;
  recent: PlatformLlmUsageItem[];
}

export interface FeatureFlag {
  id: string;
  key: string;
  description: string | null;
  enabled_globally: boolean;
  enabled_tenants: string[];
  disabled_tenants: string[];
  created_at: string;
  updated_at: string;
}

export interface FeatureFlagListResponse {
  items: FeatureFlag[];
}
