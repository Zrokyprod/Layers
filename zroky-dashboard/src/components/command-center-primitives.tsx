"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Circle,
  Code2,
  ExternalLink,
  GitPullRequest,
  KeyRound,
  LockKeyhole,
  Route,
  Send,
  ShieldCheck,
  Terminal,
} from "lucide-react";

export type ReadinessState = "good" | "warn" | "blocked" | "neutral";

export function EmptyQueue({ children }: { children: string }) {
  return <div className="fi-empty">{children}</div>;
}

export function QueueList<T>({
  items,
  renderItem,
  empty,
}: {
  items: readonly T[];
  renderItem: (item: T) => ReactNode;
  empty: string;
}) {
  if (items.length === 0) {
    return <EmptyQueue>{empty}</EmptyQueue>;
  }
  return <div className="fi-queue-list">{items.map(renderItem)}</div>;
}

export function LockedUpgradeLink({ label }: { label: string }) {
  return (
    <Link href="/settings/billing" className="btn btn-soft btn-sm fi-btn-secondary" title={label}>
      <LockKeyhole aria-hidden="true" />
      Upgrade
    </Link>
  );
}

export function KpiCard({
  icon,
  label,
  value,
  helper,
  trend,
  active,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  helper: string;
  trend?: string | null;
  active?: boolean;
  onClick?: () => void;
}) {
  const body = (
    <>
      <div className="fi-kpi-topline">
        <span>{label}</span>
        <div className="fi-kpi-card-mark">
          {trend ? <span className="fi-kpi-trend">{trend}</span> : null}
          <div className="fi-kpi-icon">{icon}</div>
        </div>
      </div>
      <strong>{value}</strong>
      <p>{helper}</p>
    </>
  );

  if (!onClick) {
    return <div className={`fi-kpi-card${active ? " is-active" : ""}`}>{body}</div>;
  }

  return (
    <button
      type="button"
      className={`fi-kpi-card${active ? " is-active" : ""}`}
      onClick={onClick}
      aria-pressed={active}
    >
      {body}
    </button>
  );
}

export function SectionHeader({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <header className="fi-section-header">
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      {action ?? (icon ? <div className="fi-section-icon">{icon}</div> : null)}
    </header>
  );
}

export function DetailMetric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="fi-detail-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function DecisionChip({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="fi-decision-chip">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function ReadinessStep({
  icon,
  label,
  value,
  helper,
  state,
  href,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  helper: string;
  state: ReadinessState;
  href: string;
}) {
  return (
    <Link className="fi-readiness-step" data-state={state} href={href}>
      <span className="fi-readiness-icon">{icon}</span>
      <div className="fi-readiness-copy">
        <span>{label}</span>
        <strong>{value}</strong>
        <p>{helper}</p>
      </div>
      <span className="fi-readiness-state" />
    </Link>
  );
}

export function ProofStep({
  icon,
  label,
  helper,
  state,
}: {
  icon: ReactNode;
  label: string;
  helper: string;
  state: ReadinessState;
}) {
  return (
    <div className="fi-proof-step" data-state={state}>
      <span className="fi-proof-icon">{icon}</span>
      <div>
        <strong>{label}</strong>
        <p>{helper}</p>
      </div>
    </div>
  );
}

type SetupState = "done" | "current" | "locked" | "idle";

