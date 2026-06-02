"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthCard, AuthShell } from "@/components/auth-shell";
import { storeAuthSession } from "@/lib/auth";

function OAuthCallbackHandler() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const accessToken = searchParams.get("access_token");
    const refreshToken = searchParams.get("refresh_token");
    const expiresIn = searchParams.get("expires_in");
    const userId = searchParams.get("user_id");
    const errorParam = searchParams.get("error");

    if (errorParam) {
      router.replace(`/login?error=${encodeURIComponent(errorParam)}`);
      return;
    }

    if (!accessToken || !refreshToken) {
      router.replace("/login?error=oauth_failed");
      return;
    }

    const finish = async () => {
      await storeAuthSession({
        access_token: accessToken,
        refresh_token: refreshToken,
        access_expires_in_seconds: Number(expiresIn) || 3600,
        refresh_expires_in_seconds: 604800,
        token_type: "bearer",
        user_id: userId || "",
        email: null,
        email_verified: true,
      });
      router.replace("/home");
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
