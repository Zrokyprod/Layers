"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthCard, AuthShell } from "@/components/auth-shell";
import { completeOAuthHandoff } from "@/lib/api";
import { getPostAuthRedirectPath, storeAuthSession } from "@/lib/auth";

function OAuthCallbackHandler() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const handoffId = searchParams.get("handoff_id");
    const errorParam = searchParams.get("error");

    if (errorParam) {
      router.replace(`/login?error=${encodeURIComponent(errorParam)}`);
      return;
    }

    if (!handoffId) {
      router.replace("/login?error=oauth_failed");
      return;
    }

    const finish = async () => {
      try {
        const tokens = await completeOAuthHandoff(handoffId);
        await storeAuthSession(tokens);
        router.replace(getPostAuthRedirectPath("/home"));
      } catch {
        router.replace("/login?error=oauth_failed");
      }
    };

    void finish();
  }, [router, searchParams]);

  return (
    <AuthShell>
      <AuthCard title="Signing you in" subtitle="Please wait while we complete authentication.">
        <div className="auth-status">
          <div className="spinner" />
          <p>Creating your Zroky session...</p>
        </div>
      </AuthCard>
    </AuthShell>
  );
}

export default function OAuthCallbackPage() {
  return (
    <Suspense fallback={
      <AuthShell>
        <AuthCard title="Signing you in" subtitle="Preparing callback context.">
          <p className="hint">Loading...</p>
        </AuthCard>
      </AuthShell>
    }>
      <OAuthCallbackHandler />
    </Suspense>
  );
}
