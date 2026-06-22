"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { AuthAssuranceList, AuthButton, AuthCard, AuthInput, AuthPasswordChecklist, AuthShell } from "@/components/auth-shell";
import { resetPassword } from "@/lib/api";
import { resetPasswordSchema, type ResetPasswordFormData } from "@/lib/schemas";

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const router = useRouter();
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetPasswordFormData>({
    resolver: zodResolver(resetPasswordSchema),
  });
  const password = useWatch({ control, name: "password", defaultValue: "" }) ?? "";

  if (!token) {
    return (
      <>
        <div className="auth-banner auth-banner-error">Invalid or missing reset token. Please request a new link.</div>
        <Link href="/forgot-password" className="auth-button auth-button-secondary">
          Request new reset link
        </Link>
      </>
    );
  }

  const onSubmit = handleSubmit(async (data) => {
    setError("");
    setMessage("");
    if (data.password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    try {
      await resetPassword(token, data.password);
      setMessage("Password reset successful. Redirecting to login...");
      setTimeout(() => router.push("/login?reset=true"), 2000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Reset failed. The link may have expired.");
    }
  });

  return (
    <form method="post" onSubmit={onSubmit} className="auth-form">
      {error && <div className="auth-banner auth-banner-error">{error}</div>}
      {message && <div className="auth-banner auth-banner-success">{message}</div>}
      <AuthInput
        label="New password"
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
        value={confirmPassword}
        onChange={(event) => setConfirmPassword(event.target.value)}
      />
      <AuthButton type="submit" loading={isSubmitting} loadingLabel="Updating password...">
        Update password
      </AuthButton>
      <AuthAssuranceList
        items={[
          "Reset token validated first",
          "Returns to sign in after reset",
        ]}
      />
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthShell>
      <AuthCard
        eyebrow="Secure reset"
        title="Create new password"
        subtitle="Choose a new workspace password."
        footer={<Link href="/login" className="auth-link">Back to login</Link>}
      >
        <Suspense fallback={<p className="hint">Loading...</p>}>
          <ResetPasswordForm />
        </Suspense>
      </AuthCard>
    </AuthShell>
  );
}
