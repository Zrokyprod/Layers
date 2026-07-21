import type { ReactNode } from "react";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

import { DashboardShell } from "@/components/dashboard-shell";
import { checkDashboardSession } from "@/lib/server-session";

const ACCESS_TOKEN_COOKIE = "zroky_access_token";
const DEFAULT_NEXT_PATH = "/home";
const LOCAL_PREVIEW_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

function safeNextPath(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return DEFAULT_NEXT_PATH;
  }
  return value;
}

function loginRedirectPath(nextPath: string, error?: string): string {
  const params = new URLSearchParams({ next: nextPath });
  if (error) {
    params.set("error", error);
  }
  return `/login?${params.toString()}`;
}

function isLocalPreviewHost(hostHeader: string | null): boolean {
  const host = hostHeader ?? "";
  const bracketedIpv6Match = host.match(/^\[([^\]]+)\](?::\d+)?$/);
  const hostname = bracketedIpv6Match?.[1] ?? host.split(":")[0] ?? "";
  return LOCAL_PREVIEW_HOSTS.has(hostname);
}

export default async function DashboardLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const nextPath = safeNextPath(headerStore.get("x-zroky-request-path"));
  if (isLocalPreviewHost(headerStore.get("host"))) {
    return <DashboardShell>{children}</DashboardShell>;
  }

  const accessToken = cookieStore.get(ACCESS_TOKEN_COOKIE)?.value;
  if (!accessToken) {
    redirect(loginRedirectPath(nextPath));
  }

  const session = await checkDashboardSession(accessToken);
  if (session.status === "unauthenticated") {
    redirect(loginRedirectPath(nextPath));
  }
  if (session.status === "unavailable") {
    redirect(loginRedirectPath(nextPath, "session_check_failed"));
  }
  if (!session.user.email_verified) {
    const emailQuery = session.user.email ? `&email=${encodeURIComponent(session.user.email)}` : "";
    redirect(`/verify-email?next=${encodeURIComponent(nextPath)}${emailQuery}`);
  }

  return <DashboardShell>{children}</DashboardShell>;
}
