"use client";
import { useState, Suspense } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { resetPasswordSchema, type ResetPasswordFormData } from "@/lib/schemas";
import { resetPassword } from "@/lib/api";

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const router = useRouter();

  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [showPw, setShowPw] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetPasswordFormData>({
    resolver: zodResolver(resetPasswordSchema),
  });

  if (!token) {
    return <div className="auth-banner auth-banner-error">Invalid or missing reset token. Please request a new link.</div>;
  }

  const onSubmit = handleSubmit(async (data) => {
    setError(""); setMessage("");
    try {
      await resetPassword(token, data.password);
      setMessage("Password reset successful! Redirecting to login…");
      setTimeout(() => router.push("/auth/login?reset=true"), 2000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Reset failed. The link may have expired.");
    }
  });

  return (
    <form onSubmit={onSubmit} className="auth-form">
      {error && <div className="auth-banner auth-banner-error">{error}</div>}
      {message && <div className="auth-banner auth-banner-success">{message}</div>}
      <div className="field">
        <label htmlFor="rp-password">New Password</label>
        <div className="input-eye-wrap">
          <input id="rp-password" type={showPw ? "text" : "password"} autoComplete="new-password" placeholder="Min 8 chars, uppercase, number" {...register("password")} />
          <button type="button" className="input-eye-btn" tabIndex={-1} aria-label={showPw ? "Hide" : "Show"} onClick={() => setShowPw((v) => !v)}>
            {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
        {errors.password && <span className="field-error">{errors.password.message}</span>}
      </div>
      <button type="submit" disabled={isSubmitting} className="btn btn-primary auth-submit-btn">
        {isSubmitting ? "Resetting…" : "Reset Password"}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-header">
          <h2 className="auth-heading">Enter new password</h2>
        </div>
        <Suspense fallback={<p className="hint">Loading…</p>}>
          <ResetPasswordForm />
        </Suspense>
        <p className="auth-foot">
          <Link href="/auth/login" className="auth-link">Back to login</Link>
        </p>
      </div>
    </div>
  );
}
