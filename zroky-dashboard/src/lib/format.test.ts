import { describe, expect, it } from "vitest";
import { formatUsd, formatCount, formatDate, formatDateTime, formatPercent } from "./format";

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
