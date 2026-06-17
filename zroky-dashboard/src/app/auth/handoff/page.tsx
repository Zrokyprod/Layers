"use client";

import { Suspense, useEffect } from "react";
import { useRouter } from "next/navigation";

import { AuthCard, AuthShell } from "@/components/auth-shell";

function HandoffContent() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/login?error=handoff_disabled");
  }, [router]);

  return (
    <AuthShell>
      <AuthCard title="Signing you in" subtitle="Completing secure access.">
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
