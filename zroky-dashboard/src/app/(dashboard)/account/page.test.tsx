import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccountPage from "./page";

const api = vi.hoisted(() => ({
  deleteAccount: vi.fn(),
  getSecurityStatus: vi.fn(),
  logoutAllSessions: vi.fn(),
}));

const hooks = vi.hoisted(() => ({
  changePasswordMutateAsync: vi.fn(),
  me: {
    user_id: "u_1",
    email: "owner@example.com",
    display_name: "Sanket K.",
    github_login: "sanket",
    google_id: null,
    has_password: true,
    is_active: true,
    email_verified: true,
    created_at: "2026-05-29T10:00:00.000Z",
  },
  updateMeMutateAsync: vi.fn(),
}));

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: navigation.push,
  }),
}));

vi.mock("@/lib/auth", () => ({
  clearAccessToken: vi.fn(),
}));

vi.mock("@/lib/hooks", () => ({
  useChangePassword: () => ({
    mutateAsync: hooks.changePasswordMutateAsync,
    isPending: false,
  }),
  useMe: () => ({
    data: hooks.me,
    error: null,
  }),
  useUpdateMe: () => ({
    mutateAsync: hooks.updateMeMutateAsync,
    isPending: false,
  }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

describe("AccountPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hooks.updateMeMutateAsync.mockResolvedValue(hooks.me);
    hooks.changePasswordMutateAsync.mockResolvedValue({ detail: "Password changed successfully." });
    api.getSecurityStatus.mockResolvedValue({
      two_factor_enabled: false,
      password_login_enabled: true,
      github_connected: true,
      google_connected: false,
      current_session_expires_at: "2026-05-30T10:00:00.000Z",
      global_logout_available: true,
    });
  });

  it("surfaces account posture and personal control flow", async () => {
    render(<AccountPage />);

    expect(screen.getByRole("heading", { name: "Sanket K." })).toBeInTheDocument();
    expect(screen.getByLabelText("Account security overview")).toBeInTheDocument();
    expect(await screen.findByText("Controlled")).toBeInTheDocument();
    expect(screen.getByLabelText("Account control summary")).toBeInTheDocument();
    for (const label of ["Identity", "Login method", "Session control", "Danger zone"]) {
      expect(screen.getByRole("link", { name: new RegExp(label) })).toBeInTheDocument();
    }
    expect(screen.getAllByText("GitHub").length).toBeGreaterThan(0);
  });

  it("loads profile identity and updates display name", async () => {
    render(<AccountPage />);

    expect(screen.getByDisplayValue("Sanket K.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Sanket Team" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(hooks.updateMeMutateAsync).toHaveBeenCalledWith({ displayName: "Sanket Team" }));
    expect(await screen.findByText("Profile updated.")).toBeInTheDocument();
  });

  it("does not expose fake two-factor controls without backend enrollment", async () => {
    render(<AccountPage />);

    expect(await screen.findByText("Account security")).toBeInTheDocument();
    expect(screen.queryByText(/two-factor/i)).not.toBeInTheDocument();
  });

  it("disables global session logout when backend does not allow it", async () => {
    api.getSecurityStatus.mockResolvedValue({
      two_factor_enabled: false,
      password_login_enabled: true,
      github_connected: true,
      google_connected: false,
      current_session_expires_at: "2026-05-30T10:00:00.000Z",
      global_logout_available: false,
    });

    render(<AccountPage />);

    expect(await screen.findAllByText("Unavailable")).not.toHaveLength(0);
    expect((screen.getByRole("button", { name: /Log out all sessions/i }) as HTMLButtonElement).disabled).toBe(true);
  });
});
