"use client";

import { FormEvent, Suspense, useState } from "react";
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
import { loginWithPassword, verifyMfaLogin } from "@/lib/api";
import { setPendingPostAuthRedirectPath, storeAuthSession } from "@/lib/auth";
import { buildSignupHref, buildVerifyEmailHref, safeAppPath } from "@/lib/onboarding-intent";
import { loginSchema, type LoginFormData } from "@/lib/schemas";
import type { AuthLoginResponse, MfaLoginChallengeResponse } from "@/lib/types";

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

function isMfaLoginChallenge(res: AuthLoginResponse): res is MfaLoginChallengeResponse {
  return "mfa_required" in res && res.mfa_required;
}

function LoginForm() {
  const [error, setError] = useState("");
  const [mfaChallenge, setMfaChallenge] = useState<{ token: string; email: string } | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [mfaLoading, setMfaLoading] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();
  const visibleError = error || authErrorMessage(searchParams.get("error"));
  const nextPath = safeAppPath(searchParams.get("next"), "/home");

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
      if (isMfaLoginChallenge(res)) {
        setMfaChallenge({ token: res.challenge_token, email: data.email });
        setMfaCode("");
        return;
      }
      await storeAuthSession(res);
      if (!res.email_verified) {
        router.push(buildVerifyEmailHref(data.email, nextPath));
        return;
      }
      router.push(nextPath);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Invalid email or password");
    }
  });

  async function onVerifyMfa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!mfaChallenge) return;
    setError("");
    setMfaLoading(true);
    try {
      const res = await verifyMfaLogin(mfaChallenge.token, mfaCode);
      await storeAuthSession(res);
      if (!res.email_verified) {
        router.push(buildVerifyEmailHref(mfaChallenge.email, nextPath));
        return;
      }
      router.push(nextPath);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Invalid authenticator code");
    } finally {
      setMfaLoading(false);
    }
  }

  const handleOAuthLogin = (provider: "github" | "google") => {
    setPendingPostAuthRedirectPath(nextPath);
    window.location.assign(`/api/zroky/v1/auth/${provider}/start`);
  };

  return (
    <AuthCard
      eyebrow="Existing workspace"
      title="Sign in to Zroky"
      subtitle="Access policy gates, approvals, source proof, and signed evidence."
      footer={<Link href={buildSignupHref(nextPath)} className="auth-link">Don&apos;t have an account? Sign up</Link>}
    >
      {visibleError && <div className="auth-banner auth-banner-error">{visibleError}</div>}
      {mfaChallenge ? (
        <form method="post" onSubmit={onVerifyMfa} className="auth-form">
          <AuthInput
            id="mfa-code"
            label="Authenticator code"
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="123456"
            value={mfaCode}
            onChange={(event) => setMfaCode(event.target.value)}
          />
          <AuthButton type="submit" loading={mfaLoading} loadingLabel="Verifying...">
            Verify and continue
          </AuthButton>
          <button type="button" className="auth-link" onClick={() => setMfaChallenge(null)}>
            Use a different account
          </button>
        </form>
      ) : (
        <>
          <div className="auth-oauth-stack">
            <AuthProviderButton provider="google" onClick={() => handleOAuthLogin("google")} />
            <AuthProviderButton provider="github" onClick={() => handleOAuthLogin("github")} />
          </div>
          <AuthDivider />
          <form method="post" onSubmit={onSubmit} className="auth-form">
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
        </>
      )}
      <AuthAssuranceList
        items={[
          "OAuth and password supported",
          "Protected workspace session",
          "Receipts and evidence stay attached",
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
