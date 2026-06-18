import type { ReplayMode } from "./api";
import { PROVIDER_KEY_OPTIONS, isKnownProvider, normalizeProviderValue } from "./provider-registry";

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
  const providerFilter = normalizedProvider
    ? isKnownProvider(normalizedProvider)
      ? normalizedProvider
      : "custom"
    : null;
  return Boolean(items?.some((key) => {
    if (!key.is_active) return false;
    if (!providerFilter) return true;
    return normalizeProviderValue(key.provider) === providerFilter;
  }));
}
