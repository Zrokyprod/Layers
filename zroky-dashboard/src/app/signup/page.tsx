"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
import { storeAuthSession } from "@/lib/auth";
import { registerSchema, type RegisterFormData } from "@/lib/schemas";

const googleOAuthEnabled = process.env.NEXT_PUBLIC_ENABLE_GOOGLE_OAUTH === "true";

export default function SignupPage() {
  const [error, setError] = useState("");
  const router = useRouter();

  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormData>({ resolver: zodResolver(registerSchema) });

  const password = useWatch({ control, name: "password", defaultValue: "" }) ?? "";

  const handleOAuth = (provider: "google" | "github") => {
    window.location.href = `/api/zroky/v1/auth/${provider}/start`;
  };

  const onSubmit = handleSubmit(async (data) => {
    setError("");
    try {
      const res = await registerWithPassword(data.email, data.password, data.confirm_password);
      await storeAuthSession(res);
      if (!res.email_verified) {
        router.push(`/verify-email?email=${encodeURIComponent(data.email)}`);
      } else {
        router.push("/home");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed. Please try again.");
    }
  });

  return (
    <AuthShell>
      <AuthCard
        eyebrow="New reliability workspace"
        title="Create your Zroky workspace"
        subtitle="Start capturing failed agent runs and turn replay proof into regression gates."
        footer={<Link href="/login" className="auth-link">Already have an account? Sign in</Link>}
      >
        <div className="auth-oauth-stack">
          {googleOAuthEnabled ? <AuthProviderButton provider="google" onClick={() => handleOAuth("google")} /> : null}
          <AuthProviderButton provider="github" onClick={() => handleOAuth("github")} />
        </div>
        <AuthDivider>Or register with email</AuthDivider>
        {error && <div className="auth-banner auth-banner-error">{error}</div>}
        <form onSubmit={onSubmit} className="auth-form">
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
          items={[
            "Email verification protects the workspace",
            "Capture failed runs after setup",
            "Replay, Goldens, and CI gates are ready",
          ]}
        />
      </AuthCard>
    </AuthShell>
  );
}
