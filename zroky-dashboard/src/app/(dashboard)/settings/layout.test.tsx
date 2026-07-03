import { render, screen } from "@testing-library/react";
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

  it("renders one real workspace settings nav without redirect aliases", () => {
    render(
      <SettingsLayout>
        <div>Settings content</div>
      </SettingsLayout>,
    );

    for (const label of ["API Keys", "Members", "Plan & Billing", "Workspace"]) {
      expect(screen.getAllByRole("link", { name: label })).toHaveLength(1);
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
    expect(screen.getByRole("navigation", { name: "Settings sections" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Workspace control loop")).not.toBeInTheDocument();
    expect(screen.queryByText("API access")).not.toBeInTheDocument();
    expect(screen.queryByText("Team access")).not.toBeInTheDocument();
    expect(screen.queryByText("Spend guard")).not.toBeInTheDocument();
    expect(screen.queryByText("Workspace record")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Evidence route/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Current section")).not.toBeInTheDocument();
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
