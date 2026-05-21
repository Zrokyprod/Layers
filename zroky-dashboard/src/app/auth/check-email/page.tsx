"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { resendVerification } from "@/lib/api";

function CheckEmailContent() {
  const searchParams = useSearchParams();
  const email = searchParams.get("email") ?? "";
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [msg, setMsg] = useState("");

  const handleResend = async () => {
    setStatus("sending");
    setMsg("");
    try {
      const res = await resendVerification();
      setStatus("sent");
      setMsg(res.detail || "Verification email sent! Check your inbox.");
    } catch (err) {
      setStatus("error");
      setMsg(err instanceof Error ? err.message : "Failed to resend. Please try again.");
    }
  };

  return (
    <div className="auth-screen">
      <div className="auth-card" style={{ textAlign: "center" }}>
        <div className="auth-header">
          <div style={{ fontSize: "3rem", marginBottom: "8px" }}>📧</div>
          <h2 className="auth-heading">Check your email</h2>
          <p className="auth-sub">
            We sent a verification link to{" "}
            {email ? <strong>{email}</strong> : "your email address"}.
            <br />
            Click the link to verify your account before logging in.
          </p>
        </div>

        <div className="auth-form" style={{ marginTop: "8px" }}>
          {msg && (
            <div className={`auth-banner ${status === "error" ? "auth-banner-error" : "auth-banner-success"}`}>
              {msg}
            </div>
          )}

          <button
            className="auth-submit-btn btn btn-secondary"
            onClick={handleResend}
            disabled={status === "sending" || status === "sent"}
            style={{ marginTop: "4px" }}
          >
            {status === "sending" ? "Sending…" : status === "sent" ? "Email sent ✓" : "Resend verification email"}
          </button>

          <p className="auth-foot" style={{ marginTop: "8px" }}>
            Already verified?{" "}
            <Link href="/auth/login" className="auth-link">
              Sign in
            </Link>
          </p>

          <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "4px" }}>
            Didn&apos;t get the email? Check your spam folder or resend above.
          </p>
        </div>
      </div>
    </div>
  );
}

export default function CheckEmailPage() {
  return (
    <Suspense>
      <CheckEmailContent />
    </Suspense>
  );
}
