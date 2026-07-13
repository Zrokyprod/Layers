"use client";

import { useState } from "react";
import { Activity, CheckCircle2, Clock, FileCheck2, TriangleAlert } from "lucide-react";

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
  top: 28,
  right: 24,
  bottom: 42,
  left: 42,
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const time = new Date(value).getTime();
  return Number.isFinite(time) ? time : null;
}

function bucketCount(windowDays: number): number {
  if (windowDays <= 7) return Math.max(1, windowDays);
  if (windowDays <= 14) return 7;
  if (windowDays <= 31) return 10;
  return 12;
}

function bucketLabel(startMs: number, endMs: number, windowDays: number): string {
  const formatter = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
  if (windowDays <= 14) {
    return formatter.format(new Date(startMs));
  }
  return `${formatter.format(new Date(startMs))} - ${formatter.format(new Date(endMs - 1))}`;
}

function hasSequenceRisk(decision: RuntimePolicyDecisionResponse): boolean {
  const reasons = decision.reasons.some((reason) => reason.toLowerCase().includes("sequence risk"));
  const policyHit = decision.policy_hit && Object.prototype.hasOwnProperty.call(decision.policy_hit, "sequence_risk");
  return Boolean(reasons || policyHit);
}

function riskMutation(mutation: SourceMutationView): boolean {
  return ["policy_bypass", "unmanaged_agent_action", "unknown_actor"].includes(mutation.classification);
}

