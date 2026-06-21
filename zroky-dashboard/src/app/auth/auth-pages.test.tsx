import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ForgotPasswordPage from "../forgot-password/page";
import LoginPage from "../login/page";
import SignupPage from "../signup/page";
import ResetPasswordPage from "../reset-password/page";
import VerifyEmailPage from "../verify-email/page";
import { loginWithPassword, registerWithPassword, verifyEmail } from "@/lib/api";
import { storeAuthSession } from "@/lib/auth";

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
    vi.mocked(loginWithPassword).mockReset();
    vi.mocked(registerWithPassword).mockReset();
    vi.mocked(verifyEmail).mockReset();
    vi.mocked(storeAuthSession).mockReset();
  });

  it("renders login with Zroky reliability copy", () => {
    render(<LoginPage />);

    expect(screen.getByRole("heading", { name: "Sign in to Zroky" })).toBeInTheDocument();
    expect(screen.getByText("Access traces, replays, and release gates.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Zroky" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue with Google" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue with GitHub" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("renders OAuth callback errors on login", () => {
    navigation.searchParams = new URLSearchParams("error=oauth_expired");

    render(<LoginPage />);

    expect(screen.getByText("Google sign-in expired. Start again.")).toBeInTheDocument();
  });

  it("sends unverified password logins to email verification before dashboard access", async () => {
    vi.mocked(loginWithPassword).mockResolvedValue({
      access_token: "access-token",
      refresh_token: "refresh-token",
      access_expires_in_seconds: 3600,
      refresh_expires_in_seconds: 86400,
      token_type: "bearer",
      user_id: "user_1",
      email: "new@example.com",
      email_verified: false,
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "new@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(storeAuthSession).toHaveBeenCalled();
      expect(navigation.push).toHaveBeenCalledWith("/verify-email?email=new%40example.com");
    });
  });

  it("renders signup workspace copy", () => {
    render(<SignupPage />);

    expect(screen.getByRole("heading", { name: "Create your Zroky workspace" })).toBeInTheDocument();
    expect(screen.getByText("Start capturing failed agent runs.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue with Google" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue with GitHub" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();
  });

  it("routes pricing signup intent to protected-agent setup after registration", async () => {
    navigation.searchParams = new URLSearchParams("intent=protect-agent&plan=pro&source=pricing");
    vi.mocked(registerWithPassword).mockResolvedValue({
      access_token: "access-token",
      refresh_token: "refresh-token",
      access_expires_in_seconds: 3600,
      refresh_expires_in_seconds: 86400,
      token_type: "bearer",
      user_id: "user_1",
      email: "buyer@example.com",
      email_verified: true,
    });

    render(<SignupPage />);

    expect(screen.getByText("Next step: project key setup for the agent you want Zroky to protect.")).toBeInTheDocument();
    expect(screen.getByText("Next step opens project key setup")).toBeInTheDocument();
    expect(screen.getByText("First capture works with a project key only")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Already have an account? Sign in" }).getAttribute("href")).toBe(
      "/login?next=%2Fsettings%2Fkeys%3Fintent%3Dprotect-agent%26plan%3Dpro%26source%3Dpricing",
    );

    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "buyer@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(storeAuthSession).toHaveBeenCalled();
      expect(navigation.push).toHaveBeenCalledWith("/settings/keys?intent=protect-agent&plan=pro&source=pricing");
    });
  });

  it("preserves pricing signup intent through email verification", async () => {
    navigation.searchParams = new URLSearchParams("intent=protect-agent&plan=starter&source=pricing");
    vi.mocked(registerWithPassword).mockResolvedValue({
      access_token: "access-token",
      refresh_token: "refresh-token",
      access_expires_in_seconds: 3600,
      refresh_expires_in_seconds: 86400,
      token_type: "bearer",
      user_id: "user_1",
      email: "pilot@example.com",
      email_verified: false,
    });

    render(<SignupPage />);

    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "pilot@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(navigation.push).toHaveBeenCalledWith(
        "/verify-email?email=pilot%40example.com&next=%2Fsettings%2Fkeys%3Fintent%3Dprotect-agent%26plan%3Dstarter%26source%3Dpricing",
      );
    });
  });

  it("renders forgot password copy", () => {
    render(<ForgotPasswordPage />);

    expect(screen.getByRole("heading", { name: "Reset your password" })).toBeInTheDocument();
    expect(screen.getByText("Send a secure reset link.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send reset link" })).toBeInTheDocument();
  });

  it("renders reset password copy", () => {
    navigation.searchParams = new URLSearchParams("token=reset-token");

    render(<ResetPasswordPage />);

    expect(screen.getByRole("heading", { name: "Create new password" })).toBeInTheDocument();
    expect(screen.getByText("Choose a new workspace password.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update password" })).toBeInTheDocument();
  });

  it("renders verify email copy", () => {
    render(<VerifyEmailPage />);

    expect(screen.getByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(screen.getByText("Open the verification link.")).toBeInTheDocument();
  });

  it("continues to protected-agent setup after successful email verification", async () => {
    navigation.searchParams = new URLSearchParams(
      "token=verify-token&next=%2Fsettings%2Fkeys%3Fintent%3Dprotect-agent%26plan%3Dpro",
    );
    vi.mocked(verifyEmail).mockResolvedValue({ detail: "Email verified." });

    render(<VerifyEmailPage />);

    const continueLink = await screen.findByRole("link", { name: "Continue setup" });
    expect(continueLink.getAttribute("href")).toBe("/settings/keys?intent=protect-agent&plan=pro");
  });
});
