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

  function setRequestHeaders(path: string, host = "zroky.com") {
    headerState.get.mockImplementation((name: string) => {
      if (name === "x-zroky-request-path") return path;
      if (name === "host") return host;
      return null;
    });
  }

  it("redirects unauthenticated dashboard access to login", async () => {
    cookieState.get.mockReturnValue(undefined);
    setRequestHeaders("/policies?tab=proof");

    await expect(DashboardLayout({ children: <main /> })).rejects.toThrow(
      "redirect:/login?next=%2Fpolicies%3Ftab%3Dproof",
    );
    expect(redirect).toHaveBeenCalledWith("/login?next=%2Fpolicies%3Ftab%3Dproof");
    expect(checkDashboardSession).not.toHaveBeenCalled();
  });

  it("redirects unverified email sessions before rendering the dashboard", async () => {
    cookieState.get.mockReturnValue({ value: "access-token" });
    setRequestHeaders("/policies");
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

  it("protects ordinary localhost dashboard routes", async () => {
    cookieState.get.mockReturnValue(undefined);
    setRequestHeaders("/home", "localhost:3000");

    await expect(DashboardLayout({ children: <main /> })).rejects.toThrow(
      "redirect:/login?next=%2Fhome",
    );
  });

  it("keeps the explicit localhost demo route available", async () => {
    cookieState.get.mockReturnValue(undefined);
    setRequestHeaders("/home?demoHome=1", "localhost:3000");

    const result = await DashboardLayout({ children: <main>demo</main> });

    expect(result).toMatchObject({ type: expect.any(Function) });
    expect(checkDashboardSession).not.toHaveBeenCalled();
    expect(redirect).not.toHaveBeenCalled();
  });
});
