"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AuthCard, AuthShell } from "@/components/auth-shell";
import { completeGithubLogin } from "@/lib/api";
import { resolvePostAuthRedirectPath, storeAuthSession } from "@/lib/auth";

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
        await storeAuthSession(auth);
        if (cancelled) {
          return;
        }
        router.replace(resolvePostAuthRedirectPath("/home"));
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
    <AuthShell>
      <AuthCard
        eyebrow="GitHub sign in"
        title="Completing GitHub sign in"
        subtitle="Verifying identity before workspace access."
      >
        {error ? (
          <div className="auth-banner auth-banner-error">
            {error} <Link href="/login" className="auth-link">Return to login</Link>
          </div>
        ) : (
          <div className="auth-status">
            <div className="spinner" />
            <p>Opening your governed workspace...</p>
          </div>
        )}
      </AuthCard>
    </AuthShell>
  );
}

function CallbackFallback() {
  return (
    <AuthShell>
      <AuthCard
        eyebrow="GitHub sign in"
        title="Preparing GitHub sign in"
        subtitle="Loading the identity handoff."
      >
        <p className="hint">Loading...</p>
      </AuthCard>
    </AuthShell>
  );
}

export default function GitHubCallbackPage() {
  return (
    <Suspense fallback={<CallbackFallback />}>
      <CallbackContent />
    </Suspense>
  );
}
