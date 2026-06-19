/**
 * Shared formatting helpers for the `Issue` product object.
 *
 * Used by the `/issues` list/detail pages and by the home-page Issue widgets
 * (`TopIssuesQueue`, `RecentIssueActivity`, `OpenIssuesBySeverity`).
 */
import type { IssueItem } from "./types";

/** Human-readable label for the backend `replay_coverage_status` enum. */
export function replayLabel(status: string | null | undefined): string {
  switch ((status ?? "").trim().toLowerCase()) {
    case "verified_fix":
      return "Verified fix";
    case "sanity_replay_passed":
    case "stub_only":
      return "Fixture validation only";
    case "real_replay_missing_tool_proof":
    case "tool_snapshot_missing":
      return "Missing tool proof";
    case "covered_failed":
      return "Replay failed";
    case "not_verified":
      return "Not verified";
    case "inconclusive":
      return "Inconclusive";
    case "real_replay_passed":
    case "covered_passed":
    case "covered_not_run":
    case "fix_pending_replay":
    case "replay_running":
      return "Covered, needs review";
    case "not_covered":
    case "replay_missing":
    case "":
      return "No trusted replay";
    default:
      return "No trusted replay";
  }
}

/** Numeric rank used to sort severities (critical highest). */
export function severityRank(severity: string | null | undefined): number {
  switch ((severity ?? "").toLowerCase()) {
    case "critical":
      return 4;
    case "high":
      return 3;
    case "medium":
      return 2;
    case "low":
      return 1;
    default:
      return 0;
  }
}

/**
 * Returns severity buckets with counts, in display order
 * (critical first, low last).
 */
export function bucketBySeverity(items: readonly IssueItem[]): {
  severity: "critical" | "high" | "medium" | "low";
  count: number;
}[] {
  const counts: Record<string, number> = {};
  for (const issue of items) {
    const key = (issue.severity || "low").toLowerCase();
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return (["critical", "high", "medium", "low"] as const).map((sev) => ({
    severity: sev,
    count: counts[sev] ?? 0,
  }));
}

/**
 * Returns true if the issue had activity (opened or resolved) within
 * `withinHours` of `now`. Used by the recent-activity feed on home.
 */
export function hasRecentActivity(
  issue: IssueItem,
  withinHours: number,
  now: number = Date.now(),
): boolean {
  const cutoff = now - withinHours * 60 * 60 * 1000;
  const lastSeenMs = new Date(issue.last_seen_at).getTime();
  if (Number.isFinite(lastSeenMs) && lastSeenMs >= cutoff) return true;
  if (issue.resolved_at) {
    const resolvedMs = new Date(issue.resolved_at).getTime();
    if (Number.isFinite(resolvedMs) && resolvedMs >= cutoff) return true;
  }
  return false;
}

/**
 * Classifies an Issue's most recent meaningful event so the activity feed
 * can render the right verb and timestamp.
 */
export function classifyIssueActivity(issue: IssueItem): {
  verb: "opened" | "reopened" | "resolved" | "updated";
  at: string;
} {
  if (
    issue.status === "resolved" &&
    issue.resolved_at &&
    new Date(issue.resolved_at).getTime() >=
      new Date(issue.last_seen_at).getTime()
  ) {
    return { verb: "resolved", at: issue.resolved_at };
  }
  if (
    issue.status === "open" &&
    new Date(issue.last_seen_at).getTime() ===
      new Date(issue.first_seen_at).getTime()
  ) {
    return { verb: "opened", at: issue.first_seen_at };
  }
  if (issue.status === "open" && issue.resolved_at === null) {
    return { verb: "updated", at: issue.last_seen_at };
  }
  if (issue.status === "open" && issue.resolved_at) {
    return { verb: "reopened", at: issue.last_seen_at };
  }
  return { verb: "updated", at: issue.last_seen_at };
}
