const MS_PER_DAY = 24 * 60 * 60 * 1000;

export const DEFAULT_DASHBOARD_WINDOW_DAYS = 7;

export function dashboardWindowDays(
  dateRange: { from: Date | null; to: Date | null },
  defaultDays = DEFAULT_DASHBOARD_WINDOW_DAYS,
): number {
  if (!dateRange.from || !dateRange.to) return defaultDays;
  const fromMs = new Date(dateRange.from).getTime();
  const toMs = new Date(dateRange.to).getTime();
  if (!Number.isFinite(fromMs) || !Number.isFinite(toMs) || toMs <= fromMs) {
    return defaultDays;
  }
  return Math.max(1, Math.min(90, Math.ceil((toMs - fromMs) / MS_PER_DAY)));
}
