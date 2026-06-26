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

  it("renders only the direct workspace settings tabs", () => {
    render(
      <SettingsLayout>
        <div>Settings content</div>
      </SettingsLayout>,
    );

    for (const label of ["Capture keys", "Members", "Plan & Billing", "Workspace"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("link", { name: "Evaluation" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Integrations" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Connectors" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Providers" })).not.toBeInTheDocument();
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
    for (const label of ["Capture key", "Team access", "Spend guard", "Workspace record"]) {
      expect(within(controlLoop).getByRole("link", { name: new RegExp(label) })).toBeInTheDocument();
    }
    expect(screen.queryByRole("link", { name: /Evidence route/ })).not.toBeInTheDocument();
    expect(screen.getByText("Current section")).toBeInTheDocument();
  });

  it("keeps direct provider settings usable without exposing a tab", () => {
    navigation.pathname = "/settings/providers";

    render(
      <SettingsLayout>
        <div>Provider vault content</div>
      </SettingsLayout>,
    );

    expect(screen.queryByRole("link", { name: "Providers" })).not.toBeInTheDocument();
    expect(screen.getByText("Providers")).toBeInTheDocument();
    expect(screen.getByText("Managed replay vault")).toBeInTheDocument();
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
