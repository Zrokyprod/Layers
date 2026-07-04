import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentProfileResponse } from "@/lib/api";
import type { ApiKeyCreateResponse, ApiKeyResponse, ProjectResponse } from "@/lib/types";
import AgentControlSetupPage from "./page";

const api = vi.hoisted(() => ({
  createProjectApiKey: vi.fn(),
  createAgentProfile: vi.fn(),
  enforceAgentProfile: vi.fn(),
  getProjectSettings: vi.fn(),
  listActionIntents: vi.fn(),
  listProjectApiKeys: vi.fn(),
}));

const navigation = vi.hoisted(() => ({ query: "" }));

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

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    createProjectApiKey: api.createProjectApiKey,
    createAgentProfile: api.createAgentProfile,
    enforceAgentProfile: api.enforceAgentProfile,
    getProjectSettings: api.getProjectSettings,
    listActionIntents: api.listActionIntents,
    listProjectApiKeys: api.listProjectApiKeys,
  };
});

function profile(overrides: Partial<AgentProfileResponse> = {}): AgentProfileResponse {
  return { id: "agent_1", display_name: "Ops Agent", ...overrides } as AgentProfileResponse;
}

function project(overrides: Partial<ProjectResponse> = {}): ProjectResponse {
  return {
    project_id: "proj_1",
    name: "My Project",
    owner_ref: "acct_1",
    is_active: true,
    created_at: "2026-07-04T00:00:00Z",
    updated_at: "2026-07-04T00:00:00Z",
    ...overrides,
  };
}

function apiKey(overrides: Partial<ApiKeyResponse> = {}): ApiKeyResponse {
  return {
    key_id: "key_1",
    project_id: "proj_1",
    name: "Protected agent runtime key",
    key_prefix: "zk_live_demo",
    scopes: ["project:member"],
    revoked: false,
    expired: false,
    expires_at: null,
    rotated_from_key_id: null,
    last_used_at: null,
    created_at: "2026-07-04T00:00:00Z",
    ...overrides,
  };
}

function createdApiKey(overrides: Partial<ApiKeyCreateResponse> = {}): ApiKeyCreateResponse {
  return {
    ...apiKey(),
    api_key: "zk_live_created_secret",
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AgentControlSetupPage />
    </QueryClientProvider>,
  );
}

describe("Protected agent setup (minimal)", () => {
  beforeEach(() => {
    navigation.query = "";
    api.createProjectApiKey.mockReset().mockResolvedValue(createdApiKey());
    api.getProjectSettings.mockReset().mockResolvedValue(project());
    api.listProjectApiKeys.mockReset().mockResolvedValue([apiKey()]);
    api.createAgentProfile.mockReset().mockResolvedValue(profile());
    api.enforceAgentProfile.mockReset().mockResolvedValue(profile());
    api.listActionIntents.mockReset().mockResolvedValue({ items: [] });
  });

  it("shows the pending capture path and defers advanced next steps", async () => {
    renderPage();

    expect(screen.getByText(/Configure policies, verifiers, and approvals later from real captured actions/i)).toBeInTheDocument();
    expect(await screen.findByText("Runtime key ready")).toBeInTheDocument();
    expect(screen.getByLabelText("Live capture status").textContent).toContain("SDK ready");
    expect(screen.getByLabelText("Live capture status").textContent).toContain("waiting for SDK run");
    expect(screen.getByText("Available after the first receipt")).toBeInTheDocument();
    const loop = screen.getByLabelText("Zroky control loop");
    for (const step of ["Propose", "Policy", "Approval", "Execution", "Verification", "Receipt"]) {
      expect(loop.textContent).toContain(step);
    }
    expect(screen.getByRole("link", { name: "Set a policy" }).getAttribute("aria-disabled")).toBe("true");
  });

  it("creates and enforces an agent from a minimal form", async () => {
    renderPage();
    await screen.findByText("Runtime key ready");

    fireEvent.change(screen.getByLabelText("Agent name"), { target: { value: "Refund Agent" } });
    fireEvent.click(screen.getByRole("button", { name: /Create & enable protection/i }));

    await waitFor(() => expect(api.createAgentProfile).toHaveBeenCalledTimes(1));
    expect(api.createAgentProfile.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        allowed_action_types: ["internal_api_mutation"],
        display_name: "Refund Agent",
        metadata: {
          runner_verification: {
            credential_ref: "customer-runner-secret://zroky/project-key/zk_live_demo",
            runner_mode: "customer_hosted",
          },
        },
        runtime_path: "sdk",
        tool_names: ["agent.protected_action"],
      }),
    );
    await waitFor(() => expect(api.enforceAgentProfile).toHaveBeenCalledWith("agent_1"));
    expect(await screen.findByText(/is protected with the safe default policy/i)).toBeInTheDocument();
  });

  it("creates a runtime project key inline when none exists", async () => {
    api.listProjectApiKeys.mockResolvedValue([]);
    renderPage();

    const createKeyButton = await screen.findByRole("button", { name: "Create project key" });
    await waitFor(() => expect((createKeyButton as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(createKeyButton);

    await waitFor(() => expect(api.createProjectApiKey).toHaveBeenCalledWith("proj_1", {
      name: "Protected agent runtime key",
      expires_in_days: 90,
      scopes: ["project:member"],
    }));
    expect(await screen.findByText("zk_live_created_secret")).toBeInTheDocument();
    expect(screen.getByText(/pip install zroky/i)).toBeInTheDocument();
  });

  it("prefills the agent name from the query param", () => {
    navigation.query = "agentName=Shadow%20Agent";
    renderPage();
    expect((screen.getByLabelText("Agent name") as HTMLInputElement).value).toBe("Shadow Agent");
  });

  it("requires an agent name before creating", async () => {
    renderPage();
    await screen.findByText("Runtime key ready");
    fireEvent.click(screen.getByRole("button", { name: /Create & enable protection/i }));
    expect(await screen.findByText(/Give the agent a name/i)).toBeInTheDocument();
    expect(api.createAgentProfile).not.toHaveBeenCalled();
  });
});
