import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginAliasPage from "./login/page";
import SignupAliasPage from "./register/page";
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
});
