"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

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
      router.replace("/auth/login");
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
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "100vh", gap: 12, background: "var(--bg-canvas)" }}>
      <div style={{ width: 32, height: 32, borderRadius: "50%", border: "3px solid #635bff", borderTopColor: "transparent", animation: "spin 0.7s linear infinite" }} />
      <p style={{ fontSize: "0.9rem", color: "var(--text-secondary)", fontWeight: 500 }}>Signing you in…</p>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export default function HandoffPage() {
  return (
    <Suspense fallback={null}>
      <HandoffContent />
    </Suspense>
  );
}
