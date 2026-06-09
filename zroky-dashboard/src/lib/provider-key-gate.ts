import type { ReplayMode } from "./api";

export const PROVIDER_KEY_QUERY_KEY = ["provider-keys", "active"] as const;

export const PROVIDER_KEY_OPTIONS = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "gemini", label: "Google Gemini" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "azure_openai", label: "Azure OpenAI" },
  { value: "custom", label: "Custom" },
];

export function replayModeRequiresProviderKey(mode: ReplayMode): boolean {
  return mode !== "stub";
}

export function hasActiveProviderKey(items: { is_active: boolean }[] | undefined): boolean {
  return Boolean(items?.some((key) => key.is_active));
}
