"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import {
  AuthAssuranceList,
  AuthButton,
  AuthCard,
  AuthDivider,
  AuthInput,
  AuthProviderButton,
  AuthShell,
} from "@/components/auth-shell";
import { loginWithPassword } from "@/lib/api";
import { storeAuthSession } from "@/lib/auth";
import { loginSchema, type LoginFormData } from "@/lib/schemas";

function authErrorMessage(code: string | null): string {
  switch (code) {
    case "access_denied":
      return "Google sign-in was cancelled.";
    case "oauth_expired":
      return "Google sign-in expired. Start again.";
    case "oauth_failed":
      return "Google sign-in could not complete. Start again.";
    default:
      return "";
  }
}

function LoginForm() {
  const [error, setError] = useState("");
  const router = useRouter();
  const searchParams = useSearchParams();
  const visibleError = error || authErrorMessage(searchParams.get("error"));

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
      if (!res.email_verified) {
        router.push(`/verify-email?email=${encodeURIComponent(data.email)}`);
        return;
      }
      router.push(next && next.startsWith("/") ? next : "/home");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Invalid email or password");
    }
  });

  const handleOAuthLogin = (provider: "github" | "google") => {
    window.location.href = `/api/zroky/v1/auth/${provider}/start`;
  };

  return (
    <AuthCard
      eyebrow="Existing workspace"
      title="Sign in to Zroky"
      subtitle="Access traces, replays, and release gates."
      footer={<Link href="/signup" className="auth-link">Don&apos;t have an account? Sign up</Link>}
    >
      {visibleError && <div className="auth-banner auth-banner-error">{visibleError}</div>}
      <div className="auth-oauth-stack">
        <AuthProviderButton provider="google" onClick={() => handleOAuthLogin("google")} />
        <AuthProviderButton provider="github" onClick={() => handleOAuthLogin("github")} />
      </div>
      <AuthDivider />
      <form onSubmit={onSubmit} className="auth-form">
        <AuthInput
          label="Email address"
          type="email"
          autoComplete="email"
          placeholder="admin@zroky.com"
          error={errors.email?.message}
          {...register("email")}
        />
        <AuthInput
          id="login-password"
          label="Password"
          type="password"
          autoComplete="current-password"
          placeholder="Your password"
          error={errors.password?.message}
          labelAction={<Link href="/forgot-password" className="auth-link">Forgot password?</Link>}
          {...register("password")}
        />
        <AuthButton type="submit" loading={isSubmitting} loadingLabel="Signing in...">
          Sign in
        </AuthButton>
      </form>
      <AuthAssuranceList
        items={[
          "OAuth and password supported",
          "Protected workspace session",
        ]}
      />
    </AuthCard>
  );
}

export default function LoginPage() {
  return (
    <AuthShell>
      <Suspense fallback={<p className="hint">Loading...</p>}>
        <LoginForm />
      </Suspense>
    </AuthShell>
  );
}
