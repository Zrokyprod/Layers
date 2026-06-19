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
    expect(screen.getByText("Provider keys are not needed for capture.")).toBeInTheDocument();
    expect(screen.getByText("Add them later only when verified replay needs live model calls.")).toBeInTheDocument();
    expect(screen.getByText("No project keys yet. Create one to start capturing calls.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open traces" }).getAttribute("href")).toBe("/trace");
    expect(screen.getByRole("link", { name: "Provider settings" }).getAttribute("href")).toBe("/settings/providers");
    expect(screen.getByText((content) => content.includes("traceRun"))).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("zroky.trace_run"))).toBeInTheDocument();
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
