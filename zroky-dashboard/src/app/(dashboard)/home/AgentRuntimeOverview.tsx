"use client";

import { AlertTriangle, RadioTower, Wifi, WifiOff } from "lucide-react";

import { DashboardButtonLink } from "@/components/dashboard-button";

type RuntimeMetric = {
  label: string;
  value: number | null;
  tone: "neutral" | "success" | "warning" | "danger";
};

type AgentRuntimeOverviewProps = {
  loading: boolean;
  runnerSourceAvailable: boolean;
  hasManagedAgent: boolean;
  hasOnlineRunner: boolean;
  lastActiveAt: string | null;
  generatedAt: string;
  environment: string | null;
  openAttention: number | null;
  actionsControlled: number | null;
  completedActions: number | null;
  pendingApprovals: number | null;
  proofGenerated: number | null;
};

type RuntimeState = "connected" | "offline" | "waiting" | "attention" | "unavailable";

const runtimeCopy: Record<RuntimeState, { title: string; detail: string }> = {
  connected: {
    title: "Connected",
    detail: "The managed agent is reporting from an active runtime.",
  },
  offline: {
    title: "Runner offline",
    detail: "The managed agent has not reported from an active runtime.",
  },
  waiting: {
    title: "Waiting for runner",
    detail: "Connect a runner before this agent can execute protected actions.",
  },
  attention: {
    title: "Needs attention",
    detail: "The runtime is connected, but an agent action needs review.",
  },
  unavailable: {
    title: "Runtime status unavailable",
    detail: "Runner status could not be loaded for this project.",
  },
};

function runtimeState(props: AgentRuntimeOverviewProps): RuntimeState {
  if (!props.runnerSourceAvailable) return "unavailable";
  if (!props.hasOnlineRunner && props.hasManagedAgent) return "offline";
  if (!props.hasOnlineRunner) return "waiting";
  if ((props.openAttention ?? 0) > 0) return "attention";
  return "connected";
}

function RuntimeIcon({ state }: { state: RuntimeState }) {
  if (state === "connected") return <Wifi aria-hidden="true" size={21} />;
  if (state === "offline") return <WifiOff aria-hidden="true" size={21} />;
  if (state === "attention") return <AlertTriangle aria-hidden="true" size={21} />;
  return <RadioTower aria-hidden="true" size={21} />;
}

function displayCount(value: number | null): string {
  return value == null ? "—" : new Intl.NumberFormat("en-US").format(value);
}

function environmentLabel(value: string | null): string {
  if (!value) return "—";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function lastActiveLabel(value: string | null, generatedAt: string): string {
  if (!value) return "No activity yet";
  const activityMs = new Date(value).getTime();
  const generatedMs = new Date(generatedAt).getTime();
  if (!Number.isFinite(activityMs) || !Number.isFinite(generatedMs)) return "Activity time unavailable";
  const minutes = Math.max(0, Math.round((generatedMs - activityMs) / 60_000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export function AgentRuntimeOverview(props: AgentRuntimeOverviewProps) {
  if (props.loading) {
    return (
      <section className="mc-agent-runtime mc-agent-runtime-loading" aria-label="Agent runtime loading">
        <span className="mc-skeleton mc-skeleton-label" />
        <span className="mc-skeleton mc-skeleton-value" />
        <span className="mc-skeleton mc-skeleton-line" />
      </section>
    );
  }

  const state = runtimeState(props);
  const copy = runtimeCopy[state];
  const lastActive = lastActiveLabel(props.lastActiveAt, props.generatedAt);
  const metrics: RuntimeMetric[] = [
    { label: "Actions controlled", value: props.actionsControlled, tone: "neutral" },
    { label: "Completed", value: props.completedActions, tone: "success" },
    { label: "Pending approvals", value: props.pendingApprovals, tone: "warning" },
    { label: "Proof generated", value: props.proofGenerated, tone: "neutral" },
  ];
  const action = state === "offline" || state === "waiting"
    ? { href: "/agents/setup", label: "View setup" }
    : state === "attention"
      ? { href: "/actions", label: "Resolve issue" }
      : null;

  return (
    <section className="mc-agent-runtime" aria-labelledby="agent-runtime-title">
      <header className="mc-runtime-header">
        <h2 id="agent-runtime-title">Agent runtime</h2>
        <p>Current execution status and recent agent activity.</p>
      </header>

      <div className="mc-runtime-layout">
        <div className="mc-runtime-status" data-state={state}>
          <span className="mc-runtime-status-icon"><RuntimeIcon state={state} /></span>
          <div className="mc-runtime-status-copy">
            <small>Status</small>
            <strong>{copy.title}</strong>
            <p>{copy.detail}</p>
          </div>
          <dl>
            <div><dt>Last active</dt><dd>{lastActive}</dd></div>
            <div><dt>Environment</dt><dd>{environmentLabel(props.environment)}</dd></div>
            <div><dt>Open attention</dt><dd>{props.openAttention == null ? "—" : props.openAttention}</dd></div>
          </dl>
          {action ? <DashboardButtonLink href={action.href} variant="primary">{action.label}</DashboardButtonLink> : null}
        </div>

        <div className="mc-runtime-summary">
          <div className="mc-runtime-metrics" aria-label="Execution summary">
            {metrics.map((metric) => (
              <article key={metric.label} data-tone={metric.tone}>
                <span><i aria-hidden="true" />{metric.label}</span>
                <strong>{displayCount(metric.value)}</strong>
              </article>
            ))}
          </div>
          {state === "offline" || state === "waiting" ? (
            <p className="mc-runtime-context">
              Runner connection is required before actions can complete and proof can be generated.
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
