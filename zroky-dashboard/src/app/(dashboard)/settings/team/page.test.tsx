import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TeamPage from "./page";

const api = vi.hoisted(() => ({
  createProjectInvitation: vi.fn(),
  getBillingMe: vi.fn(),
  listProjectInvitations: vi.fn(),
  listProjectMembers: vi.fn(),
  resendProjectInvitation: vi.fn(),
  revokeProjectInvitation: vi.fn(),
  upsertProjectMember: vi.fn(),
}));

const membershipState = vi.hoisted(() => ({
  role: "owner",
}));

vi.mock("@/lib/store", () => ({
  useDashboardStore: () => ({
    selectedProject: "proj_1",
  }),
}));

vi.mock("@/lib/hooks", async () => {
  const actual = await vi.importActual<typeof import("@/lib/hooks")>("@/lib/hooks");
  return {
    ...actual,
    useMyProjects: () => ({
      data: [
        {
          membership_id: "mem_current",
          project_id: "proj_1",
          project_name: "My Project",
          role: membershipState.role,
          is_active: true,
          created_at: "2026-05-29T10:00:00.000Z",
          updated_at: "2026-05-29T10:00:00.000Z",
        },
      ],
      isLoading: false,
      error: null,
    }),
    useProjectSettings: () => ({
      data: { project_id: "proj_1" },
      isLoading: false,
      error: null,
    }),
  };
});

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

const now = "2026-05-29T10:00:00.000Z";

function renderTeamPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <TeamPage />
    </QueryClientProvider>,
  );
}

describe("TeamPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    membershipState.role = "owner";
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
    renderTeamPage();

    expect(await screen.findByText("owner@example.com")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Members" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Invite member" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Project members" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Workspace access command center")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Seat usage")).not.toBeInTheDocument();
    expect(screen.queryByText("1 / 5")).not.toBeInTheDocument();
    expect(screen.queryByText("No members found.")).not.toBeInTheDocument();
    expect(api.listProjectMembers).toHaveBeenCalledWith("proj_1");
  });

  it("prevents the last active owner from being demoted or removed", async () => {
    renderTeamPage();

    expect(await screen.findByText("owner@example.com")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Change role for owner@example.com" })).toHaveProperty(
      "disabled",
      true,
    );
    expect(screen.getByRole("button", { name: "Remove" })).toHaveProperty("disabled", true);
    expect(screen.getByText("Last active owner cannot be demoted or removed.")).toBeInTheDocument();
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

    renderTeamPage();

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

  it("renders member management read-only for non-admin roles", async () => {
    membershipState.role = "viewer";
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

    renderTeamPage();

    expect(await screen.findByText("member@example.com")).toBeInTheDocument();
    expect(screen.getByText("Your role is Viewer. Member access is read-only for this account.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Send invite" })).toHaveProperty("disabled", true);
    expect(screen.getByRole("combobox", { name: "Change role for member@example.com" })).toHaveProperty("disabled", true);
    expect(screen.getAllByRole("button", { name: "Remove" })[0]).toHaveProperty("disabled", true);
    expect(api.upsertProjectMember).not.toHaveBeenCalled();
  });

  it("confirms email delivery after creating an invitation", async () => {
    api.createProjectInvitation.mockResolvedValue({
      invitation_id: "inv_1",
      project_id: "proj_1",
      email: "new@example.com",
      role: "member",
      invited_by_subject: "user:owner@example.com",
      expires_at: now,
      accepted_at: null,
      revoked_at: null,
      created_at: now,
      email_sent: true,
    });

    renderTeamPage();

    await screen.findByText("owner@example.com");
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Send invite" }));

    expect(await screen.findByText("Invitation email sent to new@example.com.")).toBeInTheDocument();
    expect(api.createProjectInvitation).toHaveBeenCalledWith("proj_1", {
      email: "new@example.com",
      role: "member",
    });
  });

  it("resends a pending invitation with a fresh token", async () => {
    const invitation = {
      invitation_id: "inv_1",
      project_id: "proj_1",
      email: "pending@example.com",
      role: "viewer",
      invited_by_subject: "user:owner@example.com",
      expires_at: now,
      accepted_at: null,
      revoked_at: null,
      created_at: now,
      email_sent: null,
    };
    api.listProjectInvitations.mockResolvedValue([invitation]);
    api.resendProjectInvitation.mockResolvedValue({ ...invitation, email_sent: true });

    renderTeamPage();

    expect(await screen.findByText("pending@example.com")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resend" }));

    expect(await screen.findByText("Invitation email resent to pending@example.com.")).toBeInTheDocument();
    expect(api.resendProjectInvitation).toHaveBeenCalledWith("proj_1", "inv_1");
  });
});
