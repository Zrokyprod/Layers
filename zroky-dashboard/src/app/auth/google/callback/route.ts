import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ACCESS_TOKEN_COOKIE = "zroky_access_token";
const REFRESH_TOKEN_COOKIE = "zroky_refresh_token";
const MIN_COOKIE_MAX_AGE_SECONDS = 60;

type AuthTokenResponse = {
  access_token: string;
  refresh_token: string;
  access_expires_in_seconds: number;
  refresh_expires_in_seconds: number;
};

function loginRedirect(request: NextRequest, error: string): NextResponse {
  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("error", error);
  return NextResponse.redirect(loginUrl, { status: 302 });
}

function isPositiveFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function parseAuthTokens(value: unknown): AuthTokenResponse | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const payload = value as Partial<AuthTokenResponse>;
  if (
    typeof payload.access_token !== "string"
    || !payload.access_token.trim()
    || typeof payload.refresh_token !== "string"
    || !payload.refresh_token.trim()
    || !isPositiveFiniteNumber(payload.access_expires_in_seconds)
    || !isPositiveFiniteNumber(payload.refresh_expires_in_seconds)
  ) {
    return null;
  }

  return {
    access_token: payload.access_token,
    refresh_token: payload.refresh_token,
    access_expires_in_seconds: Math.max(
      MIN_COOKIE_MAX_AGE_SECONDS,
      Math.floor(payload.access_expires_in_seconds),
    ),
    refresh_expires_in_seconds: Math.max(
      MIN_COOKIE_MAX_AGE_SECONDS,
      Math.floor(payload.refresh_expires_in_seconds),
    ),
  };
}

function setSessionCookies(response: NextResponse, tokens: AuthTokenResponse): void {
  const isProduction = process.env.NODE_ENV === "production";

  response.cookies.set(ACCESS_TOKEN_COOKIE, tokens.access_token, {
    httpOnly: true,
    secure: isProduction,
    sameSite: "strict",
    maxAge: tokens.access_expires_in_seconds,
    path: "/",
  });

  response.cookies.set(REFRESH_TOKEN_COOKIE, tokens.refresh_token, {
    httpOnly: true,
    secure: isProduction,
    sameSite: "strict",
    maxAge: tokens.refresh_expires_in_seconds,
    path: "/",
  });
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const error = request.nextUrl.searchParams.get("error");
  if (error) {
    return loginRedirect(request, error);
  }

  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  if (!code || !state) {
    return loginRedirect(request, "oauth_failed");
  }

  const callbackUrl = new URL("/api/zroky/v1/auth/google/callback", request.url);
  request.nextUrl.searchParams.forEach((value, key) => {
    callbackUrl.searchParams.set(key, value);
  });

  let response: Response;
  try {
    response = await fetch(callbackUrl, {
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return loginRedirect(request, "oauth_failed");
  }

  const location = response.headers.get("location");
  if (response.status === 400) {
    return loginRedirect(request, "oauth_expired");
  }
  if (!location || response.status < 300 || response.status >= 400) {
    return loginRedirect(request, "oauth_failed");
  }

  const handoffUrl = new URL(location, request.url);
  const handoffId = handoffUrl.searchParams.get("handoff_id");
  if (!handoffId) {
    return loginRedirect(request, "oauth_failed");
  }

  let handoffResponse: Response;
  try {
    handoffResponse = await fetch(new URL("/api/zroky/v1/auth/oauth/handoff", request.url), {
      method: "POST",
      cache: "no-store",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({ handoff_id: handoffId }),
    });
  } catch {
    return loginRedirect(request, "oauth_failed");
  }

  if (!handoffResponse.ok) {
    return loginRedirect(request, "oauth_failed");
  }

  let rawTokens: unknown;
  try {
    rawTokens = await handoffResponse.json();
  } catch {
    return loginRedirect(request, "oauth_failed");
  }

  const tokens = parseAuthTokens(rawTokens);
  if (!tokens) {
    return loginRedirect(request, "oauth_failed");
  }

  const dashboardUrl = new URL("/home", request.url);
  const redirect = NextResponse.redirect(dashboardUrl, { status: 302 });
  setSessionCookies(redirect, tokens);
  return redirect;
}
