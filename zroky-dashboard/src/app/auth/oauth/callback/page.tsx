"use client";
import { useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
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
      router.replace(`/auth/login?error=${encodeURIComponent(errorParam)}`);
      return;
    }

    if (!accessToken || !refreshToken) {
      router.replace("/auth/login?error=oauth_failed");
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
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-header">
          <h2 className="auth-heading">Signing you in…</h2>
          <p className="auth-sub">Please wait while we complete authentication.</p>
        </div>
        <div style={{ display: "flex", justifyContent: "center", padding: "24px" }}>
          <div className="spinner" />
        </div>
      </div>
    </div>
  );
}

export default function OAuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="auth-screen">
        <div className="auth-card">
          <p className="hint">Loading…</p>
        </div>
      </div>
    }>
      <OAuthCallbackHandler />
    </Suspense>
  );
}
