const devDefaultBaseUrl = "http://127.0.0.1:8000";

export type DashboardSessionUser = {
  user_id: string;
  email: string | null;
  email_verified: boolean;
  is_active: boolean;
};

export type DashboardSessionCheck =
  | { status: "authenticated"; user: DashboardSessionUser }
  | { status: "unauthenticated" }
  | { status: "unavailable" };

function getBaseUrl(): string {
  const raw = process.env.ZROKY_API_BASE_URL;
  const isProduction = process.env.NODE_ENV === "production";
  const allowLocalProductionBaseUrl = process.env.ZROKY_ALLOW_LOCAL_API_BASE_URL === "1";

  if (!raw && isProduction) {
    throw new Error("ZROKY_API_BASE_URL is required in production.");
  }

  const value = raw ?? devDefaultBaseUrl;
  const parsed = new URL(value);
  if (
    isProduction
    && !allowLocalProductionBaseUrl
    && ["localhost", "127.0.0.1", "::1"].includes(parsed.hostname)
  ) {
    throw new Error("ZROKY_API_BASE_URL must point to a real backend in production.");
  }

  const normalized = parsed.toString();
  return normalized.endsWith("/") ? normalized.slice(0, -1) : normalized;
}

function parseMePayload(value: unknown): DashboardSessionUser | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const payload = value as Partial<DashboardSessionUser>;
  if (
    typeof payload.user_id !== "string"
    || typeof payload.email_verified !== "boolean"
    || typeof payload.is_active !== "boolean"
    || (payload.email != null && typeof payload.email !== "string")
  ) {
    return null;
  }

  return {
    user_id: payload.user_id,
    email: payload.email ?? null,
    email_verified: payload.email_verified,
    is_active: payload.is_active,
  };
}

export async function checkDashboardSession(accessToken: string): Promise<DashboardSessionCheck> {
  let baseUrl: string;
  try {
    baseUrl = getBaseUrl();
  } catch {
    return { status: "unavailable" };
  }

  let response: Response;
  try {
    response = await fetch(`${baseUrl}/v1/auth/me`, {
      method: "GET",
      cache: "no-store",
      headers: {
        authorization: accessToken.toLowerCase().startsWith("bearer ") ? accessToken : `Bearer ${accessToken}`,
      },
    });
  } catch {
    return { status: "unavailable" };
  }

  if (response.status === 401 || response.status === 403) {
    return { status: "unauthenticated" };
  }
  if (!response.ok) {
    return { status: "unavailable" };
  }

  let rawPayload: unknown;
  try {
    rawPayload = await response.json();
  } catch {
    return { status: "unavailable" };
  }

  const user = parseMePayload(rawPayload);
  if (!user || !user.is_active) {
    return { status: "unauthenticated" };
  }

  return { status: "authenticated", user };
}
