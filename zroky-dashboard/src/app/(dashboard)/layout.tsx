import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { DashboardShell } from "@/components/dashboard-shell";
import { checkDashboardSession } from "@/lib/server-session";

const ACCESS_TOKEN_COOKIE = "zroky_access_token";

export default async function DashboardLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  const accessToken = cookieStore.get(ACCESS_TOKEN_COOKIE)?.value;
  if (!accessToken) {
    redirect("/login?next=%2Fhome");
  }

  const session = await checkDashboardSession(accessToken);
  if (session.status === "unauthenticated") {
    redirect("/login?next=%2Fhome");
  }
  if (session.status === "unavailable") {
    redirect("/login?error=session_check_failed&next=%2Fhome");
  }
  if (!session.user.email_verified) {
    const emailQuery = session.user.email ? `&email=${encodeURIComponent(session.user.email)}` : "";
    redirect(`/verify-email?next=%2Fhome${emailQuery}`);
  }

  return <DashboardShell>{children}</DashboardShell>;
}
