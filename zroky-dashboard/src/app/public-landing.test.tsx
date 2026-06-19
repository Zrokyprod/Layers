import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { PublicLanding } from "@/components/public-landing";

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

beforeAll(() => {
  class MockIntersectionObserver implements IntersectionObserver {
    readonly root = null;
    readonly rootMargin = "";
    readonly thresholds = [];

    disconnect() {}
    observe() {}
    takeRecords() {
      return [];
    }
    unobserve() {}
  }

  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
});

describe("PublicLanding", () => {
  it("renders the reliability control-plane story and primary actions", () => {
    const { container } = render(<PublicLanding />);

    expect(screen.getByRole("heading", { name: "Catch AI agent regressions before your users do." })).toBeInTheDocument();
    expect(screen.getByText(/capture the exact run, replay the fix/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Start workspace" }).some((link) => link.getAttribute("href") === "/signup")).toBe(true);
    expect(screen.getAllByRole("link", { name: "Sign in" }).some((link) => link.getAttribute("href") === "/login")).toBe(true);
    expect(screen.getByText("One reliability layer across your model stack.")).toBeInTheDocument();
    expect(screen.getByText("The dashboard zooms into the part that matters.")).toBeInTheDocument();
    expect(screen.getByText("A fix is not accepted until the replay proves it.")).toBeInTheDocument();
    expect(screen.queryByText(/Latest captured trace/i)).not.toBeInTheDocument();
    expect(screen.getByText("© 2026 Zroky")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Privacy" }).getAttribute("href")).toBe("/privacy");
    expect(screen.getByRole("link", { name: "Security" }).getAttribute("href")).toBe("/security");
    expect(screen.getByRole("link", { name: "Contact" }).getAttribute("href")).toBe("/contact");
    expect(screen.getByRole("link", { name: "LinkedIn" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Instagram" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Twitter" })).toBeInTheDocument();
    expect(container.textContent).toContain('import { init, traceRun, wrap } from "@zroky-ai/sdk";');
    expect(container.textContent).not.toContain("new Zroky");
    expect(container.textContent).not.toContain("zroky-sdk");
  });
});
