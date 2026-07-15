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
  it("uses twelve two-hour points for the last 24 hours", () => {
    const buckets = series({
      windowDays: 1,
      windowStart: "2026-07-14T09:00:00.000Z",
      generatedAt: "2026-07-15T09:00:00.000Z",
    });

    expect(buckets).toHaveLength(12);
    expect(buckets.map((bucket) => bucket.axisLabel)).toEqual([
      "11 AM",
      "1 PM",
      "3 PM",
      "5 PM",
      "7 PM",
      "9 PM",
      "11 PM",
      "1 AM",
      "3 AM",
      "5 AM",
      "7 AM",
      "9 AM",
    ]);
  });

  it("plots seven-day activity on its actual UTC calendar date", () => {
    const buckets = series({
      windowDays: 7,
      windowStart: "2026-07-08T09:00:00.000Z",
      generatedAt: "2026-07-15T09:00:00.000Z",
      intents: [intent("2026-07-11T02:30:00.000Z")],
    });

    expect(buckets).toHaveLength(7);
    expect(buckets.find((bucket) => bucket.protectedActions === 1)?.axisLabel).toBe("Jul 11");
  });

  it("uses fourteen daily buckets with exact ranges", () => {
    const buckets = series({
      windowDays: 14,
      windowStart: "2026-07-01T09:00:00.000Z",
      generatedAt: "2026-07-15T09:00:00.000Z",
    });

    expect(buckets).toHaveLength(14);
    expect(buckets[0].axisLabel).toBe("Jul 2");
    expect(buckets[0].label).toBe("Jul 1, 9 AM - Jul 2, 9 AM UTC");
  });

  it("uses thirty daily buckets for a thirty-day window", () => {
    const buckets = series({
      windowDays: 30,
      windowStart: "2026-06-15T09:00:00.000Z",
      generatedAt: "2026-07-15T09:00:00.000Z",
    });

    expect(buckets).toHaveLength(30);
    expect(buckets[0].axisLabel).toBe("Jun 16");
    expect(buckets[29].axisLabel).toBe("Jul 15");
  });
});
