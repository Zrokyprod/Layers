import type { AuthTokenResponse } from "@/lib/types";
import { isSafeAppPath, POST_AUTH_REDIRECT_COOKIE, safeAppPath } from "@/lib/onboarding-intent";

const AUTH_SESSION_STORAGE_KEY = "zroky_auth_session";
const LS_ACCESS_TOKEN_KEY = "zroky_at";
const LS_REFRESH_TOKEN_KEY = "zroky_rt";
const LS_EMAIL_VERIFIED_KEY = "zroky_ev";
const POST_AUTH_REDIRECT_STORAGE_KEY = "zroky_post_auth_redirect";
export const AUTH_SESSION_CHANGED_EVENT = "zroky:auth-session-changed";
const POST_AUTH_REDIRECT_COOKIE_MAX_AGE_SECONDS = 10 * 60;
const DEFAULT_ACCESS_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 72;
const DEFAULT_REFRESH_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

export type BrowserAuthSession = {
  accessToken: string | null;
  refreshToken: string | null;
  accessTokenExpiresAtEpochSeconds: number | null;
  refreshTokenExpiresAtEpochSeconds: number | null;
};

export function readAccessTokenFromBrowser(): string | null {
  return null;
}

export function readRefreshTokenFromBrowser(): string | null {
  return null;
}

function clearLegacyStoredTokens(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(LS_ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(LS_REFRESH_TOKEN_KEY);
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

function notifyAuthSessionChanged(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(AUTH_SESSION_CHANGED_EVENT));
  }
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

  if (typeof window !== "undefined") {
    clearLegacyStoredTokens();
    window.localStorage.setItem(LS_EMAIL_VERIFIED_KEY, String(tokens.email_verified ?? true));
  }

  // Also set HttpOnly cookies via server route for middleware + proxy auth
  await fetch("/api/auth/set-session", {
    method: "POST",
    credentials: "same-origin",
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
    accessToken: null,
    refreshToken: null,
    accessTokenExpiresAtEpochSeconds: nowEpochSeconds + accessMaxAgeSeconds,
    refreshTokenExpiresAtEpochSeconds: nowEpochSeconds + refreshMaxAgeSeconds,
  });
  notifyAuthSessionChanged();
}

export function storeAccessToken(token: string, maxAgeSeconds = DEFAULT_ACCESS_TOKEN_MAX_AGE_SECONDS): void {
  void token;
  const refreshExpiry = readSessionMetadata().refreshTokenExpiresAtEpochSeconds;
  const nowEpochSeconds = Math.floor(Date.now() / 1000);
  persistSessionMetadata({
    accessToken: null,
    refreshToken: null,
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
  void fetch("/api/auth/clear-session", { method: "POST", credentials: "same-origin" });
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
    clearLegacyStoredTokens();
    window.localStorage.removeItem(LS_EMAIL_VERIFIED_KEY);
  }
  notifyAuthSessionChanged();
}

export function clearAccessToken(): void {
  clearAuthSession();
}

export function readAuthSessionFromBrowser(): BrowserAuthSession {
  const metadata = readSessionMetadata();

  return {
    accessToken: null,
    refreshToken: null,
    accessTokenExpiresAtEpochSeconds: metadata.accessTokenExpiresAtEpochSeconds,
    refreshTokenExpiresAtEpochSeconds: metadata.refreshTokenExpiresAtEpochSeconds,
  };
}

export function hasPersistedSession(): boolean {
  const session = readAuthSessionFromBrowser();
  const nowEpochSeconds = Math.floor(Date.now() / 1000);
  return Boolean(
    (session.accessTokenExpiresAtEpochSeconds && session.accessTokenExpiresAtEpochSeconds > nowEpochSeconds)
    || (session.refreshTokenExpiresAtEpochSeconds && session.refreshTokenExpiresAtEpochSeconds > nowEpochSeconds),
  );
}

function writePostAuthRedirectCookie(path: string): void {
  document.cookie = [
    `${POST_AUTH_REDIRECT_COOKIE}=${encodeURIComponent(path)}`,
    "Path=/",
    `Max-Age=${POST_AUTH_REDIRECT_COOKIE_MAX_AGE_SECONDS}`,
    "SameSite=Lax",
  ].join("; ");
}

function readPostAuthRedirectCookie(): string | null {
  const match = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${POST_AUTH_REDIRECT_COOKIE}=`));
  if (!match) return null;

  try {
    return decodeURIComponent(match.slice(POST_AUTH_REDIRECT_COOKIE.length + 1));
  } catch {
    return null;
  }
}

function clearPostAuthRedirectCookie(): void {
  document.cookie = `${POST_AUTH_REDIRECT_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
}

export function setPendingPostAuthRedirectPath(path: string): void {
  if (typeof window === "undefined") {
    return;
  }
  if (!isSafeAppPath(path)) {
    return;
  }
  window.sessionStorage.setItem(POST_AUTH_REDIRECT_STORAGE_KEY, path);
  writePostAuthRedirectCookie(path);
}

export function consumePendingPostAuthRedirectPath(fallback = "/home"): string {
  if (typeof window === "undefined") {
    return fallback;
  }

  const stored = window.sessionStorage.getItem(POST_AUTH_REDIRECT_STORAGE_KEY);
  if (stored) {
    window.sessionStorage.removeItem(POST_AUTH_REDIRECT_STORAGE_KEY);
    clearPostAuthRedirectCookie();
    if (isSafeAppPath(stored)) {
      return stored;
    }
  }

  const cookieValue = readPostAuthRedirectCookie();
  clearPostAuthRedirectCookie();
  if (isSafeAppPath(cookieValue)) {
    return cookieValue;
  }

  return fallback;
}

export function getPostAuthRedirectPath(fallback = "/home"): string {
  if (typeof window === "undefined") {
    return fallback;
  }

  const params = new URLSearchParams(window.location.search);
  const next = params.get("next");
  return safeAppPath(next, fallback);
}

export function resolvePostAuthRedirectPath(fallback = "/home"): string {
  const fromQuery = getPostAuthRedirectPath("");
  if (fromQuery) {
    return fromQuery;
  }
  return consumePendingPostAuthRedirectPath(fallback);
}
