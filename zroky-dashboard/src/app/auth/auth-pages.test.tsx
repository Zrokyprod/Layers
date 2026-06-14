import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ForgotPasswordPage from "../forgot-password/page";
import LoginPage from "../login/page";
import SignupPage from "../signup/page";
import ResetPasswordPage from "../reset-password/page";
import VerifyEmailPage from "../verify-email/page";

const navigation = vi.hoisted(() => ({
  searchParams: new URLSearchParams(),
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/image", () => ({
  default: ({
    alt,
    src,
    ...props
  }: {
    alt: string;
    src: string;
    [key: string]: unknown;
  }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} src={src} {...props} />
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: navigation.push,
    replace: navigation.replace,
    refresh: navigation.refresh,
  }),
  useSearchParams: () => navigation.searchParams,
}));

vi.mock("@/lib/api", () => ({
  forgotPassword: vi.fn(),
  loginWithPassword: vi.fn(),
  registerWithPassword: vi.fn(),
  resetPassword: vi.fn(),
  resendVerification: vi.fn(),
  verifyEmail: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({
  storeAuthSession: vi.fn(),
}));

describe("auth pages", () => {
  beforeEach(() => {
    navigation.searchParams = new URLSearchParams();
    navigation.push.mockReset();
    navigation.replace.mockReset();
    navigation.refresh.mockReset();
  });

  it("renders login with Zroky reliability copy", () => {
    render(<LoginPage />);

    expect(screen.getByRole("heading", { name: "Sign in to Zroky" })).toBeInTheDocument();
    expect(screen.getByText("Review failed runs, replay proof, golden contracts, CI gates, and owner evidence.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Zroky" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("renders signup workspace copy", () => {
    render(<SignupPage />);

    expect(screen.getByRole("heading", { name: "Create your Zroky workspace" })).toBeInTheDocument();
    expect(screen.getByText("Create the workspace where failed agent runs become replay proof and release gates.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();
  });

  it("renders forgot password copy", () => {
    render(<ForgotPasswordPage />);

    expect(screen.getByRole("heading", { name: "Recover workspace access" })).toBeInTheDocument();
    expect(screen.getByText("Send a reset link while keeping account discovery private.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send reset link" })).toBeInTheDocument();
  });

  it("renders reset password copy", () => {
    navigation.searchParams = new URLSearchParams("token=reset-token");

    render(<ResetPasswordPage />);

    expect(screen.getByRole("heading", { name: "Set a new password" })).toBeInTheDocument();
    expect(screen.getByText("Set a new key for your reliability workspace session.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update password" })).toBeInTheDocument();
  });

  it("renders verify email copy", () => {
    render(<VerifyEmailPage />);

    expect(screen.getByRole("heading", { name: "Verify your email" })).toBeInTheDocument();
    expect(screen.getByText("Confirm your email to unlock trace capture, replay, and golden gates.")).toBeInTheDocument();
  });
});
