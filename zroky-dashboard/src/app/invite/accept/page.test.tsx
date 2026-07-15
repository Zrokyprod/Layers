import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AcceptInvitationPage from "./page";

const mocks = vi.hoisted(() => ({
  acceptInvitation: vi.fn(),
  setSelectedProject: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("token=secure-invite-token"),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    acceptInvitation: mocks.acceptInvitation,
  };
});

vi.mock("@/lib/store", () => ({
  useDashboardStore: (selector: (state: { setSelectedProject: typeof mocks.setSelectedProject }) => unknown) =>
    selector({ setSelectedProject: mocks.setSelectedProject }),
}));

describe("AcceptInvitationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("accepts the invitation and selects the invited project", async () => {
    mocks.acceptInvitation.mockResolvedValue({
      success: true,
      message: "Invitation accepted. You now have access to the project.",
      project_id: "proj_invited",
      membership_id: "mem_1",
    });

    render(<AcceptInvitationPage />);

    expect(await screen.findByRole("heading", { name: "Invitation accepted" })).toBeInTheDocument();
    expect(mocks.acceptInvitation).toHaveBeenCalledWith("secure-invite-token");
    expect(mocks.setSelectedProject).toHaveBeenCalledWith("proj_invited");
    expect(screen.getByRole("link", { name: "Open project" }).getAttribute("href")).toBe("/home");
  });

  it("shows the invited-email error returned by the backend", async () => {
    mocks.acceptInvitation.mockResolvedValue({
      success: false,
      message: "Sign in with the email address that received this invitation.",
      project_id: null,
      membership_id: null,
    });

    render(<AcceptInvitationPage />);

    await waitFor(() => expect(mocks.acceptInvitation).toHaveBeenCalled());
    expect(await screen.findAllByText("Sign in with the email address that received this invitation.")).toHaveLength(2);
    expect(mocks.setSelectedProject).not.toHaveBeenCalled();
  });
});
