import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SlackIntegrationPage from "./page";

const api = vi.hoisted(() => ({
  disconnectSlackInstall: vi.fn(),
  getSlackInstallStatus: vi.fn(),
  sendSlackTestMessage: vi.fn(),
  startSlackInstall: vi.fn(),
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

const disconnectedStatus: import("@/lib/types").SlackInstallStatusResponse = {
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
};

const connectedStatus: import("@/lib/types").SlackInstallStatusResponse = {
  connected: true,
  team_id: "T123",
  team_name: "Acme",
  channel_id: "C123",
  channel_name: "alerts",
  bot_user_id: "B123",
  scopes: ["incoming-webhook", "commands"],
  installed_by_user: "owner@example.com",
  installed_at: "2026-06-01T10:00:00.000Z",
  updated_at: "2026-06-01T10:00:00.000Z",
};

describe("SlackIntegrationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getSlackInstallStatus.mockResolvedValue(disconnectedStatus);
    api.startSlackInstall.mockResolvedValue({
      authorization_url: "https://slack.com/oauth/v2/authorize?state=test",
    });
    api.sendSlackTestMessage.mockResolvedValue({
      ok: true,
      message: "Slack test message sent.",
    });
  });

  it("renders disconnected state without requiring Slack credentials", async () => {
    render(<SlackIntegrationPage />);

    expect(await screen.findByRole("heading", { name: "Slack" })).toBeInTheDocument();
    expect(screen.getByText("Install the Zroky Slack app for this project.")).toBeInTheDocument();
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect Slack" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send Test Message" })).toHaveProperty("disabled", true);
  });

  it("shows a clean config warning when status cannot load", async () => {
    api.getSlackInstallStatus.mockRejectedValue(new Error("Slack OAuth is not configured on this server."));

    render(<SlackIntegrationPage />);

    expect(await screen.findByText("Slack OAuth is not ready in this environment.")).toBeInTheDocument();
    expect(screen.getAllByText("Slack OAuth is not configured on this server.").length).toBeGreaterThan(0);
  });

  it("starts Slack OAuth when connect is clicked", async () => {
    render(<SlackIntegrationPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Connect Slack" }));

    await waitFor(() => expect(api.startSlackInstall).toHaveBeenCalledTimes(1));
  });

  it("sends a test message and surfaces Slack delivery failures", async () => {
    api.getSlackInstallStatus.mockResolvedValue(connectedStatus);

    render(<SlackIntegrationPage />);

    expect(await screen.findByText("#alerts")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Send Test Message" }));

    await waitFor(() =>
      expect(api.sendSlackTestMessage).toHaveBeenCalledWith(
        "Zroky test alert: Slack integration is connected.",
      ),
    );
    expect(await screen.findByText("Slack test message sent.")).toBeInTheDocument();

    api.sendSlackTestMessage.mockRejectedValueOnce(new Error("Slack test message failed."));
    fireEvent.click(screen.getByRole("button", { name: "Send Test Message" }));

    await waitFor(() => expect(screen.getAllByText("Slack test message failed.").length).toBeGreaterThan(0));
  });
});