export function FirstRunOnboarding({
  projectKeyCount,
  capturedCallCount,
  captureStatus,
  providerKeyCount,
  replayUnlocked,
  goldensUnlocked,
  ciUnlocked,
}: {
  projectKeyCount: number;
  capturedCallCount: number;
  captureStatus: "connected" | "stale" | "no_data" | "unknown";
  providerKeyCount: number;
  replayUnlocked: boolean;
  goldensUnlocked: boolean;
  ciUnlocked: boolean;
}) {
  const hasProjectKey = projectKeyCount > 0;
  const hasCapture = capturedCallCount > 0 || captureStatus === "connected" || captureStatus === "stale";
  const nextAction = !hasProjectKey
    ? {
        href: "/settings/keys",
        label: "Create project key",
        title: "Create a project key",
        detail: "Use it from your SDK or Gateway so the first real trace can enter Zroky.",
        icon: <KeyRound aria-hidden="true" />,
      }
    : !hasCapture
      ? {
          href: "/trace",
          label: "Send test capture",
          title: "Send test capture",
          detail: "Run one agent call and confirm the first trace lands in Zroky.",
          icon: <Send aria-hidden="true" />,
        }
      : {
          href: "/trace",
          label: "Review trace",
          title: "Trace capture is ready",
          detail: "When a run fails, this page promotes it into an issue and the next proof action.",
          icon: <CheckCircle2 aria-hidden="true" />,
        };
  const captureLabel =
    capturedCallCount > 0
      ? `${new Intl.NumberFormat().format(capturedCallCount)} captured`
      : captureStatus === "connected"
        ? "Live"
        : captureStatus === "stale"
          ? "Stale"
          : "Waiting";
  const setupSteps: { label: string; detail: string; state: SetupState }[] = [
    {
      label: "Project key",
      detail: hasProjectKey ? "Created" : "In progress",
      state: hasProjectKey ? "done" : "current",
    },
    {
      label: "SDK/Gateway connected",
      detail: hasCapture ? "Connected" : hasProjectKey ? "Waiting" : "Locked",
      state: hasCapture ? "done" : hasProjectKey ? "current" : "locked",
    },
    {
      label: "First trace received",
      detail: hasCapture ? captureLabel : "Waiting",
      state: hasCapture ? "done" : "locked",
    },
    {
      label: "First issue/replay ready",
      detail: hasCapture && replayUnlocked ? "Ready when issue appears" : replayUnlocked ? "Waiting" : "Upgrade later",
      state: hasCapture && replayUnlocked ? "current" : "locked",
    },
  ];
  const healthRows: { label: string; value: string; state: SetupState; icon: ReactNode }[] = [
    {
      label: "API key",
      value: hasProjectKey ? "Created" : "Missing",
      state: hasProjectKey ? "done" : "current",
      icon: <KeyRound aria-hidden="true" />,
    },
    {
      label: "Capture",
      value: hasCapture ? "Connected" : "Waiting",
      state: hasCapture ? "done" : "current",
      icon: <Route aria-hidden="true" />,
    },
    {
      label: "Provider key",
      value: providerKeyCount > 0 ? "Connected" : "Optional",
      state: providerKeyCount > 0 ? "done" : "idle",
      icon: <Terminal aria-hidden="true" />,
    },
    {
      label: "CI",
      value: ciUnlocked ? "Not configured" : "Locked",
      state: ciUnlocked ? "idle" : "locked",
      icon: <GitPullRequest aria-hidden="true" />,
    },
  ];
  const canShowReplayNext = replayUnlocked || goldensUnlocked || ciUnlocked;

  return (
    <section className="fi-setup-cockpit" aria-label="First capture setup">
      <div className="fi-setup-primary-grid">
        <article className="fi-next-setup" aria-label="Next required setup action">
          <span className="fi-setup-icon" aria-hidden="true">
            {nextAction.icon}
          </span>
          <span className="fi-section-kicker">Next required action</span>
          <h3>{nextAction.title}</h3>
          <p>{nextAction.detail}</p>
          <div className="fi-capture-path" aria-label="Developer capture path">
            <span>
              <Code2 aria-hidden="true" />
              SDK
            </span>
            <ArrowRight aria-hidden="true" />
            <span>
              <Route aria-hidden="true" />
              Gateway
            </span>
            <ArrowRight aria-hidden="true" />
            <span>
              <Send aria-hidden="true" />
              Trace
            </span>
          </div>
          <div className="fi-setup-actions">
            <Link href={nextAction.href} className="btn btn-primary btn-sm fi-btn-primary">
              {nextAction.icon}
              {nextAction.label}
            </Link>
            <Link href="/docs" className="fi-inline-link">
              View setup docs
              <ExternalLink aria-hidden="true" />
            </Link>
          </div>
        </article>

        <article className="fi-connection-panel" aria-label="Connection health">
          <h3>Connection health</h3>
          <div className="fi-health-list">
            {healthRows.map((row) => (
              <div className="fi-health-row" data-state={row.state} key={row.label}>
                <span className="fi-health-icon">{row.icon}</span>
                <strong>{row.label}</strong>
                <span className="fi-health-value">
                  <Circle aria-hidden="true" />
                  {row.value}
                </span>
              </div>
            ))}
          </div>
        </article>
      </div>

      <div className="fi-onboarding-flow" aria-label="Command Center setup path">
        <h3>Setup progress</h3>
        {setupSteps.map((step, index) => (
          <div className="fi-onboarding-flow-step" data-state={step.state} key={step.label}>
            <span>{index + 1}</span>
            <div>
              <strong>{step.label}</strong>
              <small>{step.detail}</small>
            </div>
            {step.state === "locked" ? <LockKeyhole aria-hidden="true" /> : null}
          </div>
        ))}
      </div>

      <div className="fi-setup-action-grid" aria-label="Setup options">
        {[
          {
            href: "/settings/keys",
            icon: <Terminal aria-hidden="true" />,
            label: "Install SDK",
            detail: "Add Zroky SDK to your agent.",
            action: "View instructions",
          },
          {
            href: "/settings/keys",
            icon: <Route aria-hidden="true" />,
            label: "Use Gateway",
            detail: "Send traces via API Gateway.",
            action: "Get gateway key",
          },
          {
            href: "/trace",
            icon: <Send aria-hidden="true" />,
            label: "Send test capture",
            detail: "Verify setup with one trace.",
            action: "Send test now",
          },
        ].map((item) => (
          <Link href={item.href} className="fi-setup-action-card" key={item.label}>
            <span className="fi-onboarding-icon">{item.icon}</span>
            <strong>{item.label}</strong>
            <small>{item.detail}</small>
            <span>
              {item.action}
              <ArrowRight aria-hidden="true" />
            </span>
          </Link>
        ))}
      </div>

      <div className="fi-onboarding-checklist" aria-label="What happens next">
        <h3>What happens next</h3>
        <div className="fi-proof-preview" aria-label="Command Center operating model">
          <div>
            <Code2 aria-hidden="true" />
            <span>Trace appears</span>
          </div>
          <div>
            <Terminal aria-hidden="true" />
            <span>Failure becomes issue</span>
          </div>
          <div>
            <ShieldCheck aria-hidden="true" />
            <span>{canShowReplayNext ? "Replay verifies fix" : "Replay unlocks after upgrade"}</span>
          </div>
          <div>
            <GitPullRequest aria-hidden="true" />
            <span>Golden blocks regression</span>
          </div>
        </div>
      </div>
    </section>
  );
}
