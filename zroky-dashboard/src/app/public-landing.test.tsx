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
    render(<PublicLanding />);

    expect(screen.getByRole("heading", { name: "AI Agent Reliability Control Plane" })).toBeInTheDocument();
    expect(screen.getByText(/failed production agent runs into trace evidence/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Create reliability workspace/i }).getAttribute("href")).toBe("/signup");
    expect(screen.getAllByRole("link", { name: "Sign in" }).some((link) => link.getAttribute("href") === "/login")).toBe(true);
    expect(screen.getByText("One product flow from incident to protected release.")).toBeInTheDocument();
    expect(screen.getByText("Instrument once. Review failures in the workspace.")).toBeInTheDocument();
  });
});