function bucketIndexFor(time: number, startMs: number, spanMs: number, count: number): number | null {
  if (time < startMs || time > startMs + spanMs) return null;
  return clamp(Math.floor(((time - startMs) / spanMs) * count), 0, count - 1);
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

export function buildAgentHealthBuckets(input: ActivitySeriesInput): AgentHealthBucket[] {
  const endMs = parseTime(input.generatedAt) ?? Date.now();
  const startMs = parseTime(input.windowStart) ?? endMs - input.windowDays * 86_400_000;
  const spanMs = Math.max(1, endMs - startMs);
  const count = bucketCount(input.windowDays);
  const bucketSpan = spanMs / count;
  const buckets = Array.from({ length: count }, (_, index) => ({
    id: `activity-${index}`,
    label: bucketLabel(startMs + bucketSpan * index, startMs + bucketSpan * (index + 1), input.windowDays),
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
    const index = bucketIndexFor(time, startMs, spanMs, count);
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
  const totalSignals = buckets.reduce(
    (sum, bucket) => sum + bucket.protectedActions + bucket.holds + bucket.checks + bucket.receipts + bucket.riskSignals + bucket.stalled,
    0,
  );
  const status = workingStatus(actionsTotal, completedTotal, attentionTotal, totalSignals);
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
  const xFor = (index: number) => buckets.length === 1
    ? CHART_PAD.left + innerWidth / 2
    : CHART_PAD.left + (index / (buckets.length - 1)) * innerWidth;
  const actionPoints = buckets.map((bucket, index) => ({ x: xFor(index), y: yFor(bucket.protectedActions) }));
  const completedPoints = buckets.map((bucket, index) => ({ x: xFor(index), y: yFor(completedWork(bucket)) }));
  const attentionPoints = buckets.map((bucket, index) => ({ x: xFor(index), y: yFor(attentionWork(bucket)) }));
  const yTicks = [0, chartMax / 2, chartMax];
  const activeBucket = activeIndex == null ? null : buckets[activeIndex];
  const activeX = activeIndex == null ? 0 : xFor(activeIndex);
  const tooltipWidth = 176;
  const tooltipX = clamp(activeX - tooltipWidth / 2, CHART_PAD.left, CHART_WIDTH - CHART_PAD.right - tooltipWidth);
  const hitWidth = innerWidth / Math.max(1, buckets.length - 1);

  return (
    <section
      className="mc-agent-health-panel"
      aria-label={`Agent activity trend, ${timeframeLabel(input.windowDays)}`}
      data-window-days={input.windowDays}
    >
      <div className="mc-agent-chart-toolbar">
        <div className="mc-agent-chart-status" data-tone={status.tone}>
          <span className="mc-agent-chart-status-dot" aria-hidden="true" />
          <div>
            <strong>{status.label}</strong>
            <span>{status.detail}</span>
          </div>
        </div>
        <div className="mc-agent-chart-legend" aria-label="Chart totals">
          <span data-series="actions"><i aria-hidden="true" />Agent actions <strong>{formatCount(actionsTotal)}</strong></span>
          <span data-series="completed"><i aria-hidden="true" />Completed <strong>{formatCount(completedTotal)}</strong></span>
          <span data-series="attention"><i aria-hidden="true" />Needs attention <strong>{formatCount(attentionTotal)}</strong></span>
        </div>
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
              <stop offset="0%" stopColor="#2f5f66" stopOpacity="0.22" />
              <stop offset="100%" stopColor="#2f5f66" stopOpacity="0.01" />
            </linearGradient>
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

          <path className="mc-agent-actions-area" d={areaPath(actionPoints, baseline)} />
          <path className="mc-agent-series-line" data-series="actions" d={smoothPath(actionPoints)} />
          <path className="mc-agent-series-line" data-series="completed" d={smoothPath(completedPoints)} />
          <path className="mc-agent-series-line" data-series="attention" d={smoothPath(attentionPoints)} />

          {buckets.map((bucket, index) => {
            const x = xFor(index);
            const actionsY = yFor(bucket.protectedActions);
            const completedY = yFor(completedWork(bucket));
            const attentionY = yFor(attentionWork(bucket));
            const showLabel = buckets.length <= 7 || index === 0 || index === buckets.length - 1 || index % 2 === 0;
            return (
              <g key={bucket.id}>
                {showLabel ? <text className="mc-health-axis mc-health-x-axis" x={x} y={CHART_HEIGHT - 12}>{bucket.label}</text> : null}
                <circle className="mc-agent-series-dot" data-series="actions" cx={x} cy={actionsY} r={activeIndex === index ? 5 : 3.5} />
                <circle className="mc-agent-series-dot" data-series="completed" cx={x} cy={completedY} r={activeIndex === index ? 4.5 : 3} />
                <circle className="mc-agent-series-dot" data-series="attention" cx={x} cy={attentionY} r={activeIndex === index ? 4.5 : 3} />
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
              <rect x={tooltipX} y={8} width={tooltipWidth} height={92} rx={7} />
              <text x={tooltipX + 12} y={29} data-row="title">{activeBucket.label}</text>
              <text x={tooltipX + 12} y={49}>Agent actions</text>
              <text x={tooltipX + tooltipWidth - 12} y={49} textAnchor="end">{activeBucket.protectedActions}</text>
              <text x={tooltipX + 12} y={68}>Completed</text>
              <text x={tooltipX + tooltipWidth - 12} y={68} textAnchor="end">{completedWork(activeBucket)}</text>
              <text x={tooltipX + 12} y={87}>Needs attention</text>
              <text x={tooltipX + tooltipWidth - 12} y={87} textAnchor="end">{attentionWork(activeBucket)}</text>
            </g>
          ) : null}
        </svg>

        {totalSignals === 0 ? <p className="mc-agent-health-empty">No agent activity in the selected timeframe.</p> : null}
      </div>

      <div className="mc-agent-chart-meta">
        <span><Clock aria-hidden="true" size={14} />Last active <strong>{lastActive}</strong></span>
        <span><FileCheck2 aria-hidden="true" size={14} />Proof generated <strong>{formatCount(receiptTotal)}</strong></span>
        <span><Activity aria-hidden="true" size={14} />Actions <strong>{formatCount(actionsTotal)}</strong></span>
        <span data-tone={attentionTotal > 0 ? "warning" : "success"}>
          {attentionTotal > 0 ? <TriangleAlert aria-hidden="true" size={14} /> : <CheckCircle2 aria-hidden="true" size={14} />}
          Open attention <strong>{formatCount(attentionTotal)}</strong>
        </span>
      </div>
    </section>
  );
}
