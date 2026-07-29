import { describe, expect, it } from "vitest";

import { dashboardWindowDays } from "./dashboard-window";

describe("dashboardWindowDays", () => {
  it("uses seven days when the dashboard range is unavailable", () => {
    expect(dashboardWindowDays({ from: null, to: null })).toBe(7);
  });

  it("converts the selected range into whole days", () => {
    expect(dashboardWindowDays({
      from: new Date("2026-06-01T00:00:00Z"),
      to: new Date("2026-06-15T00:00:00Z"),
    })).toBe(14);
  });

  it("caps dashboard lifecycle queries at ninety days", () => {
    expect(dashboardWindowDays({
      from: new Date("2026-01-01T00:00:00Z"),
      to: new Date("2026-07-01T00:00:00Z"),
    })).toBe(90);
  });
});
