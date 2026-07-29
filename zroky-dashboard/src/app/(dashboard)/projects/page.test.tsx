import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProjectsPage from "./page";

const api = vi.hoisted(() => ({
  createCurrentUserProject: vi.fn(),
  getBillingMe: vi.fn(),
  getProjectSettings: vi.fn(),
  listMyProjects: vi.fn(),
}));

const router = vi.hoisted(() => ({
  push: vi.fn(),
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
  useRouter: () => router,
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
    role: "admin",
    is_active: true,
    created_at: "2026-06-18T10:00:00.000Z",
    updated_at: "2026-06-18T10:30:00.000Z",
  },
];

function billing(maxProjects: number) {
  return {
    org_id: "proj_1",
    plan_code: "pro",
    status: "active",
    seats: 1,
    payment_provider: "stripe",
    payment_customer_ref: null,
    payment_subscription_ref: null,
    payment_request_ref: null,
    current_period_end: null,
    trial_end: null,
    sla_tier: "standard",
    plan_template: { max_projects: maxProjects },
  };
}

describe("ProjectsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    store.selectedProject = "proj_1";
    api.getProjectSettings.mockResolvedValue(activeProject);
    api.listMyProjects.mockResolvedValue(projectRows);
    api.getBillingMe.mockResolvedValue(billing(3));
  });

  it("renders accessible projects with subscription project usage", async () => {
    render(<ProjectsPage />);

    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getByText("2 / 3 projects used")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Refund Agent" }).getAttribute("href")).toBe("/projects/proj_1");
    expect(screen.getByRole("link", { name: "Open Checkout Agent" }).getAttribute("href")).toBe("/projects/proj_2");
    expect(screen.getByText("Owner")).toBeInTheDocument();
    expect(screen.getByText("Admin")).toBeInTheDocument();
  });

  it("creates a project inside the active project context and opens its detail page", async () => {
    api.listMyProjects.mockResolvedValue([projectRows[0]]);
    api.createCurrentUserProject.mockResolvedValue({
      membership_id: "mem_3",
      project_id: "proj_3",
      project_name: "Support Agent",
      role: "owner",
      is_active: true,
      created_at: "2026-06-19T10:00:00.000Z",
      updated_at: "2026-06-19T10:00:00.000Z",
    });

    render(<ProjectsPage />);

    fireEvent.change(await screen.findByLabelText("New project"), {
      target: { value: "Support Agent" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => {
      expect(api.createCurrentUserProject).toHaveBeenCalledWith({ name: "Support Agent" }, "proj_1");
    });
    expect(store.setSelectedProject).toHaveBeenCalledWith("proj_3");
    expect(router.push).toHaveBeenCalledWith("/projects/proj_3");
  });

  it("blocks create controls when the current plan project limit is reached", async () => {
    api.getBillingMe.mockResolvedValue(billing(2));

    render(<ProjectsPage />);

    expect(await screen.findByText("2 / 2 projects used")).toBeInTheDocument();
    expect((screen.getByRole("button", { name: "Limit reached" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("New project") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole("link", { name: "Upgrade plan" }).getAttribute("href")).toBe("/settings/billing");
  });
});
