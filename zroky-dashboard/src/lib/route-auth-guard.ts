import { NextRequest, NextResponse } from "next/server";

import {
  isDashboardProtectedPath,
  isDashboardRetiredPath,
} from "./dashboard-route-contract";

const ACCESS_TOKEN_COOKIE = "zroky_access_token";
const LOCAL_PREVIEW_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

function localDashboardPreviewEnabled(request: NextRequest): boolean {
  return LOCAL_PREVIEW_HOSTS.has(request.nextUrl.hostname);
}

export function guardDashboardRoute(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;

  if (isDashboardRetiredPath(pathname)) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = "/home";
    redirectUrl.search = "";
    return NextResponse.redirect(redirectUrl);
  }

  if (!isDashboardProtectedPath(pathname)) {
    return NextResponse.next();
  }

  const token = request.cookies.get(ACCESS_TOKEN_COOKIE)?.value;
  if (token || localDashboardPreviewEnabled(request)) {
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
