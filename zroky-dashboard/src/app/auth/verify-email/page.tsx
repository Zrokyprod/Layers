"use client";
import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { verifyEmail } from "@/lib/api";

function VerifyEmailHandler() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Invalid verification link. Please request a new one.");
      return;
    }

    verifyEmail(token)
      .then((res) => {
        setStatus("success");
        setMessage(res.detail || "Email verified successfully!");
      })
      .catch((err: unknown) => {
        setStatus("error");
        setMessage(
          err instanceof Error ? err.message : "Verification failed. The link may have expired."
        );
      });
  }, [token]);

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-header">
          {status === "loading" && <h2 className="auth-heading">Verifying your email…</h2>}
          {status === "success" && <h2 className="auth-heading">Email Verified ✓</h2>}
          {status === "error" && <h2 className="auth-heading">Verification Failed</h2>}
        </div>

        {status === "loading" && (
          <div style={{ display: "flex", justifyContent: "center", padding: "24px" }}>
            <div className="spinner" />
          </div>
        )}

        {status === "success" && (
          <>
            <div className="auth-banner auth-banner-success">{message}</div>
            <p className="auth-foot" style={{ marginTop: "16px" }}>
              <Link href="/home" className="btn btn-primary auth-submit-btn" style={{ display: "inline-block", textDecoration: "none" }}>
                Go to Dashboard
              </Link>
            </p>
          </>
        )}

        {status === "error" && (
          <>
            <div className="auth-banner auth-banner-error">{message}</div>
            <p className="auth-foot" style={{ marginTop: "16px" }}>
              <Link href="/auth/login" className="auth-link">Back to login</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={
      <div className="auth-screen">
        <div className="auth-card"><p className="hint">Loading…</p></div>
      </div>
    }>
      <VerifyEmailHandler />
    </Suspense>
  );
}
