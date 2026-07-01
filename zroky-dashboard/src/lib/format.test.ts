import { describe, expect, it } from "vitest";
import {
  compactJson,
  field,
  formatCount,
  formatDate,
  formatDateTime,
  formatPercent,
  formatUsd,
  humanize,
  timeSince,
  timeUntil,
} from "./format";

describe("formatUsd", () => {
  it("formats dollars with 4 decimals", () => {
    expect(formatUsd(1234.5678)).toBe("$1,234.5678");
  });

  it("handles zero", () => {
    expect(formatUsd(0)).toBe("$0.00");
  });

  it("handles null", () => {
    expect(formatUsd(null as unknown as number)).toBe("$0.00");
  });
});

describe("formatCount", () => {
  it("formats integers", () => {
    expect(formatCount(1500)).toBe("1,500");
  });

  it("handles null", () => {
    expect(formatCount(null as unknown as number)).toBe("0");
  });
});

describe("formatDate", () => {
  it("formats ISO date", () => {
    const result = formatDate("2024-01-15");
    expect(result).toContain("Jan 15");
  });

  it("handles null", () => {
    expect(formatDate(null)).toBe("-");
  });
});

describe("formatDateTime", () => {
  it("formats ISO datetime", () => {
    const result = formatDateTime("2024-01-15T10:30:00Z");
    expect(result).toContain("Jan 15");
  });

  it("handles null", () => {
    expect(formatDateTime(null)).toBe("-");
  });
});

describe("formatPercent", () => {
  it("formats percentage", () => {
    expect(formatPercent(12.34)).toBe("12.34%");
  });

  it("handles zero", () => {
    expect(formatPercent(0)).toBe("0.00%");
  });
});

describe("compactJson", () => {
  it("removes empty object fields before rendering", () => {
    expect(compactJson({ a: 1, b: "", c: null })).toBe(JSON.stringify({ a: 1 }, null, 2));
  });

  it("renders fallback for empty objects", () => {
    expect(compactJson({})).toBe("-");
  });
});

describe("field", () => {
  it("renders primitives and object values", () => {
    expect(field(" value ")).toBe("value");
    expect(field(true)).toBe("true");
    expect(field({ id: "x" })).toBe(JSON.stringify({ id: "x" }));
  });
});

describe("humanize", () => {
  it("humanizes snake and kebab case values", () => {
    expect(humanize("not_verified")).toBe("Not verified");
    expect(humanize("policy-bypass")).toBe("Policy bypass");
  });
});

describe("relative time", () => {
  const now = new Date("2026-06-28T12:00:00Z").getTime();

  it("formats elapsed time", () => {
    expect(timeSince("2026-06-28T11:45:00Z", now)).toBe("15m old");
    expect(timeSince("2026-06-27T10:00:00Z", now)).toBe("26h old");
  });

  it("formats future time", () => {
    expect(timeUntil("2026-06-28T12:30:00Z", now)).toBe("30m left");
    expect(timeUntil("2026-06-28T11:59:00Z", now)).toBe("Expired");
  });
});
