"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { completeGithubLogin } from "@/lib/api";
import { getPostAuthRedirectPath, storeAuthSession } from "@/lib/auth";

function CallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    if (!code || !state) {
      setError("Missing OAuth callback parameters. Start sign-in again.");
      return;
    }

    const oauthCode = code;
    const oauthState = state;

    let cancelled = false;

    async function completeSignIn() {
      try {
        const auth = await completeGithubLogin(oauthCode, oauthState);
        if (cancelled) {
          return;
        }
        storeAuthSession(auth);
        router.replace(getPostAuthRedirectPath("/home"));
        router.refresh();
      } catch (callbackError) {
        if (cancelled) {
          return;
        }
        const message = callbackError instanceof Error ? callbackError.message : "GitHub sign-in failed.";
        setError(message);
      }
    }

    void completeSignIn();

    return () => {
      cancelled = true;
    };
  }, [router, searchParams]);

  return (
    <div className="auth-callback-screen">
      <div className="auth-card">
        <div className="auth-header">
          <h2 className="auth-heading">Completing GitHub Sign-In</h2>
          <p className="auth-sub">Validating OAuth callback and creating your Zroky session.</p>
        </div>
        {error ? (
          <div className="auth-banner auth-banner-error">
            {error} — <Link href="/auth/login" className="auth-link">Return to login</Link>
          </div>
        ) : (
          <p className="hint">Please wait. Redirecting to dashboard…</p>
        )}
      </div>
    </div>
  );
}

function CallbackFallback() {
  return (
    <div className="auth-callback-screen">
      <div className="auth-card">
        <div className="auth-header">
          <h2 className="auth-heading">Completing GitHub Sign-In</h2>
          <p className="auth-sub">Preparing callback context…</p>
        </div>
      </div>
    </div>
  );
}

export default function GitHubCallbackPage() {
  return (
    <Suspense fallback={<CallbackFallback />}>
      <CallbackContent />
    </Suspense>
  );
}
