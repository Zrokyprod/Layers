export const legacyProductSurfaceEnabled =
  process.env.NEXT_PUBLIC_ZROKY_LEGACY_PRODUCT_SURFACES === "1" ||
  process.env.NEXT_PUBLIC_ZROKY_LEGACY_PRODUCT_SURFACES === "true";

export function legacyProductSurfaceQueryEnabled(
  requestedEnabled: unknown = true,
): boolean {
  return legacyProductSurfaceEnabled && requestedEnabled !== false;
}

export function legacyProductSurfaceDisabledError(surface: string): Error {
  return new Error(`${surface} is disabled for launch.`);
}
