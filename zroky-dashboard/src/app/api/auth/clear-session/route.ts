import { NextResponse } from "next/server";

const ACCESS_TOKEN_COOKIE = "zroky_access_token";
const REFRESH_TOKEN_COOKIE = "zroky_refresh_token";

export async function POST(): Promise<NextResponse> {
  const response = NextResponse.json({ ok: true });

  response.cookies.set(ACCESS_TOKEN_COOKIE, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    maxAge: 0,
    path: "/",
  });

  response.cookies.set(REFRESH_TOKEN_COOKIE, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    maxAge: 0,
    path: "/",
  });

  return response;
}
