import { NextRequest, NextResponse } from "next/server";

const ACCESS_TOKEN_COOKIE = "zroky_access_token";

const PROTECTED_PREFIXES = [
  "/home",
  "/calls",
  "/cost",
  "/alerts",
  "/settings",
  "/account",
  "/fixes",
  "/onboarding",
  "/owner",
];

export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );

  if (!isProtected) {
    return NextResponse.next();
  }

  const token = request.cookies.get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/auth/login";
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/).*)"],
};
