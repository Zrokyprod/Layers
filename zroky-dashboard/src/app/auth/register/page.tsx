"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { registerSchema, type RegisterFormData } from "@/lib/schemas";
import { registerWithPassword } from "@/lib/api";
import { storeAuthSession } from "@/lib/auth";

export default function RegisterPage() {
  const [error, setError] = useState("");
  const router = useRouter();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
  });

  const onSubmit = handleSubmit(async (data) => {
    setError("");
    try {
      const res = await registerWithPassword(data.email, data.password, data.confirm_password);
      storeAuthSession(res);
      router.push("/home");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
    }
  });

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-header">
          <h2 className="auth-heading">Create an account</h2>
          <p className="auth-sub">Join Zroky AI Rate Limit Engine</p>
        </div>
        {error && <div className="auth-banner auth-banner-error">{error}</div>}
        <form onSubmit={onSubmit} className="auth-form">
          <div className="field">
            <label htmlFor="reg-email">Email address</label>
            <input id="reg-email" type="email" {...register("email")} placeholder="you@example.com" />
            {errors.email && <span className="field-error">{errors.email.message}</span>}
          </div>
          <div className="field">
            <label htmlFor="reg-password">Password</label>
            <input id="reg-password" type="password" {...register("password")} placeholder="Min 8 characters" />
            {errors.password && <span className="field-error">{errors.password.message}</span>}
          </div>
          <div className="field">
            <label htmlFor="reg-confirm">Confirm Password</label>
            <input id="reg-confirm" type="password" {...register("confirm_password")} placeholder="Repeat your password" />
            {errors.confirm_password && <span className="field-error">{errors.confirm_password.message}</span>}
          </div>
          <button type="submit" disabled={isSubmitting} className="btn btn-primary auth-submit-btn">
            {isSubmitting ? "Creating account…" : "Sign up"}
          </button>
        </form>
        <p className="auth-foot">
          <Link href="/auth/login" className="auth-link">Already have an account? Sign in</Link>
        </p>
      </div>
    </div>
  );
}
