"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthCard, AuthShell } from "@/components/auth-shell";

function HandoffContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const at = searchParams.get("at");
    const rt = searchParams.get("rt");
    const atExp = Number(searchParams.get("at_exp") ?? "259200");
    const rtExp = Number(searchParams.get("rt_exp") ?? "2592000");
    const ev = searchParams.get("ev") !== "false";

    if (!at || !rt) {
      router.replace("/login");
      return;
    }

    if (typeof window !== "undefined") {
      window.localStorage.setItem("zroky_at", at);
      window.localStorage.setItem("zroky_rt", rt);
      window.localStorage.setItem("zroky_ev", String(ev));
    }

    fetch("/api/auth/set-session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        access_token: at,
        refresh_token: rt,
        access_max_age_seconds: atExp,
        refresh_max_age_seconds: rtExp,
      }),
    }).finally(() => {
      router.replace("/agents");
    });
  }, [router, searchParams]);

  return (
    <AuthShell>
      <AuthCard title="Signing you in" subtitle="Creating your authenticated dashboard session.">
        <div className="auth-status">
          <div className="spinner" />
          <p>Redirecting to dashboard...</p>
        </div>
      </AuthCard>
    </AuthShell>
  );
}

export default function HandoffPage() {
  return (
    <Suspense fallback={null}>
      <HandoffContent />
    </Suspense>
  );
}
