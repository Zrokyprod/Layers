"use client";

import { useState } from "react";
import { Activity, CalendarRange, CheckCircle2, Clock, FileCheck2, TriangleAlert } from "lucide-react";

import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  SourceMutationView,
} from "@/lib/api";
import { formatCount } from "@/lib/format";

type ActivitySeriesInput = {
  windowDays: number;
  windowStart: string;
  generatedAt: string;
  intents: ActionIntentResponse[];
  approvals: RuntimePolicyDecisionResponse[];
  outcomes: OutcomeReconciliationView[];
  mutations: SourceMutationView[];
  staleAttempts: ActionExecutionAttemptResponse[];
};

export type AgentHealthBucket = {
  id: string;
  startMs: number;
  endMs: number;
  axisLabel: string;
  label: string;
  protectedActions: number;
  completed: number;
  holds: number;
  verified: number;
  checks: number;
  receipts: number;
  riskSignals: number;
  stalled: number;
};

type AgentHealthTimelineProps = ActivitySeriesInput & {
  loading: boolean;
};

type ChartPoint = {
  x: number;
  y: number;
};

const CHART_WIDTH = 960;
const CHART_HEIGHT = 270;
const CHART_PAD = {
  top: 64,
  right: 24,
  bottom: 38,
  left: 42,
};

const MS_PER_DAY = 86_400_000;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const time = new Date(value).getTime();
  return Number.isFinite(time) ? time : null;
}

function bucketCount(windowDays: number): number {
  if (windowDays <= 1) return 12;
  if (windowDays <= 7) return 7;
  if (windowDays <= 14) return 14;
  if (windowDays <= 31) return 30;
  return Math.min(90, Math.max(1, Math.round(windowDays)));
}

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

const timeFormatter = new Intl.DateTimeFormat("en-US", {
  hour: "numeric",
  timeZone: "UTC",
});

function bucketLabels(startMs: number, endMs: number, windowDays: number): Pick<AgentHealthBucket, "axisLabel" | "label"> {
  if (windowDays <= 1) {
    return {
      axisLabel: timeFormatter.format(new Date(endMs)),
      label: `${dateFormatter.format(new Date(startMs))}, ${timeFormatter.format(new Date(startMs))} - ${timeFormatter.format(new Date(endMs))} UTC`,
    };
  }
  return {
    axisLabel: dateFormatter.format(new Date(endMs)),
    label: `${dateFormatter.format(new Date(startMs))}, ${timeFormatter.format(new Date(startMs))} - ${dateFormatter.format(new Date(endMs))}, ${timeFormatter.format(new Date(endMs))} UTC`,
  };
}

function bucketBoundaries(startMs: number, endMs: number, windowDays: number): number[] {
  const count = bucketCount(windowDays);
  const spanMs = Math.max(1, endMs - startMs);
  return Array.from({ length: count + 1 }, (_, index) => startMs + (spanMs * index) / count);
}

function bucketIndexFor(time: number, boundaries: number[]): number | null {
  if (time < boundaries[0] || time > boundaries[boundaries.length - 1]) return null;
  if (time === boundaries[boundaries.length - 1]) return boundaries.length - 2;
  const index = boundaries.findIndex((boundary, boundaryIndex) => (
    boundaryIndex < boundaries.length - 1 && time >= boundary && time < boundaries[boundaryIndex + 1]
  ));
  return index >= 0 ? index : null;
}

function hasSequenceRisk(decision: RuntimePolicyDecisionResponse): boolean {
  const reasons = decision.reasons.some((reason) => reason.toLowerCase().includes("sequence risk"));
  const policyHit = decision.policy_hit && Object.prototype.hasOwnProperty.call(decision.policy_hit, "sequence_risk");
  return Boolean(reasons || policyHit);
}

function riskMutation(mutation: SourceMutationView): boolean {
  return ["policy_bypass", "unmanaged_agent_action", "unknown_actor"].includes(mutation.classification);
}

function isCompletedIntent(intent: ActionIntentResponse): boolean {
  const status = intent.status.toLowerCase();
  return (
    intent.receipt_status === "generated" ||
    intent.proof_status === "matched" ||
    ["completed", "executed", "succeeded", "verified"].includes(status)
  );
}

