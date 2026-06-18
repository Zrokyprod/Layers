import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "./page";

const api = vi.hoisted(() => ({
  exportProjectData: vi.fn(),
  getProjectSettings: vi.fn(),
  listMyProjects: vi.fn(),
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
    api.listMyProjects.mockResolvedValue([
      {
        membership_id: "mem_1",
        project_id: "proj_1",
        project_name: "My Project",
        role: "owner",
        is_active: true,
        created_at: "2026-06-17T10:00:00.000Z",
        updated_at: "2026-06-17T10:30:00.000Z",
      },
      {
        membership_id: "mem_2",
        project_id: "proj_2",
        project_name: "Checkout Agent",
        role: "member",
        is_active: true,
        created_at: "2026-06-18T10:00:00.000Z",
        updated_at: "2026-06-18T10:30:00.000Z",
      },
    ]);
  });

  it("shows a retryable error panel when project settings cannot load", async () => {
    api.getProjectSettings.mockRejectedValue(new Error("Backend API is unavailable."));

    render(<SettingsPage />);

    expect(await screen.findByText("Settings could not load")).toBeInTheDocument();
    expect(screen.getByText("Backend API is unavailable.")).toBeInTheDocument();
    expect(screen.queryByText("Project directory")).not.toBeInTheDocument();
  });

  it("shows the active project, project directory, and only project setup actions", async () => {
    render(<SettingsPage />);

    expect(await screen.findByRole("heading", { name: "My Project" })).toBeInTheDocument();
    expect(screen.getByText(/Workspace identity, capture scope/i)).toBeInTheDocument();
    expect(screen.getByText("Project directory")).toBeInTheDocument();
    expect(screen.getByText("Checkout Agent")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Switch" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Project key/i }).getAttribute("href")).toBe("/settings/keys");
    expect(screen.getByRole("link", { name: /Provider keys/i }).getAttribute("href")).toBe("/settings/providers");
    expect(screen.getByRole("link", { name: /Members/i }).getAttribute("href")).toBe("/settings/team");
    expect(screen.getByRole("link", { name: /Plan & usage/i }).getAttribute("href")).toBe("/settings/billing");
    expect(screen.queryByText("GitHub connection")).not.toBeInTheDocument();
    expect(screen.queryByText("Retention & Notifications")).not.toBeInTheDocument();
    expect(screen.queryByText("Danger zone")).not.toBeInTheDocument();
  });
});
