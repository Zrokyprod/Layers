import { NextRequest, NextResponse } from "next/server";

const ACCESS_TOKEN_COOKIE = "zroky_access_token";

const AUTH_PATH_PREFIX = "/auth";
const PUBLIC_PATHS = new Set<string>(["/auth", "/auth/login", "/auth/register", "/auth/github/callback", "/auth/forgot-password", "/auth/reset-password", "/onboarding"]);
const AUTH_CALLBACK_PASSTHROUGH_PATHS = new Set<string>(["/auth/github/callback", "/auth/github/connect/callback"]);
const PROTECTED_PREFIXES = ["/home", "/calls", "/cost", "/alerts", "/settings", "/account", "/fixes", "/loops", "/trace", "/auth-health"];
// /owner has its own token-gate UI — exclude from cookie auth entirely
const OWNER_PREFIX = "/owner";

function isProtectedPath(pathname: string): boolean {
  if (pathname === "/") {
    return true;
  }
  return PROTECTED_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

function isPublicPath(pathname: string): boolean {
  if (PUBLIC_PATHS.has(pathname)) {
    return true;
  }
  return pathname.startsWith(`${AUTH_PATH_PREFIX}/`);
}

export function middleware(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;
  const token = request.cookies.get(ACCESS_TOKEN_COOKIE)?.value;

  // Owner dashboard uses its own token gate — skip cookie auth
  if (pathname === OWNER_PREFIX || pathname.startsWith(`${OWNER_PREFIX}/`)) {
    return NextResponse.next();
  }

  if (!token && isProtectedPath(pathname)) {
    const loginUrl = new URL("/auth/login", request.url);
    const nextPath = `${pathname}${search}`;
    loginUrl.searchParams.set("next", nextPath);
    return NextResponse.redirect(loginUrl);
  }

  if (token && isPublicPath(pathname) && !AUTH_CALLBACK_PASSTHROUGH_PATHS.has(pathname)) {
    const nextPath = request.nextUrl.searchParams.get("next") || "/home";
    return NextResponse.redirect(new URL(nextPath, request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
