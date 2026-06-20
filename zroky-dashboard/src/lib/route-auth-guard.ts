import { NextRequest, NextResponse } from "next/server";

const ACCESS_TOKEN_COOKIE = "zroky_access_token";

const PROTECTED_PREFIXES = [
  "/account",
  "/agents",
  "/alerts",
  "/approvals",
  "/calls",
  "/ci-gates",
  "/contracts",
  "/cost",
  "/goldens",
  "/home",
  "/integrations",
  "/issues",
  "/outcomes",
  "/policies",
  "/projects",
  "/replay",
  "/settings",
  "/trace",
];

const RETIRED_DASHBOARD_PREFIXES = ["/drift", "/labs"];

function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

function isRetiredDashboardPath(pathname: string): boolean {
  return RETIRED_DASHBOARD_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function guardDashboardRoute(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;

  if (isRetiredDashboardPath(pathname)) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = "/home";
    redirectUrl.search = "";
    return NextResponse.redirect(redirectUrl);
  }

  if (!isProtectedPath(pathname)) {
    return NextResponse.next();
  }

  const token = request.cookies.get(ACCESS_TOKEN_COOKIE)?.value;
  if (token) {
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set("x-zroky-request-path", `${pathname}${search}`);
    return NextResponse.next({
      request: {
        headers: requestHeaders,
      },
    });
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", `${pathname}${search}`);
  return NextResponse.redirect(loginUrl);
}
