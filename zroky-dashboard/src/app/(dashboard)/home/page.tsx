"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getActivityFeed, getAnalyticsSummary, getAuthSummary, getCaptureHealth, getHealthScore } from "@/lib/api";
import { formatCount, formatDateTime, formatPercent, formatUsd, numberFromUnknown, safeString } from "@/lib/format";
import { useDashboardStore } from "@/lib/store";
import type {
  ActivityFeedItemResponse,
  AnalyticsSummaryResponse,
  AuthSummaryResponse,
  CaptureHealthResponse,
  HealthScoreResponse,
} from "@/lib/types";
import { StatusPill } from "@/components/status-pill";
import { ComingSoonPoll } from "@/components/coming-soon-poll";
import { CaptureConnectPanel } from "@/components/capture-connect-panel";
import { JudgeHealthPanel } from "@/components/judge-health-panel";
import { TopIssuesQueue } from "@/components/top-issues-queue";
import { RecentIssueActivity } from "@/components/recent-issue-activity";
import { OpenIssuesBySeverity } from "@/components/open-issues-by-severity";

const pollMs = 10000;
const liveRetryMs = 5000;
const ONBOARDING_WIZARD_OPENED_KEY = "zroky.onboardingWizardOpened";

type LiveFeedState = "connecting" | "live" | "retrying";

type HealthBreakdownItem = {
  key: "success_rate" | "latency_score" | "cost_anomaly_score" | "open_issues_score";
  label: string;
  weight: number;
  score: number;
  weightedPoints: number;
  inputSummary: string;
  thresholdSummary: string;
};

function actionLabel(action: string): string {
  const normalized = action.trim().toLowerCase();
  if (normalized === "diagnosis_viewed") {
    return "Diagnosis Viewed";
  }
  if (normalized === "fix_copied") {
    return "Fix Copied";
  }
  if (normalized === "pr_generated") {
    return "PR Generated";
  }
  if (normalized === "resolved") {
    return "Resolved";
  }
  return action;
}

function KpiDelta({
  current,
  previous,
  lowerIsBetter,
}: {
  current: number;
  previous: number;
  lowerIsBetter: boolean;
}) {
  if (previous === 0) return <span className="kpi-delta-flat">vs yesterday</span>;
  const delta = current - previous;
  const pct = Math.abs((delta / previous) * 100);
  const isGood = lowerIsBetter ? delta <= 0 : delta >= 0;
  const arrow = delta > 0 ? "â†‘" : delta < 0 ? "â†“" : "â†’";
  const colorClass = delta === 0 ? "kpi-delta-flat" : isGood ? "kpi-delta-good" : "kpi-delta-bad";
  return (
    <span className={colorClass}>
      {arrow} {pct.toFixed(1)}% vs yesterday
    </span>
  );
}

function captureHealthText(captureHealth: CaptureHealthResponse | null): string {
  if (!captureHealth) return "Checking ingest path";
  if (captureHealth.status === "no_data") return "No calls received yet";
  if (captureHealth.status === "stale") {
    return `Last event ${captureHealth.last_seen_at ? formatDateTime(captureHealth.last_seen_at) : "unknown"}`;
  }
  return `${formatCount(captureHealth.calls_24h)} events in 24h`;
}

