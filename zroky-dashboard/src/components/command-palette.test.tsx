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

    const input = await screen.findByPlaceholderText("Search pages and actions…");
    fireEvent.change(input, { target: { value: "profile" } });

    expect(await screen.findByText("Account → Profile")).toBeInTheDocument();
    expect(screen.queryByText("Settings → Profile")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Account → Profile"));
    expect(routerState.push).toHaveBeenCalledWith("/account");
  });

  it("hides labs, agent console, and drift from primary command discovery", async () => {
    render(<CommandPalette />);

    window.dispatchEvent(new CustomEvent("open-command-palette"));

    const input = await screen.findByPlaceholderText("Search pages and actions…");
    fireEvent.change(input, { target: { value: "agent" } });

    expect(screen.queryByText("Labs → Agent Console")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Agent Console")).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: "drift" } });

    expect(screen.queryByText("Labs → Provider Drift")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Drift")).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: "labs" } });

    expect(screen.queryByText("Go to Labs")).not.toBeInTheDocument();
    expect(routerState.push).not.toHaveBeenCalled();
  });

  it("promotes final reliability routes and hides deprecated customer surfaces", async () => {
    render(<CommandPalette />);

    window.dispatchEvent(new CustomEvent("open-command-palette"));

    expect(await screen.findByText("Go to Overview")).toBeInTheDocument();
    expect(screen.getByText("Go to Incidents")).toBeInTheDocument();
    expect(screen.getByText("Go to Replays")).toBeInTheDocument();
    expect(screen.getByText("Go to Contracts")).toBeInTheDocument();
    expect(screen.getByText("Go to CI")).toBeInTheDocument();
    expect(screen.getByText("Go to Settings")).toBeInTheDocument();
    expect(screen.getByText("Settings → API Keys")).toBeInTheDocument();
    expect(screen.getByText("Settings → Providers")).toBeInTheDocument();
    expect(screen.getByText("Integrations → Slack")).toBeInTheDocument();

    expect(screen.queryByText("Go to Agents")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Traces")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Failures")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Goldens")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Policies")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Approvals")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Integrations")).not.toBeInTheDocument();
    expect(screen.queryByText("Ask Zroky")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Cost")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Alerts")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Flight Recorder")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Trace Graphs")).not.toBeInTheDocument();
    expect(screen.queryByText("Go to Replay Lab")).not.toBeInTheDocument();
  });
});
