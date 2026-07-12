import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ToolCatalogPage from "./page";
import * as hooks from "@/lib/hooks";
import type { OwnerToolRegistryResponse } from "@/lib/owner-api";

vi.mock("@/lib/hooks", () => ({
  useOwnerToolRegistry: vi.fn(),
}));

const registry: OwnerToolRegistryResponse = {
  schema_version: "zroky.agent_tool_control.v1",
  project_id: "proj_live",
  agent_id: null,
  action_type: null,
  runtime_paths: [
    {
      id: "mcp_gateway",
      kind: "runtime_path",
      label: "MCP Gateway",
      description: "Inline MCP interception for protected agent tools.",
      category: "Agent runtime",
      phase: "phase1",
      implementation_status: "available",
      launch_tier: "p0",
      supported_action_types: ["refund"],
      recommended_for_action_types: ["refund"],
      requires_customer_credentials: false,
      dashboard_href: null,
      backend_capability: "mcp_interception",
      availability_notes: null,
    },
  ],
  verification_connectors: [
    {
      id: "okta_user_status",
      kind: "verification_connector",
      label: "Okta User Status",
      description: "Verifies identity lifecycle changes against Okta.",
      category: "Identity",
      phase: "phase1",
      implementation_status: "template",
      launch_tier: "p1",
      supported_action_types: ["user_deactivate"],
      recommended_for_action_types: ["user_deactivate"],
      requires_customer_credentials: true,
      dashboard_href: null,
      backend_capability: "okta_identity_status",
      availability_notes: "Customer-hosted verifier required.",
    },
  ],
  native_tool_families: [],
  recommended: {
    action_types: [],
    runtime_path_ids: ["mcp_gateway"],
    verification_connector_ids: ["okta_user_status"],
    native_tool_family_ids: [],
    next_steps: ["Run one live preflight."],
  },
};

function mockRegistry(data: OwnerToolRegistryResponse | null, opts: { loading?: boolean; error?: Error | null } = {}) {
  vi.mocked(hooks.useOwnerToolRegistry).mockReturnValue({
    data,
    error: opts.error ?? null,
    isLoading: opts.loading ?? false,
  } as unknown as ReturnType<typeof hooks.useOwnerToolRegistry>);
}

describe("ToolCatalogPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the live backend registry instead of the old static catalog", () => {
    mockRegistry(registry);

    render(<ToolCatalogPage />);

    expect(screen.getByText("Connector Catalog")).toBeInTheDocument();
    expect(screen.getByText("MCP Gateway")).toBeInTheDocument();
    expect(screen.getByText("Okta User Status")).toBeInTheDocument();
    expect(screen.getByText("Backend capability: okta_identity_status")).toBeInTheDocument();
    expect(screen.queryByText("Stripe Refund")).toBe(null);
    expect(screen.queryByText("Generic REST")).toBe(null);
  });

  it("does not show static connector rows while the live registry is loading", () => {
    mockRegistry(null, { loading: true });

    render(<ToolCatalogPage />);

    expect(screen.getByText("Loading live connector registry...")).toBeInTheDocument();
    expect(screen.queryByText("Stripe Refund")).toBe(null);
    expect(screen.queryByText("Generic REST")).toBe(null);
  });

  it("does not show a static fallback when the live registry fails", () => {
    mockRegistry(null, { error: new Error("HTTP 500") });

    render(<ToolCatalogPage />);

    expect(screen.getByText("Live connector registry unavailable. Static connector data is intentionally hidden.")).toBeInTheDocument();
    expect(screen.queryByText("Stripe Refund")).toBe(null);
    expect(screen.queryByText("Generic REST")).toBe(null);
  });
});
