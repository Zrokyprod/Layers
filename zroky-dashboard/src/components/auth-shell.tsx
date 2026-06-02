"use client";

import {
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  GitBranch,
  KeyRound,
  Mail,
  ScanLine,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { useState } from "react";

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

const reliabilityLoop = ["Failure", "Evidence", "Replay", "Gate"];

const proofCards = [
  {
    icon: ScanLine,
    title: "Trace",
    copy: "Every failed run keeps its evidence.",
  },
  {
    icon: GitBranch,
    title: "Replay",
    copy: "Fixes run against the exact scenario.",
  },
  {
    icon: ShieldCheck,
    title: "Guard",
    copy: "CI blocks repeat regressions.",
  },
] satisfies Array<{ icon: LucideIcon; title: string; copy: string }>;

const consoleRows = [
  { label: "Failed run", value: "Captured", tone: "orange" },
  { label: "Root cause", value: "Diagnosed", tone: "neutral" },
  { label: "Replay proof", value: "Verified", tone: "green" },
  { label: "Regression gate", value: "Ready", tone: "neutral" },
] as const;

export function AuthBrandPanel() {
  return (
    <section className="auth-brand-panel" aria-label="Zroky reliability platform">
      <div className="auth-mark-row">
        <div className="auth-logo-wrap">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/zroky-auth-logo.png" alt="Zroky" className="auth-logo" />
        </div>
      </div>
      <div className="auth-brand-copy">
        <p className="auth-kicker">AI reliability control plane</p>
        <h1>Catch. Replay. Guard.</h1>
        <p className="auth-brand-subtitle">
          Enter the workspace where failed AI-agent runs become diagnosis, replay proof, golden traces, and CI gates.
        </p>
      </div>
      <ol className="auth-loop" aria-label="Zroky reliability loop">
        {reliabilityLoop.map((step, index) => (
          <li key={step}>
            <span>{step}</span>
            {index < reliabilityLoop.length - 1 && <b aria-hidden="true">-&gt;</b>}
          </li>
        ))}
      </ol>
      <div className="auth-signal-console" aria-label="Reliability proof preview">
        <div className="auth-console-header">
          <span className="auth-console-dot" aria-hidden="true" />
          <span>Failure path preview</span>
        </div>
        <div className="auth-console-flow">
          {consoleRows.map((row) => (
            <div key={row.label} className={`auth-console-row auth-console-row-${row.tone}`}>
              <span>{row.label}</span>
              <strong>{row.value}</strong>
            </div>
          ))}
        </div>
      </div>
      <div className="auth-proof-grid">
        {proofCards.map((card) => (
          <article key={card.title} className="auth-proof-card">
            <card.icon size={16} aria-hidden="true" />
            <strong>{card.title}</strong>
            <span>{card.copy}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

export function AuthShell({ children }: AuthShellProps) {
  return (
    <main className="auth-shell">
      <AuthBrandPanel />
      <section className="auth-form-panel" aria-label="Authentication form">
        {children}
      </section>
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
        {isGoogle ? "G" : "GH"}
      </span>
      <span>{label}</span>
      <ArrowRight size={15} aria-hidden="true" />
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
