import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EvidencePage from "./page";
import type { OutcomeGraphCoverageSummary, OutcomeGraphRow } from "@/lib/api";

const api = vi.hoisted(() => ({
  fetchOutcomeGraphCoverage: vi.fn(),
  fetchOutcomeGraphs: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode; [key: string]: unknown }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, ...api };
});

function coverage(overrides: Partial<OutcomeGraphCoverageSummary> = {}): OutcomeGraphCoverageSummary {
  return {
    counts: {
      conflicted: 1,
      duplicate: 1,
      forbidden: 1,
      missing: 2,
      pending: 3,
      stale: 1,
      unknown: 1,
      verified: 8,
      wrong: 4,
    },
    coverage_percent: 36.36,
    total: 22,
    ...overrides,
  };
}

function graph(overrides: Partial<OutcomeGraphRow> = {}): OutcomeGraphRow {
  return {
    id: "graph_1",
    project_id: "proj_1",
    environment: "prod",
    intent_id: "intent_1234567890",
    graph_digest: "sha256:graph_1",
    graph: {
      workflow_key: "refund_workflow",
      expected_effects: [
        { effect_key: "refund_created", object_type: "refund", predicate: { field: "status", equals: "succeeded" } },
      ],
      actual_effects: [
        {
          effect_key: "refund_created",
          observed: false,
          matched: false,
          stale: false,
          conflicted: false,
          observation_digest: "obs_digest_1",
          source_binding: null,
        },
      ],
    },
    verification_status: "failed",
    classification: "missing",
    reason_code: null,
    last_checked_at: "2026-07-29T06:30:00Z",
    next_check_at: null,
    verified_at: null,
    created_at: "2026-07-29T06:29:00Z",
    ...overrides,
  };
}

function renderEvidencePage() {
  const client = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <EvidencePage />
    </QueryClientProvider>,
  );
}

describe("EvidencePage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    window.history.pushState({}, "", "/evidence");
    api.fetchOutcomeGraphCoverage.mockResolvedValue(coverage());
    api.fetchOutcomeGraphs.mockResolvedValue({ items: [graph()] });
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:evidence") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  it("renders caught count as the hero number, not coverage percent", async () => {
    renderEvidencePage();

    expect(await screen.findByRole("heading", { name: "8 actions claimed but not proven" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /36\.36%/ })).not.toBeInTheDocument();
    expect(screen.getByText("36.36% verified in system of record")).toBeInTheDocument();
  });

  it("passes classification when a filter chip maps to an API filter", async () => {
    renderEvidencePage();
    await screen.findByRole("heading", { name: "8 actions claimed but not proven" });

    fireEvent.click(screen.getByRole("button", { name: "Proven" }));

    await waitFor(() => expect(api.fetchOutcomeGraphs).toHaveBeenLastCalledWith(
      expect.objectContaining({ classification: "verified", limit: 100 }),
      expect.any(AbortSignal),
    ));
  });

  it("renders integrations CTA for a no_connector drill-down", async () => {
    api.fetchOutcomeGraphs.mockResolvedValue({
      items: [
        graph({
          classification: "unknown",
          reason_code: "no_connector",
          verification_status: "inconclusive",
        }),
      ],
    });

    renderEvidencePage();

    await screen.findByText("Is system ka connector configured nahi hai");
    const panel = screen.getByLabelText("Focused proof panel");
    expect(within(panel).getByText("Is system ka connector configured nahi hai")).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: "Open integrations" }).getAttribute("href")).toBe("/integrations");
    expect(within(panel).getByText("obs_digest_1")).toBeInTheDocument();
  });

  it("shows setup empty state when coverage total is zero", async () => {
    api.fetchOutcomeGraphCoverage.mockResolvedValue(coverage({ total: 0, coverage_percent: 0 }));
    api.fetchOutcomeGraphs.mockResolvedValue({ items: [] });

    renderEvidencePage();

    expect(await screen.findByRole("heading", { name: "No outcome graphs yet" })).toBeInTheDocument();
    expect(screen.getByText("Declare your first intent.")).toBeInTheDocument();
    expect(screen.getByText("Outcome graphs appear here once an agent run is verified against your systems of record.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Read setup docs" }).getAttribute("href")).toBe("/docs");
  });
});
