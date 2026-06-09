import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { DashboardShell } from "@/components/dashboard-shell";

const ACCESS_TOKEN_COOKIE = "zroky_access_token";

export default async function DashboardLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  if (!cookieStore.get(ACCESS_TOKEN_COOKIE)?.value) {
    redirect("/login?next=%2Fhome");
  }

  return <DashboardShell>{children}</DashboardShell>;
}
