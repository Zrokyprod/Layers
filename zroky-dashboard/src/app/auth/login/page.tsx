"use client";

import { Suspense, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { storeAuthSession } from "@/lib/auth";
import { loginWithPassword } from "@/lib/api";
import { loginSchema, type LoginFormData } from "@/lib/schemas";

function LoginForm() {
  const [error, setError] = useState("");
  const [showPw, setShowPw] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = handleSubmit(async (data) => {
    setError("");
    try {
      const res = await loginWithPassword(data.email, data.password);
      await storeAuthSession(res);
      const next = searchParams.get("next");
      router.push(next && next.startsWith("/") ? next : "/home");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Invalid email or password");
    }
  });

  const handleOAuthLogin = (provider: "github" | "google") => {
    window.location.href = `/api/zroky/v1/auth/${provider}/start`;
  };

  return (
    <>
      {error && <div className="auth-banner auth-banner-error">{error}</div>}
      <div className="auth-oauth-stack">
        <button onClick={() => handleOAuthLogin("google")} className="auth-oauth-btn">
          Continue with Google
        </button>
        <button onClick={() => handleOAuthLogin("github")} className="auth-oauth-btn auth-oauth-btn-dark">
          Continue with GitHub
        </button>
      </div>
      <div className="auth-divider"><span>Or continue with email</span></div>
      <form onSubmit={onSubmit} className="auth-form">
        <div className="field">
          <label htmlFor="login-email">Email address</label>
          <input id="login-email" type="email" {...register("email")} placeholder="admin@zroky.com" />
          {errors.email && <span className="field-error">{errors.email.message}</span>}
        </div>
        <div className="field">
          <div className="auth-label-row">
            <label htmlFor="login-password">Password</label>
            <Link href="/auth/forgot-password" className="auth-link">Forgot password?</Link>
          </div>
          <div className="input-eye-wrap">
            <input id="login-password" type={showPw ? "text" : "password"} autoComplete="current-password" {...register("password")} placeholder="Your password" />
            <button type="button" className="input-eye-btn" tabIndex={-1} aria-label={showPw ? "Hide password" : "Show password"} onClick={() => setShowPw((v) => !v)}>
              {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          {errors.password && <span className="field-error">{errors.password.message}</span>}
        </div>
        <button type="submit" disabled={isSubmitting} className="btn btn-primary auth-submit-btn">
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </>
  );
}

export default function LoginPage() {
  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-header">
          <h2 className="auth-heading">Sign in to Zroky</h2>
          <p className="auth-sub">AI Agent Reliability Platform</p>
        </div>
        <Suspense fallback={<p className="hint">Loading…</p>}>
          <LoginForm />
        </Suspense>
        <p className="auth-foot">
          <Link href="/auth/register" className="auth-link">Don&apos;t have an account? Sign up</Link>
        </p>
      </div>
    </div>
  );
}
