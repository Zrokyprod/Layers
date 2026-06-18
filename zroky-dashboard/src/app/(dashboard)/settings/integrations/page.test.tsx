import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IntegrationsSettingsPage from "./page";

const api = vi.hoisted(() => ({
  disconnectGithubRepoConnection: vi.fn(),
  getGithubConnectionStatus: vi.fn(),
  getSlackInstallStatus: vi.fn(),
  getTeamsInstallStatus: vi.fn(),
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

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

describe("IntegrationsSettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getGithubConnectionStatus.mockResolvedValue({
      connected: true,
      github_id: "123",
      github_login: "zroky",
      scopes: ["repo"],
      connected_at: "2026-06-17T10:00:00.000Z",
      updated_at: "2026-06-17T10:30:00.000Z",
    });
    api.getSlackInstallStatus.mockResolvedValue({
      connected: false,
      team_id: null,
      team_name: null,
      channel_id: null,
      channel_name: null,
      bot_user_id: null,
      scopes: [],
      installed_by_user: null,
      installed_at: null,
      updated_at: null,
    });
    api.getTeamsInstallStatus.mockResolvedValue({
      connected: false,
      channel_name: null,
      connector_type: null,
      installed_by_user: null,
      installed_at: null,
      updated_at: null,
    });
  });

  it("shows GitHub beside alert delivery integrations", async () => {
    render(<IntegrationsSettingsPage />);

    expect(await screen.findByRole("heading", { name: "GitHub" })).toBeInTheDocument();
    expect(screen.getAllByText("@zroky").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Reconnect GitHub" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Slack" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Microsoft Teams" })).toBeInTheDocument();
  });
});
