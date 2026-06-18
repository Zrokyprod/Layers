import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import IntegrationsPage from "./page";

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

vi.mock("../settings/integrations/page", () => ({
  default: () => <section aria-label="Integration status">GitHub Slack status</section>,
}));

describe("IntegrationsPage", () => {
  it("keeps the overview focused on provider, GitHub, capture, and Slack", () => {
    render(<IntegrationsPage />);

    expect(screen.getByRole("heading", { name: "Integrations" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage providers" }).getAttribute("href")).toBe("/settings/providers");
    expect(screen.getByRole("link", { name: "Open CI gates" }).getAttribute("href")).toBe("/ci-gates");
    expect(screen.getByRole("link", { name: "Open health" }).getAttribute("href")).toBe("/home");
    expect(screen.getByRole("link", { name: "Manage Slack" }).getAttribute("href")).toBe("/settings/integrations/slack");
  });
});
