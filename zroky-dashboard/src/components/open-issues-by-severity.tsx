"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { listIssues } from "@/lib/api";
import { bucketBySeverity } from "@/lib/issue-format";
import type { IssueListResponse } from "@/lib/types";

/**
 * OpenIssuesBySeverity — replaces the legacy Active Alerts panel on the home
 * page. Aggregates currently-open Issues by severity bucket and links to the
 * filtered `/issues?severity=...` view.
 */

const FETCH_LIMIT = 100;

const SEVERITY_DESCRIPTIONS: Record<
  "critical" | "high" | "medium" | "low",
  string
> = {
  critical: "Production stoppers — fix today.",
  high: "Frequent or expensive — triage this week.",
  medium: "Recurring but bounded — schedule a fix.",
  low: "Minor or noisy signal — review when convenient.",
};

export function OpenIssuesBySeverity() {
  const issuesQuery = useQuery<IssueListResponse>({
    queryKey: ["issues", "by-severity", { status: "open", limit: FETCH_LIMIT }],
    queryFn: () => listIssues({ status: "open", limit: FETCH_LIMIT }),
    refetchInterval: 30_000,
  });

  const buckets = useMemo(() => {
    const items = issuesQuery.data?.items ?? [];
    return bucketBySeverity(items);
  }, [issuesQuery.data]);

  const total = buckets.reduce((sum, b) => sum + b.count, 0);

  return (
    <article className="panel panel-muted">
      <header className="panel-header">
        <div>
          <h3>Open Issues by Severity</h3>
          <p>Grouped product problems — click a row to triage that bucket.</p>
        </div>
        <Link href="/approvals" className="btn btn-soft">
          See All
        </Link>
      </header>

      <div className="list">
        {issuesQuery.isLoading ? (
          <div className="empty">Loading…</div>
        ) : total === 0 ? (
          <div className="empty">
            <span aria-hidden="true">✓</span> No open issues — system is quiet.
          </div>
        ) : (
          buckets.map((bucket) => (
            <Link
              key={bucket.severity}
              href="/approvals"
              className="list-row"
              aria-label={`${bucket.count} ${bucket.severity} open issues`}
            >
              <div className="list-main">
                <strong>
                  <span
                    className={`priority-queue-severity sev-${bucket.severity}`}
                    style={{ marginRight: "0.5rem" }}
                  >
                    {bucket.severity}
                  </span>
                  {bucket.count === 0
                    ? "No open"
                    : `${bucket.count} open`}
                </strong>
                <span>{SEVERITY_DESCRIPTIONS[bucket.severity]}</span>
              </div>
              <span className="mono">{bucket.count}</span>
            </Link>
          ))
        )}
      </div>
    </article>
  );
}
