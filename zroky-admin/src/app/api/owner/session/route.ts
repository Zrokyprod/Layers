import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const OWNER_TOKEN_COOKIE = "zroky_owner_token";
const devDefaultBaseUrl = "http://127.0.0.1:8000";
const defaultOwnerSessionMaxAgeSeconds = 8 * 60 * 60;

type OwnerSessionRequest = {
  token?: unknown;
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

function ownerSessionMaxAgeSeconds(): number {
  const raw = Number(process.env.ZROKY_OWNER_SESSION_MAX_AGE_SECONDS ?? defaultOwnerSessionMaxAgeSeconds);
  return Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : defaultOwnerSessionMaxAgeSeconds;
}

function clearOwnerCookie(response: NextResponse): void {
  response.cookies.set(OWNER_TOKEN_COOKIE, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    maxAge: 0,
    path: "/",
  });
}

async function verifyOwnerToken(token: string): Promise<Response> {
  const baseUrl = getBaseUrl();
  return fetch(`${baseUrl}/v1/owner/stats`, {
    method: "GET",
    cache: "no-store",
    headers: {
      "x-zroky-admin-token": token,
    },
  });
}

function ownerError(status: number): NextResponse {
  return NextResponse.json({ ok: false, error: "Owner session verification failed" }, { status });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  let body: OwnerSessionRequest;
  try {
    body = (await request.json()) as OwnerSessionRequest;
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON body" }, { status: 400 });
  }

  const token = typeof body.token === "string" ? body.token.trim() : "";
  if (!token) {
    return NextResponse.json({ ok: false, error: "Missing owner token" }, { status: 400 });
  }

  let backendResponse: Response;
  try {
    backendResponse = await verifyOwnerToken(token);
  } catch {
    return NextResponse.json({ ok: false, error: "Backend API is unavailable" }, { status: 502 });
  }

  if (!backendResponse.ok) {
    return ownerError(backendResponse.status === 401 ? 401 : backendResponse.status);
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(OWNER_TOKEN_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    maxAge: ownerSessionMaxAgeSeconds(),
    path: "/",
  });
  return response;
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = request.cookies.get(OWNER_TOKEN_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ ok: false }, { status: 401 });
  }

  let backendResponse: Response;
  try {
    backendResponse = await verifyOwnerToken(token);
  } catch {
    return NextResponse.json({ ok: false, error: "Backend API is unavailable" }, { status: 502 });
  }

  if (!backendResponse.ok) {
    const response = ownerError(backendResponse.status === 401 ? 401 : backendResponse.status);
    if (backendResponse.status === 401) {
      clearOwnerCookie(response);
    }
    return response;
  }

  return NextResponse.json({ ok: true });
}

export async function DELETE(): Promise<NextResponse> {
  const response = NextResponse.json({ ok: true });
  clearOwnerCookie(response);
  return response;
}
