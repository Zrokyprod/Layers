import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EvidencePage from "./page";
import type { OutcomeGraphCoverageSummary, OutcomeGraphListResponse, OutcomeGraphRow } from "@/lib/api";

const api = vi.hoisted(() => ({
  fetchOutcomeGraphCoverage: vi.fn(),
  fetchOutcomeGraphEvidenceExport: vi.fn(),
  fetchOutcomeGraphs: vi.fn(),
}));
const navigation = vi.hoisted(() => ({ searchParams: new URLSearchParams() }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => navigation.searchParams,
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

function graphPage(
  items: OutcomeGraphRow[] = [graph()],
  overrides: Partial<Omit<OutcomeGraphListResponse, "items">> = {},
): OutcomeGraphListResponse {
  return { items, total: items.length, limit: 100, offset: 0, ...overrides };
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
    navigation.searchParams = new URLSearchParams();
    window.history.pushState({}, "", "/evidence");
    api.fetchOutcomeGraphCoverage.mockResolvedValue(coverage());
    api.fetchOutcomeGraphEvidenceExport.mockResolvedValue({
      attestation: { payload: "e30=", payloadType: "application/vnd.in-toto+json", signatures: [{ keyid: "dev", sig: "sig" }] },
      public_key: { algorithm: "ed25519", key_id: "dev", public_key: "pub", public_key_encoding: "base64-raw-ed25519" },
      summary: { classification: "missing" },
      verify_instructions: "python -m zroky.verify_attestation zroky-evidence-graph_1.json",
    });
    api.fetchOutcomeGraphs.mockResolvedValue(graphPage());
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

  it("does not invent zero coverage while proof data is loading", () => {
    api.fetchOutcomeGraphCoverage.mockReturnValue(new Promise(() => undefined));
    api.fetchOutcomeGraphs.mockReturnValue(new Promise(() => undefined));

    renderEvidencePage();

    expect(screen.getByRole("heading", { name: "Loading proof ledger" })).toBeInTheDocument();
    expect(screen.getByText("Reading coverage")).toBeInTheDocument();
    expect(screen.getByText("Loading", { selector: ".dashboard-metric-card strong" })).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    expect(screen.queryByText("No outcome graphs yet")).not.toBeInTheDocument();
  });

  it("shows unavailable proof state and retries after a coverage error", async () => {
    api.fetchOutcomeGraphCoverage.mockRejectedValue(new Error("coverage unavailable"));
    api.fetchOutcomeGraphs.mockRejectedValue(new Error("ledger unavailable"));

    renderEvidencePage();

    expect(await screen.findByRole("heading", { name: "Proof ledger unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Coverage unavailable")).toBeInTheDocument();
    expect(screen.getByText("Unavailable", { selector: ".dashboard-metric-card strong" })).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Retry loading" }));
    await waitFor(() => expect(api.fetchOutcomeGraphCoverage).toHaveBeenCalledTimes(2));
    expect(api.fetchOutcomeGraphs).toHaveBeenCalledTimes(2);
  });

  it("uses singular copy when exactly one action is caught", async () => {
    api.fetchOutcomeGraphCoverage.mockResolvedValue(coverage({
      counts: {
        conflicted: 0,
        duplicate: 0,
        forbidden: 0,
        missing: 1,
        pending: 0,
        stale: 0,
        unknown: 0,
        verified: 2,
        wrong: 0,
      },
      coverage_percent: 66.67,
      total: 3,
    }));

    renderEvidencePage();

    expect(await screen.findByRole("heading", { name: "1 action claimed but not proven" })).toBeInTheDocument();
  });

  it("passes classification when a filter chip maps to an API filter", async () => {
    renderEvidencePage();
    await screen.findByRole("heading", { name: "8 actions claimed but not proven" });

    fireEvent.click(screen.getByRole("button", { name: "Proven" }));

    await waitFor(() => expect(api.fetchOutcomeGraphs).toHaveBeenLastCalledWith(
      expect.objectContaining({ classification: ["verified"], limit: 100, offset: 0 }),
      expect.any(AbortSignal),
    ));
  });

  it("applies the hero filter without leaving stale local state", async () => {
    api.fetchOutcomeGraphCoverage.mockResolvedValue(coverage({
      counts: {
        conflicted: 0,
        duplicate: 0,
        forbidden: 0,
        missing: 0,
        pending: 0,
        stale: 0,
        unknown: 0,
        verified: 2,
        wrong: 0,
      },
      coverage_percent: 100,
      total: 2,
    }));
    renderEvidencePage();

    fireEvent.click(await screen.findByRole("link", { name: "Review proven" }));

    await waitFor(() => expect(api.fetchOutcomeGraphs).toHaveBeenLastCalledWith(
      expect.objectContaining({ classification: ["verified"], limit: 100, offset: 0 }),
      expect.any(AbortSignal),
    ));
    expect(screen.getByRole("button", { name: "Proven" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("honors a filter supplied by client-side route state", async () => {
    navigation.searchParams = new URLSearchParams("filter=caught");
    window.history.replaceState({}, "", "/home");

    renderEvidencePage();

    await waitFor(() => expect(api.fetchOutcomeGraphs).toHaveBeenCalledWith(
      expect.objectContaining({
        classification: ["wrong", "missing", "forbidden", "duplicate"],
        limit: 100,
        offset: 0,
      }),
      expect.any(AbortSignal),
    ));
    expect(screen.getByRole("button", { name: "Caught" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("searchbox", { name: "Search evidence" })).toBeInTheDocument();
  });

  it("loads a compound caught filter with one indexed request", async () => {
    api.fetchOutcomeGraphs.mockImplementation(async ({ classification }) => {
      const values = Array.isArray(classification) ? classification : [];
      return graphPage(
        values.map((value) => graph({ classification: value, id: `graph_${value}` })),
        { total: values.length > 0 ? 8 : 22 },
      );
    });
    renderEvidencePage();
    await screen.findByRole("heading", { name: "8 actions claimed but not proven" });

    fireEvent.click(screen.getByRole("button", { name: "Caught" }));

    await waitFor(() => expect(api.fetchOutcomeGraphs).toHaveBeenLastCalledWith(
      expect.objectContaining({
        classification: ["wrong", "missing", "forbidden", "duplicate"],
        limit: 100,
        offset: 0,
      }),
      expect.any(AbortSignal),
    ));
    expect(await screen.findByText("4 of 8 shown")).toBeInTheDocument();
  });

  it("renders every classification with honest badge semantics", async () => {
    const cases = [
      ["verified", "success"],
      ["wrong", "danger"],
      ["missing", "danger"],
      ["forbidden", "danger"],
      ["duplicate", "danger"],
      ["pending", "warning"],
      ["stale", "warning"],
      ["conflicted", "warning"],
      ["unknown", "warning"],
    ] as const;
    api.fetchOutcomeGraphs.mockResolvedValue(graphPage(cases.map(([classification]) => graph({
      classification,
      id: `graph_${classification}`,
      graph: { workflow_key: `${classification}_workflow` },
    }))));

    renderEvidencePage();

    const ledger = screen.getByLabelText("Evidence ledger");
    await within(ledger).findByText("Verified", { selector: ".status-pill" });
    for (const [classification, tone] of cases) {
      const label = classification[0].toUpperCase() + classification.slice(1);
      expect(within(ledger).getByText(label, { selector: ".status-pill" }).getAttribute("data-tone")).toBe(tone);
    }
  });

  it("loads older evidence pages on demand", async () => {
    api.fetchOutcomeGraphs.mockImplementation(async ({ offset = 0 }) => graphPage(
      [graph({ id: `graph_${offset}`, graph: { workflow_key: offset === 0 ? "first_workflow" : "older_workflow" } })],
      { total: 2, offset },
    ));
    renderEvidencePage();

    fireEvent.click(await screen.findByRole("button", { name: "Load more" }));

    await waitFor(() => expect(api.fetchOutcomeGraphs).toHaveBeenCalledWith(
      expect.objectContaining({ offset: 1 }),
      expect.any(AbortSignal),
    ));
    expect(await screen.findByText("older_workflow")).toBeInTheDocument();
    expect(screen.getByText("2 shown")).toBeInTheDocument();
  });

  it("loads additional pages to resolve a graph deep link", async () => {
    navigation.searchParams = new URLSearchParams("graph_id=graph_older");
    window.history.replaceState({}, "", "/evidence?graph_id=graph_older");
    const firstPage = Array.from({ length: 100 }, (_, index) => graph({
      id: `graph_${index}`,
      graph: { workflow_key: `workflow_${index}` },
    }));
    api.fetchOutcomeGraphs.mockImplementation(async ({ offset = 0 }) => offset === 0
      ? graphPage(firstPage, { total: 101, offset })
      : graphPage([graph({ id: "graph_older", graph: { workflow_key: "older_workflow" } })], { total: 101, offset }));

    renderEvidencePage();

    await waitFor(() => expect(api.fetchOutcomeGraphs).toHaveBeenCalledWith(
      expect.objectContaining({ offset: 100 }),
      expect.any(AbortSignal),
    ));
    const panel = screen.getByLabelText("Focused proof panel");
    expect(await within(panel).findByRole("heading", { name: "older_workflow" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inspect older_workflow proof" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("renders integrations CTA for a no_connector drill-down", async () => {
    api.fetchOutcomeGraphs.mockResolvedValue(graphPage([
        graph({
          classification: "unknown",
          reason_code: "no_connector",
          verification_status: "inconclusive",
        }),
      ]));

    renderEvidencePage();

    await screen.findByText("This system does not have a configured connector");
    const panel = screen.getByLabelText("Focused proof panel");
    expect(within(panel).getByText("This system does not have a configured connector")).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: "Open integrations" }).getAttribute("href")).toBe("/integrations");
    expect(within(panel).getByText("obs_digest_1")).toBeInTheDocument();
    const effect = within(panel).getByLabelText("Effect refund_created");
    expect(within(effect).getByText("Expected")).toBeInTheDocument();
    expect(within(effect).getAllByText("Observed")).toHaveLength(2);
  });

  it.each([
    {
      href: "/operations?view=unverifiable",
      link: "Open runner status",
      message: "The private runner is offline",
      reason: "runner_offline",
    },
    {
      href: null,
      link: null,
      message: "No matching record was found in the system of record",
      reason: "no_sor_trace",
    },
    {
      href: null,
      link: null,
      message: "The system was unreachable; Zroky will retry",
      reason: "sor_unreachable",
    },
  ])("renders the $reason finding without overstating proof", async ({ href, link, message, reason }) => {
    api.fetchOutcomeGraphs.mockResolvedValue(graphPage([graph({
      classification: "unknown",
      next_check_at: "2026-08-09T08:00:00Z",
      reason_code: reason as OutcomeGraphRow["reason_code"],
      verification_status: "inconclusive",
    })]));

    renderEvidencePage();

    await screen.findByText(message);
    const panel = screen.getByLabelText("Focused proof panel");
    expect(within(panel).getByText(message)).toBeInTheDocument();
    if (href && link) {
      expect(within(panel).getByRole("link", { name: link }).getAttribute("href")).toBe(href);
    } else {
      expect(within(panel).queryByRole("link")).not.toBeInTheDocument();
    }
    if (reason === "sor_unreachable") expect(within(panel).getByText(/Next check/)).toBeInTheDocument();
  });

  it("shows setup empty state when coverage total is zero", async () => {
    api.fetchOutcomeGraphCoverage.mockResolvedValue(coverage({ total: 0, coverage_percent: 0 }));
    api.fetchOutcomeGraphs.mockResolvedValue(graphPage([]));

    renderEvidencePage();

    expect(await screen.findByRole("heading", { name: "No outcome graphs yet" })).toBeInTheDocument();
    expect(screen.getByText("Declare your first intent.")).toBeInTheDocument();
    expect(screen.getByText("Outcome graphs appear here once an agent run is verified against your systems of record.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Read setup docs" }).getAttribute("href")).toBe("/docs");
  });

  it("downloads a signed evidence pack for the focused graph", async () => {
    renderEvidencePage();

    const button = await screen.findByRole("button", { name: "Export evidence pack" });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);

    await waitFor(() => expect(api.fetchOutcomeGraphEvidenceExport).toHaveBeenCalledWith("graph_1"));
    expect(await screen.findByText("Evidence pack exported.")).toBeInTheDocument();
  });

  it("exports only rows in the searched view", async () => {
    api.fetchOutcomeGraphs.mockResolvedValue(graphPage([
      graph(),
      graph({ id: "graph_2", graph: { workflow_key: "invoice_workflow" } }),
    ]));
    renderEvidencePage();

    fireEvent.change(await screen.findByRole("searchbox", { name: "Search evidence" }), { target: { value: "invoice" } });
    fireEvent.click(screen.getByRole("button", { name: "Export view" }));

    expect(await screen.findByText("Exported 1 outcome graph.")).toBeInTheDocument();
  });

  it("reports signed evidence export failures", async () => {
    api.fetchOutcomeGraphEvidenceExport.mockRejectedValue(new Error("signing unavailable"));
    renderEvidencePage();

    const button = await screen.findByRole("button", { name: "Export evidence pack" });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Evidence pack could not be exported. Verify signing readiness and try again.",
    );
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
  });
});
