"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { AuthAssuranceList, AuthButton, AuthCard, AuthEmailNotice, AuthShell } from "@/components/auth-shell";
import { resendVerification, verifyEmail } from "@/lib/api";
import { buildLoginHref, safeAppPath } from "@/lib/onboarding-intent";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const email = searchParams.get("email") ?? "";
  const nextPath = safeAppPath(searchParams.get("next"), "/home");
  const isSetupNext = nextPath.startsWith("/settings/keys");
  const [status, setStatus] = useState<"pending" | "loading" | "success" | "error">(token ? "loading" : "pending");
  const [message, setMessage] = useState("");
  const [resendStatus, setResendStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  useEffect(() => {
    if (!token) {
      return;
    }

    verifyEmail(token)
      .then((res) => {
        setStatus("success");
        setMessage(res.detail || "Email verified.");
      })
      .catch((err: unknown) => {
        setStatus("error");
        setMessage(err instanceof Error ? err.message : "Verification link expired or invalid.");
      });
  }, [token]);

  const handleResend = async () => {
    setResendStatus("sending");
    setMessage("");
    try {
      const res = await resendVerification();
      setResendStatus("sent");
      setMessage(res.detail || "Verification email sent. Check your inbox.");
    } catch (err) {
      setResendStatus("error");
      setMessage(err instanceof Error ? err.message : "Failed to resend. Please try again.");
    }
  };

  if (status === "pending") {
    return (
      <>
        <AuthEmailNotice>
          Verification link sent to {email ? <strong>{email}</strong> : "your email address"}.
        </AuthEmailNotice>
        {message && (
          <div className={`auth-banner ${resendStatus === "error" ? "auth-banner-error" : "auth-banner-success"}`}>
            {message}
          </div>
        )}
        <AuthButton type="button" loading={resendStatus === "sending"} loadingLabel="Sending..." onClick={handleResend}>
          {resendStatus === "sent" ? "Email sent" : "Resend verification email"}
        </AuthButton>
        <AuthAssuranceList
          items={[
            "Verification protects workspace access",
            isSetupNext ? "Next step opens project key setup" : "Resend is available if it expires",
          ]}
        />
        <p className="auth-small-copy">
          Already verified? <Link href={buildLoginHref(nextPath)} className="auth-link">Sign in</Link>
        </p>
      </>
    );
  }

  if (status === "loading") {
    return (
      <div className="auth-status">
        <div className="spinner" />
        <p>Verifying your email</p>
      </div>
    );
  }

  if (status === "success") {
    return (
      <>
        <div className="auth-banner auth-banner-success">{message}</div>
        <Link href={nextPath} className="auth-button auth-button-primary">
          {isSetupNext ? "Continue setup" : "Continue to dashboard"}
        </Link>
      </>
    );
  }

  return (
    <>
      <div className="auth-banner auth-banner-error">{message || "Verification link expired or invalid."}</div>
      <Link href="/login" className="auth-link">Back to login</Link>
    </>
  );
}

export default function VerifyEmailPage() {
  return (
    <AuthShell>
      <AuthCard
        eyebrow="Workspace verification"
        title="Check your email"
        subtitle="Open the verification link."
      >
        <Suspense fallback={<p className="hint">Loading...</p>}>
          <VerifyEmailContent />
        </Suspense>
      </AuthCard>
    </AuthShell>
  );
}
