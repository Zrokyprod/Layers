import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsLayout from "./layout";

const navigation = vi.hoisted(() => ({
  pathname: "/settings",
}));

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

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
}));

describe("SettingsLayout", () => {
  beforeEach(() => {
    navigation.pathname = "/settings";
  });

  it("renders the real workspace settings tabs without redirect aliases", () => {
    render(
      <SettingsLayout>
        <div>Settings content</div>
      </SettingsLayout>,
    );

    for (const label of ["API Keys", "Members", "Plan & Billing", "Workspace"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByText("Advanced")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Provider Vault" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Evaluation" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Integrations" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Connectors" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Project" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Profile" })).not.toBeInTheDocument();
  });

  it("frames settings as the workspace control plane", () => {
    render(
      <SettingsLayout>
        <div>Settings content</div>
      </SettingsLayout>,
    );

    expect(screen.getByRole("heading", { name: "Workspace control plane" })).toBeInTheDocument();
    const controlLoop = screen.getByLabelText("Workspace control loop");
    expect(controlLoop).toBeInTheDocument();
    for (const label of ["API access", "Team access", "Spend guard", "Workspace record"]) {
      expect(within(controlLoop).getByRole("link", { name: new RegExp(label) })).toBeInTheDocument();
    }
    expect(within(controlLoop).queryByRole("link", { name: /Provider vault/ })).not.toBeInTheDocument();
    expect(within(controlLoop).queryByRole("link", { name: /Evaluation defaults/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Evidence route/ })).not.toBeInTheDocument();
    expect(screen.getByText("Current section")).toBeInTheDocument();
  });

  it("does not include provider vault in the Settings chrome", () => {
    navigation.pathname = "/settings/providers";

    render(
      <SettingsLayout>
        <div>Provider vault content</div>
      </SettingsLayout>,
    );

    expect(screen.queryByRole("link", { name: "Provider Vault" })).not.toBeInTheDocument();
    expect(screen.queryByText("Provider Vault")).not.toBeInTheDocument();
  });

  it("does not keep connector redirect aliases in the settings chrome", () => {
    navigation.pathname = "/settings/integrations/slack";

    render(
      <SettingsLayout>
        <div>Slack content</div>
      </SettingsLayout>,
    );

    expect(screen.queryByRole("link", { name: "Integrations" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Connectors" })).not.toBeInTheDocument();
    expect(screen.queryByText("Moved to the Connectors module")).not.toBeInTheDocument();
  });

  it("does not include personal account controls in workspace settings", () => {
    render(
      <SettingsLayout>
        <div>Settings content</div>
      </SettingsLayout>,
    );

    expect(screen.queryByText("Identity and account security")).not.toBeInTheDocument();
  });
});
