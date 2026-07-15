import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ActionIntentResponse } from "@/lib/api";

import { AgentHealthTimeline } from "./AgentHealthTimeline";

function intent(createdAt: string): ActionIntentResponse {
  return {
    created_at: createdAt,
    status: "completed",
    receipt_status: "generated",
    proof_status: "matched",
  } as ActionIntentResponse;
}

describe("AgentHealthTimeline", () => {
  it.each([
    { windowDays: 14, windowStart: "2026-07-01T09:00:00.000Z", points: 14 },
    { windowDays: 30, windowStart: "2026-06-15T09:00:00.000Z", points: 30 },
  ])("renders $points independent daily points for a $windowDays-day window", ({ windowDays, windowStart, points }) => {
    const { container } = render(
      <AgentHealthTimeline
        loading={false}
        windowDays={windowDays}
        windowStart={windowStart}
        generatedAt="2026-07-15T09:00:00.000Z"
        intents={[]}
        approvals={[]}
        outcomes={[]}
        mutations={[]}
        staleAttempts={[]}
      />,
    );

    expect(screen.getByText(`Daily, ${points} points`)).toBeInTheDocument();
    expect(container.querySelectorAll(".mc-agent-chart-hitbox")).toHaveLength(points);
    expect(container.querySelectorAll(".mc-health-x-tick")).toHaveLength(points);
  });

  it("shows the selected interval and a detailed interactive tooltip", () => {
    const { container } = render(
      <AgentHealthTimeline
        loading={false}
        windowDays={7}
        windowStart="2026-07-08T09:00:00.000Z"
        generatedAt="2026-07-15T09:00:00.000Z"
        intents={[intent("2026-07-11T02:30:00.000Z")]}
        approvals={[]}
        outcomes={[]}
        mutations={[]}
        staleAttempts={[]}
      />,
    );

    expect(screen.getByText("Daily, 7 points")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();

    const hitboxes = container.querySelectorAll(".mc-agent-chart-hitbox");
    expect(hitboxes).toHaveLength(7);
    fireEvent.pointerDown(hitboxes[2]);

    expect(container.querySelector(".mc-agent-chart-tooltip")?.textContent).toContain("Window ending Jul 11");
    expect(container.querySelector(".mc-agent-chart-tooltip")?.textContent).toContain("Completion rate100%");
  });
});
