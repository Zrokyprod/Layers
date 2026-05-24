"use client";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Eye, EyeOff } from "lucide-react";
import { registerSchema, type RegisterFormData } from "@/lib/schemas";
import { registerWithPassword } from "@/lib/api";
import { storeAuthSession } from "@/lib/auth";

export default function RegisterPage() {
  const [error, setError] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [showCfm, setShowCfm] = useState(false);
  const router = useRouter();

  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormData>({ resolver: zodResolver(registerSchema) });

  const pw = useWatch({ control, name: "password", defaultValue: "" }) ?? "";

  const strengthRules = [
    { label: "8+ chars", met: pw.length >= 8 },
    { label: "Uppercase", met: /[A-Z]/.test(pw) },
    { label: "Lowercase", met: /[a-z]/.test(pw) },
    { label: "Number", met: /[0-9]/.test(pw) },
  ];

  const handleOAuth = (provider: "google" | "github") => {
    window.location.href = `/api/zroky/v1/auth/${provider}/start`;
  };

  const onSubmit = handleSubmit(async (data) => {
    setError("");
    try {
      const res = await registerWithPassword(data.email, data.password, data.confirm_password);
      await storeAuthSession(res);
      if (!res.email_verified) {
        router.push(`/auth/check-email?email=${encodeURIComponent(data.email)}`);
      } else {
        router.push("/agents");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed. Please try again.");
    }
  });

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-header">
          <h2 className="auth-heading">Create an account</h2>
          <p className="auth-sub">AI Agent Reliability Platform</p>
        </div>

        <div className="auth-oauth-stack">
          <button type="button" onClick={() => handleOAuth("google")} className="auth-oauth-btn">
            <svg width="18" height="18" viewBox="0 0 24 24" style={{marginRight:8}} aria-hidden="true"><path fill="#4285F4" d="M23.745 12.27c0-.79-.07-1.54-.19-2.27h-11.3v4.51h6.47c-.29 1.48-1.14 2.73-2.4 3.58v3h3.86c2.26-2.09 3.56-5.17 3.56-8.82z"/><path fill="#34A853" d="M12.255 24c3.24 0 5.95-1.08 7.93-2.91l-3.86-3c-1.08.72-2.45 1.16-4.07 1.16-3.13 0-5.78-2.11-6.73-4.96h-3.98v3.09C3.515 21.3 7.565 24 12.255 24z"/><path fill="#FBBC05" d="M5.525 14.29c-.25-.72-.38-1.49-.38-2.29s.14-1.57.38-2.29V6.62h-3.98a11.86 11.86 0 0 0 0 10.76l3.98-3.09z"/><path fill="#EA4335" d="M12.255 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C18.205 1.19 15.495 0 12.255 0c-4.69 0-8.74 2.7-10.71 6.62l3.98 3.09c.95-2.85 3.6-4.96 6.73-4.96z"/></svg>
            Continue with Google
          </button>
          <button type="button" onClick={() => handleOAuth("github")} className="auth-oauth-btn auth-oauth-btn-dark">
            <svg width="18" height="18" viewBox="0 0 24 24" style={{marginRight:8}} fill="currentColor" aria-hidden="true"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>
            Continue with GitHub
          </button>
        </div>

        <div className="auth-divider"><span>Or register with email</span></div>

        {error && <div className="auth-banner auth-banner-error">{error}</div>}

        <form onSubmit={onSubmit} className="auth-form">
          <div className="field">
            <label htmlFor="reg-email">Email address</label>
            <input
              id="reg-email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              {...register("email")}
            />
            {errors.email && <span className="field-error">{errors.email.message}</span>}
          </div>

          <div className="field">
            <label htmlFor="reg-pw">Password</label>
            <div className="input-eye-wrap">
              <input
                id="reg-pw"
                type={showPw ? "text" : "password"}
                autoComplete="new-password"
                placeholder="Min 8 chars, uppercase, number"
                {...register("password")}
              />
              <button
                type="button"
                className="input-eye-btn"
                tabIndex={-1}
                aria-label={showPw ? "Hide password" : "Show password"}
                onClick={() => setShowPw((v) => !v)}
              >
                {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            {errors.password && <span className="field-error">{errors.password.message}</span>}
            {pw.length > 0 && (
              <div className="password-strength">
                {strengthRules.map(({ label, met }) => (
                  <span key={label} className={`strength-chip ${met ? "strength-met" : "strength-unmet"}`}>
                    {met ? "✓" : "✗"} {label}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="field">
            <label htmlFor="reg-cfm">Confirm Password</label>
            <div className="input-eye-wrap">
              <input
                id="reg-cfm"
                type={showCfm ? "text" : "password"}
                autoComplete="new-password"
                placeholder="Repeat your password"
                {...register("confirm_password")}
              />
              <button
                type="button"
                className="input-eye-btn"
                tabIndex={-1}
                aria-label={showCfm ? "Hide password" : "Show password"}
                onClick={() => setShowCfm((v) => !v)}
              >
                {showCfm ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            {errors.confirm_password && <span className="field-error">{errors.confirm_password.message}</span>}
          </div>

          <button type="submit" disabled={isSubmitting} className="btn btn-primary auth-submit-btn">
            {isSubmitting ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="auth-foot">
          <Link href="/auth/login" className="auth-link">Already have an account? Sign in</Link>
        </p>
      </div>
    </div>
  );
}
