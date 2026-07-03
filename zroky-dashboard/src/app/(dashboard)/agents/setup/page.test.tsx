import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentProfileResponse } from "@/lib/api";
import AgentControlSetupPage from "./page";

const api = vi.hoisted(() => ({
  createAgentProfile: vi.fn(),
  enforceAgentProfile: vi.fn(),
  listActionIntents: vi.fn(),
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
    createAgentProfile: api.createAgentProfile,
    enforceAgentProfile: api.enforceAgentProfile,
    listActionIntents: api.listActionIntents,
  };
});

function profile(overrides: Partial<AgentProfileResponse> = {}): AgentProfileResponse {
  return { id: "agent_1", display_name: "Ops Agent", ...overrides } as AgentProfileResponse;
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
    api.createAgentProfile.mockReset().mockResolvedValue(profile());
    api.enforceAgentProfile.mockReset().mockResolvedValue(profile());
    api.listActionIntents.mockReset().mockResolvedValue({ items: [] });
  });

  it("creates and enforces an agent from a minimal form", async () => {
    renderPage();

    fireEvent.change(screen.getByLabelText("Agent name"), { target: { value: "Refund Agent" } });
    fireEvent.click(screen.getByRole("button", { name: /Create & enable protection/i }));

    await waitFor(() => expect(api.createAgentProfile).toHaveBeenCalledTimes(1));
    expect(api.createAgentProfile.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({ display_name: "Refund Agent", runtime_path: "sdk" }),
    );
    await waitFor(() => expect(api.enforceAgentProfile).toHaveBeenCalledWith("agent_1"));
    expect(await screen.findByText(/is protected with the safe default policy/i)).toBeInTheDocument();
  });

  it("prefills the agent name from the query param", () => {
    navigation.query = "agentName=Shadow%20Agent";
    renderPage();
    expect((screen.getByLabelText("Agent name") as HTMLInputElement).value).toBe("Shadow Agent");
  });

  it("requires an agent name before creating", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Create & enable protection/i }));
    expect(await screen.findByText(/Give the agent a name/i)).toBeInTheDocument();
    expect(api.createAgentProfile).not.toHaveBeenCalled();
  });
});
