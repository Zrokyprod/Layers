"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AuthCard, AuthShell } from "@/components/auth-shell";
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
    <AuthShell>
      <AuthCard
        eyebrow="GitHub connection"
        title="Connecting GitHub"
        subtitle="Saving repository access for workspace controls."
      >
        {error ? (
          <div className="auth-banner auth-banner-error">
            {error} <Link href="/settings" className="auth-link">Return to settings</Link>
          </div>
        ) : (
          <div className="auth-status">
            <div className="spinner" />
            <p>Returning to workspace settings...</p>
          </div>
        )}
      </AuthCard>
    </AuthShell>
  );
}

function ConnectCallbackFallback() {
  return (
    <AuthShell>
      <AuthCard
        eyebrow="GitHub connection"
        title="Preparing GitHub connection"
        subtitle="Loading the repository handoff."
      >
        <p className="hint">Loading...</p>
      </AuthCard>
    </AuthShell>
  );
}

export default function GithubConnectCallbackPage() {
  return (
    <Suspense fallback={<ConnectCallbackFallback />}>
      <ConnectCallbackContent />
    </Suspense>
  );
}
