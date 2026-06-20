import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProjectDetailPage from "./page";

const api = vi.hoisted(() => ({
  deleteProject: vi.fn(),
  getProjectSettings: vi.fn(),
  listMyProjects: vi.fn(),
}));

const navigation = vi.hoisted(() => ({
  params: { projectId: "proj_2" },
  replace: vi.fn(),
}));

const store = vi.hoisted(() => ({
  setSelectedProject: vi.fn(),
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
  useParams: () => navigation.params,
  useRouter: () => ({ replace: navigation.replace }),
}));

vi.mock("@/lib/store", () => ({
  useDashboardStore: (selector: (state: typeof store) => unknown) => selector(store),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

const activeProject = {
  project_id: "proj_1",
  name: "Refund Agent",
  owner_ref: "email:founder@zroky.com",
  is_active: true,
  created_at: "2026-06-17T10:00:00.000Z",
  updated_at: "2026-06-17T10:30:00.000Z",
};

const projectRows = [
  {
    membership_id: "mem_1",
    project_id: "proj_1",
    project_name: "Refund Agent",
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
];

describe("ProjectDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.params = { projectId: "proj_2" };
    api.getProjectSettings.mockResolvedValue(activeProject);
    api.listMyProjects.mockResolvedValue(projectRows);
    api.deleteProject.mockResolvedValue({
      ...activeProject,
      project_id: "proj_2",
      name: "Checkout Agent",
      is_active: false,
    });
  });

  it("renders project facts and can switch the selected project", async () => {
    render(<ProjectDetailPage />);

    expect(await screen.findByRole("heading", { name: "Checkout Agent" })).toBeInTheDocument();
    expect(screen.getByText("Project ID")).toBeInTheDocument();
    expect(screen.getByText("proj_2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Make active" }));

    expect(store.setSelectedProject).toHaveBeenCalledWith("proj_2");
    expect(screen.getByText("Active project changed.")).toBeInTheDocument();
  });

  it("deletes an owned project only after typed confirmation", async () => {
    render(<ProjectDetailPage />);

    fireEvent.change(await screen.findByLabelText("Type project name"), {
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
    expect(navigation.replace).toHaveBeenCalledWith("/projects/proj_1");
  });

  it("shows not-found state for a project outside the user's memberships", async () => {
    navigation.params = { projectId: "proj_missing" };

    render(<ProjectDetailPage />);

    expect(await screen.findByText("Project not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View projects" }).getAttribute("href")).toBe("/projects");
  });
});