function completedWork(bucket: Pick<AgentHealthBucket, "completed" | "verified" | "receipts">): number {
  return Math.max(bucket.completed, bucket.verified, bucket.receipts);
}

function attentionWork(bucket: Pick<AgentHealthBucket, "holds" | "riskSignals" | "stalled">): number {
  return bucket.holds + bucket.riskSignals + bucket.stalled;
}

function completionRate(actions: number, completed: number): number | null {
  if (actions === 0) return null;
  return Math.round((completed / actions) * 100);
}

function intervalLabel(windowDays: number): string {
  if (windowDays <= 1) return "2-hour, 12 points";
  return `Daily, ${bucketCount(windowDays)} points`;
}

function showAxisLabel(index: number, count: number): boolean {
  if (count <= 8) return true;
  const stride = count <= 14 ? 2 : 5;
  return index === 0 || index === count - 1 || (index + 1) % stride === 0;
}

export function buildAgentHealthBuckets(input: ActivitySeriesInput): AgentHealthBucket[] {
  const endMs = parseTime(input.generatedAt) ?? Date.now();
  const startMs = parseTime(input.windowStart) ?? endMs - input.windowDays * MS_PER_DAY;
  const boundaries = bucketBoundaries(startMs, endMs, input.windowDays);
  const buckets = Array.from({ length: boundaries.length - 1 }, (_, index) => ({
    id: `activity-${index}`,
    startMs: boundaries[index],
    endMs: boundaries[index + 1],
    ...bucketLabels(boundaries[index], boundaries[index + 1], input.windowDays),
    protectedActions: 0,
    completed: 0,
    holds: 0,
    verified: 0,
    checks: 0,
    receipts: 0,
    riskSignals: 0,
    stalled: 0,
  }));

  const bump = (timeValue: string | null | undefined, apply: (bucket: typeof buckets[number]) => void) => {
    const time = parseTime(timeValue);
    if (time == null) return;
    const index = bucketIndexFor(time, boundaries);
    if (index == null) return;
    apply(buckets[index]);
  };

  for (const intent of input.intents) {
    bump(intent.created_at, (bucket) => {
      bucket.protectedActions += 1;
      if (isCompletedIntent(intent)) bucket.completed += 1;
      if (intent.receipt_status === "generated") bucket.receipts += 1;
      if (intent.proof_status === "matched") bucket.verified += 1;
      if (["mismatched", "failed"].includes(intent.proof_status)) bucket.riskSignals += 1;
    });
  }

  for (const approval of input.approvals) {
    bump(approval.created_at, (bucket) => {
      const waitingForApproval = approval.status === "pending_approval" || approval.requires_approval;
      if (waitingForApproval) bucket.holds += 1;
      if (hasSequenceRisk(approval) && !waitingForApproval) bucket.riskSignals += 1;
    });
  }

  for (const outcome of input.outcomes) {
    bump(outcome.checked_at ?? outcome.created_at, (bucket) => {
      bucket.checks += 1;
      if (outcome.verdict === "matched" || outcome.verification_status === "matched") {
        bucket.verified += 1;
        bucket.completed += 1;
      }
      if (outcome.verdict === "mismatched" || outcome.verification_status === "mismatched") bucket.riskSignals += 1;
    });
  }

  for (const mutation of input.mutations) {
    bump(mutation.occurred_at ?? mutation.created_at, (bucket) => {
      if (riskMutation(mutation)) bucket.riskSignals += 1;
    });
  }

  for (const attempt of input.staleAttempts) {
    bump(attempt.updated_at ?? attempt.created_at, (bucket) => {
      bucket.stalled += 1;
    });
  }

  return buckets;
}

function smoothPath(points: ChartPoint[]): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  return points.reduce((path, point, index) => {
    if (index === 0) return `M ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    const previous = points[index - 1];
    const controlX = (previous.x + point.x) / 2;
    return `${path} C ${controlX.toFixed(1)} ${previous.y.toFixed(1)}, ${controlX.toFixed(1)} ${point.y.toFixed(1)}, ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
  }, "");
}

function areaPath(points: ChartPoint[], baseline: number): string {
  if (points.length === 0) return "";
  const line = smoothPath(points);
  const first = points[0];
  const last = points[points.length - 1];
  return `${line} L ${last.x.toFixed(1)} ${baseline.toFixed(1)} L ${first.x.toFixed(1)} ${baseline.toFixed(1)} Z`;
}

