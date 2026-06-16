import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ACCESS_TOKEN_COOKIE = "zroky_access_token";
const REFRESH_TOKEN_COOKIE = "zroky_refresh_token";
const devDefaultBaseUrl = "http://127.0.0.1:8000";

type BackendRefreshResponse = {
  access_token: string;
  refresh_token: string;
  access_expires_in_seconds: number;
  refresh_expires_in_seconds: number;
  email_verified?: boolean;
};

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

function isPositiveFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function parseBackendRefreshPayload(value: unknown): BackendRefreshResponse | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const payload = value as Partial<BackendRefreshResponse>;
  if (
    typeof payload.access_token !== "string"
    || payload.access_token.trim() === ""
    || typeof payload.refresh_token !== "string"
    || payload.refresh_token.trim() === ""
    || !isPositiveFiniteNumber(payload.access_expires_in_seconds)
    || !isPositiveFiniteNumber(payload.refresh_expires_in_seconds)
  ) {
    return null;
  }

  return {
    access_token: payload.access_token,
    refresh_token: payload.refresh_token,
    access_expires_in_seconds: Math.floor(payload.access_expires_in_seconds),
    refresh_expires_in_seconds: Math.floor(payload.refresh_expires_in_seconds),
    email_verified: payload.email_verified,
  };
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const refreshToken = request.cookies.get(REFRESH_TOKEN_COOKIE)?.value;
  if (!refreshToken) {
    return NextResponse.json({ error: "Missing refresh session" }, { status: 401 });
  }

  let baseUrl: string;
  try {
    baseUrl = getBaseUrl();
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Backend API is not configured." },
      { status: 500 },
    );
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${baseUrl}/v1/auth/refresh`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } catch {
    return NextResponse.json(
      { error: "Backend API is unavailable. Start the Zroky backend and retry." },
      { status: 502 },
    );
  }

  if (!backendResponse.ok) {
    return NextResponse.json({ error: "Refresh failed" }, { status: backendResponse.status });
  }

  let rawPayload: unknown;
  try {
    rawPayload = await backendResponse.json();
  } catch {
    return NextResponse.json({ error: "Malformed refresh response" }, { status: 502 });
  }

  const payload = parseBackendRefreshPayload(rawPayload);
  if (!payload) {
    return NextResponse.json({ error: "Malformed refresh response" }, { status: 502 });
  }

  const isProduction = process.env.NODE_ENV === "production";
  const response = NextResponse.json({
    ok: true,
    access_expires_in_seconds: payload.access_expires_in_seconds,
    refresh_expires_in_seconds: payload.refresh_expires_in_seconds,
    email_verified: payload.email_verified ?? true,
  });

  response.cookies.set(ACCESS_TOKEN_COOKIE, payload.access_token, {
    httpOnly: true,
    secure: isProduction,
    sameSite: "lax",
    maxAge: payload.access_expires_in_seconds,
    path: "/",
  });

  response.cookies.set(REFRESH_TOKEN_COOKIE, payload.refresh_token, {
    httpOnly: true,
    secure: isProduction,
    sameSite: "lax",
    maxAge: payload.refresh_expires_in_seconds,
    path: "/",
  });

  return response;
}
