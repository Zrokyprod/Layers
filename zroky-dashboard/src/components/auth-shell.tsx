"use client";

import { CheckCircle2, Eye, EyeOff, KeyRound, Mail } from "lucide-react";
import { motion, useReducedMotion, type Variants } from "motion/react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { useState } from "react";
import { FaGithub } from "react-icons/fa";
import { FcGoogle } from "react-icons/fc";

type AuthShellProps = {
  children: ReactNode;
};

type AuthCardProps = {
  title: string;
  subtitle: string;
  children: ReactNode;
  eyebrow?: string;
  footer?: ReactNode;
};

type AuthInputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
  labelAction?: ReactNode;
};

type AuthButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  loading?: boolean;
  loadingLabel?: string;
  variant?: "primary" | "secondary";
};

type AuthProvider = "google" | "github";

const authFade: Variants = {
  hidden: { opacity: 0, y: 14 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.42, ease: "easeOut" },
  },
};

const authStagger: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.06, delayChildren: 0.04 },
  },
};

const authLogoSrc = "/logo.png?v=landing-white";

export function AuthBrandPanel() {
  const shouldReduceMotion = useReducedMotion();
  const motionProps = shouldReduceMotion
    ? { initial: false as const }
    : { initial: "hidden", animate: "visible", variants: authStagger };

  return (
    <motion.section className="auth-brand-panel" aria-label="Zroky reliability platform" {...motionProps}>
      <motion.div className="auth-mark-row" variants={authFade}>
        <div className="auth-logo-wrap">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={authLogoSrc} alt="Zroky" className="auth-logo" />
        </div>
      </motion.div>
      <motion.div className="auth-brand-copy" variants={authFade}>
        <p className="auth-kicker">AI agent reliability</p>
        <h1>Workspace access.</h1>
        <p className="auth-brand-subtitle">Capture failures. Replay fixes. Gate releases.</p>
      </motion.div>
    </motion.section>
  );
}

export function AuthShell({ children }: AuthShellProps) {
  const shouldReduceMotion = useReducedMotion();

  return (
    <main className="auth-shell">
      <AuthBrandPanel />
      <motion.section
        className="auth-form-panel"
        aria-label="Authentication form"
        initial={shouldReduceMotion ? false : { opacity: 0, y: 18 }}
        animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
        transition={{ duration: 0.44, ease: "easeOut" as const, delay: 0.08 }}
      >
        {children}
      </motion.section>
    </main>
  );
}

export function AuthCard({ title, subtitle, children, eyebrow, footer }: AuthCardProps) {
  return (
    <div className="auth-card-shell" aria-label={title}>
      <div className="auth-card-header">
        {eyebrow && <span className="auth-card-eyebrow">{eyebrow}</span>}
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      {children}
      {footer && <div className="auth-card-footer">{footer}</div>}
    </div>
  );
}

export function AuthInput({ label, error, labelAction, id, type = "text", ...props }: AuthInputProps) {
  const [showPassword, setShowPassword] = useState(false);
  const isPassword = type === "password";
  const inputType = isPassword && showPassword ? "text" : type;
  const inputId = id ?? props.name;
  const errorId = inputId ? `${inputId}-error` : undefined;
  const describedBy = [props["aria-describedby"], error && errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="auth-field">
      <div className="auth-label-row">
        <label htmlFor={inputId}>{label}</label>
        {labelAction}
      </div>
      <div className={isPassword ? "auth-input-wrap auth-input-wrap-password" : "auth-input-wrap"}>
        <input
          {...props}
          id={inputId}
          type={inputType}
          aria-invalid={error ? "true" : undefined}
          aria-describedby={describedBy}
        />
        {isPassword && (
          <button
            type="button"
            className="auth-password-toggle"
            aria-controls={inputId}
            aria-label={showPassword ? "Hide password" : "Show password"}
            onClick={() => setShowPassword((value) => !value)}
          >
            {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        )}
      </div>
      {error && <span id={errorId} className="field-error">{error}</span>}
    </div>
  );
}

export function AuthButton({
  children,
  loading,
  loadingLabel,
  variant = "primary",
  disabled,
  className = "",
  ...props
}: AuthButtonProps) {
  return (
    <button
      className={`auth-button auth-button-${variant} ${className}`.trim()}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? (
        <>
          <span className="auth-button-spinner" aria-hidden="true" />
          <span>{loadingLabel ?? "Working..."}</span>
        </>
      ) : (
        children
      )}
    </button>
  );
}

export function AuthDivider({ children = "Or continue with email" }: { children?: ReactNode }) {
  return (
    <div className="auth-divider">
      <span>{children}</span>
    </div>
  );
}

export function AuthProviderButton({
  provider,
  onClick,
}: {
  provider: AuthProvider;
  onClick: () => void;
}) {
  const isGoogle = provider === "google";
  const label = isGoogle ? "Continue with Google" : "Continue with GitHub";

  return (
    <AuthButton type="button" variant="secondary" className="auth-provider-button" onClick={onClick}>
      <span className={`auth-provider-mark auth-provider-${provider}`} aria-hidden="true">
        {isGoogle ? <FcGoogle size={20} /> : <FaGithub size={20} />}
      </span>
      <span>{label}</span>
    </AuthButton>
  );
}

export function AuthAssuranceList({ items }: { items: string[] }) {
  return (
    <ul className="auth-assurance-list" aria-label="Authentication assurances">
      {items.map((item) => (
        <li key={item}>
          <CheckCircle2 size={14} aria-hidden="true" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export function AuthPasswordChecklist({ password }: { password: string }) {
  const checks = [
    { label: "8 or more characters", met: password.length >= 8 },
  ];

  return (
    <ul className="auth-password-checklist" aria-label="Password requirements">
      {checks.map((check) => (
        <li key={check.label} className={check.met ? "auth-check-met" : "auth-check-pending"}>
          {check.met ? <CheckCircle2 size={13} aria-hidden="true" /> : <KeyRound size={13} aria-hidden="true" />}
          <span>{check.label}</span>
        </li>
      ))}
    </ul>
  );
}

export function AuthEmailNotice({ children }: { children: ReactNode }) {
  return (
    <div className="auth-email-notice">
      <Mail size={15} aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}