function timeframeLabel(windowDays: number): string {
  if (windowDays <= 1) return "last 24 hours";
  return `last ${windowDays} days`;
}

function latestActivityTime(buckets: AgentHealthBucket[], input: ActivitySeriesInput): number | null {
  const times = [
    ...input.intents.map((item) => parseTime(item.created_at)),
    ...input.approvals.map((item) => parseTime(item.created_at)),
    ...input.outcomes.map((item) => parseTime(item.checked_at ?? item.created_at)),
    ...input.mutations.map((item) => parseTime(item.occurred_at ?? item.created_at)),
    ...input.staleAttempts.map((item) => parseTime(item.updated_at ?? item.created_at)),
  ].filter((time): time is number => time != null);
  if (times.length === 0 || buckets.every((bucket) => bucket.protectedActions + bucket.checks + bucket.holds === 0)) return null;
  return Math.max(...times);
}

function relativeTimeLabel(time: number | null, generatedAt: string): string {
  if (time == null) return "No recent activity";
  const endMs = parseTime(generatedAt) ?? Date.now();
  const diffMinutes = Math.max(0, Math.round((endMs - time) / 60_000));
  if (diffMinutes < 1) return "Just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.round(diffHours / 24)}d ago`;
}

function workingStatus(actions: number, completed: number, attention: number, signals: number) {
  if (signals === 0) {
    return { label: "No recent activity", detail: "The graph will start after the first agent action.", tone: "neutral" } as const;
  }
  if (attention > 0) {
    return { label: "Needs attention", detail: `${formatCount(attention)} item${attention === 1 ? "" : "s"} waiting for review.`, tone: "warning" } as const;
  }
  if (completed > 0) {
    return { label: "Working as expected", detail: `${formatCount(completed)} completed with no open attention.`, tone: "success" } as const;
  }
  if (actions > 0) {
    return { label: "Agent is active", detail: `${formatCount(actions)} action${actions === 1 ? "" : "s"} recorded; outcome proof is pending.`, tone: "success" } as const;
  }
  return { label: "Activity recorded", detail: "Verification activity is available in this window.", tone: "neutral" } as const;
}

