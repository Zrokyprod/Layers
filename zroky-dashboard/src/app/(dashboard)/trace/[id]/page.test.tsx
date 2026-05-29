import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CallDetailResponse, TraceListItem, TraceTreeNode } from "@/lib/types";

import TraceDetailPage from "./page";

const hooks = vi.hoisted(() => ({
  mutateReplay: vi.fn(),
  useCallDetail: vi.fn(),
  useCallTraceTree: vi.fn(),
  useCreateReplayRunFromCall: vi.fn(),
  useRecentTraces: vi.fn(),
  useTraceById: vi.fn(),
}));

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  traceId: "trace_refund",
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
  useParams: () => ({ id: navigation.traceId }),
  useRouter: () => ({ push: navigation.push }),
}));

vi.mock("@/lib/hooks", async () => {
  const actual = await vi.importActual<typeof import("@/lib/hooks")>("@/lib/hooks");
  return {
    ...actual,
    useCallDetail: hooks.useCallDetail,
    useCallTraceTree: hooks.useCallTraceTree,
    useCreateReplayRunFromCall: hooks.useCreateReplayRunFromCall,
    useRecentTraces: hooks.useRecentTraces,
    useTraceById: hooks.useTraceById,
  };
});

const now = "2026-05-29T10:00:00.000Z";

