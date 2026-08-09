import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProjectDetailPage from "./page";

const api = vi.hoisted(() => ({
  deleteProject: vi.fn(),
  getProjectSettings: vi.fn(),
  listActionRunners: vi.fn(),
  listMyProjects: vi.fn(),
  registerActionRunner: vi.fn(),
}));

const navigation = vi.hoisted(() => ({
  params: { projectId: "proj_2" },
  replace: vi.fn(),
}));

const store = vi.hoisted(() => ({
  selectedProject: "proj_1" as string | null,
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
    store.selectedProject = "proj_1";
    api.getProjectSettings.mockResolvedValue(activeProject);
    api.listActionRunners.mockResolvedValue({ items: [] });
    api.listMyProjects.mockResolvedValue(projectRows);
    api.deleteProject.mockResolvedValue({
      ...activeProject,
      project_id: "proj_2",
      name: "Checkout Agent",
      is_active: false,
    });
    api.registerActionRunner.mockResolvedValue({
      runner_id: "runner_123",
      project_id: "proj_1",
      name: "Protected action runner",
      runner_type: "customer_hosted",
      environment: "production",
      status: "registered",
      supported_operation_kinds: ["TRANSFER"],
      credential_scope: {
        allowed_prefixes: ["customer-runner-secret://payments/stripe"],
        default_credential_ref: "customer-runner-secret://payments/stripe",
      },
      capability_manifest: {},
      heartbeat_payload: {},
      capability_version: null,
      last_heartbeat_at: null,
      created_at: "2026-08-08T04:00:00.000Z",
      updated_at: "2026-08-08T04:00:00.000Z",
    });
  });

  it("renders project facts and can switch the selected project", async () => {
    render(<ProjectDetailPage />);

    expect(await screen.findByRole("heading", { level: 1, name: "Checkout Agent" })).toBeInTheDocument();
    expect(api.getProjectSettings).toHaveBeenCalledWith("proj_2");
    expect(api.listActionRunners).toHaveBeenCalledWith(undefined, "proj_2");
    expect(screen.getByText("Project ID")).toBeInTheDocument();
    expect(screen.getByText("proj_2")).toBeInTheDocument();
    expect(screen.getByText("available", { selector: ".status-pill" })).toBeInTheDocument();
    expect(screen.getByText("Project data is not immediately erased.", { exact: false })).toBeInTheDocument();

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

  it("does not expose owner controls when memberships fail to load", async () => {
    api.listMyProjects.mockRejectedValue(new Error("Membership service unavailable."));

    render(<ProjectDetailPage />);

    expect(await screen.findByText("Project access unavailable")).toBeInTheDocument();
    expect(screen.queryByLabelText("Type project name")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete project" })).not.toBeInTheDocument();
  });

  it("registers a scoped runner and renders secret-safe launch instructions", async () => {
    navigation.params = { projectId: "proj_1" };

    render(<ProjectDetailPage />);

    fireEvent.change(await screen.findByLabelText("Credential reference"), {
      target: { value: "customer-runner-secret://payments/stripe" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Register runner" }));

    await waitFor(() => {
      expect(api.registerActionRunner).toHaveBeenCalledWith(
        {
          name: "Protected action runner",
          runner_type: "customer_hosted",
          environment: "production",
          supported_operation_kinds: ["TRANSFER"],
          credential_scope: {
            allowed_prefixes: ["customer-runner-secret://payments/stripe"],
            default_credential_ref: "customer-runner-secret://payments/stripe",
          },
        },
        "proj_1",
      );
    });

    fireEvent.click(await screen.findByText("Launch this runner"));
    expect(screen.getByText(/ZROKY_RUNNER_SECRET_PAYMENTS_STRIPE=<local-secret-or-json>/)).toBeInTheDocument();
    expect(screen.getByText(/ZROKY_API_KEY=<project-api-key>/)).toBeInTheDocument();
    expect(screen.queryByText(/sk_live_|sk_test_/)).not.toBeInTheDocument();
  });
});
