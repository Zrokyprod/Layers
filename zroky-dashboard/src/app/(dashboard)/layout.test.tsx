import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DashboardLayout from "./layout";
import { checkDashboardSession } from "@/lib/server-session";
import { redirect } from "next/navigation";

const cookieState = vi.hoisted(() => ({
  get: vi.fn(),
}));

const headerState = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({
    get: cookieState.get,
  })),
  headers: vi.fn(async () => ({
    get: headerState.get,
  })),
}));

vi.mock("next/navigation", () => ({
  redirect: vi.fn((url: string) => {
    throw new Error(`redirect:${url}`);
  }),
}));

vi.mock("@/components/dashboard-shell", () => ({
  DashboardShell: ({ children }: { children: ReactNode }) => <div data-testid="dashboard-shell">{children}</div>,
}));

vi.mock("@/lib/server-session", () => ({
  checkDashboardSession: vi.fn(),
}));

describe("DashboardLayout", () => {
  beforeEach(() => {
    cookieState.get.mockReset();
    headerState.get.mockReset();
    headerState.get.mockReturnValue(null);
    vi.mocked(checkDashboardSession).mockReset();
    vi.mocked(redirect).mockClear();
  });

  it("redirects unauthenticated dashboard access to login", async () => {
    cookieState.get.mockReturnValue(undefined);
    headerState.get.mockReturnValue("/policies?tab=proof");

    await expect(DashboardLayout({ children: <main /> })).rejects.toThrow(
      "redirect:/login?next=%2Fpolicies%3Ftab%3Dproof",
    );
    expect(redirect).toHaveBeenCalledWith("/login?next=%2Fpolicies%3Ftab%3Dproof");
    expect(checkDashboardSession).not.toHaveBeenCalled();
  });

  it("redirects unverified email sessions before rendering the dashboard", async () => {
    cookieState.get.mockReturnValue({ value: "access-token" });
    headerState.get.mockReturnValue("/policies");
    vi.mocked(checkDashboardSession).mockResolvedValue({
      status: "authenticated",
      user: {
        user_id: "user_1",
        email: "new@example.com",
        email_verified: false,
        is_active: true,
      },
    });

    await expect(DashboardLayout({ children: <main /> })).rejects.toThrow(
      "redirect:/verify-email?next=%2Fpolicies&email=new%40example.com",
    );
    expect(checkDashboardSession).toHaveBeenCalledWith("access-token");
    expect(redirect).toHaveBeenCalledWith("/verify-email?next=%2Fpolicies&email=new%40example.com");
  });
});
