import type { AuthTokenResponse } from "@/lib/types";

const ACCESS_TOKEN_COOKIE = "zroky_access_token";
const REFRESH_TOKEN_COOKIE = "zroky_refresh_token";
const AUTH_SESSION_STORAGE_KEY = "zroky_auth_session";
const LS_ACCESS_TOKEN_KEY = "zroky_at";
const LS_REFRESH_TOKEN_KEY = "zroky_rt";
const LS_EMAIL_VERIFIED_KEY = "zroky_ev";
const POST_AUTH_REDIRECT_STORAGE_KEY = "zroky_post_auth_redirect";
const DEFAULT_ACCESS_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 72;
const DEFAULT_REFRESH_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

export type BrowserAuthSession = {
  accessToken: string | null;
  refreshToken: string | null;
  accessTokenExpiresAtEpochSeconds: number | null;
  refreshTokenExpiresAtEpochSeconds: number | null;
};

function buildCookiePrefix(name: string): string {
  return `${name}=`;
}

function isSafeAppPath(path: string): boolean {
  if (!path.startsWith("/")) {
    return false;
  }
  if (path.startsWith("//")) {
    return false;
  }
  return true;
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }

  const prefix = buildCookiePrefix(name);
  const parts = document.cookie.split(";");
  for (const item of parts) {
    const trimmed = item.trim();
    if (trimmed.startsWith(prefix)) {
      const encoded = trimmed.slice(prefix.length);
      if (!encoded) {
        return null;
      }
      return decodeURIComponent(encoded);
    }
  }
  return null;
}

export function readAccessTokenFromBrowser(): string | null {
  if (typeof window !== "undefined") {
    const ls = window.localStorage.getItem(LS_ACCESS_TOKEN_KEY);
    if (ls) return ls;
  }
  return readCookie(ACCESS_TOKEN_COOKIE);
}

export function readRefreshTokenFromBrowser(): string | null {
  if (typeof window !== "undefined") {
    const ls = window.localStorage.getItem(LS_REFRESH_TOKEN_KEY);
    if (ls) return ls;
  }
  return readCookie(REFRESH_TOKEN_COOKIE);
}

function decodeJwtExpiryEpochSeconds(token: string): number | null {
  try {
    const parts = token.split(".");
    if (parts.length < 2) {
      return null;
    }

    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padding = payload.length % 4 === 0 ? "" : "=".repeat(4 - (payload.length % 4));
    const decodedPayload = atob(payload + padding);
    const parsed = JSON.parse(decodedPayload) as { exp?: unknown };
    if (typeof parsed.exp === "number" && Number.isFinite(parsed.exp)) {
      return parsed.exp;
    }
  } catch {
    return null;
  }
  return null;
}

function persistSessionMetadata(session: BrowserAuthSession): void {
  if (typeof window === "undefined") {
    return;
  }

  const payload = JSON.stringify({
    accessTokenExpiresAtEpochSeconds: session.accessTokenExpiresAtEpochSeconds,
    refreshTokenExpiresAtEpochSeconds: session.refreshTokenExpiresAtEpochSeconds,
  });
  window.localStorage.setItem(AUTH_SESSION_STORAGE_KEY, payload);
}

function readSessionMetadata(): {
  accessTokenExpiresAtEpochSeconds: number | null;
  refreshTokenExpiresAtEpochSeconds: number | null;
} {
  if (typeof window === "undefined") {
    return {
      accessTokenExpiresAtEpochSeconds: null,
      refreshTokenExpiresAtEpochSeconds: null,
    };
  }

  const raw = window.localStorage.getItem(AUTH_SESSION_STORAGE_KEY);
  if (!raw) {
    return {
      accessTokenExpiresAtEpochSeconds: null,
      refreshTokenExpiresAtEpochSeconds: null,
    };
  }

  try {
    const parsed = JSON.parse(raw) as {
      accessTokenExpiresAtEpochSeconds?: unknown;
      refreshTokenExpiresAtEpochSeconds?: unknown;
    };
    return {
      accessTokenExpiresAtEpochSeconds:
        typeof parsed.accessTokenExpiresAtEpochSeconds === "number" && Number.isFinite(parsed.accessTokenExpiresAtEpochSeconds)
          ? parsed.accessTokenExpiresAtEpochSeconds
          : null,
      refreshTokenExpiresAtEpochSeconds:
        typeof parsed.refreshTokenExpiresAtEpochSeconds === "number" && Number.isFinite(parsed.refreshTokenExpiresAtEpochSeconds)
          ? parsed.refreshTokenExpiresAtEpochSeconds
          : null,
    };
  } catch {
    return {
      accessTokenExpiresAtEpochSeconds: null,
      refreshTokenExpiresAtEpochSeconds: null,
    };
  }
}

