import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function loginRedirect(request: NextRequest, error: string): NextResponse {
  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("error", error);
  return NextResponse.redirect(loginUrl, { status: 302 });
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
  if (location && response.status >= 300 && response.status < 400) {
    return NextResponse.redirect(location, { status: 302 });
  }

  if (response.status === 400) {
    return loginRedirect(request, "oauth_expired");
  }

  return loginRedirect(request, "oauth_failed");
}
