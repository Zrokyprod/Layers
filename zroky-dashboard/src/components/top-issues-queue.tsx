"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { listIssues } from "@/lib/api";
import { severityBadgeColor } from "@/lib/detector-meta";
import type { IssueItem, IssueListResponse } from "@/lib/types";

/**
 * TopIssuesQueue — "what should I look at right now?" widget for the home page.
 *
 * Replaces the legacy alert-based PriorityQueue. Sources data from the rich
 * `/v1/issues` endpoint which already returns grouped product problems sorted
 * by (severity, blast_radius_usd, occurrence_count, last_seen_at). The
 * backend's `priority_score` field encodes the composite ranking — we trust
 * it and render the top 5 directly.
 */

const MAX_ITEMS = 5;

export function TopIssuesQueue() {
  const issuesQuery = useQuery<IssueListResponse>({
    queryKey: ["issues", "top", { status: "open", limit: MAX_ITEMS }],
    queryFn: () => listIssues({ status: "open", limit: MAX_ITEMS }),
    refetchInterval: 30_000,
  });

  if (issuesQuery.isLoading) {
    return (
      <article
        className="priority-queue panel"
        aria-label="Today's Priority issues"
      >
        <header className="panel-header">
          <div>
            <h3>Today&apos;s Priority</h3>
            <p>The five issues most worth your attention right now.</p>
          </div>
        </header>
        <p className="priority-queue-empty">Loading priorities…</p>
      </article>
    );
  }

  const items = issuesQuery.data?.items ?? [];

  if (items.length === 0) {
    return (
      <article
        className="priority-queue panel"
        aria-label="Today's Priority issues"
      >
        <header className="panel-header">
          <div>
            <h3>Today&apos;s Priority</h3>
            <p>The five issues most worth your attention right now.</p>
          </div>
        </header>
        <p className="priority-queue-empty">
          <span aria-hidden="true">✓</span> Inbox zero — nothing open right now.
        </p>
      </article>
    );
  }

  return (
    <article
      className="priority-queue panel"
      aria-label="Today's Priority issues"
    >
      <header className="panel-header">
        <div>
          <h3>Today&apos;s Priority</h3>
          <p>
            Top {items.length} open issues — grouped product problems, not raw
            traces.
          </p>
        </div>
        <Link href="/approvals" className="priority-queue-see-all">
          See all open →
        </Link>
      </header>

      <ol className="priority-queue-list">
        {items.map((issue, idx) => (
          <TopIssuesQueueItem
            key={issue.id}
            issue={issue}
            rank={idx + 1}
          />
        ))}
      </ol>
    </article>
  );
}

function TopIssuesQueueItem({
  issue,
  rank,
}: {
  issue: IssueItem;
  rank: number;
}) {
  const sevKey = (issue.severity || "low").toLowerCase();
  const sevColor = severityBadgeColor(issue.severity);
  const factorParts: string[] = [];
  factorParts.push(`${issue.occurrence_count} call${issue.occurrence_count === 1 ? "" : "s"}`);
  if (issue.cost_impact_usd > 0) {
    factorParts.push(formatUsdCompact(issue.cost_impact_usd));
  }
  if (issue.affected_agent) {
    factorParts.push(issue.affected_agent);
  } else if (issue.affected_workflow) {
    factorParts.push(issue.affected_workflow);
  }

  return (
    <li className="priority-queue-item">
      <Link
        href="/approvals"
        className="priority-queue-link"
      >
        <span className="priority-queue-rank mono" aria-hidden="true">
          #{rank}
        </span>
        <div className="priority-queue-body">
          <div className="priority-queue-title-row">
            <span
              className={`priority-queue-badge badge-${sevColor}`}
              title={issue.failure_code}
            >
              {issue.failure_code.replace(/_/g, " ").toLowerCase()}
            </span>
            <span
              className={`priority-queue-severity sev-${sevKey}`}
            >
              {sevKey}
            </span>
          </div>
          <p className="priority-queue-headline">{issue.title}</p>
          <p className="priority-queue-factors">{factorParts.join(" · ")}</p>
        </div>
        <span className="priority-queue-cta" aria-hidden="true">
          →
        </span>
      </Link>
    </li>
  );
}

function formatUsdCompact(n: number): string {
  if (n < 1) return `$${n.toFixed(2)}`;
  if (n < 100) return `$${n.toFixed(2)}`;
  if (n < 1000) return `$${Math.round(n)}`;
  if (n < 1_000_000) return `$${(n / 1000).toFixed(1)}k`;
  return `$${(n / 1_000_000).toFixed(1)}M`;
}
