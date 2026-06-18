export type ProviderMeta = {
  value: string;
  label: string;
  description: string;
};

export const PROVIDER_KEY_OPTIONS: ProviderMeta[] = [
  {
    value: "openai",
    label: "OpenAI",
    description: "Chat completions, responses, and embeddings.",
  },
  {
    value: "anthropic",
    label: "Anthropic",
    description: "Claude models for reasoning and long context.",
  },
  {
    value: "gemini",
    label: "Google Gemini",
    description: "Gemini models for multimodal and long-context workflows.",
  },
  {
    value: "openrouter",
    label: "OpenRouter",
    description: "Multi-provider routing for replay and evaluation workers.",
  },
  {
    value: "azure_openai",
    label: "Azure OpenAI",
    description: "Azure-hosted OpenAI deployments.",
  },
  {
    value: "vertex",
    label: "Vertex AI",
    description: "Google Cloud Vertex-hosted model endpoints.",
  },
  {
    value: "cohere",
    label: "Cohere",
    description: "Command models and embeddings for enterprise workflows.",
  },
  {
    value: "mistral",
    label: "Mistral AI",
    description: "Mistral and Mixtral model families.",
  },
  {
    value: "deepseek",
    label: "DeepSeek",
    description: "DeepSeek chat and reasoning models.",
  },
  {
    value: "bedrock",
    label: "Amazon Bedrock",
    description: "AWS Bedrock-hosted model providers.",
  },
  {
    value: "groq",
    label: "Groq",
    description: "Low-latency hosted inference endpoints.",
  },
  {
    value: "custom",
    label: "Custom",
    description: "Private or custom provider endpoint.",
  },
];

export const PRIMARY_PROVIDER_VALUES = ["openai", "anthropic", "gemini", "openrouter"] as const;

const PROVIDER_ALIASES: Record<string, string> = {
  azure: "azure_openai",
  "azure-openai": "azure_openai",
  azureopenai: "azure_openai",
  google: "gemini",
  "google-gemini": "gemini",
  google_gemini: "gemini",
  vertexai: "vertex",
  vertex_ai: "vertex",
  aws: "bedrock",
  aws_bedrock: "bedrock",
  "amazon-bedrock": "bedrock",
};

const PROVIDER_META_BY_VALUE = new Map(PROVIDER_KEY_OPTIONS.map((provider) => [provider.value, provider]));

export function normalizeProviderValue(provider: string | null | undefined): string | null {
  const raw = provider?.trim().toLowerCase();
  if (!raw) return null;
  const normalized = raw.replace(/\s+/g, "_");
  return PROVIDER_ALIASES[normalized] ?? normalized;
}

export function isKnownProvider(provider: string | null | undefined): boolean {
  const normalized = normalizeProviderValue(provider);
  return Boolean(normalized && PROVIDER_META_BY_VALUE.has(normalized));
}

export function providerMeta(provider: string | null | undefined): ProviderMeta | null {
  const normalized = normalizeProviderValue(provider);
  return normalized ? PROVIDER_META_BY_VALUE.get(normalized) ?? null : null;
}

export function providerLabel(provider: string | null | undefined): string {
  const normalized = normalizeProviderValue(provider);
  if (!normalized) return "Unknown provider";
  return providerMeta(normalized)?.label ?? normalized;
}

export function providerDescription(provider: string | null | undefined): string {
  return providerMeta(provider)?.description ?? "Provider is available for replay checks when a matching key exists.";
}
