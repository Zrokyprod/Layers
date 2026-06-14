"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { AuthAssuranceList, AuthButton, AuthCard, AuthEmailNotice, AuthInput, AuthShell } from "@/components/auth-shell";
import { forgotPassword } from "@/lib/api";
import { forgotPasswordSchema, type ForgotPasswordFormData } from "@/lib/schemas";

export default function ForgotPasswordPage() {
  const [message, setMessage] = useState("");
  const [isSuccess, setIsSuccess] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotPasswordFormData>({
    resolver: zodResolver(forgotPasswordSchema),
  });

  const onSubmit = handleSubmit(async (data) => {
    setMessage("");
    try {
      await forgotPassword(data.email);
      setIsSuccess(true);
      setMessage("If that email is registered, a reset link was sent. Check your inbox.");
    } catch {
      setIsSuccess(true);
      setMessage("If that email is registered, a reset link was sent. Check your inbox.");
    }
  });

  return (
    <AuthShell>
      <AuthCard
        eyebrow="Account recovery"
        title="Recover workspace access"
        subtitle="Send a reset link while keeping account discovery private."
        footer={<Link href="/login" className="auth-link">Back to login</Link>}
      >
        {message && <div className={`auth-banner ${isSuccess ? "auth-banner-success" : "auth-banner-error"}`}>{message}</div>}
        {!message && (
          <AuthEmailNotice>
            Use the email connected to your Zroky workspace. The recovery response stays privacy-preserving.
          </AuthEmailNotice>
        )}
        <form onSubmit={onSubmit} className="auth-form">
          <AuthInput
            label="Email address"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            error={errors.email?.message}
            {...register("email")}
          />
          <AuthButton type="submit" loading={isSubmitting} loadingLabel="Sending...">
            Send reset link
          </AuthButton>
        </form>
        <AuthAssuranceList
          items={[
            "The response stays privacy-preserving",
            "Reset instructions go only to the workspace inbox",
            "You can return to sign in anytime",
          ]}
        />
      </AuthCard>
    </AuthShell>
  );
}
