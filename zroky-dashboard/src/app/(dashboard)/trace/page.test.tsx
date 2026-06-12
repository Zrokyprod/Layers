import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CallListItem, TraceListItem, TraceListResponse } from "@/lib/types";

import TracePage from "./page";

const hooks = vi.hoisted(() => ({
  mutateReplay: vi.fn(),
  refetchCalls: vi.fn(),
  refetchTraces: vi.fn(),
  useCreateReplayRunFromCall: vi.fn(),
  useListCalls: vi.fn(),
  useRecentTraces: vi.fn(),
}));

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
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
  useRouter: () => ({ push: navigation.push }),
}));

vi.mock("@/lib/hooks", async () => {
  const actual = await vi.importActual<typeof import("@/lib/hooks")>("@/lib/hooks");
  return {
    ...actual,
    useCreateReplayRunFromCall: hooks.useCreateReplayRunFromCall,
    useListCalls: hooks.useListCalls,
    useRecentTraces: hooks.useRecentTraces,
  };
});

const now = "2026-05-29T10:00:00.000Z";

function trace(overrides: Partial<TraceListItem> = {}): TraceListItem {
  return {
    trace_id: "trace_refund",
    root_call_id: "call_refund",
    call_count: 7,
    agent_count: 1,
    agents: ["Refund Agent"],
    providers: ["openai"],
    started_at: now,
    last_seen_at: now,
    total_cost_usd: 0.46,
    has_failure: true,
    root_failure_category: "TOOL_FAILURE",
    ...overrides,
  };
}