export default function HomePage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<AnalyticsSummaryResponse | null>(null);
  const [health, setHealth] = useState<HealthScoreResponse | null>(null);
  const [captureHealth, setCaptureHealth] = useState<CaptureHealthResponse | null>(null);
  const [activityFeed, setActivityFeed] = useState<ActivityFeedItemResponse[]>([]);
  const [authSummary, setAuthSummary] = useState<AuthSummaryResponse | null>(null);
  const [windowDays, setWindowDays] = useState<1 | 7 | 30>(1);
  const setSdkConnected = useDashboardStore((s) => s.setSdkConnected);
  const sdkConnected = useDashboardStore((s) => s.sdkConnected);
  const [onboardingWizardOpened, setOnboardingWizardOpened] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [summaryPayload, healthPayload, capturePayload, activityPayload, authPayload] = await Promise.all([
        getAnalyticsSummary(windowDays),
        getHealthScore(),
        getCaptureHealth(),
        getActivityFeed({ limit: 12, offset: 0 }),
        getAuthSummary(24),
      ]);

      setSummary(summaryPayload);
      setHealth(healthPayload);
      setCaptureHealth(capturePayload);
      setSdkConnected(capturePayload.status === "connected");
      setActivityFeed(activityPayload.items);
      setAuthSummary(authPayload);
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : "Failed to load dashboard state.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [setSdkConnected, windowDays]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, pollMs);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    setOnboardingWizardOpened(window.localStorage.getItem(ONBOARDING_WIZARD_OPENED_KEY) === "1");
  }, []);

  const markOnboardingWizardOpened = useCallback(() => {
    setOnboardingWizardOpened(true);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ONBOARDING_WIZARD_OPENED_KEY, "1");
    }
  }, []);

  const unusualActivity = useMemo(() => {
    if (!summary?.unusual_activity) {
      return null;
    }

    const multiplier = numberFromUnknown(summary.unusual_activity.anomaly_multiplier);
    const callMultiplier = numberFromUnknown(summary.unusual_activity.call_multiplier);
    const costMultiplier = numberFromUnknown(summary.unusual_activity.cost_multiplier);
    const currentCalls = Math.max(0, Math.round(numberFromUnknown(summary.unusual_activity.current_calls)));
    const normalCallsPerUser = numberFromUnknown(summary.unusual_activity.normal_calls_per_user);
    const currentCostUsd = numberFromUnknown(summary.unusual_activity.current_cost_usd);
    const normalCostPerUserUsd = numberFromUnknown(summary.unusual_activity.normal_cost_per_user_usd);

    return {
      impactedUser: safeString(summary.unusual_activity.impacted_user, "unknown"),
      multiplier,
      callMultiplier: callMultiplier > 0 ? callMultiplier : multiplier,
      costMultiplier: costMultiplier > 0 ? costMultiplier : multiplier,
      currentCalls,
      normalCallsPerUser,
      currentCostUsd,
      normalCostPerUserUsd,
      wasteUsd: numberFromUnknown(summary.unusual_activity.current_waste_estimate_usd),
      action: safeString(summary.unusual_activity.suggested_action, "Review activity"),
    };
  }, [summary]);

  const healthBreakdown = useMemo(() => {
    if (!health) {
      return null;
    }

    const details = health.details;
    const successfulCalls24h = Math.max(0, Math.round(numberFromUnknown(details["successful_calls_24h"])));
    const totalCalls24h = Math.max(0, Math.round(numberFromUnknown(details["total_calls_24h"])));
    const latencySloMs = numberFromUnknown(details["latency_slo_ms"]);
    const projectP95LatencyMs = numberFromUnknown(details["project_p95_latency_ms"]);
    const current15mSpendUsd = numberFromUnknown(details["current_15m_spend_usd"]);
    const baseline15mSpendUsd = numberFromUnknown(details["baseline_15m_spend_usd"]);
    const costRatio = numberFromUnknown(details["cost_ratio"]);
    const openHighSeverityIssues = Math.max(0, Math.round(numberFromUnknown(details["open_high_severity_issues"])));
    const issuesPer1000Calls = numberFromUnknown(details["issues_per_1000_calls"]);

    const items: HealthBreakdownItem[] = [
      {
        key: "success_rate",
        label: "Success Rate",
        weight: 0.4,
        score: health.success_rate,
        weightedPoints: health.success_rate * 0.4,
        inputSummary: `${formatCount(successfulCalls24h)} / ${formatCount(totalCalls24h)} successful calls (24h)` ,
        thresholdSummary: "Score = (successful_calls / total_calls) * 100",
      },
      {
        key: "latency_score",
        label: "Latency Score",
        weight: 0.25,
        score: health.latency_score,
        weightedPoints: health.latency_score * 0.25,
        inputSummary: `P95 ${projectP95LatencyMs.toFixed(2)}ms vs SLO ${latencySloMs.toFixed(2)}ms`,
        thresholdSummary: "100 when p95 <= SLO, else 100 * (SLO / p95)",
      },
      {
        key: "cost_anomaly_score",
        label: "Cost Anomaly",
        weight: 0.2,
        score: health.cost_anomaly_score,
        weightedPoints: health.cost_anomaly_score * 0.2,
        inputSummary: `${formatUsd(current15mSpendUsd)} current / ${formatUsd(baseline15mSpendUsd)} baseline (15m)` ,
        thresholdSummary: `Ratio ${costRatio.toFixed(2)}x; buckets: <=1.25 => 100, <=2 => 70, <=3 => 40, >3 => 10`,
      },
      {
        key: "open_issues_score",
        label: "Open Issues",
        weight: 0.15,
        score: health.open_issues_score,
        weightedPoints: health.open_issues_score * 0.15,
        inputSummary: `${formatCount(openHighSeverityIssues)} high/critical open issues, ${issuesPer1000Calls.toFixed(2)} per 1000 calls`,
        thresholdSummary: "Buckets: 0 => 100, <=3 => 70, <=6 => 40, >6 => 10",
      },
    ];

    const weightedTotal = items.reduce((sum, item) => sum + item.weightedPoints, 0);

    return {
      items,
      weightedTotal,
      reconciliationDelta: Math.abs(health.health_score - weightedTotal),
      successfulCalls24h,
      totalCalls24h,
      projectP95LatencyMs,
      latencySloMs,
      current15mSpendUsd,
      baseline15mSpendUsd,
      costRatio,
      openHighSeverityIssues,
      issuesPer1000Calls,
    };
  }, [health]);

  const fixAdoption = summary?.fix_adoption ?? null;
  const feedbackLoop = summary?.feedback_loop ?? null;
  const shouldShowCaptureSetup =
    !loading &&
    captureHealth !== null &&
    (captureHealth.status !== "connected" || (summary !== null && summary.calls_today === 0 && summary.calls_yesterday === 0));
  const onboardingChecklist = useMemo(() => {
    const captureConnected = sdkConnected || captureHealth?.status === "connected";
    const items = [
      { label: "Capture stream connected", done: captureConnected },
      { label: "At least one call ingested", done: (summary?.calls_today ?? 0) > 0 },
      { label: "Setup path opened", done: onboardingWizardOpened },
    ];
    const completed = items.filter((item) => item.done).length;
    return {
      items,
      completed,
      total: items.length,
      pct: Math.round((completed / items.length) * 100),
    };
  }, [captureHealth?.status, onboardingWizardOpened, sdkConnected, summary?.calls_today]);

  return (
    <>
      <section className="hero panel page-enter">
        <h1>Command Center</h1>
        <p>
          Monitor system health, spot unusual spend, and land fixes in minutes. Data refreshes every {Math.floor(pollMs / 1000)} seconds while this page is open.
        </p>
        <div className="hero-footer">
          <div className="actions">
            <Link href="/issues" className="btn btn-primary">
              Triage Top Issues
            </Link>
          </div>
          <div className="window-toggle" role="group" aria-label="Time window">
            {([1, 7, 30] as const).map((d) => (
              <button
                key={d}
                type="button"
                className={`window-toggle-btn ${windowDays === d ? "window-toggle-btn-active" : ""}`}
                onClick={() => setWindowDays(d)}
              >
                {d === 1 ? "24h" : d === 7 ? "7d" : "30d"}
              </button>
            ))}
          </div>
          <p className="hint" style={{ fontSize: "0.72rem", marginTop: "0.25rem", opacity: 0.7 }}>Applies to KPI cards</p>
        </div>
      </section>

      {shouldShowCaptureSetup ? (
        <CaptureConnectPanel
          captureHealth={captureHealth}
          checklistItems={onboardingChecklist.items}
          completedCount={onboardingChecklist.completed}
          totalCount={onboardingChecklist.total}
          progressPct={onboardingChecklist.pct}
          onRefresh={() => void load()}
          onMarkOpened={markOnboardingWizardOpened}
        />
      ) : null}

      {error ? <section className="panel"><p>{error}</p></section> : null}

      {authSummary && authSummary.open_alert_count > 0 ? (
        <section className="panel home-auth-banner">
          <header className="panel-header">
            <div>
              <h3 className="home-auth-banner-title">
                {authSummary.open_alert_count > 1 ? "âš  Auth Failures Detected" : "âš  Auth Failure Detected"}
              </h3>
              <p>
                {authSummary.open_alert_count} unacknowledged auth failure alert{authSummary.open_alert_count > 1 ? "s" : ""} in the last 24 hours.
                {authSummary.total_auth_failures > 0 ? ` ${authSummary.total_auth_failures} total failure${authSummary.total_auth_failures > 1 ? "s" : ""} detected.` : ""}
                {authSummary.affected_providers.length > 0 ? ` Providers: ${authSummary.affected_providers.join(", ")}.` : ""}
                {authSummary.mean_time_to_acknowledge_minutes != null
                  ? ` Mean time to acknowledge: ${authSummary.mean_time_to_acknowledge_minutes.toFixed(1)} min.`
                  : " Not yet acknowledged."}
              </p>
            </div>
            <Link href="/issues?failure_code=AUTH_FAILURE" className="btn btn-primary home-auth-banner-btn">
              Triage Auth Issues
            </Link>
          </header>
        </section>
      ) : null}

      {loading && !summary ? (
        <section className="kpi-grid">
          <div className="loading" />
          <div className="loading" />
          <div className="loading" />
          <div className="loading" />
        </section>
      ) : null}

      <section className="kpi-grid">
        <article className="kpi-card">
          <span className="kpi-label">Health Score</span>
          <strong className="kpi-value">{health ? formatPercent(health.health_score) : "-"}</strong>
          <div className="kpi-helper">Updated: {health ? formatDateTime(health.updated_at) : "-"}</div>
        </article>

        <article className="kpi-card">
          <span className="kpi-label">Capture Health</span>
          <strong className="kpi-value">
            <StatusPill value={captureHealth?.status ?? "checking"} />
          </strong>
          <div className="kpi-helper">{captureHealthText(captureHealth)}</div>
        </article>

        <article className="kpi-card">
          <span className="kpi-label">Calls ({windowDays === 1 ? "24h" : windowDays === 7 ? "7d" : "30d"})</span>
          <strong className="kpi-value">{summary ? formatCount(summary.calls_today) : "-"}</strong>
          <div className="kpi-helper">
            {summary && summary.calls_yesterday > 0 ? (
              <KpiDelta current={summary.calls_today} previous={summary.calls_yesterday} lowerIsBetter={false} />
            ) : (
              `Traffic Â· last ${windowDays === 1 ? "24 hours" : windowDays === 7 ? "7 days" : "30 days"}`
            )}
          </div>
        </article>

        <article className="kpi-card">
          <span className="kpi-label">Cost ({windowDays === 1 ? "24h" : windowDays === 7 ? "7d" : "30d"})</span>
          <strong className="kpi-value mono">{summary ? formatUsd(summary.cost_today_usd) : "$0.00"}</strong>
          <div className="kpi-helper">
            {summary && summary.cost_yesterday_usd > 0 ? (
              <KpiDelta current={summary.cost_today_usd} previous={summary.cost_yesterday_usd} lowerIsBetter={true} />
            ) : (
              "Current burn estimate"
            )}
          </div>
        </article>

        <article className="kpi-card">
          <span className="kpi-label">Open Issues</span>
          <strong className="kpi-value">{summary ? formatCount(summary.open_issues) : "0"}</strong>
          <div className="kpi-helper">Grouped product problems, ranked by impact</div>
        </article>

        <article className="kpi-card">
          <span className="kpi-label">Fix Adoption Rate</span>
          <strong className="kpi-value">{fixAdoption ? formatPercent(fixAdoption.adoption_rate_percent) : "-"}</strong>
          <div className="kpi-helper">
            {fixAdoption
              ? `${formatCount(fixAdoption.resolved_diagnoses)} resolved of ${formatCount(fixAdoption.viewed_diagnoses)} viewed`
              : "Needs viewed and resolved activity"}
          </div>
        </article>
      </section>

      {/* Top Issues Queue: top-5 open grouped Issues ranked by priority_score */}
      <TopIssuesQueue />

      <JudgeHealthPanel />

      <section className="grid-two">
        <RecentIssueActivity />

        <article className="panel panel-muted">
          <header className="panel-header">
            <div>
              <h3>Unusual Activity</h3>
              <p>Automatic anomaly hint for bursty users.</p>
            </div>
          </header>

          {unusualActivity ? (
            <div className="list unusual-activity-panel">
              <div className="list-row unusual-activity-headline">
                <div className="list-main">
                  <strong>{unusualActivity.multiplier.toFixed(2)} times normal</strong>
                  <span>{unusualActivity.impactedUser} is showing burst behavior vs project baseline.</span>
                </div>
                <StatusPill value={unusualActivity.multiplier >= 3 ? "critical" : "warning"} />
              </div>

              <div className="list-row">
                <div className="list-main">
                  <strong>Impacted User</strong>
                </div>
                <span className="mono">{unusualActivity.impactedUser}</span>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Anomaly Multiplier</strong>
                  <span className="list-subtle">Maximum of call and cost multiplier.</span>
                </div>
                <span className="mono">{unusualActivity.multiplier.toFixed(2)} times normal</span>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Call Pattern</strong>
                  <span className="list-subtle">
                    {formatCount(unusualActivity.currentCalls)} current vs {unusualActivity.normalCallsPerUser.toFixed(2)} normal calls per user
                  </span>
                </div>
                <span className="mono">{unusualActivity.callMultiplier.toFixed(2)}x</span>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Cost Pattern</strong>
                  <span className="list-subtle">
                    {formatUsd(unusualActivity.currentCostUsd)} current vs {formatUsd(unusualActivity.normalCostPerUserUsd)} normal spend per user
                  </span>
                </div>
                <span className="mono">{unusualActivity.costMultiplier.toFixed(2)}x</span>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Current Waste Estimate</strong>
                </div>
                <span className="mono">{formatUsd(unusualActivity.wasteUsd)}</span>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Suggested Action</strong>
                </div>
                <span>{unusualActivity.action}</span>
              </div>

              <div className="actions unusual-activity-actions">
                <Link
                  href={`/calls?user_id=${encodeURIComponent(unusualActivity.impactedUser)}`}
                  className="btn btn-primary"
                >
                  Investigate User Calls
                </Link>
                <Link href="/issues" className="btn btn-soft">
                  Open Issues
                </Link>
              </div>
            </div>
          ) : (
            <div className="empty">No unusual user activity detected in current window.</div>
          )}
        </article>
      </section>

      <section className="grid-two">
        <OpenIssuesBySeverity />

        <article className="panel panel-muted">
          <header className="panel-header">
            <div>
              <h3>Health Breakdown</h3>
              <p>Expandable widget with transparent weighted scoring.</p>
            </div>
            <StatusPill value={health?.status_band} />
          </header>

          <details className="health-breakdown-widget" open>
            <summary className="health-breakdown-summary">
              <div className="list-main">
                <strong>Health Score Breakdown</strong>
                <span>4 sub-scores, weighted contributions, and raw inputs.</span>
              </div>
              <span className="mono">{health ? formatPercent(health.health_score) : "-"}</span>
            </summary>

            {health && healthBreakdown ? (
              <div className="health-breakdown-body">
                <div className="list">
                  {healthBreakdown.items.map((item) => (
                    <div key={item.key} className="list-row health-breakdown-row">
                      <div className="list-main">
                        <strong>
                          {item.label} ({Math.round(item.weight * 100)}%)
                        </strong>
                        <span>{item.inputSummary}</span>
                        <span className="list-subtle">{item.thresholdSummary}</span>
                      </div>

                      <div className="health-breakdown-values">
                        <span className="mono">{formatPercent(item.score)}</span>
                        <span className="mono health-weighted-points">{item.weightedPoints.toFixed(2)} pts</span>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="health-transparency-block">
                  <p className="hint">Calculation transparency</p>
                  <p className="mono">
                    Health = (40% x {health.success_rate.toFixed(2)}) + (25% x {health.latency_score.toFixed(2)}) + (20% x {health.cost_anomaly_score.toFixed(2)}) + (15% x {health.open_issues_score.toFixed(2)}) = {healthBreakdown.weightedTotal.toFixed(2)}
                  </p>

                  <div className="health-transparency-grid">
                    <div className="health-transparency-item">
                      <span>Successful Calls (24h)</span>
                      <span className="mono">
                        {formatCount(healthBreakdown.successfulCalls24h)} / {formatCount(healthBreakdown.totalCalls24h)}
                      </span>
                    </div>
                    <div className="health-transparency-item">
                      <span>Latency p95 vs SLO</span>
                      <span className="mono">
                        {healthBreakdown.projectP95LatencyMs.toFixed(2)}ms / {healthBreakdown.latencySloMs.toFixed(2)}ms
                      </span>
                    </div>
                    <div className="health-transparency-item">
                      <span>15m Spend Ratio</span>
                      <span className="mono">
                        {formatUsd(healthBreakdown.current15mSpendUsd)} / {formatUsd(healthBreakdown.baseline15mSpendUsd)} ({healthBreakdown.costRatio.toFixed(2)}x)
                      </span>
                    </div>
                    <div className="health-transparency-item">
                      <span>Open High Severity Issues</span>
                      <span className="mono">
                        {formatCount(healthBreakdown.openHighSeverityIssues)} ({healthBreakdown.issuesPer1000Calls.toFixed(2)} per 1000)
                      </span>
                    </div>
                    <div className="health-transparency-item">
                      <span>API Score vs Recomputed</span>
                      <span className="mono">
                        {health.health_score.toFixed(2)} vs {healthBreakdown.weightedTotal.toFixed(2)} (delta {healthBreakdown.reconciliationDelta.toFixed(4)})
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="empty">Health score data unavailable.</div>
            )}
          </details>
        </article>
      </section>

      {fixAdoption && fixAdoption.viewed_diagnoses > 0 ? (
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Fix Adoption and Feedback Loop</h3>
            <p>Track diagnose-to-fix conversion and thumbs-down visibility by category.</p>
          </div>
        </header>

        <div className="grid-two">
          <article className="panel panel-muted">
            <header className="panel-header">
              <div>
                <h3>Fix Adoption Tracking</h3>
                <p>Formula: resolved diagnoses / viewed diagnoses.</p>
              </div>
              <StatusPill value={fixAdoption?.status_band} />
            </header>

            {fixAdoption ? (
              <div className="list">
                <div className="list-row">
                  <div className="list-main">
                    <strong>Adoption Rate</strong>
                    <span>North-star conversion from diagnosis views to fixes.</span>
                  </div>
                  <span className="mono">{formatPercent(fixAdoption.adoption_rate_percent)}</span>
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Viewed Diagnoses</strong>
                  </div>
                  <span className="mono">{formatCount(fixAdoption.viewed_diagnoses)}</span>
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Resolved Diagnoses</strong>
                  </div>
                  <span className="mono">{formatCount(fixAdoption.resolved_diagnoses)}</span>
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Status Band</strong>
                    <span className="list-subtle">Strong: &gt;= 40%, Warning: 20-39%, Critical: &lt; 20%</span>
                  </div>
                  <StatusPill value={fixAdoption.status_band} />
                </div>
              </div>
            ) : (
              <div className="empty">Fix adoption data unavailable.</div>
            )}
          </article>

          <article className="panel">
            <header className="panel-header">
              <div>
                <h3>Feedback Loop Visibility</h3>
                <p>Thumbs-down percentage by diagnosis category.</p>
              </div>
            </header>

            {feedbackLoop && feedbackLoop.feedback_total > 0 ? (
              <div className="list">
                <div className="list-row">
                  <div className="list-main">
                    <strong>Overall Thumbs Down</strong>
                    <span>
                      {formatCount(feedbackLoop.thumbs_down_total)} downvotes from {formatCount(feedbackLoop.feedback_total)} feedback votes
                    </span>
                  </div>
                  <span className="mono">{formatPercent(feedbackLoop.thumbs_down_rate_percent)}</span>
                </div>

                {feedbackLoop.by_category.slice(0, 6).map((item) => (
                  <div className="list-row" key={item.category}>
                    <div className="list-main">
                      <strong>{item.category}</strong>
                      <span>
                        {formatCount(item.thumbs_down_count)} thumbs-down of {formatCount(item.feedback_total)} feedback
                      </span>
                    </div>
                    <span className="mono">{formatPercent(item.thumbs_down_rate_percent)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty">No feedback yet. Ask developers for quick thumbs-up/down on diagnoses.</div>
            )}
          </article>
        </div>
      </section>
      ) : null}

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>What&apos;s coming next</h3>
            <p>Vote on features we&apos;re evaluating. Your feedback shapes the roadmap.</p>
          </div>
        </header>
        <ComingSoonPoll
          featureKey="pilot.tier1_autonomy"
          title="Tier-1 Autonomy"
          description="Auto-apply safe config fixes (model rollback, fallback swap, retry tune) without a PR. Fully reversible, kill-switch protected. Today: only Tier-2 PR-based fixes ship."
          useCasePrompt="What's the #1 AI agent failure you'd want fixed without a PR? (your answer shapes what we build)"
        />
      </section>

      <details className="panel">
        <summary className="panel-header" style={{ cursor: "pointer", listStyle: "none", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <h3>Enterprise Audit Feed</h3>
            <p>Immutable action trail: diagnosis viewed, fix copied, PR generated, and resolved.</p>
          </div>
          <span className="mono hint">{activityFeed.length > 0 ? activityFeed.length + " events" : "No events"}</span>
        </summary>

        <div className="list">
          {activityFeed.length === 0 ? (
            <div className="empty">No audited actions yet.</div>
          ) : (
            activityFeed.map((item) => (
              <Link key={item.log_id} href={`/calls/${item.diagnosis_id}`} className="list-row">
                <div className="list-main">
                  <strong>{actionLabel(item.action)}</strong>
                  <span>
                    {item.diagnosis_id} Â· {safeString(item.actor_subject, "system")} Â· {formatDateTime(item.created_at)}
                  </span>
                </div>
                <StatusPill value={item.action} />
              </Link>
            ))
          )}
        </div>
      </details>
    </>
  );
}
