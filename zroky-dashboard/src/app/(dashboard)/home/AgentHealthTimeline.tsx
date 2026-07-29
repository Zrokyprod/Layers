"use client";

import { Activity, HeartPulse, Minus, ShieldCheck, TrendingDown, TrendingUp, TriangleAlert } from "lucide-react";

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

function scoreBucket(bucket: Omit<AgentHealthBucket, "id" | "label" | "score">, fleet: AgentFleetView): number | null {
  const signalCount = bucket.protectedActions + bucket.holds + bucket.checks + bucket.receipts + bucket.riskSignals + bucket.stalled;
  if (signalCount === 0) return null;

  const runnerRatio = fleet.runners.total > 0 ? fleet.runners.online / fleet.runners.total : 0;
  const proofRatio = bucket.checks > 0 ? bucket.verified / bucket.checks : bucket.receipts > 0 ? 0.65 : 0;
  const receiptRatio = bucket.protectedActions > 0 ? Math.min(bucket.receipts / bucket.protectedActions, 1) : bucket.receipts > 0 ? 1 : 0;
  const coverageRatio = fleet.totals.coveragePercent == null ? 0.45 : fleet.totals.coveragePercent / 100;
  const penalty = Math.min(42, bucket.riskSignals * 14 + bucket.stalled * 16 + bucket.holds * 4);

  return clamp(Math.round(34 + runnerRatio * 16 + coverageRatio * 12 + proofRatio * 22 + receiptRatio * 16 - penalty), 0, 100);
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
      if (outcome.verdict === "matched" || outcome.verification_status === "matched") bucket.verified += 1;
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
    score: scoreBucket(bucket, input.fleet),
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
  if (score == null) return "Waiting for signal";
  if (score >= 80) return "Stable control";
  if (score >= 55) return "Needs attention";
  return "At risk";
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

export function AgentHealthTimeline({
  loading,
  ...input
}: AgentHealthTimelineProps) {
  if (loading) {
    return (
      <section className="mc-agent-health-panel mc-agent-health-loading" aria-label="Agent health over time">
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
  const riskTotal = buckets.reduce((sum, bucket) => sum + bucket.riskSignals + bucket.stalled, 0);
  const protectedTotal = buckets.reduce((sum, bucket) => sum + bucket.protectedActions, 0);
  const proofTotal = buckets.reduce((sum, bucket) => sum + bucket.verified + bucket.receipts, 0);
  const innerWidth = CHART_WIDTH - CHART_PAD.left - CHART_PAD.right;
  const innerHeight = CHART_HEIGHT - CHART_PAD.top - CHART_PAD.bottom;
  const barWidth = Math.max(16, innerWidth / Math.max(1, buckets.length) - 12);
  const TrendIcon = delta == null ? Minus : delta >= 0 ? TrendingUp : TrendingDown;

  return (
    <section className="mc-agent-health-panel" aria-label="Agent health over time">
      <div className="mc-agent-health-copy">
        <div>
          <p className="mc-eyebrow">Agent health over time</p>
          <h2>Timeframe-wise control confidence</h2>
        </div>
        <p>One operational view of runner availability, protected action volume, signed proof, and risk pressure.</p>
        <div className="mc-agent-health-pills" aria-label="Agent health window and trend">
          <span>{timeframeLabel(input.windowDays)}</span>
          <span data-trend={delta == null ? "flat" : delta >= 0 ? "up" : "down"}>
            <TrendIcon aria-hidden="true" size={14} />
            {delta == null ? "Trend pending" : `${delta >= 0 ? "+" : ""}${delta} pts`}
          </span>
        </div>
      </div>

      <div className="mc-agent-health-score" data-tone={tone}>
        <HeartPulse aria-hidden="true" size={18} />
        <span>Health score</span>
        <strong>{score == null ? "No signal" : `${score}/100`}</strong>
        <em>{status}</em>
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
                {bucket.riskSignals + bucket.stalled > 0 ? (
                  <circle className="mc-health-risk-dot" cx={centerX} cy={CHART_PAD.top + 12} r={4 + Math.min(4, bucket.riskSignals + bucket.stalled)} />
                ) : null}
                {scoreY == null ? null : <circle className="mc-health-score-dot" cx={centerX} cy={scoreY} r={4.5} />}
              </g>
            );
          })}
          {path ? <path className="mc-health-score-line" d={path} /> : null}
        </svg>
        <div className="mc-agent-health-chart-footer" aria-hidden="true">
          <span>Start</span>
          <span>Now</span>
        </div>
      </div>

      <div className="mc-agent-health-breakdown">
        <div>
          <Activity aria-hidden="true" size={15} />
          <span>Activity</span>
          <strong>{formatCount(protectedTotal)} protected</strong>
        </div>
        <div>
          <ShieldCheck aria-hidden="true" size={15} />
          <span>Proof</span>
          <strong>{formatCount(proofTotal)} verified/receipts</strong>
        </div>
        <div>
          <HeartPulse aria-hidden="true" size={15} />
          <span>Runners</span>
          <strong>{formatCount(input.fleet.runners.online)} / {formatCount(input.fleet.runners.total)} online</strong>
        </div>
        <div data-tone={riskTotal > 0 ? "warning" : "success"}>
          <TriangleAlert aria-hidden="true" size={15} />
          <span>Risk</span>
          <strong>{formatCount(riskTotal)} signals</strong>
        </div>
      </div>

      {totalSignals === 0 ? (
        <p className="mc-agent-health-empty">No agent health events in this timeframe yet.</p>
      ) : null}
    </section>
  );
}
