import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WorkspaceSettingsPage from "./page";

const clipboardWrite = vi.hoisted(() => vi.fn());
const updateProject = vi.hoisted(() => vi.fn());

const hookState = vi.hoisted(() => ({
  project: {
    project_id: "proj_1234567890abcdef",
    name: "Refund Operations",
    owner_ref: "user_owner_1234567890",
    is_active: true,
    created_at: "2026-06-20T10:00:00Z",
    updated_at: "2026-06-24T12:30:00Z",
  },
  projects: [
    {
      membership_id: "mem_1",
      project_id: "proj_1234567890abcdef",
      project_name: "Refund Operations",
      role: "owner",
      is_active: true,
      created_at: "2026-06-20T10:00:00Z",
      updated_at: "2026-06-24T12:30:00Z",
    },
  ],
  selectedProject: "proj_1234567890abcdef" as string | null,
  loading: false,
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

vi.mock("@/lib/hooks", () => ({
  useProjectSettings: () => ({
    data: hookState.project,
    isLoading: hookState.loading,
  }),
  useMyProjects: () => ({
    data: hookState.projects,
    isLoading: hookState.loading,
  }),
  useUpdateProjectSettings: () => ({
    mutateAsync: updateProject,
    isPending: false,
  }),
}));

vi.mock("@/lib/store", () => ({
  useDashboardStore: <T,>(selector: (state: { selectedProject: string | null }) => T) =>
    selector({ selectedProject: hookState.selectedProject }),
}));

describe("WorkspaceSettingsPage", () => {
  beforeEach(() => {
    clipboardWrite.mockReset();
    clipboardWrite.mockResolvedValue(undefined);
    updateProject.mockReset();
    updateProject.mockResolvedValue({
      ...hookState.project,
      name: "Revenue Operations",
    });
    Object.assign(navigator, {
      clipboard: {
        writeText: clipboardWrite,
      },
    });
  });

  it("shows focused workspace metadata and project actions", async () => {
    render(<WorkspaceSettingsPage />);

    expect(screen.getAllByText("Refund Operations").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Workspace access boundary")).toBeInTheDocument();
    expect(screen.getByLabelText("Workspace routing")).toBeInTheDocument();
    expect(screen.getByLabelText("Workspace authority")).toBeInTheDocument();
    expect(screen.getByText("Stable dashboard project context")).toBeInTheDocument();
    expect(screen.getAllByText("Owner").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Open projects" }).getAttribute("href")).toBe("/projects");
    expect(screen.getByRole("link", { name: "Manage members" }).getAttribute("href")).toBe("/settings/team");

    fireEvent.click(screen.getByRole("button", { name: "Copy project ID" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith("proj_1234567890abcdef"));
  });

  it("renames the workspace through the backend settings endpoint", async () => {
    render(<WorkspaceSettingsPage />);

    fireEvent.change(screen.getByLabelText("Workspace name"), {
      target: { value: "Revenue Operations" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save workspace name" }));

    await waitFor(() => expect(updateProject).toHaveBeenCalledWith({ name: "Revenue Operations" }));
    expect(await screen.findByText("Workspace name updated.")).toBeInTheDocument();
  });
});