export async function storeAuthSession(tokens: AuthTokenResponse): Promise<void> {
  const accessMaxAgeSeconds = Math.max(
    60,
    Number.isFinite(tokens.access_expires_in_seconds) ? tokens.access_expires_in_seconds : DEFAULT_ACCESS_TOKEN_MAX_AGE_SECONDS,
  );
  const refreshMaxAgeSeconds = Math.max(
    60,
    Number.isFinite(tokens.refresh_expires_in_seconds) ? tokens.refresh_expires_in_seconds : DEFAULT_REFRESH_TOKEN_MAX_AGE_SECONDS,
  );

  // Store tokens in localStorage so client-side reads work (httpOnly cookies are invisible to JS)
  if (typeof window !== "undefined") {
    window.localStorage.setItem(LS_ACCESS_TOKEN_KEY, tokens.access_token);
    window.localStorage.setItem(LS_REFRESH_TOKEN_KEY, tokens.refresh_token);
    window.localStorage.setItem(LS_EMAIL_VERIFIED_KEY, String(tokens.email_verified ?? true));
  }

  // Also set HttpOnly cookies via server route for middleware + proxy auth
  await fetch("/api/auth/set-session", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token,
      access_max_age_seconds: accessMaxAgeSeconds,
      refresh_max_age_seconds: refreshMaxAgeSeconds,
    }),
  });

  const nowEpochSeconds = Math.floor(Date.now() / 1000);
  persistSessionMetadata({
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    accessTokenExpiresAtEpochSeconds: nowEpochSeconds + accessMaxAgeSeconds,
    refreshTokenExpiresAtEpochSeconds: nowEpochSeconds + refreshMaxAgeSeconds,
  });
}

export function storeAccessToken(token: string, maxAgeSeconds = DEFAULT_ACCESS_TOKEN_MAX_AGE_SECONDS): void {
  const refreshExpiry = readSessionMetadata().refreshTokenExpiresAtEpochSeconds;
  const refreshMaxAge = refreshExpiry ? Math.max(0, refreshExpiry - Math.floor(Date.now() / 1000)) : DEFAULT_REFRESH_TOKEN_MAX_AGE_SECONDS;
  const refreshToken = readRefreshTokenFromBrowser() ?? "";

  if (typeof window !== "undefined") {
    window.localStorage.setItem(LS_ACCESS_TOKEN_KEY, token);
  }

  void fetch("/api/auth/set-session", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      access_token: token,
      refresh_token: refreshToken,
      access_max_age_seconds: maxAgeSeconds,
      refresh_max_age_seconds: refreshMaxAge,
    }),
  });

  const nowEpochSeconds = Math.floor(Date.now() / 1000);
  persistSessionMetadata({
    accessToken: token,
    refreshToken: refreshToken || null,
    accessTokenExpiresAtEpochSeconds: nowEpochSeconds + maxAgeSeconds,
    refreshTokenExpiresAtEpochSeconds: refreshExpiry,
  });
}

export function readEmailVerifiedFromBrowser(): boolean | null {
  if (typeof window === "undefined") return null;
  const val = window.localStorage.getItem(LS_EMAIL_VERIFIED_KEY);
  if (val === null) return null;
  return val === "true";
}

export function clearAuthSession(): void {
  // Clear HttpOnly cookies via server route
  void fetch("/api/auth/clear-session", { method: "POST" });
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
    window.localStorage.removeItem(LS_ACCESS_TOKEN_KEY);
    window.localStorage.removeItem(LS_REFRESH_TOKEN_KEY);
    window.localStorage.removeItem(LS_EMAIL_VERIFIED_KEY);
  }
}

export function clearAccessToken(): void {
  clearAuthSession();
}

export function readAuthSessionFromBrowser(): BrowserAuthSession {
  const accessToken = readAccessTokenFromBrowser();
  const refreshToken = readRefreshTokenFromBrowser();
  const metadata = readSessionMetadata();

  const accessExpiryFromToken = accessToken ? decodeJwtExpiryEpochSeconds(accessToken) : null;
  const refreshExpiryFromToken = refreshToken ? decodeJwtExpiryEpochSeconds(refreshToken) : null;

  return {
    accessToken,
    refreshToken,
    accessTokenExpiresAtEpochSeconds: metadata.accessTokenExpiresAtEpochSeconds ?? accessExpiryFromToken,
    refreshTokenExpiresAtEpochSeconds: metadata.refreshTokenExpiresAtEpochSeconds ?? refreshExpiryFromToken,
  };
}

export function hasPersistedSession(): boolean {
  const session = readAuthSessionFromBrowser();
  return Boolean(session.accessToken || session.refreshToken);
}

export function setPendingPostAuthRedirectPath(path: string): void {
  if (typeof window === "undefined") {
    return;
  }
  if (!isSafeAppPath(path)) {
    return;
  }
  window.sessionStorage.setItem(POST_AUTH_REDIRECT_STORAGE_KEY, path);
}

export function consumePendingPostAuthRedirectPath(fallback = "/home"): string {
  if (typeof window === "undefined") {
    return fallback;
  }

  const stored = window.sessionStorage.getItem(POST_AUTH_REDIRECT_STORAGE_KEY);
  if (stored) {
    window.sessionStorage.removeItem(POST_AUTH_REDIRECT_STORAGE_KEY);
    if (isSafeAppPath(stored)) {
      return stored;
    }
  }
  return fallback;
}

export function getPostAuthRedirectPath(fallback = "/home"): string {
  if (typeof window === "undefined") {
    return fallback;
  }

  const params = new URLSearchParams(window.location.search);
  const next = params.get("next");
  if (!next) {
    return fallback;
  }

  if (!next.startsWith("/")) {
    return fallback;
  }

  if (!isSafeAppPath(next)) {
    return fallback;
  }

  return next;
}

export function resolvePostAuthRedirectPath(fallback = "/home"): string {
  const fromQuery = getPostAuthRedirectPath("");
  if (fromQuery) {
    return fromQuery;
  }
  return consumePendingPostAuthRedirectPath(fallback);
}
