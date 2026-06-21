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

  it("renders customer-facing settings tabs", () => {
    render(
      <SettingsLayout>
        <div>Settings content</div>
      </SettingsLayout>,
    );

    for (const label of ["API keys", "Members", "Plan & Billing", "Evaluation", "Integrations"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("link", { name: "Providers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Project" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Profile" })).not.toBeInTheDocument();
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

  it("keeps Slack child routes active under Integrations", () => {
    navigation.pathname = "/settings/integrations/slack";

    render(
      <SettingsLayout>
        <div>Slack content</div>
      </SettingsLayout>,
    );

    expect(screen.getByRole("link", { name: "Integrations" }).className).toContain("settings-tab-link-active");
    expect(screen.getByText("Repos, alerts, records")).toBeInTheDocument();
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
