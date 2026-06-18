import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProvidersPage from "./page";

const api = vi.hoisted(() => ({
  createProviderKey: vi.fn(),
  getBillingMe: vi.fn(),
  listProviderKeys: vi.fn(),
  listProviderVerifications: vi.fn(),
  revokeProviderKey: vi.fn(),
  testProviderConnection: vi.fn(),
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

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

const now = "2026-05-29T10:00:00.000Z";

function providerKey(overrides: Partial<import("@/lib/types").ProviderKeyResponse> = {}): import("@/lib/types").ProviderKeyResponse {
  return {
    id: "provider_key_1",
    project_id: "proj_1",
    provider: "openai",
    key_fingerprint: "abcdef1234567890",
    key_last4: "1234",
    kms_key_id: "kms_1",
    label: "production",
    is_active: true,
    created_by_user_id: "user_1",
    last_used_at: now,
    revoked_at: null,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function verification(overrides: Partial<import("@/lib/types").ProviderVerificationItem> = {}): import("@/lib/types").ProviderVerificationItem {
  return {
    provider: "openai",
    status: "verified",
    tracked_call_count: 12,
    last_checked_at: now,
    last_error: null,
    ...overrides,
  };
}

function billing(overrides: Partial<import("@/lib/types").BillingMeResponse> = {}): import("@/lib/types").BillingMeResponse {
  return {
    org_id: "org_1",
    plan_code: "pro",
    status: "active",
    seats: 1,
    payment_provider: "manual",
    payment_customer_ref: null,
    payment_subscription_ref: null,
    payment_request_ref: null,
    current_period_end: null,
    trial_end: null,
    sla_tier: "standard",
    plan_template: {
      "enterprise.provider_key_vault": true,
    },
    ...overrides,
  };
}

function mockProviderApi({
  keys = [],
  verifications = [verification()],
  billingMe = billing(),
}: {
  keys?: import("@/lib/types").ProviderKeyResponse[];
  verifications?: import("@/lib/types").ProviderVerificationItem[];
  billingMe?: import("@/lib/types").BillingMeResponse;
} = {}) {
  api.listProviderKeys.mockResolvedValue({ items: keys, total_in_page: keys.length });
  api.listProviderVerifications.mockResolvedValue({ items: verifications });
  api.getBillingMe.mockResolvedValue(billingMe);
}

describe("ProvidersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockProviderApi();
  });

  it("renders the BYOK setup story and no-key empty state", async () => {
    render(<ProvidersPage />);

    expect(await screen.findByRole("heading", { name: "Save provider keys only when replay needs real provider access." })).toBeInTheDocument();
    expect(screen.getByText("Capture and stub replay stay keyless. Vault keys are encrypted and used only by provider-backed replay paths enabled for this workspace.")).toBeInTheDocument();
    expect(screen.getByText("Capture without key")).toBeInTheDocument();
    expect(screen.getAllByText("Stub replay").length).toBeGreaterThan(0);
    expect(screen.getByText("CI gate")).toBeInTheDocument();
    expect(screen.getByText("Do not add provider keys for capture.")).toBeInTheDocument();
    expect(await screen.findByText("No provider keys saved yet. Capture still works; connect a key when verified replay is needed.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Replay/ }).getAttribute("href")).toBe("/replay");
  });

  it("saves a provider key with the expected payload and clears plaintext input", async () => {
    api.createProviderKey.mockResolvedValue(providerKey());

    render(<ProvidersPage />);
    await screen.findByRole("heading", { name: "Save provider keys only when replay needs real provider access." });

    const keyInput = screen.getByLabelText("API key");
    fireEvent.change(keyInput, { target: { value: "sk-test-provider-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Save provider key" }));

    await waitFor(() =>
      expect(api.createProviderKey).toHaveBeenCalledWith({
        provider: "openai",
        plaintext_key: "sk-test-provider-key",
        label: "production",
      }),
    );
    expect(await screen.findByText("OpenAI key saved in the encrypted vault.")).toBeInTheDocument();
    expect((keyInput as HTMLInputElement).value).toBe("");
    expect(screen.queryByText("sk-test-provider-key")).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("sk-test-provider-key")).not.toBeInTheDocument();
  });

  it("lists active provider keys with status and fingerprint", async () => {
    mockProviderApi({ keys: [providerKey({ last_used_at: null })] });

    render(<ProvidersPage />);

    expect(await screen.findByText("abcdef12...1234")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("OpenAI")).toBeInTheDocument();
    expect(within(table).getByText("production")).toBeInTheDocument();
    expect(within(table).getByText("Active")).toBeInTheDocument();
    expect(within(table).getByText("Never")).toBeInTheDocument();
  });

  it("revokes an active provider key from the confirmation modal", async () => {
    mockProviderApi({ keys: [providerKey()] });
    api.revokeProviderKey.mockResolvedValue(providerKey({ is_active: false, revoked_at: now }));

    render(<ProvidersPage />);

    await screen.findByText("abcdef12...1234");
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    expect(screen.getByRole("dialog", { name: "Revoke provider key" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Yes, revoke key" }));

    await waitFor(() => expect(api.revokeProviderKey).toHaveBeenCalledWith("provider_key_1"));
    expect(await screen.findByText("OpenAI key revoked.")).toBeInTheDocument();
  });

  it("tests provider connectivity and displays the result", async () => {
    api.testProviderConnection.mockResolvedValue({
      provider: "openai",
      status: "verified",
      message: "Connection verified.",
      checked_at: now,
    });

    render(<ProvidersPage />);

    await screen.findByText("Priority providers");
    fireEvent.click(screen.getAllByRole("button", { name: "Check provider status" })[0]);

    await waitFor(() => expect(api.testProviderConnection).toHaveBeenCalledWith("openai"));
    expect(await screen.findByText("OK: Connection verified.")).toBeInTheDocument();
  });

  it("shows vault config errors without hiding the save form", async () => {
    api.listProviderKeys.mockRejectedValue(new Error("Provider vault not configured."));
    api.listProviderVerifications.mockResolvedValue({ items: [] });

    render(<ProvidersPage />);

    expect(await screen.findByText("Provider vault is not ready in this environment.")).toBeInTheDocument();
    expect(screen.getByText("Provider vault not configured.")).toBeInTheDocument();
    expect(screen.getByLabelText("Provider")).toBeInTheDocument();
    expect(screen.getByLabelText("API key")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save provider key" })).toBeInTheDocument();
  });

  it("locks the save form before free-plan users paste a provider secret", async () => {
    mockProviderApi({
      billingMe: billing({
        plan_code: "free",
        plan_template: {
          "enterprise.provider_key_vault": false,
        },
      }),
    });

    render(<ProvidersPage />);

    expect(await screen.findByText("Provider key vault is not included in Free Plan.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upgrade plan" }).getAttribute("href")).toBe("/settings/billing?upgrade_hint=enterprise.provider_key_vault");
    expect(screen.queryByLabelText("API key")).not.toBeInTheDocument();
  });
});
