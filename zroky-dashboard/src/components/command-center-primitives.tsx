"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import {
  CheckCircle2,
  Code2,
  GitPullRequest,
  KeyRound,
  LockKeyhole,
  PlayCircle,
  Route,
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
  active,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  helper: string;
  active?: boolean;
  onClick?: () => void;
}) {
  const body = (
    <>
      <div className="fi-kpi-topline">
        <span>{label}</span>
        <div className="fi-kpi-card-mark" aria-hidden="true">
          <div className="fi-kpi-spark">
            <span />
            <span />
            <span />
            <span />
          </div>
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
  planLabel,
  eventLimitLabel,
  projectKeyCount,
  capturedCallCount,
  captureStatus,
  providerKeyCount,
  replayUnlocked,
  goldensUnlocked,
  ciUnlocked,
}: {
  planLabel: string;
  eventLimitLabel: string;
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
          label: "Send first trace",
          title: "Send one real agent trace",
          detail: "Run a staging or production agent call and confirm it appears in Traces.",
          icon: <PlayCircle aria-hidden="true" />,
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
      detail: hasProjectKey ? `${projectKeyCount} active key${projectKeyCount === 1 ? "" : "s"}` : "Required first",
      state: hasProjectKey ? "done" : "current",
    },
    {
      label: "Trace capture",
      detail: hasCapture ? captureLabel : "Send one run",
      state: hasCapture ? "done" : hasProjectKey ? "current" : "locked",
    },
    {
      label: "Failure issue",
      detail: hasCapture ? "Waiting for failure" : "Needs evidence",
      state: hasCapture ? "current" : "locked",
    },
    {
      label: "Replay proof",
      detail: replayUnlocked ? "Available" : "Plan locked",
      state: replayUnlocked ? "idle" : "locked",
    },
    {
      label: "Golden / CI",
      detail: goldensUnlocked || ciUnlocked ? "Available after proof" : "Upgrade path",
      state: goldensUnlocked || ciUnlocked ? "idle" : "locked",
    },
  ];
  const unlocks = [
    {
      label: "Provider key",
      value: providerKeyCount > 0 ? `${providerKeyCount} active` : "Add later",
      state: providerKeyCount > 0 ? "done" : "idle",
    },
    {
      label: "Replay",
      value: replayUnlocked ? "Available" : "Locked",
      state: replayUnlocked ? "done" : "locked",
    },
    {
      label: "Goldens",
      value: goldensUnlocked ? "Available" : "Locked",
      state: goldensUnlocked ? "done" : "locked",
    },
    {
      label: "CI gates",
      value: ciUnlocked ? "Available" : "Locked",
      state: ciUnlocked ? "done" : "locked",
    },
  ];

  return (
    <section className="fi-onboarding" aria-label="First capture setup">
      <div className="fi-onboarding-top fi-setup-hero">
        <div className="fi-onboarding-copy">
          <span className="fi-section-kicker">Workspace setup</span>
          <h2>Start with one captured agent run.</h2>
          <p>
            Create a project key, send a real trace, then let failures promote into replay proof, Goldens, and CI
            gates when your plan unlocks them.
          </p>
          <div className="fi-setup-status-grid" aria-label="Workspace setup snapshot">
            <div className="fi-setup-status" data-state="done">
              <span>Plan</span>
              <strong>{planLabel}</strong>
            </div>
            <div className="fi-setup-status">
              <span>Event limit</span>
              <strong>{eventLimitLabel}</strong>
            </div>
            <div className="fi-setup-status" data-state={hasProjectKey ? "done" : "current"}>
              <span>Project key</span>
              <strong>{hasProjectKey ? `${projectKeyCount} active` : "Missing"}</strong>
            </div>
            <div className="fi-setup-status" data-state={hasCapture ? "done" : "current"}>
              <span>Capture</span>
              <strong>{captureLabel}</strong>
            </div>
          </div>
          <div className="fi-onboarding-actions">
            <Link href={nextAction.href} className="btn btn-primary btn-sm fi-btn-primary">
              {nextAction.icon}
              {nextAction.label}
            </Link>
            <Link href="/trace" className="btn btn-soft btn-sm fi-btn-secondary">
              <PlayCircle aria-hidden="true" />
              Open traces
            </Link>
          </div>
        </div>

        <div className="fi-next-setup" aria-label="Next required setup action">
          <span className="fi-section-kicker">Next required action</span>
          <h3>{nextAction.title}</h3>
          <p>{nextAction.detail}</p>
          <Link href={nextAction.href} className="btn btn-primary btn-sm fi-btn-primary">
            {nextAction.icon}
            {nextAction.label}
          </Link>
        </div>
      </div>

      <div className="fi-onboarding-flow" aria-label="Command Center setup path">
        {setupSteps.map((step, index) => (
          <div className="fi-onboarding-flow-step" data-state={step.state} key={step.label}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{step.label}</strong>
            <small>{step.detail}</small>
          </div>
        ))}
      </div>

      <div className="fi-onboarding-grid">
        <article className="fi-onboarding-card">
          <div className="fi-onboarding-card-head">
            <span className="fi-onboarding-icon">
              <Code2 aria-hidden="true" />
            </span>
            <div>
              <h3>SDK capture</h3>
              <p>Wrap the agent call where your application already invokes the model or tool chain.</p>
            </div>
          </div>
          <pre className="fi-onboarding-code" aria-label="Python SDK capture snippet">
            <code>{`pip install zroky
export ZROKY_API_KEY=...

zroky.init()
zroky.call("checkout-agent", input=payload)`}</code>
          </pre>
        </article>

        <article className="fi-onboarding-card">
          <div className="fi-onboarding-card-head">
            <span className="fi-onboarding-icon">
              <Route aria-hidden="true" />
            </span>
            <div>
              <h3>Gateway capture</h3>
              <p>Route provider traffic through Zroky when you cannot change agent code quickly.</p>
            </div>
          </div>
          <pre className="fi-onboarding-code" aria-label="Gateway capture snippet">
            <code>{`docker run -p 8090:8090 \\
  ghcr.io/zroky-ai/zroky-gateway:latest

export OPENAI_BASE_URL=http://localhost:8090/v1`}</code>
          </pre>
        </article>

        <article className="fi-onboarding-card fi-onboarding-provider">
          <div className="fi-onboarding-card-head">
            <span className="fi-onboarding-icon">
              <Terminal aria-hidden="true" />
            </span>
            <div>
              <h3>Unlock sequence</h3>
              <p>Keep capture separate from paid replay work.</p>
            </div>
          </div>
          <div className="fi-unlock-list" aria-label="Plan unlock status">
            {unlocks.map((unlock) => (
              <div className="fi-unlock-row" data-state={unlock.state} key={unlock.label}>
                <span>{unlock.label}</span>
                <strong>{unlock.value}</strong>
              </div>
            ))}
          </div>
          <Link href="/settings/providers" className="btn btn-soft btn-sm fi-btn-secondary">
            <KeyRound aria-hidden="true" />
            Open provider settings
          </Link>
        </article>
      </div>

      <div className="fi-onboarding-checklist" aria-label="First run checklist">
        <div>
          <span className="fi-section-kicker">Operating model</span>
          <h3>Evidence first. Proof after.</h3>
        </div>
        <div className="fi-proof-preview" aria-label="Command Center operating model">
          <div>
            <Code2 aria-hidden="true" />
            <span>Capture a real run</span>
          </div>
          <div>
            <Terminal aria-hidden="true" />
            <span>Diagnose the failure</span>
          </div>
          <div>
            <ShieldCheck aria-hidden="true" />
            <span>Promote verified behavior</span>
          </div>
          <div>
            <GitPullRequest aria-hidden="true" />
            <span>Gate risky releases</span>
          </div>
        </div>
      </div>
    </section>
  );
}
