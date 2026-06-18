import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "./page";

const api = vi.hoisted(() => ({
  deleteProject: vi.fn(),
  getProjectSettings: vi.fn(),
  listMyProjects: vi.fn(),
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
        role: "owner",
        is_active: true,
        created_at: "2026-06-18T10:00:00.000Z",
        updated_at: "2026-06-18T10:30:00.000Z",
      },
    ]);
    api.deleteProject.mockResolvedValue({
      project_id: "proj_2",
      name: "Checkout Agent",
      owner_ref: "email:user@example.com",
      is_active: false,
      created_at: "2026-06-18T10:00:00.000Z",
      updated_at: "2026-06-18T10:31:00.000Z",
    });
  });

  it("shows a retryable error panel when projects cannot load", async () => {
    api.getProjectSettings.mockRejectedValue(new Error("Backend API is unavailable."));

    render(<SettingsPage />);

    expect(await screen.findByText("Projects could not load")).toBeInTheDocument();
    expect(screen.getByText("Backend API is unavailable.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Active projects" })).not.toBeInTheDocument();
  });

  it("shows active projects as a list and keeps setup cards out of project settings", async () => {
    render(<SettingsPage />);

    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View My Project" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View Checkout Agent" })).toBeInTheDocument();
    expect(screen.getAllByText("No project selected").length).toBeGreaterThan(0);
    expect(screen.queryByText("2 active projects")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Project key/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Provider keys/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Project export")).not.toBeInTheDocument();
  });

  it("shows project details only after a project is clicked", async () => {
    render(<SettingsPage />);

    expect(await screen.findByRole("button", { name: "View My Project" })).toBeInTheDocument();
    expect(screen.queryByText("Project ID")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "View My Project" }));

    expect(screen.getByText("Project ID")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete project" })).toBeInTheDocument();
  });

  it("selects a project and calls delete with typed confirmation", async () => {
    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "View Checkout Agent" }));
    fireEvent.change(screen.getByLabelText("Type project name"), {
      target: { value: "Checkout Agent" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Delete project" }));

    await waitFor(() => {
      expect(api.deleteProject).toHaveBeenCalledWith(
        "proj_2",
        { confirm_project_name: "Checkout Agent" },
        "proj_2",
      );
    });
  });
});
