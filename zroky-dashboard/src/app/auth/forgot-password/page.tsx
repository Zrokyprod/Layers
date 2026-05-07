"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { forgotPasswordSchema, type ForgotPasswordFormData } from "@/lib/schemas";

export default function ForgotPasswordPage() {
  const [message, setMessage] = useState("");

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
      await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
      });
      setMessage("If that email exists, a password reset link has been sent.");
    } catch {
      setMessage("An error occurred. Please try again.");
    }
  });

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-header">
          <h2 className="auth-heading">Reset your password</h2>
          <p className="auth-sub">Enter your email and we will send you a reset link.</p>
        </div>
        {message && <div className="auth-banner auth-banner-info">{message}</div>}
        <form onSubmit={onSubmit} className="auth-form">
          <div className="field">
            <label htmlFor="fp-email">Email address</label>
            <input id="fp-email" type="email" {...register("email")} />
            {errors.email && <span className="field-error">{errors.email.message}</span>}
          </div>
          <button type="submit" disabled={isSubmitting} className="btn btn-primary auth-submit-btn">
            {isSubmitting ? "Sending…" : "Send reset link"}
          </button>
        </form>
        <p className="auth-foot">
          <Link href="/auth/login" className="auth-link">Back to login</Link>
        </p>
      </div>
    </div>
  );
}