function call(overrides: Partial<CallListItem> = {}): CallListItem {
  return {
    call_id: "call_refund",
    tenant_id: "tenant_1",
    status: "failed",
    provider: "openai",
    model: "gpt-4.1",
    agent_name: "Refund Agent",
    user_id: "user_1",
    call_type: "tool_call",
    total_tokens: 1200,
    cost_usd: 0.46,
    pricing_version: "demo",
    pricing_last_updated_at: now,
    pricing_age_days: 0,
    cost_confidence: "known",
    latency_ms: 2420,
    error_code: "TOOL_TIMEOUT",
    diagnoses: [],
    has_blast_radius: true,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

const traceItems = [
  trace(),
  trace({
    trace_id: "trace_checkout",
    root_call_id: "call_checkout",
    call_count: 3,
    agents: ["Checkout Agent"],
    providers: ["anthropic"],
    total_cost_usd: 0.12,
    has_failure: false,
    root_failure_category: null,
  }),
];

function mockTracePage({
  traces = traceItems,
  calls = [call(), call({ call_id: "call_checkout", status: "success", model: "claude-sonnet", agent_name: "Checkout Agent", call_type: "chat", latency_ms: 900, error_code: null })],
  traceError = null,
  callError = null,
  traceLoading = false,
}: {
  traces?: TraceListItem[];
  calls?: CallListItem[];
  traceError?: Error | null;
  callError?: Error | null;
  traceLoading?: boolean;
} = {}) {
  const response: TraceListResponse = {
    window_days: 7,
    total: traces.length,
    multi_agent_count: traces.filter((item) => item.agent_count > 1).length,
    failed_count: traces.filter((item) => item.has_failure).length,
    items: traces,
  };
  hooks.useRecentTraces.mockReturnValue({
    data: traceError || traceLoading ? undefined : response,
    error: traceError,
    isFetching: false,
    isLoading: traceLoading,
    refetch: hooks.refetchTraces,
  });
  hooks.useListCalls.mockReturnValue({
    data: callError ? undefined : { items: calls, total: calls.length, limit: 200, offset: 0 },
    error: callError,
    isFetching: false,
    isLoading: false,
    refetch: hooks.refetchCalls,
  });
  hooks.useCreateReplayRunFromCall.mockReturnValue({
    isPending: false,
    mutate: hooks.mutateReplay,
  });
}

describe("Traces list MVP", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hooks.refetchCalls.mockResolvedValue({});
    hooks.refetchTraces.mockResolvedValue({});
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    URL.createObjectURL = vi.fn(() => "blob:trace-export");
    URL.revokeObjectURL = vi.fn();
    HTMLAnchorElement.prototype.click = vi.fn();
    mockTracePage();
  });

  it("renders the evidence-browser header, KPIs, and filters as styled regions", async () => {
    const { container } = render(<TracePage />);

    expect(container.querySelector(".traces-mvp")).toBeInTheDocument();
    const title = await screen.findByRole("heading", { name: "Traces" });
    expect(title.closest(".trace-mvp-hero")).toBeInTheDocument();
    expect(screen.getByText("Captured agent inputs, tool steps, retrieval events, policy decisions, outcomes, and replay-ready evidence.")).toBeInTheDocument();
    const overview = screen.getByLabelText("Trace overview");
    expect(overview.classList.contains("trace-mvp-kpis")).toBe(true);
    expect(container.querySelectorAll(".trace-mvp-kpi")).toHaveLength(4);
    for (const label of ["Captured traces", "Failed calls", "Replay-ready", "Avg latency"]) {
      expect(within(overview).getByText(label)).toBeInTheDocument();
    }
    const filters = screen.getByLabelText("Trace filters");
    expect(filters.classList.contains("trace-mvp-filter-panel")).toBe(true);
    for (const label of ["Window", "Status", "Agent", "Call type", "Provider/model", "Latency", "Search"]) {
      expect(within(filters).getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: /Refresh/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Copy IDs/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Export JSON/ })).toBeInTheDocument();
    expect(within(filters).getAllByText("Replay-ready").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Trace evidence" }).closest(".trace-mvp-table-section")).toBeInTheDocument();
  });

  it("renders trace rows with failed status, cost, latency, and actions", async () => {
    render(<TracePage />);

    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Trace / Call",
      "Status",
      "Agent",
      "Type",
      "Model",
      "Cost",
      "Latency",
      "Created",
      "Action",
    ]);

    expect(await screen.findByText("trace_refund · 7 spans")).toBeInTheDocument();
    const row = screen.getByText("trace_refund · 7 spans").closest("tr");
    if (!row) throw new Error("Missing refund trace row");
    expect(within(row).getByText("Failed")).toBeInTheDocument();
    expect(within(row).getByText("tool_call")).toBeInTheDocument();
    expect(within(row).getByText("gpt-4.1")).toBeInTheDocument();
    expect(within(row).getByText("$0.46")).toBeInTheDocument();
    expect(within(row).getByText("2.42s")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "View trace" }).getAttribute("href")).toBe("/trace/trace_refund");
    expect(within(row).getByRole("link", { name: "Source call" }).getAttribute("href")).toBe("/calls/call_refund");
    fireEvent.click(within(row).getByRole("button", { name: "Copy ID" }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("trace_refund"));
    fireEvent.click(within(row).getByRole("button", { name: "Replay" }));
    expect(hooks.mutateReplay).toHaveBeenCalledWith({
      callId: "call_refund",
      payload: { replay_mode: "real_llm" },
    });
  });

  it("filters local trace rows by status", async () => {
    render(<TracePage />);

    await screen.findByText("trace_refund · 7 spans");
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "success" } });
    expect(screen.queryByText("trace_refund · 7 spans")).not.toBeInTheDocument();
    expect(screen.getByText("trace_checkout · 3 spans")).toBeInTheDocument();
  });

  it("uses the backend-safe trace limit and widens the window from the toolbar", async () => {
    render(<TracePage />);

    await screen.findByText("trace_refund · 7 spans");
    expect(hooks.useRecentTraces).toHaveBeenCalledWith(7, 100);
    fireEvent.change(screen.getByLabelText("Window"), { target: { value: "30" } });
    expect(hooks.useRecentTraces).toHaveBeenCalledWith(30, 100);
  });

  it("turns overview cards into live filters and supports clearing filters", async () => {
    render(<TracePage />);

    await screen.findByText("trace_refund · 7 spans");
    fireEvent.click(screen.getByRole("button", { name: /Failed calls/ }));
    expect(screen.getByText("trace_refund · 7 spans")).toBeInTheDocument();
    expect(screen.queryByText("trace_checkout · 3 spans")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Captured traces/ }));
    expect(screen.getByText("trace_checkout · 3 spans")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Avg latency/ }));
    expect(screen.getByText("trace_refund · 7 spans")).toBeInTheDocument();
    expect(screen.queryByText("trace_checkout · 3 spans")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByText("trace_checkout · 3 spans")).toBeInTheDocument();
  });

  it("refreshes, copies, and exports the visible trace set", async () => {
    render(<TracePage />);

    await screen.findByText("trace_refund · 7 spans");
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(hooks.refetchTraces).toHaveBeenCalledTimes(1));
    expect(hooks.refetchCalls).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status").textContent).toBe("Trace data refreshed.");

    fireEvent.click(screen.getByRole("button", { name: "Copy IDs" }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("trace_refund\ntrace_checkout"));

    fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:trace-export");
  });

  it("keeps rows visible when root-call enrichment fails", async () => {
    mockTracePage({ callError: new Error("GET /v1/calls failed") });
    render(<TracePage />);

    expect(await screen.findByText("trace_refund · 7 spans")).toBeInTheDocument();
    expect(screen.getByText("Call enrichment unavailable. Trace rows are still shown.")).toBeInTheDocument();
    const row = screen.getByText("trace_refund · 7 spans").closest("tr");
    if (!row) throw new Error("Missing refund trace row");
    expect(within(row).getByText("trace")).toBeInTheDocument();
    expect(within(row).getByText("openai")).toBeInTheDocument();
  });

  it("renders the SDK setup empty state", async () => {
    mockTracePage({ traces: [], calls: [] });
    render(<TracePage />);

    expect(await screen.findByText("No traces captured yet")).toBeInTheDocument();
    expect(screen.getByText("No traces captured yet").closest(".trace-mvp-table-section")).toBeInTheDocument();
    expect(screen.getByText(/Run one SDK or Gateway call with your project key/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to project key setup" }).getAttribute("href")).toBe("/settings/keys");

    fireEvent.click(screen.getByRole("button", { name: "Refresh traces" }));
    await waitFor(() => expect(hooks.refetchTraces).toHaveBeenCalledTimes(1));
    expect(hooks.refetchCalls).toHaveBeenCalledTimes(1);
  });

  it("keeps the loading state inside the styled trace evidence card", async () => {
    mockTracePage({ traces: [], calls: [], traceLoading: true });
    render(<TracePage />);

    const loading = await screen.findByText("Loading captured traces...");
    expect(loading.classList.contains("trace-mvp-empty")).toBe(true);
    expect(loading.closest(".trace-mvp-table-section")).toBeInTheDocument();
  });
});
