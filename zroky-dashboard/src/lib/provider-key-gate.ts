import type { ReplayMode } from "./api";
import { PROVIDER_KEY_OPTIONS, normalizeProviderValue } from "./provider-registry";

export const PROVIDER_KEY_QUERY_KEY = ["provider-keys", "active"] as const;
export { PROVIDER_KEY_OPTIONS };

export function replayModeRequiresProviderKey(mode: ReplayMode): boolean {
  return mode !== "stub";
}

export function hasActiveProviderKey(
  items: { is_active: boolean; provider?: string | null }[] | undefined,
  provider?: string | null,
): boolean {
  const normalizedProvider = normalizeProviderValue(provider);
  return Boolean(items?.some((key) => {
    if (!key.is_active) return false;
    if (!normalizedProvider) return true;
    return normalizeProviderValue(key.provider) === normalizedProvider;
  }));
}
