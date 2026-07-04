"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import {
  AuthAssuranceList,
  AuthButton,
  AuthCard,
  AuthDivider,
  AuthInput,
  AuthPasswordChecklist,
  AuthProviderButton,
  AuthShell,
} from "@/components/auth-shell";
import { registerWithPassword } from "@/lib/api";
import { setPendingPostAuthRedirectPath, storeAuthSession } from "@/lib/auth";
import {
  buildLoginHref,
  buildVerifyEmailHref,
  isProtectedAgentSignupIntent,
  resolveSignupRedirectPath,
} from "@/lib/onboarding-intent";
import { registerSchema, type RegisterFormData } from "@/lib/schemas";

function SignupForm() {
  const [error, setError] = useState("");
  const router = useRouter();
  const searchParams = useSearchParams();
  const postSignupPath = resolveSignupRedirectPath(searchParams);
  const protectedAgentIntent = isProtectedAgentSignupIntent(searchParams);
  const signInHref = buildLoginHref(postSignupPath);

  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormData>({ resolver: zodResolver(registerSchema) });

  const password = useWatch({ control, name: "password", defaultValue: "" }) ?? "";

  const handleOAuth = (provider: "google" | "github") => {
    setPendingPostAuthRedirectPath(postSignupPath);
    window.location.assign(`/api/zroky/v1/auth/${provider}/start`);
  };

  const onSubmit = handleSubmit(async (data) => {
    setError("");
    try {
      const res = await registerWithPassword(data.email, data.password, data.confirm_password);
      await storeAuthSession(res);
      if (!res.email_verified) {
        router.push(buildVerifyEmailHref(data.email, postSignupPath));
      } else {
        router.push(postSignupPath);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed. Please try again.");
    }
  });

  return (
    <AuthCard
      eyebrow={protectedAgentIntent ? "Protected agent setup" : "New control-plane workspace"}
      title="Create your Zroky workspace"
      subtitle={
        protectedAgentIntent
          ? "Create a runtime key, connect your first agent, and send the first protected action."
          : "Start with one governed action, then expand by policy."
      }
      footer={<Link href={signInHref} className="auth-link">Already have an account? Sign in</Link>}
    >
      {protectedAgentIntent && (
        <div className="auth-banner auth-banner-info">
          Next step: guided agent setup for the runtime you want Zroky to protect.
        </div>
      )}
      <div className="auth-oauth-stack">
        <AuthProviderButton provider="google" onClick={() => handleOAuth("google")} />
        <AuthProviderButton provider="github" onClick={() => handleOAuth("github")} />
      </div>
      <AuthDivider>Or register with email</AuthDivider>
      {error && <div className="auth-banner auth-banner-error">{error}</div>}
      <form method="post" onSubmit={onSubmit} className="auth-form">
        <AuthInput
          label="Email address"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          error={errors.email?.message}
          {...register("email")}
        />
        <AuthInput
          label="Password"
          type="password"
          autoComplete="new-password"
          placeholder="Minimum 8 characters"
          error={errors.password?.message}
          {...register("password")}
        />
        {password.length > 0 && <AuthPasswordChecklist password={password} />}
        <AuthInput
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          placeholder="Repeat your password"
          error={errors.confirm_password?.message}
          {...register("confirm_password")}
        />
        <AuthButton type="submit" loading={isSubmitting} loadingLabel="Creating account...">
          Create account
        </AuthButton>
      </form>
      <AuthAssuranceList
        items={
          protectedAgentIntent
            ? [
                "Next step opens agent setup",
                "Key, SDK, and first receipt stay in one path",
              ]
            : [
                "Email verification protects workspace access",
                "First protected action can start free",
              ]
        }
      />
    </AuthCard>
  );
}

export default function SignupPage() {
  return (
    <AuthShell>
      <Suspense fallback={<p className="hint">Loading...</p>}>
        <SignupForm />
      </Suspense>
    </AuthShell>
  );
}
