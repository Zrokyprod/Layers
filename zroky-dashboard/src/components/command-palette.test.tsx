import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CommandPalette } from "./command-palette";

const routerState = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: routerState.push,
  }),
}));

describe("CommandPalette", () => {
  beforeEach(() => {
    routerState.push.mockClear();
  });

  it("uses account profile command instead of settings profile", async () => {
    render(<CommandPalette />);

    window.dispatchEvent(new CustomEvent("open-command-palette"));

    const input = await screen.findByPlaceholderText(/Search pages and actions/);
    fireEvent.change(input, { target: { value: "profile" } });

    expect(await screen.findByText(/Account.*Profile/)).toBeInTheDocument();
    expect(screen.queryByText(/Settings.*Profile/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(/Account.*Profile/));
    expect(routerState.push).toHaveBeenCalledWith("/account");
  });

  it("hides labs, agent console, and drift from primary command discovery", async () => {
    render(<CommandPalette />);

    window.dispatchEvent(new CustomEvent("open-command-palette"));

    const input = await screen.findByPlaceholderText(/Search pages and actions/);
    fireEvent.change(input, { target: { value: "agent" } });

    expect(screen.queryByText(/Labs.*Agent Console/)).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Agent Console")).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: "drift" } });

    expect(screen.queryByText(/Labs.*Provider Drift/)).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Drift")).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: "labs" } });

    expect(screen.queryByText("Go to Labs")).not.toBeInTheDocument();
    expect(routerState.push).not.toHaveBeenCalled();
  });

  it("promotes action-accountability routes and hides deprecated customer surfaces", async () => {
    render(<CommandPalette />);

    window.dispatchEvent(new CustomEvent("open-command-palette"));

    expect(await screen.findByText("Go to Home")).toBeInTheDocument();
    expect(screen.getByText("Go to Agents")).toBeInTheDocument();
    expect(screen.getByText("Go to Approvals")).toBeInTheDocument();
    expect(screen.getByText("Go to Outcomes")).toBeInTheDocument();
    expect(screen.getByText("Go to Evidence")).toBeInTheDocument();
    expect(screen.getByText("Go to Connectors")).toBeInTheDocument();
    expect(screen.getByText("Go to Incidents")).toBeInTheDocument();
    expect(screen.getByText("Go to Policies")).toBeInTheDocument();
    expect(screen.getByText("Go to Replays")).toBeInTheDocument();
    expect(screen.getByText("Engineering - Contracts")).toBeInTheDocument();
    expect(screen.getByText("Engineering - CI")).toBeInTheDocument();
    expect(screen.getByText("Go to Projects")).toBeInTheDocument();
    expect(screen.getByText("Go to Settings")).toBeInTheDocument();
    expect(screen.getByText(/Settings.*API Keys/)).toBeInTheDocument();
    expect(screen.getByText(/Settings.*Providers/)).toBeInTheDocument();
    expect(screen.getByText(/Settings.*Connectors/)).toBeInTheDocument();
    expect(screen.getByText(/Connectors.*Slack/)).toBeInTheDocument();

    expect(screen.queryByText("Go to Overview")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Traces")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Failures")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Goldens")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Contracts")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to CI")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Integrations")).not.toBeInTheDocument();
    expect(screen.queryByText("Ask Zroky")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Cost")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Alerts")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Flight Recorder")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Trace Graphs")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Replay Lab")).not.toBeInTheDocument();
  });
});
