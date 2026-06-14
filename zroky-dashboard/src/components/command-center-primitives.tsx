"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { CheckCircle2, Code2, KeyRound, LockKeyhole, PlayCircle, Route, Terminal } from "lucide-react";

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
  return (
    <button
      type="button"
      className={`fi-kpi-card${active ? " is-active" : ""}`}
      onClick={onClick}
      aria-pressed={active}
    >
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

const onboardingSteps = [
  "Create a project key for capture.",
  "Install the SDK or route traffic through the Gateway.",
  "Run one real agent call from staging or production.",
  "Confirm the trace appears in Zroky.",
  "Use stub replay for a first sanity check.",
  "Connect your provider key only when verified replay needs to run.",
];

export function FirstRunOnboarding() {
  return (
    <section className="fi-onboarding" aria-label="First capture setup">
      <div className="fi-onboarding-top">
        <div className="fi-onboarding-copy">
          <span className="fi-section-kicker">First capture setup</span>
          <h2>Capture your first agent failure.</h2>
          <p>
            Start by sending one agent call to Zroky. Capture works without a provider key; verified replay asks for
            your key only when the replay actually runs.
          </p>
          <div className="fi-onboarding-actions">
            <Link href="/settings/keys" className="btn btn-primary btn-sm fi-btn-primary">
              <KeyRound aria-hidden="true" />
              Create project key
            </Link>
            <Link href="/trace" className="btn btn-soft btn-sm fi-btn-secondary">
              <PlayCircle aria-hidden="true" />
              Confirm first trace
            </Link>
          </div>
        </div>

        <div className="fi-onboarding-flow" aria-label="Capture to verified replay path">
          {["Capture", "Issue", "Stub replay", "Provider key", "Verified replay"].map((step, index) => (
            <div className="fi-onboarding-flow-step" key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{step}</strong>
            </div>
          ))}
        </div>
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
              <h3>Provider key timing</h3>
              <p>Provider keys are only needed later for verified replay.</p>
            </div>
          </div>
          <p>
            Capture, issues, traces, and stub replay stay usable without a provider key. Verified replay uses your
            provider account so model spend remains visible to your team.
          </p>
          <Link href="/settings/providers" className="btn btn-soft btn-sm fi-btn-secondary">
            <KeyRound aria-hidden="true" />
            Open provider settings
          </Link>
        </article>
      </div>

      <div className="fi-onboarding-checklist" aria-label="First run checklist">
        <div>
          <span className="fi-section-kicker">Recommended order</span>
          <h3>Do not start with replay. Start with evidence.</h3>
        </div>
        <ol>
          {onboardingSteps.map((step) => (
            <li key={step}>
              <CheckCircle2 aria-hidden="true" />
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
