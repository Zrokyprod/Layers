import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccountPage from "./page";

const api = vi.hoisted(() => ({
  confirmTotpMfa: vi.fn(),
  deleteAccount: vi.fn(),
  disableTotpMfa: vi.fn(),
  getBillingMe: vi.fn(),
  getBillingUsage: vi.fn(),
  getSecurityStatus: vi.fn(),
  logoutAllSessions: vi.fn(),
  startTotpMfa: vi.fn(),
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
  meError: null as Error | null,
  meLoading: false,
  updateMeMutateAsync: vi.fn(),
}));

const store = vi.hoisted(() => ({
  selectedProject: "proj_1" as string | null,
}));

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
}));

const auth = vi.hoisted(() => ({
  clearAccessToken: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: navigation.push,
  }),
}));

vi.mock("@/lib/auth", () => ({
  clearAccessToken: auth.clearAccessToken,
}));

vi.mock("@/lib/store", () => ({
  useDashboardStore: <T,>(selector: (state: typeof store) => T) => selector(store),
}));

vi.mock("@/lib/hooks", () => ({
  useChangePassword: () => ({
    mutateAsync: hooks.changePasswordMutateAsync,
    isPending: false,
  }),
  useMe: () => ({
    data: hooks.me,
    error: hooks.meError,
    isLoading: hooks.meLoading,
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
    hooks.me.has_password = true;
    hooks.me.github_login = "sanket";
    hooks.me.google_id = null;
    hooks.meError = null;
    hooks.meLoading = false;
    store.selectedProject = "proj_1";
    hooks.updateMeMutateAsync.mockResolvedValue(hooks.me);
    hooks.changePasswordMutateAsync.mockResolvedValue({ detail: "Password changed. Sign in again to continue." });
    auth.clearAccessToken.mockResolvedValue(undefined);
    api.getSecurityStatus.mockResolvedValue({
      two_factor_enabled: false,
      password_login_enabled: true,
      github_connected: true,
      google_connected: false,
      current_session_expires_at: "2026-05-30T10:00:00.000Z",
      global_logout_available: true,
    });
    api.startTotpMfa.mockResolvedValue({
      secret: "JBSWY3DPEHPK3PXP",
      otpauth_uri: "otpauth://totp/Zroky:owner@example.com?secret=JBSWY3DPEHPK3PXP&issuer=Zroky",
      expires_in_seconds: 600,
    });
    api.confirmTotpMfa.mockResolvedValue({ detail: "Authenticator MFA enabled. Sign in again to continue." });
    api.disableTotpMfa.mockResolvedValue({ detail: "Authenticator MFA disabled. Sign in again to continue." });
    api.getBillingMe.mockResolvedValue({
      org_id: "org_1",
      plan_code: "pro",
      status: "active",
      seats: 3,
      payment_provider: "razorpay",
      payment_customer_ref: "billing@example.com",
      payment_subscription_ref: "sub_1",
      payment_request_ref: null,
      current_period_end: null,
      trial_end: null,
      sla_tier: "standard",
      plan_template: {},
    });
    api.getBillingUsage.mockResolvedValue({
      tenant_id: "org_1",
      org_id: "org_1",
      period_month: "2026-06",
      period_start: "2026-06-01T00:00:00Z",
      period_end: "2026-07-01T00:00:00Z",
      plan_code: "pro",
      plan_name: "Team",
      subscription_status: "active",
      calls: { used: 0, limit: null, unlimited: true, overage: null, state: "ok", resets_at: null },
      replay: { used: 0, limit: null, unlimited: true, overage: null, state: "ok", resets_at: null },
      goldens: { used: 0, limit: null, unlimited: true, overage: null, state: "ok", resets_at: null },
      golden_sets: { used: 0, limit: null, unlimited: true, overage: null, state: "ok", resets_at: null },
      protected_actions: { used: 7, limit: 10000, unlimited: false, overage: null, state: "ok", resets_at: null },
      policy_checks: { used: 18, limit: 50000, unlimited: false, overage: null, state: "ok", resets_at: null },
      runner_executions: { used: 4, limit: 10000, unlimited: false, overage: null, state: "ok", resets_at: null },
      action_receipts: { used: 4, limit: 10000, unlimited: false, overage: null, state: "ok", resets_at: null },
      verification_checks: { used: 9, limit: 25000, unlimited: false, overage: null, state: "ok", resets_at: null },
      source_mutations: { used: 11, limit: 50000, unlimited: false, overage: null, state: "ok", resets_at: null },
      active_connectors: { used: 1, limit: 6, unlimited: false, overage: null, state: "ok", resets_at: null },
      metering_health: { state: "ok", failure_count: 0, last_failure_at: null, last_failure_type: null, failure_policy: "strict", detail: "Event metering is healthy." },
    });
  });

  it("surfaces account posture without duplicate in-page navigation", async () => {
    render(<AccountPage />);

    expect(screen.getByRole("heading", { name: "Sanket K." })).toBeInTheDocument();
    expect(screen.getByLabelText("Account overview")).toBeInTheDocument();
    expect(await screen.findByText("Add MFA")).toBeInTheDocument();
    expect(screen.getByLabelText("Account security")).toBeInTheDocument();
    expect(await screen.findByLabelText("Account plan")).toBeInTheDocument();
    expect(screen.getByText("Team Plan")).toBeInTheDocument();
    expect(screen.getByText("7 / 10,000")).toBeInTheDocument();
    expect(screen.getByText("Recovery and workspace invites.")).toBeInTheDocument();
    expect(screen.queryByText("u_1")).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Account control flow" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Your identity" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Change password" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Account security" })).toBeInTheDocument();
    expect(screen.getAllByText("GitHub").length).toBeGreaterThan(0);
  });

  it("loads profile identity and updates display name", async () => {
    render(<AccountPage />);

    expect(screen.getByDisplayValue("Sanket K.")).toBeInTheDocument();
    expect((screen.getByRole("button", { name: "Save profile" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Sanket Team" } });
    expect((screen.getByRole("button", { name: "Save profile" }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(hooks.updateMeMutateAsync).toHaveBeenCalledWith({ displayName: "Sanket Team" }));
    expect(await screen.findByText("Profile updated.")).toBeInTheDocument();
  });

  it("treats OAuth-only login as controlled when sessions are manageable", async () => {
    hooks.me.has_password = false;
    api.getSecurityStatus.mockResolvedValue({
      two_factor_enabled: false,
      password_login_enabled: false,
      github_connected: true,
      google_connected: false,
      current_session_expires_at: "2026-05-30T10:00:00.000Z",
      global_logout_available: true,
    });

    render(<AccountPage />);

    expect(await screen.findByText("Controlled")).toBeInTheDocument();
    expect(screen.queryByText("Limited login")).not.toBeInTheDocument();
    expect(await screen.findByText("OAuth only")).toBeInTheDocument();
  });

  it("starts authenticator MFA setup from backend enrollment", async () => {
    render(<AccountPage />);

    expect(await screen.findByText("Account security")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Set up authenticator" }));

    await waitFor(() => expect(api.startTotpMfa).toHaveBeenCalled());
    expect(await screen.findByDisplayValue("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enable authenticator" })).toBeInTheDocument();
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

  it("does not infer security or billing states when their APIs fail", async () => {
    api.getSecurityStatus.mockRejectedValue(new Error("Security unavailable."));
    api.getBillingMe.mockRejectedValue(new Error("Billing unavailable."));
    api.getBillingUsage.mockRejectedValue(new Error("Billing unavailable."));

    render(<AccountPage />);

    expect(await screen.findByText("Security unavailable.")).toBeInTheDocument();
    expect(await screen.findByText("Billing unavailable.")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.queryByText("No paid checkout")).not.toBeInTheDocument();
    expect((screen.getByRole("button", { name: /Log out all sessions/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("clears stale security posture when a refresh fails", async () => {
    render(<AccountPage />);
    expect(await screen.findByText("Add MFA")).toBeInTheDocument();

    api.getSecurityStatus.mockRejectedValueOnce(new Error("Security refresh failed."));
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await screen.findByText("Security refresh failed.")).toBeInTheDocument();
    expect(screen.getByText("Needs review")).toBeInTheDocument();
    expect(screen.queryByText("Add MFA")).not.toBeInTheDocument();
  });

  it("reloads billing for the selected workspace", async () => {
    const view = render(<AccountPage />);
    await waitFor(() => expect(api.getBillingMe).toHaveBeenCalledWith(expect.any(AbortSignal), "proj_1"));

    store.selectedProject = "proj_2";
    view.rerender(<AccountPage />);

    await waitFor(() => expect(api.getBillingMe).toHaveBeenCalledWith(expect.any(AbortSignal), "proj_2"));
    expect(api.getBillingUsage).toHaveBeenCalledWith(expect.any(AbortSignal), "proj_2");
  });

  it("does not render placeholder identity when account loading fails", () => {
    hooks.meError = new Error("Account service unavailable.");
    render(<AccountPage />);

    expect(screen.getByRole("heading", { name: "Account unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Account service unavailable.")).toBeInTheDocument();
    expect(screen.queryByText("No email set")).not.toBeInTheDocument();
  });

  it("accepts case-insensitive email confirmation for account deletion", async () => {
    api.deleteAccount.mockResolvedValue({ detail: "Account deleted successfully." });
    render(<AccountPage />);

    fireEvent.click(screen.getByRole("button", { name: "Delete my account" }));
    fireEvent.change(screen.getByLabelText("Confirmation email"), {
      target: { value: " OWNER@EXAMPLE.COM " },
    });
    const deleteButton = screen.getByRole("button", { name: "Permanently delete account" });
    expect((deleteButton as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(deleteButton);

    await waitFor(() => expect(api.deleteAccount).toHaveBeenCalledWith("OWNER@EXAMPLE.COM"));
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/login"));
  });

  it("returns to sign-in after a password change revokes every session", async () => {
    render(<AccountPage />);

    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "old-password" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "new-password" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "new-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));

    await waitFor(() => expect(hooks.changePasswordMutateAsync).toHaveBeenCalledWith({
      currentPassword: "old-password",
      newPassword: "new-password",
    }));
    expect(auth.clearAccessToken).toHaveBeenCalledTimes(1);
    expect(navigation.push).toHaveBeenCalledWith("/login");
  });

  it("requires confirmation before revoking every session", async () => {
    api.logoutAllSessions.mockResolvedValue({ detail: "Sessions revoked." });
    render(<AccountPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Log out all sessions" }));

    expect(api.logoutAllSessions).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Log out all sessions" })).toBeInTheDocument();
    expect(screen.getByText(/including this browser/i)).toBeInTheDocument();

    fireEvent.keyDown(screen.getByRole("dialog", { name: "Log out all sessions" }), { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Log out all sessions" })).not.toBeInTheDocument();
    expect(api.logoutAllSessions).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Log out all sessions" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, log out everywhere" }));

    await waitFor(() => expect(api.logoutAllSessions).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/login"));
  });
});
