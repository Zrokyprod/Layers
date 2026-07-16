"use client";

import type { ComponentType } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  FileCheck2,
  RefreshCw,
  ShieldCheck,
  Wifi,
} from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";

import {
  calculateAgentHealth,
  healthStatusLabel,
  type AgentHealthInput,
  type HealthSignal,
  type HealthStatus,
} from "./agent-health";

type AgentHealthPanelProps = AgentHealthInput & {
  loading: boolean;
  updatedLabel: string;
  onRefresh: () => void;
};

const signalIcons: Record<HealthSignal["id"], ComponentType<{ size?: number; "aria-hidden"?: boolean }>> = {
  runner: Wifi,
  actions: Activity,
  policy: ShieldCheck,
  proof: FileCheck2,
};

function StatusIcon({ status }: { status: HealthStatus }) {
  if (status === "healthy") return <CheckCircle2 aria-hidden="true" size={14} />;
  if (status === "critical") return <AlertTriangle aria-hidden="true" size={14} />;
  if (status === "degraded") return <Clock3 aria-hidden="true" size={14} />;
  return <span className="mc-health-neutral-mark" aria-hidden="true" />;
}

function HealthScoreRing({ score, status }: { score: number | null; status: HealthStatus }) {
  const circumference = 2 * Math.PI * 46;
  const offset = score == null ? circumference : circumference * (1 - score / 100);

  return (
    <div className="mc-health-score-ring" data-status={status}>
      <svg viewBox="0 0 112 112" aria-hidden="true">
        <circle className="mc-health-ring-track" cx="56" cy="56" r="46" />
        <circle
          className="mc-health-ring-value"
          cx="56"
          cy="56"
          r="46"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <span>
        <strong>{score ?? "—"}</strong>
        {score == null ? null : <small>/100</small>}
      </span>
    </div>
  );
}

function HealthSignalCard({ signal }: { signal: HealthSignal }) {
  const Icon = signalIcons[signal.id];
  return (
    <article className="mc-health-signal-card" data-status={signal.status}>
      <div className="mc-health-signal-head">
        <span aria-hidden="true"><Icon size={17} /></span>
        <i><StatusIcon status={signal.status} /></i>
      </div>
      <p>{signal.label}</p>
      <strong>{signal.displayValue}</strong>
      <small>{signal.context}</small>
      {signal.value == null ? null : (
        <span className="mc-health-microbar" aria-hidden="true">
          <i style={{ width: `${signal.value}%` }} />
        </span>
      )}
    </article>
  );
}

function LiveSignalRow({ label, value, status }: { label: string; value: string; status: HealthStatus }) {
  return (
    <li data-status={status}>
      <span>{label}</span>
      <strong><i aria-hidden="true" />{value}</strong>
    </li>
  );
}

