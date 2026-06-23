import fs from "node:fs";
import path from "node:path";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OwnerLayout from "./layout";

const mockVerifyOwnerToken = vi.fn();
const mockVerifyOwnerSession = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/owner/money-path",
}));

vi.mock("@/lib/owner-api", () => ({
  clearOwnerToken: vi.fn(),
  verifyOwnerSession: (...args: unknown[]) => mockVerifyOwnerSession(...args),
  verifyOwnerToken: (...args: unknown[]) => mockVerifyOwnerToken(...args),
}));

const EXPECTED_NAV = [
  { href: "/owner", label: "Overview" },
  { href: "/owner/money-path", label: "Money Path" },
  { href: "/owner/launch-readiness", label: "Launch Gate" },
  { href: "/owner/projects", label: "Projects" },
  { href: "/owner/pricing", label: "Billing" },
  { href: "/owner/audit", label: "Audit Log" },
  { href: "/owner/settings", label: "Settings" },
];

const HIDDEN_SUPPORT_NAV = [
  { href: "/owner/ops", label: "Ops" },
  { href: "/owner/infrastructure", label: "Infrastructure" },
  { href: "/owner/support", label: "Support" },
  { href: "/owner/users", label: "Users" },
  { href: "/owner/rate-limits", label: "Rate Limits" },
  { href: "/owner/platform-llm", label: "LLM Usage" },
  { href: "/owner/feature-flags", label: "Feature Flags" },
  { href: "/owner/feature-votes", label: "Feature Interest" },
];

function routeFileFor(href: string): string {
  if (href === "/owner") return path.join(process.cwd(), "src", "app", "owner", "page.tsx");
  const segment = href.replace("/owner/", "");
  return path.join(process.cwd(), "src", "app", "owner", segment, "page.tsx");
}

describe("OwnerLayout regression guard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockVerifyOwnerSession.mockResolvedValue(true);
    mockVerifyOwnerToken.mockResolvedValue(true);
  });

  it("renders only backed owner navigation routes after token verification", async () => {
    render(
      <OwnerLayout>
        <div>Owner child route</div>
      </OwnerLayout>,
    );

    await waitFor(() => expect(screen.getByText("Owner child route")).toBeInTheDocument());

    const navLinks = screen.getByLabelText("Owner navigation").querySelectorAll("a");
    const actual = Array.from(navLinks).map((link) => ({
      href: link.getAttribute("href"),
      label: link.textContent,
    }));

    expect(actual).toEqual(EXPECTED_NAV);
    expect(actual.some((item) => item.href === "/owner/issues-ci-risk")).toBe(false);
    expect(actual.some((item) => item.href === "/owner/revenue-entitlements")).toBe(false);
    for (const item of HIDDEN_SUPPORT_NAV) {
      expect(actual.some((navItem) => navItem.href === item.href || navItem.label === item.label)).toBe(false);
    }

    for (const item of [...EXPECTED_NAV, ...HIDDEN_SUPPORT_NAV]) {
      expect(fs.existsSync(routeFileFor(item.href))).toBe(true);
    }
  });
});
