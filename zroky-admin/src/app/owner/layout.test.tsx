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
  { href: "/owner/infrastructure", label: "Infrastructure" },
  { href: "/owner/projects", label: "Tenants" },
  { href: "/owner/users", label: "Users" },
  { href: "/owner/pricing", label: "Billing" },
  { href: "/owner/support", label: "Support" },
  { href: "/owner/tool-catalog", label: "Connector Catalog" },
  { href: "/owner/audit", label: "Audit" },
  { href: "/owner/settings", label: "Settings" },
];

// Old-IA routes that were removed in the Owner 360 consolidation. They must not
// appear in the nav and their route files must no longer exist.
const REMOVED_ROUTES = [
  "/owner/launch-readiness",
  "/owner/ops",
  "/owner/rate-limits",
  "/owner/platform-llm",
  "/owner/feature-flags",
  "/owner/feature-votes",
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
    expect(screen.getByText("Local dev")).toBeInTheDocument();
    expect(screen.queryByText("Production scoped")).toBe(null);

    const navLinks = screen.getByLabelText("Owner navigation").querySelectorAll("a");
    const actual = Array.from(navLinks).map((link) => ({
      href: link.getAttribute("href"),
      label: link.textContent,
    }));

    expect(actual).toEqual(EXPECTED_NAV);

    // Removed old-IA routes: not in nav, and route files deleted.
    for (const href of REMOVED_ROUTES) {
      expect(actual.some((navItem) => navItem.href === href)).toBe(false);
      expect(fs.existsSync(routeFileFor(href))).toBe(false);
    }

    // Every visible nav route is backed by a real page file.
    for (const item of EXPECTED_NAV) {
      expect(fs.existsSync(routeFileFor(item.href))).toBe(true);
    }
  });
});
