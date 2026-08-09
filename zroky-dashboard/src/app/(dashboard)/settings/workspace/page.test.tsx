import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WorkspaceSettingsPage from "./page";

const clipboardWrite = vi.hoisted(() => vi.fn());
const refetchWorkspace = vi.hoisted(() => vi.fn());
const updateProject = vi.hoisted(() => vi.fn());
const projectSettingsProjectId = vi.hoisted(() => vi.fn());
const updateSettingsProjectId = vi.hoisted(() => vi.fn());

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
  error: null as Error | null,
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
  useProjectSettings: (projectId: string | null) => {
    projectSettingsProjectId(projectId);
    return {
      data: hookState.project,
      isLoading: hookState.loading,
      error: hookState.error,
      refetch: refetchWorkspace,
    };
  },
  useMyProjects: () => ({
    data: hookState.projects,
    isLoading: hookState.loading,
    error: hookState.error,
    refetch: refetchWorkspace,
  }),
  useUpdateProjectSettings: (projectId: string | null) => {
    updateSettingsProjectId(projectId);
    return {
      mutateAsync: updateProject,
      isPending: false,
    };
  },
}));

vi.mock("@/lib/store", () => ({
  useDashboardStore: <T,>(selector: (state: { selectedProject: string | null }) => T) =>
    selector({ selectedProject: hookState.selectedProject }),
}));

describe("WorkspaceSettingsPage", () => {
  beforeEach(() => {
    hookState.project = {
      project_id: "proj_1234567890abcdef",
      name: "Refund Operations",
      owner_ref: "user_owner_1234567890",
      is_active: true,
      created_at: "2026-06-20T10:00:00Z",
      updated_at: "2026-06-24T12:30:00Z",
    };
    hookState.projects = [
      {
        membership_id: "mem_1",
        project_id: "proj_1234567890abcdef",
        project_name: "Refund Operations",
        role: "owner",
        is_active: true,
        created_at: "2026-06-20T10:00:00Z",
        updated_at: "2026-06-24T12:30:00Z",
      },
    ];
    hookState.selectedProject = "proj_1234567890abcdef";
    hookState.loading = false;
    hookState.error = null;
    clipboardWrite.mockReset();
    clipboardWrite.mockResolvedValue(undefined);
    updateProject.mockReset();
    refetchWorkspace.mockReset();
    refetchWorkspace.mockResolvedValue(undefined);
    projectSettingsProjectId.mockReset();
    updateSettingsProjectId.mockReset();
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

    expect((screen.getByLabelText("Workspace name") as HTMLInputElement).value).toBe("Refund Operations");
    expect(screen.getByRole("heading", { name: "Workspace" })).toBeInTheDocument();
    expect(screen.getByText("Workspace details")).toBeInTheDocument();
    expect(screen.getByText("Project details")).toBeInTheDocument();
    expect(screen.queryByLabelText("Workspace access boundary")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Workspace routing")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Workspace authority")).not.toBeInTheDocument();
    expect(screen.getAllByText("Owner").length).toBeGreaterThan(0);
    expect(screen.getByText("Project ID")).toBeInTheDocument();
    expect(screen.getByText("Dashboard environment")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open projects" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Manage members" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith("proj_1234567890abcdef"));
  });

  it("renames the workspace through the backend settings endpoint", async () => {
    render(<WorkspaceSettingsPage />);

    fireEvent.change(screen.getByLabelText("Workspace name"), {
      target: { value: "Revenue Operations" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));

    await waitFor(() => expect(updateProject).toHaveBeenCalledWith({ name: "Revenue Operations" }));
    expect(await screen.findByText("Workspace name updated.")).toBeInTheDocument();
    expect(updateSettingsProjectId).toHaveBeenCalledWith("proj_1234567890abcdef");
  });

  it("renders backend rename failures as errors", async () => {
    updateProject.mockRejectedValue(new Error("Only owners and admins can rename this workspace."));
    render(<WorkspaceSettingsPage />);

    fireEvent.change(screen.getByLabelText("Workspace name"), {
      target: { value: "Revenue Operations" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Only owners and admins");
    expect(alert.className).toContain("field-error");
  });

  it("keeps workspace metadata read-only for viewers", () => {
    hookState.projects[0].role = "viewer";
    render(<WorkspaceSettingsPage />);

    expect((screen.getByLabelText("Workspace name") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Save name" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Read only")).toBeInTheDocument();
  });

  it("resets project-bound form state when the workspace changes", () => {
    const view = render(<WorkspaceSettingsPage />);
    fireEvent.change(screen.getByLabelText("Workspace name"), {
      target: { value: "Unsaved name" },
    });

    hookState.selectedProject = "proj_2";
    hookState.project = {
      ...hookState.project,
      project_id: "proj_2",
      name: "Second Workspace",
    };
    hookState.projects = [{
      ...hookState.projects[0],
      membership_id: "mem_2",
      project_id: "proj_2",
      project_name: "Second Workspace",
    }];
    view.rerender(<WorkspaceSettingsPage />);

    expect((screen.getByLabelText("Workspace name") as HTMLInputElement).value).toBe("Second Workspace");
    expect(projectSettingsProjectId).toHaveBeenCalledWith("proj_2");
    expect(updateSettingsProjectId).toHaveBeenCalledWith("proj_2");
  });

  it("does not infer an active workspace when settings cannot load", () => {
    hookState.error = new Error("Workspace service unavailable.");

    render(<WorkspaceSettingsPage />);

    expect(screen.getByText("Unavailable", { selector: ".dashboard-verdict-pill" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Workspace unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Workspace data is unavailable.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Workspace name")).not.toBeInTheDocument();
    expect(screen.queryByText("Active", { selector: ".dashboard-verdict-pill" })).not.toBeInTheDocument();
  });
});