export function AgentHealthPanel({ loading, updatedLabel, onRefresh, ...input }: AgentHealthPanelProps) {
  if (loading) {
    return (
      <section className="mc-agent-health-panel mc-agent-health-loading" aria-label="Agent health loading">
        <span className="mc-skeleton mc-skeleton-label" />
        <span className="mc-skeleton mc-skeleton-value" />
        <span className="mc-skeleton mc-skeleton-line" />
      </section>
    );
  }

  const health = calculateAgentHealth(input);
  const timelineHasData = health.timeline.some((segment) => segment.status !== "no-data");
  const midpoint = Math.floor(health.timeline.length / 2);

  return (
    <section className="mc-agent-health-panel" aria-labelledby="agent-health-title">
      <header className="mc-health-header">
        <div>
          <span className="mc-health-heading-icon" aria-hidden="true"><Activity size={20} /></span>
          <span>
            <h2 id="agent-health-title">Agent health</h2>
            <p>Operational health across runtime, execution, policy and proof signals.</p>
          </span>
        </div>
        <div className="mc-health-updated">
          <span><i aria-hidden="true" />{updatedLabel === "Loading" ? "Updating" : "Updated moments ago"}</span>
          <DashboardButton
            aria-label="Refresh agent health"
            icon={<RefreshCw />}
            onClick={onRefresh}
            variant="ghost"
          />
        </div>
      </header>

      <div className="mc-health-layout">
        <section className="mc-health-score" aria-label="Overall agent health">
          <HealthScoreRing score={health.overallScore} status={health.overallStatus} />
          <div>
            <small>Overall health</small>
            <strong data-status={health.overallStatus}>{healthStatusLabel(health.overallStatus)}</strong>
            <p>Overall agent reliability</p>
          </div>
          {health.overallScore == null ? (
            <p className="mc-health-score-note">Score appears after runner, action, policy and proof data are all available.</p>
          ) : null}
        </section>

        <div className="mc-health-signal-grid" aria-label="Health signals">
          {health.signals.map((signal) => <HealthSignalCard key={signal.id} signal={signal} />)}
        </div>

        <aside className="mc-live-signals" aria-label="Live signals">
          <div>
            <h3>Live signals</h3>
            <span><i aria-hidden="true" />Live</span>
          </div>
          <ul>
            <LiveSignalRow label="Runner status" value={health.runnerLabel} status={health.runnerStatus} />
            <LiveSignalRow label="Last action" value={health.lastActionLabel} status={health.lastActionStatus} />
            <LiveSignalRow label="Open attention" value={health.openAttention == null ? "—" : `${health.openAttention} open`} status={health.openAttention == null ? "no-data" : health.openAttention > 0 ? "critical" : "healthy"} />
            <LiveSignalRow label="Proof freshness" value={health.proofFreshnessLabel} status={health.proofFreshnessStatus} />
            <LiveSignalRow label="Pending approvals" value={health.pendingApprovals == null ? "—" : `${health.pendingApprovals} pending`} status={health.pendingApprovals == null ? "no-data" : health.pendingApprovals > 0 ? "degraded" : "healthy"} />
          </ul>
        </aside>
      </div>

      <div className="mc-health-timeline">
        <div className="mc-health-timeline-head">
          <div>
            <h3>Health timeline</h3>
            <p>{input.windowDays <= 1 ? "Last 24 hours" : `Last ${input.windowDays} days`}</p>
          </div>
          <div className="mc-health-legend" aria-label="Timeline status legend">
            {(["healthy", "degraded", "critical", "no-data"] as const).map((status) => (
              <span key={status} data-status={status}><i aria-hidden="true" />{healthStatusLabel(status)}</span>
            ))}
          </div>
        </div>

        {timelineHasData ? (
          <>
            <div className="mc-health-segments" role="group" aria-label="Agent health history">
              {health.timeline.map((segment) => (
                <button
                  type="button"
                  className="mc-health-segment"
                  data-status={segment.status}
                  key={segment.id}
                  aria-label={`${segment.label}. ${healthStatusLabel(segment.status)}. ${segment.actions} actions, ${segment.attention} attention items.`}
                >
                  <span role="tooltip">
                    <strong>{healthStatusLabel(segment.status)}</strong>
                    <small>{segment.label}</small>
                    <em>{segment.actions} actions · {segment.proofChecks} checks · {segment.attention} attention</em>
                  </span>
                </button>
              ))}
            </div>
            <div className="mc-health-time-labels" aria-hidden="true">
              <span>{health.timeline[0]?.label.split(" - ")[0]}</span>
              <span>{health.timeline[midpoint]?.label.split(" - ")[0]}</span>
              <span>{health.timeline.at(-1)?.label.split(" - ")[1]?.replace(" UTC", "")}</span>
            </div>
          </>
        ) : (
          <div className="mc-health-timeline-empty">
            <Clock3 aria-hidden="true" size={18} />
            <span>
              <strong>No health history available yet.</strong>
              <small>Health signals will appear after the agent begins reporting.</small>
            </span>
          </div>
        )}
      </div>
    </section>
  );
}
