import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DevComponentsPage from "./page";
import { isDashboardProtectedPath } from "@/lib/dashboard-route-contract";

describe("DevComponentsPage", () => {
  it("is not behind the dashboard auth route contract", () => {
    expect(isDashboardProtectedPath("/dev/components")).toBe(false);
  });

  it("renders screenshot-ready proof-chain variants without backend data", () => {
    const { container } = render(<DevComponentsPage />);

    expect(screen.getByRole("heading", { name: "Dashboard component preview" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Proof chain stepper variants" })).toBeInTheDocument();
    expect(screen.getAllByRole("navigation", { name: "Proof chain" })).toHaveLength(5);

    expect(container.querySelectorAll(".evidence-receipt-stepper--compact")).toHaveLength(2);
    expect(container.querySelectorAll(".evidence-receipt-stepper--evidence")).toHaveLength(1);
    expect(container.querySelectorAll(".evidence-receipt-stepper:not(.evidence-receipt-stepper--compact):not(.evidence-receipt-stepper--evidence)")).toHaveLength(2);

    expect(screen.getByText("Pill tones")).toBeInTheDocument();
    expect(screen.getByText("Mission-control surface")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Dashboard scaffold primitives" })).toBeInTheDocument();
    expect(container.querySelector(".dashboard-verdict-hero")).toBeInTheDocument();
    expect(container.querySelector(".dashboard-metric-strip")).toBeInTheDocument();
    expect(container.querySelector(".dashboard-workspace")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Settings scaffold primitives" })).toBeInTheDocument();
    expect(container.querySelector(".settings-control-page")).toBeInTheDocument();
    expect(container.querySelector(".settings-control-hero.dashboard-verdict-hero")).toBeInTheDocument();
    expect(container.querySelector(".settings-control-metrics.dashboard-metric-strip")).toBeInTheDocument();
    expect(container.querySelector(".settings-control-section")).toBeInTheDocument();
    const buttonSamples = screen.getByRole("region", { name: "Button primitive samples" });
    expect(buttonSamples).toBeInTheDocument();
    expect(within(buttonSamples).getByRole("button", { name: "Refresh" }).className).toContain("dashboard-button-primary");
    expect(within(buttonSamples).getByRole("link", { name: "Open preview" }).className).toContain("dashboard-button-soft");
    expect(within(buttonSamples).getByRole("button", { name: "Icon refresh" }).className).toContain("dashboard-button-icon");
  });
});
