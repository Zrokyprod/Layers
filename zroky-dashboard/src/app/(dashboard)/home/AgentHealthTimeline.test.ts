import { describe, expect, it } from "vitest";

import type { ActionIntentResponse } from "@/lib/api";

import { buildAgentHealthBuckets } from "./AgentHealthTimeline";

function series({
  windowDays,
  windowStart,
  generatedAt,
  intents = [],
}: {
  windowDays: number;
  windowStart: string;
  generatedAt: string;
  intents?: ActionIntentResponse[];
}) {
  return buildAgentHealthBuckets({
    windowDays,
    windowStart,
    generatedAt,
    intents,
    approvals: [],
    outcomes: [],
    mutations: [],
    staleAttempts: [],
  });
}

function intent(createdAt: string): ActionIntentResponse {
  return {
    created_at: createdAt,
    status: "authorized",
    receipt_status: "missing",
    proof_status: "pending",
  } as ActionIntentResponse;
}

describe("buildAgentHealthBuckets", () => {
  it("uses eight three-hour points for the last 24 hours", () => {
    const buckets = series({
      windowDays: 1,
      windowStart: "2026-07-14T09:00:00.000Z",
      generatedAt: "2026-07-15T09:00:00.000Z",
    });

    expect(buckets).toHaveLength(8);
    expect(buckets.map((bucket) => bucket.axisLabel)).toEqual([
      "9:00 AM",
      "12:00 PM",
      "3:00 PM",
      "6:00 PM",
      "9:00 PM",
      "12:00 AM",
      "3:00 AM",
      "6:00 AM",
    ]);
  });

  it("plots seven-day activity on its actual UTC calendar date", () => {
    const buckets = series({
      windowDays: 7,
      windowStart: "2026-07-08T09:00:00.000Z",
      generatedAt: "2026-07-15T09:00:00.000Z",
      intents: [intent("2026-07-11T02:30:00.000Z")],
    });

    expect(buckets).toHaveLength(8);
    expect(buckets.find((bucket) => bucket.protectedActions === 1)?.axisLabel).toBe("Jul 11");
  });

  it("describes multi-day buckets with an exact range", () => {
    const buckets = series({
      windowDays: 14,
      windowStart: "2026-07-01T09:00:00.000Z",
      generatedAt: "2026-07-15T09:00:00.000Z",
    });

    expect(buckets).toHaveLength(7);
    expect(buckets[0].axisLabel).toBe("Jul 1");
    expect(buckets[0].label).toBe("Jul 1 - Jul 3");
  });
});
