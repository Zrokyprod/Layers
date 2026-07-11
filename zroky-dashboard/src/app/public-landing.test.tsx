import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { PublicLanding } from "@/components/public-landing";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode; [key: string]: unknown }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

describe("PublicLanding", () => {
  it("presents the current action-control product and primary conversion paths", () => {
    render(<PublicLanding />);

    expect(screen.getByRole("heading", { name: "The control plane for AI agent actions." })).toBeInTheDocument();
    expect(screen.getByText(/Intercept risky tool calls before they reach business systems/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Protect an agent/i }).some((link) => link.getAttribute("href") === "/signup")).toBe(true);
    expect(screen.getByRole("link", { name: "Sign in" }).getAttribute("href")).toBe("/login");
    expect(screen.getByText("MCP interception")).toBeInTheDocument();
    expect(screen.getByText("Source-of-record proof")).toBeInTheDocument();
  });

  it("shows the full decision-to-receipt loop and honest proof taxonomy", () => {
    render(<PublicLanding />);

    for (const label of ["Intercept", "Decide", "Execute", "Verify", "Receipt"]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.getByRole("heading", { name: "The agent said success. The system of record said otherwise." })).toBeInTheDocument();
    for (const status of ["Matched", "Mismatched", "Pending", "Unverifiable", "Partial"]) {
      expect(screen.getByText(status)).toBeInTheDocument();
    }
    expect(screen.getByText(/Alert raised with rollback guidance and evidence/i)).toBeInTheDocument();
  });

  it("explains connector and enterprise architecture without unsupported claims", () => {
    render(<PublicLanding />);

    expect(screen.getByRole("heading", { name: "Verify any business system without an integrations treadmill." })).toBeInTheDocument();
    expect(screen.getByText("Certified packs")).toBeInTheDocument();
    expect(screen.getByText("Declarative connectors")).toBeInTheDocument();
    expect(screen.getByText("Private runner")).toBeInTheDocument();
    expect(screen.getByText("Fail-closed where it matters")).toBeInTheDocument();
    expect(screen.getByText("Tenant-safe execution")).toBeInTheDocument();
    expect(screen.queryByText(/0 false blocks/i)).not.toBeInTheDocument();
  });

  it("keeps legal, pricing, pilot, and account routes available", () => {
    render(<PublicLanding />);

    expect(screen.getAllByRole("link", { name: "Security" }).some((link) => link.getAttribute("href") === "/security")).toBe(true);
    expect(screen.getByRole("link", { name: "Privacy" }).getAttribute("href")).toBe("/privacy");
    expect(screen.getByRole("link", { name: "Contact" }).getAttribute("href")).toBe("/contact");
    expect(screen.getAllByRole("link", { name: "Pricing" }).some((link) => link.getAttribute("href") === "/pricing")).toBe(true);
    expect(screen.getByRole("link", { name: "Plan a pilot" }).getAttribute("href")).toBe("/pilot");
    expect(screen.getByText("Copyright 2026 Zroky")).toBeInTheDocument();
  });
});
