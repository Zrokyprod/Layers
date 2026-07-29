import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentRuntimeOverview } from "./AgentRuntimeOverview";

const baseProps = {
  loading: false,
  runnerSourceAvailable: true,
  hasManagedAgent: true,
  hasOnlineRunner: false,
  lastActiveAt: "2026-07-12T09:00:00.000Z",
  generatedAt: "2026-07-15T09:00:00.000Z",
  environment: "production",
  openAttention: 1,
  actionsControlled: 2,
  completedActions: 0,
  pendingApprovals: 0,
  proofGenerated: 0,
};

describe("AgentRuntimeOverview", () => {
  it("renders an offline runtime using real counts and no percentages", () => {
    render(<AgentRuntimeOverview {...baseProps} />);

    const runtime = screen.getByRole("heading", { name: "Agent runtime" }).closest("section") as HTMLElement;
    expect(within(runtime).getByText("Runner offline")).toBeInTheDocument();
    expect(within(runtime).getByText("The managed agent has not reported from an active runtime.")).toBeInTheDocument();
    expect(within(runtime).getByText("3 days ago")).toBeInTheDocument();
    expect(within(runtime).getByText("Production")).toBeInTheDocument();
    expect(within(runtime).getByRole("link", { name: "View setup" }).getAttribute("href")).toBe("/agents/setup");
    expect(within(runtime).getByLabelText("Execution summary").textContent).toContain("Actions controlled2");
    expect(runtime.textContent).not.toContain("%");
  });

  it("uses a dash instead of converting unavailable counts into zero", () => {
    render(
      <AgentRuntimeOverview
        {...baseProps}
        runnerSourceAvailable={false}
        lastActiveAt={null}
        environment={null}
        openAttention={null}
        actionsControlled={null}
        completedActions={null}
        pendingApprovals={null}
        proofGenerated={null}
      />,
    );

    expect(screen.getByText("Runtime status unavailable")).toBeInTheDocument();
    expect(screen.getByText("No activity yet")).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(6);
    expect(screen.queryByRole("link", { name: "View setup" })).not.toBeInTheDocument();
  });
});