export function AgentHealthTimeline({ loading, ...input }: AgentHealthTimelineProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  if (loading) {
    return (
      <section className="mc-agent-health-panel mc-agent-health-loading" aria-label="Agent activity trend loading">
        <span className="mc-skeleton mc-skeleton-label" />
        <span className="mc-skeleton mc-skeleton-value" />
        <span className="mc-skeleton mc-skeleton-line" />
      </section>
    );
  }

  const buckets = buildAgentHealthBuckets(input);
  const actionsTotal = buckets.reduce((sum, bucket) => sum + bucket.protectedActions, 0);
  const completedTotal = buckets.reduce((sum, bucket) => sum + completedWork(bucket), 0);
  const attentionTotal = buckets.reduce((sum, bucket) => sum + attentionWork(bucket), 0);
  const receiptTotal = buckets.reduce((sum, bucket) => sum + bucket.receipts, 0);
  const proofCheckTotal = buckets.reduce((sum, bucket) => sum + bucket.checks, 0);
  const totalSignals = buckets.reduce(
    (sum, bucket) => sum + bucket.protectedActions + bucket.holds + bucket.checks + bucket.receipts + bucket.riskSignals + bucket.stalled,
    0,
  );
  const status = workingStatus(actionsTotal, completedTotal, attentionTotal, totalSignals);
  const overallCompletionRate = completionRate(actionsTotal, completedTotal);
  const lastActive = relativeTimeLabel(latestActivityTime(buckets, input), input.generatedAt);
  const innerWidth = CHART_WIDTH - CHART_PAD.left - CHART_PAD.right;
  const innerHeight = CHART_HEIGHT - CHART_PAD.top - CHART_PAD.bottom;
  const baseline = CHART_PAD.top + innerHeight;
  const rawMax = Math.max(
    1,
    ...buckets.map((bucket) => Math.max(bucket.protectedActions, completedWork(bucket), attentionWork(bucket))),
  );
  const chartMax = Math.max(2, Math.ceil(rawMax / 2) * 2);
  const yFor = (value: number) => CHART_PAD.top + innerHeight - (value / chartMax) * innerHeight;
  const bucketWidth = innerWidth / Math.max(1, buckets.length);
  const xFor = (index: number) => CHART_PAD.left + bucketWidth * (index + 0.5);
  const actionPoints = buckets.map((bucket, index) => ({ x: xFor(index), y: yFor(bucket.protectedActions) }));
  const completedPoints = buckets.map((bucket, index) => ({ x: xFor(index), y: yFor(completedWork(bucket)) }));
  const attentionPoints = buckets.map((bucket, index) => ({ x: xFor(index), y: yFor(attentionWork(bucket)) }));
  const yTicks = [0, chartMax / 2, chartMax];
  const activeBucket = activeIndex == null ? null : buckets[activeIndex];
  const activeX = activeIndex == null ? 0 : xFor(activeIndex);
  const tooltipWidth = 232;
  const tooltipX = clamp(activeX - tooltipWidth / 2, CHART_PAD.left, CHART_WIDTH - CHART_PAD.right - tooltipWidth);
  const hitWidth = bucketWidth;
  const peakActionIndex = buckets.reduce(
    (peakIndex, bucket, index) => bucket.protectedActions > buckets[peakIndex].protectedActions ? index : peakIndex,
    0,
  );
  const peakAttentionIndex = buckets.reduce(
    (peakIndex, bucket, index) => attentionWork(bucket) > attentionWork(buckets[peakIndex]) ? index : peakIndex,
    0,
  );
  const peakActionBucket = buckets[peakActionIndex];
  const peakAttentionBucket = buckets[peakAttentionIndex];
  const peakActionX = xFor(peakActionIndex);
  const peakAttentionX = xFor(peakAttentionIndex);
  const annotationWidth = 112;
  const actionAnnotationX = clamp(peakActionX - annotationWidth / 2, CHART_PAD.left, CHART_WIDTH - CHART_PAD.right - annotationWidth);
  const attentionAnnotationX = clamp(peakAttentionX - annotationWidth / 2, CHART_PAD.left, CHART_WIDTH - CHART_PAD.right - annotationWidth);
  const selectedWindowLabel = input.windowDays <= 1 ? "24H" : `${Math.round(input.windowDays)}D`;

  return (
    <section
      className="mc-agent-health-panel"
      aria-label={`Agent activity trend, ${timeframeLabel(input.windowDays)}`}
      data-window-days={input.windowDays}
    >
      <div className="mc-agent-overview-head">
        <div className="mc-agent-overview-title">
          <span className="mc-agent-overview-icon" aria-hidden="true"><Activity size={21} /></span>
          <div>
            <h2>Agent activity overview</h2>
            <p>Action trends, completion, and proof signals</p>
          </div>
        </div>
        <div className="mc-agent-overview-stats" aria-label="Activity summary">
          <span><small>Actions controlled</small><strong>{formatCount(actionsTotal)}</strong><em>{timeframeLabel(input.windowDays)}</em></span>
          <span data-tone={attentionTotal > 0 ? "warning" : "success"}><small>Needs attention</small><strong>{formatCount(attentionTotal)}</strong><em>{status.label}</em></span>
          <span data-tone={overallCompletionRate == null ? "neutral" : overallCompletionRate >= 90 ? "success" : "warning"}><small>Completion rate</small><strong>{overallCompletionRate == null ? "--" : `${overallCompletionRate}%`}</strong><em>{formatCount(completedTotal)} completed</em></span>
        </div>
        <div className="mc-agent-window-summary" aria-label={`Selected timeframe ${timeframeLabel(input.windowDays)}`}>
          <strong>{selectedWindowLabel}</strong>
          <span><CalendarRange aria-hidden="true" size={13} />{intervalLabel(input.windowDays)}</span>
        </div>
      </div>

      <div className="mc-agent-chart-frame">
        <div className="mc-agent-chart-legend" aria-label="Chart totals">
          <span data-series="actions"><i aria-hidden="true" />Agent actions <strong>{formatCount(actionsTotal)}</strong></span>
          <span data-series="completed"><i aria-hidden="true" />Completed <strong>{formatCount(completedTotal)}</strong></span>
          <span data-series="attention"><i aria-hidden="true" />Needs attention <strong>{formatCount(attentionTotal)}</strong></span>
          <span data-series="events"><i aria-hidden="true" />Proof checks <strong>{formatCount(proofCheckTotal)}</strong></span>
        </div>

        <div className="mc-agent-health-chart">
        <svg
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
          role="img"
          aria-label={`${formatCount(actionsTotal)} agent actions, ${formatCount(completedTotal)} completed, ${formatCount(attentionTotal)} need attention.`}
          onMouseLeave={() => setActiveIndex(null)}
        >
          <defs>
            <linearGradient id="agent-actions-area" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#1d4ed8" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#1d4ed8" stopOpacity="0.01" />
            </linearGradient>
            <filter id="agent-line-glow" x="-20%" y="-40%" width="140%" height="180%">
              <feDropShadow dx="0" dy="2" stdDeviation="2.5" floodColor="#1d4ed8" floodOpacity="0.12" />
            </filter>
          </defs>

          {yTicks.map((tick) => {
            const y = yFor(tick);
            return (
              <g key={tick} aria-hidden="true">
                <line className="mc-health-grid-line" x1={CHART_PAD.left} x2={CHART_WIDTH - CHART_PAD.right} y1={y} y2={y} />
                <text className="mc-health-axis mc-health-y-axis" x={CHART_PAD.left - 12} y={y + 4}>{tick}</text>
              </g>
            );
          })}

          {activeBucket ? (
            <rect
              className="mc-agent-chart-focus-band"
              x={activeX - hitWidth / 2}
              y={CHART_PAD.top}
              width={hitWidth}
              height={innerHeight}
              rx={6}
            />
          ) : null}

          <path className="mc-agent-actions-area" d={areaPath(actionPoints, baseline)} />
          <path className="mc-agent-series-line" data-series="actions" d={smoothPath(actionPoints)} />
          <path className="mc-agent-series-line" data-series="completed" d={smoothPath(completedPoints)} />
          <path className="mc-agent-series-line" data-series="attention" d={smoothPath(attentionPoints)} />

          {peakActionBucket.protectedActions > 0 ? (
            <g className="mc-agent-chart-annotation" data-tone="actions" aria-hidden="true">
              <line x1={peakActionX} x2={peakActionX} y1={46} y2={yFor(peakActionBucket.protectedActions) - 6} />
              <rect x={actionAnnotationX} y={8} width={annotationWidth} height={40} rx={8} />
              <text x={actionAnnotationX + annotationWidth / 2} y={24} textAnchor="middle">Peak actions</text>
              <text data-row="value" x={actionAnnotationX + annotationWidth / 2} y={40} textAnchor="middle">{peakActionBucket.protectedActions}</text>
            </g>
          ) : null}

          {attentionWork(peakAttentionBucket) > 0 ? (
            <g className="mc-agent-chart-annotation" data-tone="attention" aria-hidden="true">
              <line x1={peakAttentionX} x2={peakAttentionX} y1={46} y2={yFor(attentionWork(peakAttentionBucket)) - 6} />
              <rect x={attentionAnnotationX} y={8} width={annotationWidth} height={40} rx={8} />
              <text x={attentionAnnotationX + annotationWidth / 2} y={24} textAnchor="middle">Attention peak</text>
              <text data-row="value" x={attentionAnnotationX + annotationWidth / 2} y={40} textAnchor="middle">{attentionWork(peakAttentionBucket)}</text>
            </g>
          ) : null}

          {buckets.map((bucket, index) => {
            const x = xFor(index);
            const actionsY = yFor(bucket.protectedActions);
            const completedY = yFor(completedWork(bucket));
            const attentionY = yFor(attentionWork(bucket));
            const showLabel = showAxisLabel(index, buckets.length);
            return (
              <g key={bucket.id}>
                <line className="mc-health-x-tick" x1={x} x2={x} y1={baseline} y2={baseline + 4} />
                {showLabel ? <text className="mc-health-axis mc-health-x-axis" data-current={index === buckets.length - 1} x={x} y={CHART_HEIGHT - 10}>{bucket.axisLabel}</text> : null}
                {bucket.protectedActions > 0 || activeIndex === index ? <circle className="mc-agent-series-dot" data-series="actions" cx={x} cy={actionsY} r={activeIndex === index ? 5 : 3.5} /> : null}
                {completedWork(bucket) > 0 || activeIndex === index ? <circle className="mc-agent-series-dot" data-series="completed" cx={x} cy={completedY} r={activeIndex === index ? 4.5 : 3} /> : null}
                {attentionWork(bucket) > 0 || activeIndex === index ? <circle className="mc-agent-series-dot" data-series="attention" cx={x} cy={attentionY} r={activeIndex === index ? 4.5 : 3} /> : null}
                {bucket.checks > 0 ? <circle className="mc-agent-series-dot" data-series="events" cx={x} cy={yFor(Math.min(chartMax, bucket.checks))} r={3.5} /> : null}
                <rect
                  className="mc-agent-chart-hitbox"
                  x={x - hitWidth / 2}
                  y={CHART_PAD.top}
                  width={hitWidth}
                  height={innerHeight}
                  onMouseEnter={() => setActiveIndex(index)}
                  onPointerDown={() => setActiveIndex(index)}
                />
              </g>
            );
          })}

          {activeBucket ? (
            <g className="mc-agent-chart-tooltip" aria-hidden="true">
              <line x1={activeX} x2={activeX} y1={CHART_PAD.top} y2={baseline} />
              <rect x={tooltipX} y={7} width={tooltipWidth} height={136} rx={8} />
              <text x={tooltipX + 13} y={28} data-row="title">Window ending {activeBucket.axisLabel}</text>
              <text x={tooltipX + 13} y={46} data-row="range">{activeBucket.label}</text>
              <line className="mc-agent-chart-tooltip-divider" x1={tooltipX + 13} x2={tooltipX + tooltipWidth - 13} y1={57} y2={57} />
              <text x={tooltipX + 13} y={76}>Agent actions</text>
              <text x={tooltipX + tooltipWidth - 13} y={76} textAnchor="end">{activeBucket.protectedActions}</text>
              <text x={tooltipX + 13} y={95}>Completed</text>
              <text x={tooltipX + tooltipWidth - 13} y={95} textAnchor="end">{completedWork(activeBucket)}</text>
              <text x={tooltipX + 13} y={114}>Needs attention</text>
              <text x={tooltipX + tooltipWidth - 13} y={114} textAnchor="end">{attentionWork(activeBucket)}</text>
              <text x={tooltipX + 13} y={133}>Completion rate</text>
              <text x={tooltipX + tooltipWidth - 13} y={133} textAnchor="end">
                {completionRate(activeBucket.protectedActions, completedWork(activeBucket)) == null
                  ? "--"
                  : `${completionRate(activeBucket.protectedActions, completedWork(activeBucket))}%`}
              </text>
            </g>
          ) : null}
        </svg>

        {totalSignals === 0 ? <p className="mc-agent-health-empty">No agent activity in the selected timeframe.</p> : null}
        </div>
      </div>

      <div className="mc-agent-chart-meta">
        <span className="mc-agent-meta-item"><i><Clock aria-hidden="true" size={15} /></i><span><small>Last active</small><strong>{lastActive}</strong></span></span>
        <span className="mc-agent-meta-item"><i><FileCheck2 aria-hidden="true" size={15} /></i><span><small>Proof generated</small><strong>{formatCount(receiptTotal)}</strong></span></span>
        <span className="mc-agent-meta-item" data-tone={attentionTotal > 0 ? "warning" : "success"}>
          <i>{attentionTotal > 0 ? <TriangleAlert aria-hidden="true" size={15} /> : <CheckCircle2 aria-hidden="true" size={15} />}</i>
          <span><small>Open attention</small><strong>{formatCount(attentionTotal)}</strong></span>
        </span>
        <span className="mc-agent-meta-item" data-tone={overallCompletionRate == null ? "neutral" : overallCompletionRate >= 90 ? "success" : "warning"}>
          <i className="mc-completion-ring" style={{ background: `conic-gradient(#1d4ed8 ${overallCompletionRate ?? 0}%, #e7ecf5 0)` }} />
          <span><small>Completion rate</small><strong>{overallCompletionRate == null ? "--" : `${overallCompletionRate}%`}</strong></span>
        </span>
      </div>
    </section>
  );
}
