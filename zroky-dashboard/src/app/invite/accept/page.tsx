"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, MailCheck, TriangleAlert } from "lucide-react";

import { AuthButton, AuthCard, AuthShell } from "@/components/auth-shell";
import { acceptInvitation, ApiError } from "@/lib/api";
import { buildLoginHref, buildSignupHref } from "@/lib/onboarding-intent";
import { useDashboardStore } from "@/lib/store";

type InviteState = "accepting" | "auth-required" | "accepted" | "failed";

function InvitationAcceptance() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token")?.trim() ?? "";
  const [state, setState] = useState<InviteState>(token ? "accepting" : "failed");
  const [message, setMessage] = useState(token ? "Verifying your invitation..." : "This invitation link is incomplete.");
  const setSelectedProject = useDashboardStore((store) => store.setSelectedProject);
  const nextPath = token ? `/invite/accept?token=${encodeURIComponent(token)}` : "/invite/accept";

  const accept = useCallback(async () => {
    if (!token) return;
    setState("accepting");
    setMessage("Verifying your invitation...");
    try {
      const result = await acceptInvitation(token);
      if (!result.success || !result.project_id) {
        setState("failed");
        setMessage(result.message);
        return;
      }
      setSelectedProject(result.project_id);
      setState("accepted");
      setMessage(result.message);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setState("auth-required");
        setMessage("Sign in or create an account with the email address that received this invitation.");
        return;
      }
      setState("failed");
      setMessage(error instanceof Error ? error.message : "Invitation could not be accepted.");
    }
  }, [setSelectedProject, token]);

  useEffect(() => {
    void accept();
  }, [accept]);

  const icon = state === "accepted"
    ? <CheckCircle2 aria-hidden="true" />
    : state === "failed"
      ? <TriangleAlert aria-hidden="true" />
      : <MailCheck aria-hidden="true" />;

  return (
    <AuthCard
      eyebrow="Project invitation"
      title={state === "accepted" ? "Invitation accepted" : "Join this workspace"}
      subtitle={message}
    >
      <div className={`auth-banner ${state === "failed" ? "auth-banner-error" : "auth-banner-info"}`}>
        {icon}
        <span>{message}</span>
      </div>

      {state === "auth-required" ? (
        <div className="auth-oauth-stack">
          <Link className="auth-button auth-button-primary" href={buildLoginHref(nextPath)}>Sign in to accept</Link>
          <Link className="auth-button auth-button-secondary" href={buildSignupHref(nextPath)}>Create account</Link>
        </div>
      ) : null}

      {state === "accepted" ? (
        <Link className="auth-button auth-button-primary" href="/home">Open project</Link>
      ) : null}

      {state === "failed" && token ? (
        <AuthButton type="button" variant="secondary" onClick={() => void accept()}>
          Try again
        </AuthButton>
      ) : null}
    </AuthCard>
  );
}

export default function AcceptInvitationPage() {
  return (
    <AuthShell>
      <Suspense fallback={<p className="hint">Loading invitation...</p>}>
        <InvitationAcceptance />
      </Suspense>
    </AuthShell>
  );
}
