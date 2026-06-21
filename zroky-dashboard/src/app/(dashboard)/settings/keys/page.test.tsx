import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ApiKeysPage from "./page";

const hooks = vi.hoisted(() => ({
  useProjectSettings: vi.fn(),
  useListProjectApiKeys: vi.fn(),
  useCreateProjectApiKey: vi.fn(),
  useRevokeProjectApiKey: vi.fn(),
  useRotateProjectApiKey: vi.fn(),
}));

const navigation = vi.hoisted(() => ({
  query: "",
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
  useSearchParams: () => new URLSearchParams(navigation.query),
}));

vi.mock("@/lib/hooks", () => hooks);

const now = "2026-05-29T10:00:00.000Z";

function apiKey(overrides: Partial<import("@/lib/types").ApiKeyResponse> = {}): import("@/lib/types").ApiKeyResponse {
  return {
    key_id: "key_1",
    project_id: "proj_1",
    name: "Production capture key",
    key_prefix: "zk_live",
    scopes: ["project:member"],
    revoked: false,
    expired: false,
    expires_at: "2026-08-29T10:00:00.000Z",
    rotated_from_key_id: null,
    last_used_at: null,
    created_at: now,
    ...overrides,
  };
}

function createdKey(overrides: Partial<import("@/lib/types").ApiKeyCreateResponse> = {}): import("@/lib/types").ApiKeyCreateResponse {
  return {
    key_id: "key_new",
    project_id: "proj_1",
    name: "Production capture key",
    key_prefix: "zk_new",
    api_key: "zk_live_created_secret",
    scopes: ["project:member"],
    expires_at: "2026-08-29T10:00:00.000Z",
    rotated_from_key_id: null,
    created_at: now,
    ...overrides,
  };
}

const createMutateAsync = vi.fn();
const revokeMutateAsync = vi.fn();
const rotateMutateAsync = vi.fn();
const clipboardWrite = vi.fn();

