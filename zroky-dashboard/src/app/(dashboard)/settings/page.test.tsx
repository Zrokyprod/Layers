import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "./page";

const api = vi.hoisted(() => ({
  disconnectGithubRepoConnection: vi.fn(),
  eraseRetentionData: vi.fn(),
  exportProjectData: vi.fn(),
  getGithubConnectionStatus: vi.fn(),
  getNotifications: vi.fn(),
  getPiiPolicy: vi.fn(),
  getProjectSettings: vi.fn(),
  getRetention: vi.fn(),
  testPiiDetector: vi.fn(),
  updateNotifications: vi.fn(),
  updatePiiPolicy: vi.fn(),
  updateRetention: vi.fn(),
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

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getProjectSettings.mockResolvedValue({
      project_id: "proj_1",
      name: "My Project",
      owner_ref: "email:user@example.com",
      is_active: true,
      created_at: "2026-06-17T10:00:00.000Z",
      updated_at: "2026-06-17T10:30:00.000Z",
    });
    api.getGithubConnectionStatus.mockResolvedValue({
      connected: false,
      github_id: null,
      github_login: null,
      scopes: [],
      connected_at: null,
      updated_at: null,
    });
    api.getPiiPolicy.mockResolvedValue({
      custom_patterns: [],
      updated_at: "2026-06-17T10:30:00.000Z",
    });
    api.getRetention.mockResolvedValue({
      retention_days: 30,
      updated_at: "2026-06-17T10:30:00.000Z",
    });
    api.getNotifications.mockResolvedValue({
      email_enabled: true,
      slack_enabled: false,
      teams_enabled: false,
      browser_enabled: true,
      terminal_enabled: true,
      updated_at: "2026-06-17T10:30:00.000Z",
    });
  });

  it("shows a retryable error panel when project settings cannot load", async () => {
    api.getProjectSettings.mockRejectedValue(new Error("Backend API is unavailable."));

    render(<SettingsPage />);

    expect(await screen.findByText("Settings could not load")).toBeInTheDocument();
    expect(screen.getByText("Backend API is unavailable.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save retention" })).not.toBeInTheDocument();
  });

  it("shows the active project and only real setup actions", async () => {
    render(<SettingsPage />);

    expect(await screen.findByRole("heading", { name: "My Project" })).toBeInTheDocument();
    expect(screen.getByText(/Your first project is created automatically/)).toBeInTheDocument();
    expect(screen.getAllByText("proj_1").length).toBeGreaterThan(0);
    expect(screen.getByText("Project details")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Project key/i }).getAttribute("href")).toBe("/settings/keys");
    expect(screen.getByRole("link", { name: /Provider keys/i }).getAttribute("href")).toBe("/settings/providers");
    expect(screen.getByRole("link", { name: /Members/i }).getAttribute("href")).toBe("/settings/team");
    expect(screen.getByRole("link", { name: /Plan & usage/i }).getAttribute("href")).toBe("/settings/billing");
    expect(screen.queryByRole("button", { name: /Create project/i })).not.toBeInTheDocument();
  });
});
