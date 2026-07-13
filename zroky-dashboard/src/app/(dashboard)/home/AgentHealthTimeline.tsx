"use client";

import { Activity, Clock, Minus, ShieldCheck, TrendingDown, TrendingUp, TriangleAlert } from "lucide-react";

import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  SourceMutationView,
} from "@/lib/api";
import type { AgentFleetView } from "@/lib/agent-fleet";
import { formatCount } from "@/lib/format";

type HealthSeriesInput = {
  windowDays: number;
  windowStart: string;
  generatedAt: string;
  intents: ActionIntentResponse[];
  approvals: RuntimePolicyDecisionResponse[];
  outcomes: OutcomeReconciliationView[];
  mutations: SourceMutationView[];
  staleAttempts: ActionExecutionAttemptResponse[];
  fleet: AgentFleetView;
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
  score: number | null;
};

type AgentHealthTimelineProps = HealthSeriesInput & {
  loading: boolean;
};

const CHART_WIDTH = 760;
const CHART_HEIGHT = 190;
const CHART_PAD = {
  top: 22,
  right: 24,
  bottom: 24,
  left: 24,
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
  if (windowDays <= 31) return 6;
  return 9;
}

function bucketLabel(startMs: number, endMs: number, windowDays: number): string {
  const formatter = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    timeZone: "UTC",
  });
  if (windowDays <= 14) {
    return formatter.format(new Date(startMs));
  }
  return `${formatter.format(new Date(startMs))}-${formatter.format(new Date(endMs - 1))}`;
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

function scoreBucket(bucket: Omit<AgentHealthBucket, "id" | "label" | "score">): number | null {
  const signalCount = bucket.protectedActions + bucket.holds + bucket.checks + bucket.receipts + bucket.riskSignals + bucket.stalled;
  if (signalCount === 0) return null;

  const completed = completedWork(bucket);
  const attention = attentionWork(bucket);
  const total = Math.max(1, completed + attention);
  const completionRatio = completed / total;
  const workBonus = bucket.protectedActions > 0 ? 10 : 0;
  const attentionPenalty = Math.min(26, attention * 5);

  return clamp(Math.round(34 + completionRatio * 58 + workBonus - attentionPenalty), 0, 100);
}

export function buildAgentHealthBuckets(input: HealthSeriesInput): AgentHealthBucket[] {
  const endMs = parseTime(input.generatedAt) ?? Date.now();
  const startMs = parseTime(input.windowStart) ?? endMs - input.windowDays * 86_400_000;
  const spanMs = Math.max(1, endMs - startMs);
  const count = bucketCount(input.windowDays);
  const bucketSpan = spanMs / count;
  const buckets = Array.from({ length: count }, (_, index) => ({
    id: `health-${index}`,
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
      if (approval.status === "pending_approval" || approval.requires_approval) bucket.holds += 1;
      if (hasSequenceRisk(approval)) bucket.riskSignals += 1;
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
      bucket.riskSignals += 1;
    });
  }

  return buckets.map((bucket) => ({
    ...bucket,
    score: scoreBucket(bucket),
  }));
}