describe("ApiKeysPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.query = "";
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: clipboardWrite },
    });
    clipboardWrite.mockResolvedValue(undefined);

    hooks.useProjectSettings.mockReturnValue({
      data: { project_id: "proj_1" },
      isLoading: false,
      error: null,
    });
    hooks.useListProjectApiKeys.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    });
    hooks.useCreateProjectApiKey.mockReturnValue({
      mutateAsync: createMutateAsync,
      isPending: false,
    });
    hooks.useRevokeProjectApiKey.mockReturnValue({
      mutateAsync: revokeMutateAsync,
      isPending: false,
    });
    hooks.useRotateProjectApiKey.mockReturnValue({
      mutateAsync: rotateMutateAsync,
      isPending: false,
    });
  });

  it("renders a capture-first setup page and empty state", () => {
    render(<ApiKeysPage />);

    expect(screen.getByRole("heading", { name: "Project key setup" })).toBeInTheDocument();
    expect(screen.getByText("Create key")).toBeInTheDocument();
    expect(screen.getByText("Run SDK/Gateway")).toBeInTheDocument();
    expect(screen.getByText("First trace")).toBeInTheDocument();
    expect(screen.getByText("Fixture validation")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Create project key" })).toBeInTheDocument();
    expect(screen.getByText("No model-provider setup is needed for capture.")).toBeInTheDocument();
    expect(screen.getByText("Use a project key first; advanced replay setup can come later when a protected workflow needs it.")).toBeInTheDocument();
    expect(screen.getByText("No project keys yet. Create one to start capturing calls.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open traces" }).getAttribute("href")).toBe("/trace");
    expect(screen.queryByRole("link", { name: "Provider settings" })).not.toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("traceRun"))).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("zroky.trace_run"))).toBeInTheDocument();
  });

  it("surfaces the protected agent setup intent with mandate and SDK copy actions", async () => {
    navigation.query = "intent=protect-agent&plan=pro&source=pricing";

    render(<ApiKeysPage />);

    expect(screen.getByRole("heading", { name: "First protected agent setup" })).toBeInTheDocument();
    expect(screen.getByText("Plan intent: Pro")).toBeInTheDocument();
    expect(screen.getByText("Source: Pricing")).toBeInTheDocument();
    expect(screen.getByText("5 starter mandates")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create project key" }).getAttribute("href")).toBe("#create-project-key");
    expect(screen.getByRole("tab", { name: "Refund / payment" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("refund-ops-agent")).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes('name: "issue_refund"'))).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "DevOps / release" }));

    expect(screen.getByText("release-ops-agent")).toBeInTheDocument();
    expect(screen.getByText("CI deployment and incident status")).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes('name: "deploy_change"'))).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy mandate" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(expect.stringContaining("release-ops-agent")));

    fireEvent.click(screen.getByRole("button", { name: "Copy SDK wrapper" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(expect.stringContaining('name: "deploy_change"')));
  });

  it("renders pilot handoff proof criteria and connector inputs after pilot signup", async () => {
    navigation.query = "intent=protect-agent&plan=pro&source=pilot";

    render(<ApiKeysPage />);

    expect(screen.getByText("Pilot handoff readiness")).toBeInTheDocument();
    expect(screen.getByText("Connect system of record")).toBeInTheDocument();
    expect(screen.getByText("Run connector preflight")).toBeInTheDocument();
    expect(screen.getByText("Run full proof command")).toBeInTheDocument();
    expect(screen.getByText("ledger/refund API base URL")).toBeInTheDocument();
    expect(screen.getByText("unsafe_action_stopped")).toBeInTheDocument();
    expect(screen.getByText("connector_configured")).toBeInTheDocument();
    expect(screen.getByText("connector_health_verified")).toBeInTheDocument();
    expect(screen.getByText("real_connector_ready")).toBeInTheDocument();
    expect(screen.getByText("saved_test_endpoint_used")).toBeInTheDocument();
    expect(screen.getByText("evidence_hash_visible")).toBeInTheDocument();
    expect(screen.getByText("evidence_json_exported")).toBeInTheDocument();
    expect(screen.getByText("not_verified_when_missing")).toBeInTheDocument();
    expect(screen.getByText("Packaged full proof command")).toBeInTheDocument();
    expect(screen.getByText("Packaged full proof runner:")).toBeInTheDocument();
    expect(screen.getByText("Refund and payment agents can use the packaged ledger/refund preflight and full proof runner.")).toBeInTheDocument();
    expect(screen.getByText(/--scenario refund/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Configure ledger connector" }).getAttribute("href")).toBe(
      "/settings/integrations#ledger-refund-connector"
    );

    fireEvent.click(screen.getByRole("button", { name: "Copy live smoke command" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(expect.stringContaining("--scenario refund")));

    fireEvent.click(screen.getByRole("tab", { name: "CRM / data" }));
    expect(screen.getByText("CRM/customer API base URL")).toBeInTheDocument();
    expect(screen.getByText("CRM and data agents can use the packaged customer-record preflight and full proof runner.")).toBeInTheDocument();
    expect(screen.getByText(/--scenario customer-record/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Configure CRM connector" }).getAttribute("href")).toBe(
      "/settings/integrations#customer-record-connector"
    );

    fireEvent.click(screen.getByRole("tab", { name: "Procurement / spend" }));
    expect(screen.getByText("ERP or purchase-order API")).toBeInTheDocument();
    expect(screen.getByText("Custom connector required before live smoke")).toBeInTheDocument();
    expect(screen.getByText("Custom connector required:")).toBeInTheDocument();
    expect(screen.getByText("This template has mandate and SDK capture coverage. Add a connector that reads ERP purchase order before calling the pilot verified.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open integrations" }).getAttribute("href")).toBe(
      "/settings/integrations"
    );
  });

  it("creates a project key with the expected payload and shows the one-time copy panel", async () => {
    createMutateAsync.mockResolvedValue(createdKey());

    render(<ApiKeysPage />);

    fireEvent.click(screen.getByRole("button", { name: "Create project key" }));

    await waitFor(() =>
      expect(createMutateAsync).toHaveBeenCalledWith({
        projectId: "proj_1",
        name: "Production capture key",
        expires_in_days: 90,
        scopes: ["project:member"],
      }),
    );
    expect(await screen.findByRole("heading", { name: "Copy this project key now." })).toBeInTheDocument();
    expect(screen.getByText("zk_live_created_secret")).toBeInTheDocument();
    expect(screen.getByText("proj_1")).toBeInTheDocument();
    expect(screen.getAllByText((content) => content.includes('export ZROKY_API_KEY="zk_live_created_secret"')).length).toBe(2);
    expect(screen.getAllByRole("link", { name: "Open traces" }).some((link) => link.getAttribute("href") === "/trace")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Copy key" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith("zk_live_created_secret"));

    fireEvent.click(screen.getByRole("button", { name: "Copy Node setup" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(expect.stringContaining("ZROKY_PROJECT_ID")));
  });

  it("rotates an active key and shows the replacement key panel", async () => {
    hooks.useListProjectApiKeys.mockReturnValue({
      data: [apiKey()],
      isLoading: false,
      error: null,
    });
    rotateMutateAsync.mockResolvedValue(createdKey({ api_key: "zk_live_rotated_secret", rotated_from_key_id: "key_1" }));

    render(<ApiKeysPage />);

    fireEvent.click(screen.getByRole("button", { name: "Rotate" }));
    expect(screen.getByRole("dialog", { name: "Rotate API key" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Rotate and show replacement" }));

    await waitFor(() => expect(rotateMutateAsync).toHaveBeenCalledWith({ projectId: "proj_1", keyId: "key_1" }));
    expect(await screen.findByText("zk_live_rotated_secret")).toBeInTheDocument();
  });

  it("keeps the revoke confirmation flow working", async () => {
    hooks.useListProjectApiKeys.mockReturnValue({
      data: [apiKey()],
      isLoading: false,
      error: null,
    });
    revokeMutateAsync.mockResolvedValue(apiKey({ revoked: true }));

    render(<ApiKeysPage />);

    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    expect(screen.getByRole("dialog", { name: "Revoke API key" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Yes, revoke key" }));

    await waitFor(() => expect(revokeMutateAsync).toHaveBeenCalledWith({ projectId: "proj_1", keyId: "key_1" }));
  });
});
