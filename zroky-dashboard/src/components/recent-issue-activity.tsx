"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { listIssues } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { severityBadgeColor } from "@/lib/detector-meta";
import {
  classifyIssueActivity,
  hasRecentActivity,
} from "@/lib/issue-format";
import type { IssueItem, IssueListResponse } from "@/lib/types";

/**
 * RecentIssueActivity — replaces the legacy raw-calls Live Feed on the home
 * page. Shows issues that were opened, resolved, or reopened in the last 24h.
 *
 * Sources from `/v1/issues?status=all` and filters client-side by recency. We
 * intentionally do NOT subscribe to a server-sent stream here — recent issue
 * activity is low-frequency, and the home page already polls every 10s.
 */

const WINDOW_HOURS = 24;
const MAX_ROWS = 8;

export function RecentIssueActivity() {
  const recentQuery = useQuery<IssueListResponse>({
    queryKey: ["issues", "recent", { status: "all", limit: 50 }],
    queryFn: () => listIssues({ status: "all", limit: 50 }),
    refetchInterval: 30_000,
  });

  const rows = useMemo<IssueItem[]>(() => {
    const items = recentQuery.data?.items ?? [];
    const now = Date.now();
    const filtered = items.filter((issue) =>
      hasRecentActivity(issue, WINDOW_HOURS, now),
    );
    filtered.sort((a, b) => {
      const aAt = new Date(classifyIssueActivity(a).at).getTime();
      const bAt = new Date(classifyIssueActivity(b).at).getTime();
      return bAt - aAt;
    });
    return filtered.slice(0, MAX_ROWS);
  }, [recentQuery.data]);

  return (
    <article className="panel">
      <header className="panel-header">
        <div>
          <h3>Recent Issue Activity</h3>
          <p>Issues opened, resolved, or reopened in the last 24 hours.</p>
        </div>
        <Link href="/approvals" className="btn btn-soft">
          Open Issues
        </Link>
      </header>

      <div className="list">
        {recentQuery.isLoading ? (
          <div className="empty">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="empty">No issue activity in the last 24 hours.</div>
        ) : (
          rows.map((issue) => {
            const activity = classifyIssueActivity(issue);
            const sevColor = severityBadgeColor(issue.severity);
            return (
              <Link
                key={`${issue.id}-${activity.verb}`}
                href="/approvals"
                className="list-row"
              >
                <div className="list-main">
                  <strong>{issue.title}</strong>
                  <span>
                    <span
                      className={`alert-cat-badge badge-${sevColor}`}
                      style={{ marginRight: "0.4rem" }}
                    >
                      {activity.verb}
                    </span>
                    {formatDateTime(activity.at)}
                    {issue.affected_agent ? ` · ${issue.affected_agent}` : ""}
                  </span>
                </div>
                <span className="mono" style={{ fontSize: "0.72rem" }}>
                  {issue.occurrence_count} call
                  {issue.occurrence_count === 1 ? "" : "s"}
                </span>
              </Link>
            );
          })
        )}
      </div>
    </article>
  );
}
