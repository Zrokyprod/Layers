import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import PilotPage from "./page";

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
    ...props
  }: {
    alt: string;
    [key: string]: unknown;
  }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} {...props} />
  ),
}));

describe("PilotPage", () => {
  it("renders a design-partner handoff path with install proof and protected setup", () => {
    render(<PilotPage />);

    expect(screen.getByRole("heading", { name: "Start with one protected agent and end with proof." })).toBeInTheDocument();
    expect(screen.getByText("Paid-launch proof, not a generic demo.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start protected setup" }).getAttribute("href")).toBe(
      "/signup?source=pilot&intent=protect-agent&plan=pro"
    );
    expect(screen.getByText("Pre-action stop")).toBeInTheDocument();
    expect(screen.getByText("System-of-record match")).toBeInTheDocument();
    expect(screen.getByText("Exportable evidence")).toBeInTheDocument();
    expect(screen.getByText(/--scenario refund/)).toBeInTheDocument();
    expect(screen.getByText(/--scenario customer-record/)).toBeInTheDocument();
    expect(screen.getByText("unsafe_action_stopped")).toBeInTheDocument();
    expect(screen.getByText("matched_outcome_shown")).toBeInTheDocument();
    expect(screen.getByText("secrets_redacted")).toBeInTheDocument();
  });
});
