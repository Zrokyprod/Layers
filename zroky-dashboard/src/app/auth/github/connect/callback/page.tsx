"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { completeGithubRepoConnect } from "@/lib/api";

function ConnectCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");

    if (!code || !state) {
      setError("Missing OAuth callback parameters. Start GitHub connect again from Settings.");
      return;
    }

    const oauthCode = code;
    const oauthState = state;
    let cancelled = false;

    async function completeConnect() {
      try {
        await completeGithubRepoConnect(oauthCode, oauthState);
        if (cancelled) {
          return;
        }
        router.replace("/settings");
        router.refresh();
      } catch (callbackError) {
        if (cancelled) {
          return;
        }
        const message = callbackError instanceof Error ? callbackError.message : "GitHub connection failed.";
        setError(message);
      }
    }

    void completeConnect();

    return () => {
      cancelled = true;
    };
  }, [router, searchParams]);

  return (
    <div className="auth-callback-screen">
      <div className="auth-card">
        <div className="auth-header">
          <h2 className="auth-heading">Connecting GitHub Repository</h2>
          <p className="auth-sub">Validating OAuth callback and saving your repo access token.</p>
        </div>
        {error ? (
          <div className="auth-banner auth-banner-error">
            {error} — <Link href="/settings" className="auth-link">Return to settings</Link>
          </div>
        ) : (
          <p className="hint">Please wait. Redirecting to settings…</p>
        )}
      </div>
    </div>
  );
}

function ConnectCallbackFallback() {
  return (
    <div className="auth-callback-screen">
      <div className="auth-card">
        <div className="auth-header">
          <h2 className="auth-heading">Connecting GitHub Repository</h2>
          <p className="auth-sub">Preparing callback context…</p>
        </div>
      </div>
    </div>
  );
}

export default function GithubConnectCallbackPage() {
  return (
    <Suspense fallback={<ConnectCallbackFallback />}>
      <ConnectCallbackContent />
    </Suspense>
  );
}
