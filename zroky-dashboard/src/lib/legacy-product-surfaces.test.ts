import { afterEach, describe, expect, it, vi } from "vitest";

async function loadLegacyModule() {
  vi.resetModules();
  return import("./legacy-product-surfaces");
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("legacy product surface launch flag", () => {
  it("keeps legacy product surfaces disabled by default", async () => {
    vi.stubEnv("NEXT_PUBLIC_ZROKY_LEGACY_PRODUCT_SURFACES", undefined);

    const legacy = await loadLegacyModule();

    expect(legacy.legacyProductSurfaceEnabled).toBe(false);
    expect(legacy.legacyProductSurfaceQueryEnabled()).toBe(false);
    expect(legacy.legacyProductSurfaceQueryEnabled(true)).toBe(false);
  });

  it("allows legacy surfaces only when explicitly enabled", async () => {
    vi.stubEnv("NEXT_PUBLIC_ZROKY_LEGACY_PRODUCT_SURFACES", "1");

    const legacy = await loadLegacyModule();

    expect(legacy.legacyProductSurfaceEnabled).toBe(true);
    expect(legacy.legacyProductSurfaceQueryEnabled()).toBe(true);
    expect(legacy.legacyProductSurfaceQueryEnabled(false)).toBe(false);
  });

  it("blocks assistant API calls when the launch flag is off", async () => {
    vi.stubEnv("NEXT_PUBLIC_ZROKY_LEGACY_PRODUCT_SURFACES", undefined);
    vi.resetModules();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { sendAssistantMessage } = await import("./assistant-api");

    await expect(sendAssistantMessage("hello", "session_1")).rejects.toThrow(
      "Assistant is disabled for launch.",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