function pathForScores(buckets: AgentHealthBucket[]): string {
  const scored = buckets
    .map((bucket, index) => ({ bucket, index }))
    .filter((item) => item.bucket.score != null);
  if (scored.length === 0) return "";
  const innerWidth = CHART_WIDTH - CHART_PAD.left - CHART_PAD.right;
  const innerHeight = CHART_HEIGHT - CHART_PAD.top - CHART_PAD.bottom;
  return scored
    .map(({ bucket, index }, pointIndex) => {
      const x = CHART_PAD.left + ((index + 0.5) / buckets.length) * innerWidth;
      const y = CHART_PAD.top + innerHeight - ((bucket.score ?? 0) / 100) * innerHeight;
      return `${pointIndex === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

function averageScore(buckets: AgentHealthBucket[]): number | null {
  const scores = buckets.map((bucket) => bucket.score).filter((score): score is number => score != null);
  if (scores.length === 0) return null;
  return Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length);
}

function scoreTone(score: number | null): "success" | "warning" | "danger" | "neutral" {
  if (score == null) return "neutral";
  if (score >= 80) return "success";
  if (score >= 55) return "warning";
  return "danger";
}

function scoreStatus(score: number | null): string {
  if (score == null) return "No recent work";
  if (score >= 72) return "Working well";
  return "Needs attention";
}

function trendDelta(buckets: AgentHealthBucket[]): number | null {
  const scores = buckets.map((bucket) => bucket.score).filter((score): score is number => score != null);
  if (scores.length < 2) return null;
  return scores[scores.length - 1] - scores[0];
}

function timeframeLabel(windowDays: number): string {
  if (windowDays <= 1) return "Today";
  if (windowDays <= 7) return `Last ${windowDays} days`;
  if (windowDays <= 31) return `Last ${windowDays} days`;
  return `${windowDays}-day window`;
}

function latestActivityTime(buckets: AgentHealthBucket[], input: HealthSeriesInput): number | null {
  const times = [
    ...input.intents.map((item) => parseTime(item.created_at)),
    ...input.approvals.map((item) => parseTime(item.created_at)),
    ...input.outcomes.map((item) => parseTime(item.checked_at ?? item.created_at)),
    ...input.mutations.map((item) => parseTime(item.occurred_at ?? item.created_at)),
    ...input.staleAttempts.map((item) => parseTime(item.updated_at ?? item.created_at)),
  ].filter((time): time is number => time != null);
  if (times.length === 0 || buckets.every((bucket) => bucket.score == null)) return null;
  return Math.max(...times);
}

function relativeTimeLabel(time: number | null, generatedAt: string): string {
  if (time == null) return "No recent work";
  const endMs = parseTime(generatedAt) ?? Date.now();
  const diffMinutes = Math.max(0, Math.round((endMs - time) / 60_000));
  if (diffMinutes < 1) return "Just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.round(diffHours / 24)}d ago`;
}

export function AgentHealthTimeline({
  loading,
  ...input
}: AgentHealthTimelineProps) {
  if (loading) {
    return (
      <section className="mc-agent-health-panel mc-agent-health-loading" aria-label="Agent working status">
        <span className="mc-skeleton mc-skeleton-label" />
        <span className="mc-skeleton mc-skeleton-value" />
        <span className="mc-skeleton mc-skeleton-line" />
      </section>
    );
  }

  const buckets = buildAgentHealthBuckets(input);
  const score = averageScore(buckets);
  const tone = scoreTone(score);
  const status = scoreStatus(score);
  const delta = trendDelta(buckets);
  const path = pathForScores(buckets);
  const maxVolume = Math.max(1, ...buckets.map((bucket) => bucket.protectedActions + bucket.checks + bucket.receipts));
  const totalSignals = buckets.reduce(
    (sum, bucket) => sum + bucket.protectedActions + bucket.holds + bucket.checks + bucket.receipts + bucket.riskSignals + bucket.stalled,
    0,
  );
  const attentionTotal = buckets.reduce((sum, bucket) => sum + attentionWork(bucket), 0);
  const completedTotal = buckets.reduce((sum, bucket) => sum + completedWork(bucket), 0);
  const receiptTotal = buckets.reduce((sum, bucket) => sum + bucket.receipts, 0);
  const lastActive = relativeTimeLabel(latestActivityTime(buckets, input), input.generatedAt);
  const innerWidth = CHART_WIDTH - CHART_PAD.left - CHART_PAD.right;
  const innerHeight = CHART_HEIGHT - CHART_PAD.top - CHART_PAD.bottom;
  const barWidth = Math.max(16, innerWidth / Math.max(1, buckets.length) - 12);
  const TrendIcon = delta == null ? Minus : delta >= 0 ? TrendingUp : TrendingDown;
  const trendLabel = delta == null ? "Trend pending" : delta >= 5 ? "More work completed" : delta <= -5 ? "Needs more attention" : "Steady";

  return (
    <section className="mc-agent-health-panel" aria-label="Agent working status">
      <div className="mc-agent-health-copy">
        <div>
          <p className="mc-eyebrow">Agent working status</p>
          <h2>Agent Working Status</h2>
        </div>
        <p>Shows whether your agent is completing work, waiting for approval, or needs attention in this timeframe.</p>
        <div className="mc-agent-health-pills" aria-label="Agent work window and trend">
          <span>{timeframeLabel(input.windowDays)}</span>
          <span data-trend={delta == null ? "flat" : delta >= 0 ? "up" : "down"}>
            <TrendIcon aria-hidden="true" size={14} />
            {trendLabel}
          </span>
        </div>
      </div>

      <div className="mc-agent-health-score" data-tone={tone}>
        <ShieldCheck aria-hidden="true" size={18} />
        <span>Current status</span>
        <strong>{status}</strong>
        <em>{formatCount(completedTotal)} completed / {formatCount(attentionTotal)} needs attention</em>
      </div>

      <div className="mc-agent-health-chart" aria-hidden="true">
        <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} role="img">
          <defs>
            <linearGradient id="agent-health-line" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0%" stopColor="#2f5f66" />
              <stop offset="100%" stopColor="#16a34a" />
            </linearGradient>
          </defs>
          {[25, 50, 75, 100].map((tick) => {
            const y = CHART_PAD.top + innerHeight - (tick / 100) * innerHeight;
            return (
              <g key={tick} aria-hidden="true">
                <line className="mc-health-grid-line" x1={CHART_PAD.left} x2={CHART_WIDTH - CHART_PAD.right} y1={y} y2={y} />
              </g>
            );
          })}
          {buckets.map((bucket, index) => {
            const centerX = CHART_PAD.left + ((index + 0.5) / buckets.length) * innerWidth;
            const volume = bucket.protectedActions + bucket.checks + bucket.receipts;
            const barHeight = (volume / maxVolume) * 72;
            const barX = centerX - barWidth / 2;
            const barY = CHART_PAD.top + innerHeight - barHeight;
            const scoreY = bucket.score == null ? null : CHART_PAD.top + innerHeight - (bucket.score / 100) * innerHeight;
            return (
              <g key={bucket.id}>
                <rect className="mc-health-volume-bar" x={barX} y={barY} width={barWidth} height={barHeight} rx={4} />
                {attentionWork(bucket) > 0 ? (
                  <circle className="mc-health-risk-dot" cx={centerX} cy={CHART_PAD.top + 12} r={4 + Math.min(4, attentionWork(bucket))} />
                ) : null}
                {scoreY == null ? null : <circle className="mc-health-score-dot" cx={centerX} cy={scoreY} r={4.5} />}
              </g>
            );
          })}
          {path ? <path className="mc-health-score-line" d={path} /> : null}
        </svg>
        <div className="mc-agent-health-chart-footer" aria-hidden="true">
          <span>Earlier</span>
          <span>Now</span>
        </div>
      </div>

      <div className="mc-agent-health-breakdown">
        <div>
          <Activity aria-hidden="true" size={15} />
          <span>Work completed</span>
          <strong>{formatCount(completedTotal)} done</strong>
        </div>
        <div data-tone={attentionTotal > 0 ? "warning" : "success"}>
          <TriangleAlert aria-hidden="true" size={15} />
          <span>Needs attention</span>
          <strong>{formatCount(attentionTotal)} items</strong>
        </div>
        <div>
          <Clock aria-hidden="true" size={15} />
          <span>Last active</span>
          <strong>{lastActive}</strong>
        </div>
        <div>
          <ShieldCheck aria-hidden="true" size={15} />
          <span>Proof generated</span>
          <strong>{formatCount(receiptTotal)} receipts</strong>
        </div>
      </div>

      {totalSignals === 0 ? (
        <p className="mc-agent-health-empty">No agent work in this timeframe yet.</p>
      ) : null}
    </section>
  );
}
