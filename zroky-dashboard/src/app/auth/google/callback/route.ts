import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function GET(request: NextRequest): NextResponse {
  const error = request.nextUrl.searchParams.get("error");
  if (error) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("error", error);
    return NextResponse.redirect(loginUrl, { status: 302 });
  }

  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  if (!code || !state) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("error", "oauth_failed");
    return NextResponse.redirect(loginUrl, { status: 302 });
  }

  const callbackUrl = new URL("/api/zroky/v1/auth/google/callback", request.url);
  request.nextUrl.searchParams.forEach((value, key) => {
    callbackUrl.searchParams.set(key, value);
  });

  return NextResponse.redirect(callbackUrl, { status: 302 });
}
