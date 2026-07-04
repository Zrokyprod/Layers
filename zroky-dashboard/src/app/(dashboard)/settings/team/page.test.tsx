import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TeamPage from "./page";

const api = vi.hoisted(() => ({
  createProjectInvitation: vi.fn(),
  getBillingMe: vi.fn(),
  listProjectInvitations: vi.fn(),
  listProjectMembers: vi.fn(),
  revokeProjectInvitation: vi.fn(),
  upsertProjectMember: vi.fn(),
}));

vi.mock("@/lib/store", () => ({
  useDashboardStore: () => ({
    selectedProject: "proj_1",
  }),
}));

vi.mock("@/lib/hooks", () => ({
  useProjectSettings: () => ({
    data: { project_id: "proj_1" },
    isLoading: false,
    error: null,
  }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

const now = "2026-05-29T10:00:00.000Z";

describe("TeamPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listProjectMembers.mockResolvedValue([
      {
        membership_id: "m_1",
        project_id: "proj_1",
        user_id: "u_1",
        subject: "user:owner@example.com",
        email: "owner@example.com",
        role: "owner",
        is_active: true,
        created_at: now,
        updated_at: now,
      },
    ]);
    api.listProjectInvitations.mockResolvedValue([]);
    api.getBillingMe.mockResolvedValue({
      org_id: "org_1",
      plan_code: "pro",
      status: "active",
      seats: 5,
      payment_provider: "razorpay",
      payment_customer_ref: "billing@example.com",
      payment_subscription_ref: "sub_1",
      payment_request_ref: null,
      current_period_end: null,
      trial_end: null,
      sla_tier: "standard",
      plan_template: {},
    });
  });

  it("renders backend array membership responses directly", async () => {
    render(<TeamPage />);

    expect(await screen.findByText("owner@example.com")).toBeInTheDocument();
    expect(screen.getByLabelText("Workspace access command center")).toBeInTheDocument();
    expect(screen.getByLabelText("Seat usage")).toBeInTheDocument();
    expect(screen.getByText("1 / 5")).toBeInTheDocument();
    expect(screen.queryByText("No members found.")).not.toBeInTheDocument();
    expect(api.listProjectMembers).toHaveBeenCalledWith("proj_1");
  });

  it("can change a member role through the project member API", async () => {
    api.listProjectMembers.mockResolvedValue([
      {
        membership_id: "m_1",
        project_id: "proj_1",
        user_id: "u_1",
        subject: "user:owner@example.com",
        email: "owner@example.com",
        role: "owner",
        is_active: true,
        created_at: now,
        updated_at: now,
      },
      {
        membership_id: "m_2",
        project_id: "proj_1",
        user_id: "u_2",
        subject: "user:member@example.com",
        email: "member@example.com",
        role: "member",
        is_active: true,
        created_at: now,
        updated_at: now,
      },
    ]);
    api.upsertProjectMember.mockResolvedValue({
      membership_id: "m_2",
      project_id: "proj_1",
      user_id: "u_2",
      subject: "user:member@example.com",
      email: "member@example.com",
      role: "admin",
      is_active: true,
      created_at: now,
      updated_at: now,
    });

    render(<TeamPage />);

    expect(await screen.findByText("member@example.com")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Change role for member@example.com" }), {
      target: { value: "admin" },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Apply role change" }));

    await waitFor(() =>
      expect(api.upsertProjectMember).toHaveBeenCalledWith("proj_1", {
        subject: "user:member@example.com",
        role: "admin",
      }),
    );
  });
});