function trace(overrides: Partial<TraceListItem> = {}): TraceListItem {
  return {
    trace_id: "trace_refund",
    root_call_id: "call_refund",
    call_count: 2,
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

function node(overrides: Partial<TraceTreeNode> = {}): TraceTreeNode {
  return {
    call_id: "call_refund",
    parent_call_id: null,
    agent_name: "Refund Agent",
    provider: "openai",
    model: "gpt-4.1",
    cost_confidence: "known",
    status: "failed",
    wasted_cost_usd: 0.46,
    latency_ms: 2420,
    error_code: null,
    created_at: now,
    children: [
      {
        call_id: "call_tool",
        parent_call_id: "call_refund",
        agent_name: "get_refund_status",
        provider: "tool",
        model: null,
        cost_confidence: "known",
        status: "timeout",
        wasted_cost_usd: 0,
        latency_ms: 320,
        error_code: "TOOL_TIMEOUT",
        created_at: now,
        children: [],
      },
    ],
    ...overrides,
  };
}

function callDetail(): CallDetailResponse {
  return {
    call: {
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
    },
    payload: {
      input: "I want a refund for order #1234",
      output: "Payment failed with timeout.",
      tool_calls: [{ name: "get_refund_status", status: "timeout", error: "Provider timeout" }],
      retrieval_context: [{ title: "refund policy" }],
    },
    cost_audit: null,
    diagnosis_result: {
      diagnoses: [
        {
          failure_code: "PAYMENT_TIMEOUT",
          root_cause: "Payment provider timed out before receipt creation.",
          confidence: "high",
        },
      ],
    },
    feedback_summary: { helpful_count: 0, not_helpful_count: 0 },
  };
}

function mockTraceDetail({
  loadedTrace = trace(),
  root = node(),
  detailData = callDetail(),
}: {
  loadedTrace?: TraceListItem;
  root?: TraceTreeNode;
  detailData?: CallDetailResponse | null;
} = {}) {
  hooks.useRecentTraces.mockReturnValue({
    data: { window_days: 30, total: 1, multi_agent_count: 0, failed_count: 1, items: [loadedTrace] },
    error: null,
    isLoading: false,
  });
  hooks.useTraceById.mockReturnValue({ data: loadedTrace, error: null, isLoading: false });
  hooks.useCallTraceTree.mockReturnValue({
    data: {
      call_id: loadedTrace.root_call_id,
      trace_id: loadedTrace.trace_id,
      root_failure: { category: "TOOL_FAILURE", root_cause: "Tool timed out." },
      total_downstream_calls: 1,
      total_wasted_cost_usd: loadedTrace.total_cost_usd,
      root_node: root,
    },
    error: null,
    isLoading: false,
  });
  hooks.useCallDetail.mockReturnValue({ data: detailData, error: null, isLoading: false });
  hooks.useCreateReplayRunFromCall.mockReturnValue({
    isPending: false,
    mutate: hooks.mutateReplay,
  });
}

describe("Trace detail MVP", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.traceId = "trace_refund";
    mockTraceDetail();
  });

  it("renders the detail header and metadata cards", async () => {
    render(<TraceDetailPage />);

    expect((await screen.findByRole("link", { name: "Back to Traces" })).getAttribute("href")).toBe("/trace");
    const title = screen.getByRole("heading", { name: "Refund Agent trace" });
    expect(title.closest(".trace-detail-hero")).toBeInTheDocument();
    const hero = title.closest(".trace-detail-hero");
    if (!hero) throw new Error("Missing trace detail hero");
    expect(within(hero).getByText("Failed")).toBeInTheDocument();
    expect(within(hero).getByText("Replay ready")).toBeInTheDocument();
    expect(within(hero).getByText("TOOL_FAILURE")).toBeInTheDocument();
    expect(screen.getByText("Failed · Refund Agent · openai")).toBeInTheDocument();
    const metadata = screen.getByLabelText("Trace metadata");
    expect(metadata.classList.contains("trace-detail-metrics")).toBe(true);
    expect(metadata.querySelectorAll(".trace-detail-metric")).toHaveLength(5);
    for (const label of ["Latency", "Cost", "Model", "Spans / steps", "Created"]) {
      expect(within(metadata).getByText(label)).toBeInTheDocument();
    }
    expect(within(metadata).getByText("2.42s")).toBeInTheDocument();
    expect(within(metadata).getByText("$0.46")).toBeInTheDocument();
    expect(within(metadata).getByText("gpt-4.1")).toBeInTheDocument();
  });

  it("renders the two-column investigation layout and action panel", async () => {
    render(<TraceDetailPage />);

    const layout = await screen.findByLabelText("Trace investigation");
    expect(layout.classList.contains("trace-detail-layout")).toBe(true);
    const panel = screen.getByLabelText("Trace action panel");
    expect(panel.classList.contains("trace-detail-panel")).toBe(true);
    expect(within(panel).getByText("Replay readiness")).toBeInTheDocument();
    expect(within(panel).getByText("Related evidence")).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: "View source call" }).getAttribute("href")).toBe("/calls/call_refund");
    expect(within(panel).getByRole("button", { name: "Run replay" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Copy trace ID" })).toBeInTheDocument();
    expect(within(panel).getByText("Golden eligibility")).toBeInTheDocument();
  });

  it("renders timeline steps, input/output, and failed tool behavior", async () => {
    render(<TraceDetailPage />);

    expect(await screen.findByRole("heading", { name: "Trace timeline" })).toBeInTheDocument();
    expect(screen.getAllByText("Root call").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Tool or agent step: TOOL_TIMEOUT")).toBeInTheDocument();
    const failedStep = screen.getByText("Tool or agent step: TOOL_TIMEOUT").closest(".trace-detail-step");
    if (!failedStep) throw new Error("Missing failed timeline step");
    expect(failedStep.classList.contains("is-failed")).toBe(true);
    expect(within(failedStep).getByText("Tool call")).toBeInTheDocument();
    expect(screen.getByText("I want a refund for order #1234")).toBeInTheDocument();
    expect(screen.getByText("Payment failed with timeout.")).toBeInTheDocument();
    const toolSection = screen.getByRole("heading", { name: "Tool behavior" }).closest("article");
    if (!toolSection) throw new Error("Missing tool behavior section");
    expect(within(toolSection).getByText("get_refund_status")).toBeInTheDocument();
    expect(within(toolSection).getByText("Provider timeout")).toBeInTheDocument();
  });

  it("renders retrieval, memory fallback, and diagnosis result", async () => {
    render(<TraceDetailPage />);

    expect(await screen.findByText("refund policy")).toBeInTheDocument();
    expect(screen.getByText("No memory events captured.")).toBeInTheDocument();
    expect(screen.getByText("PAYMENT_TIMEOUT")).toBeInTheDocument();
    expect(screen.getByText("Payment provider timed out before receipt creation.")).toBeInTheDocument();
  });

  it("renders compact fallbacks when captured evidence is missing", async () => {
    mockTraceDetail({
      loadedTrace: trace({ has_failure: false, root_failure_category: null, total_cost_usd: 0 }),
      root: node({ status: "success", wasted_cost_usd: 0, latency_ms: null, children: [] }),
      detailData: { ...callDetail(), payload: {}, diagnosis_result: null },
    });
    render(<TraceDetailPage />);

    expect(await screen.findByText("No input captured.")).toBeInTheDocument();
    expect(screen.getByText("No output captured.")).toBeInTheDocument();
    expect(screen.getByText("No tool calls captured.")).toBeInTheDocument();
    expect(screen.getByText("No retrieval context captured.")).toBeInTheDocument();
    expect(screen.getByText("No memory events captured.")).toBeInTheDocument();
    expect(screen.getByText("No diagnosis generated yet.")).toBeInTheDocument();
  });

  it("keeps raw JSON collapsed and never creates a Golden from raw trace", async () => {
    render(<TraceDetailPage />);

    await screen.findByRole("heading", { name: "Trace timeline" });
    const summary = screen.getByText("View raw payload JSON");
    const details = summary.closest("details");
    expect(details?.hasAttribute("open")).toBe(false);
    expect(screen.getByText("Run trusted replay before creating a Golden.")).toBeInTheDocument();
    expect(screen.queryByText("Create Golden")).not.toBeInTheDocument();
  });

  it("runs replay from the root call when eligible", async () => {
    render(<TraceDetailPage />);

    const button = await screen.findByRole("button", { name: "Run replay" });
    fireEvent.click(button);
    expect(hooks.mutateReplay).toHaveBeenCalledWith({
      callId: "call_refund",
      payload: { replay_mode: "real_llm" },
    });
  });
});
