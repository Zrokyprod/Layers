import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ACCESS_TOKEN_COOKIE = "zroky_access_token";
const REFRESH_TOKEN_COOKIE = "zroky_refresh_token";

type SetSessionBody = {
  access_token: string;
  refresh_token: string;
  access_max_age_seconds: number;
  refresh_max_age_seconds: number;
};

export async function POST(request: NextRequest): Promise<NextResponse> {
  let body: SetSessionBody;
  try {
    body = (await request.json()) as SetSessionBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { access_token, refresh_token, access_max_age_seconds, refresh_max_age_seconds } = body;

  if (!access_token || !refresh_token || !access_max_age_seconds || !refresh_max_age_seconds) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
  }

  const isProduction = process.env.NODE_ENV === "production";

  const response = NextResponse.json({ ok: true });

  response.cookies.set(ACCESS_TOKEN_COOKIE, access_token, {
    httpOnly: true,
    secure: isProduction,
    sameSite: "strict",
    maxAge: access_max_age_seconds,
    path: "/",
  });

  response.cookies.set(REFRESH_TOKEN_COOKIE, refresh_token, {
    httpOnly: true,
    secure: isProduction,
    sameSite: "strict",
    maxAge: refresh_max_age_seconds,
    path: "/",
  });

  return response;
}
