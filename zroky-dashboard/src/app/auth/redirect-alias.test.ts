import { beforeEach, describe, expect, it, vi } from "vitest";

import AuthIndexPage from "./page";
import CheckEmailAliasPage from "./check-email/page";
import ForgotPasswordAliasPage from "./forgot-password/page";
import LoginAliasPage from "./login/page";
import ResetPasswordAliasPage from "./reset-password/page";
import SignupAliasPage from "./register/page";
import VerifyEmailAliasPage from "./verify-email/page";
import { buildAuthAliasUrl } from "./redirect-alias";

const redirectMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

describe("auth redirect aliases", () => {
  beforeEach(() => {
    redirectMock.mockReset();
  });

  it("builds auth alias URLs while preserving query params", () => {
    expect(buildAuthAliasUrl("/reset-password", { token: "abc", email: "dev@zroky.com" })).toBe(
      "/reset-password?token=abc&email=dev%40zroky.com"
    );
    expect(buildAuthAliasUrl("/verify-email", {})).toBe("/verify-email");
  });

  it("redirects /auth/login to the canonical login route", async () => {
    await LoginAliasPage({ searchParams: Promise.resolve({ next: "/home" }) });

    expect(redirectMock).toHaveBeenCalledWith("/login?next=%2Fhome");
  });

  it("redirects /auth/register to the canonical signup route", async () => {
    await SignupAliasPage({ searchParams: Promise.resolve({ source: "pricing" }) });

    expect(redirectMock).toHaveBeenCalledWith("/signup?source=pricing");
  });

  it("redirects every legacy auth alias to its canonical top-level route", async () => {
    const cases = [
      {
        page: AuthIndexPage,
        params: { next: "/approvals" },
        expected: "/login?next=%2Fapprovals",
      },
      {
        page: ForgotPasswordAliasPage,
        params: { email: "demo@zroky.local" },
        expected: "/forgot-password?email=demo%40zroky.local",
      },
      {
        page: ResetPasswordAliasPage,
        params: { token: "reset-token" },
        expected: "/reset-password?token=reset-token",
      },
      {
        page: VerifyEmailAliasPage,
        params: { token: "verify-token" },
        expected: "/verify-email?token=verify-token",
      },
      {
        page: CheckEmailAliasPage,
        params: { email: "demo@zroky.local" },
        expected: "/verify-email?email=demo%40zroky.local",
      },
    ];

    for (const item of cases) {
      redirectMock.mockReset();
      await item.page({ searchParams: Promise.resolve(item.params) });
      expect(redirectMock).toHaveBeenCalledWith(item.expected);
    }
  });
});
