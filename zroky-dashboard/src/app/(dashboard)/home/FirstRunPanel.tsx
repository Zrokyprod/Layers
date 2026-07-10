"use client";

import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  KeyRound,
  FileCheck2,
  PackageCheck,
  ShieldCheck,
  UserRoundCheck,
} from "lucide-react";

import { DashboardButtonLink } from "@/components/dashboard-button";

export type FirstRunSignals = {
  agentId: string | null;
  hasProjectKey: boolean;
  hasActiveAgent: boolean;
  hasInstalledActions: boolean;
  hasActionIntent: boolean;
  hasProofSignal: boolean;
};

const STEPS = [
  {
    id: "key",
    label: "Create project key",
    detail: "Create the scoped credential your agent runtime will use.",
    completeDetail: "An active project key is ready.",
    cta: "Start agent setup",
    href: "/agents/setup?intent=protect-agent&source=home",
    icon: KeyRound,
  },
  {
    id: "agent",
    label: "Connect agent",
    detail: "Name one runtime and apply safe fail-closed defaults.",
    completeDetail: "An active agent profile is connected.",
    cta: "Connect agent",
    href: "/agents/setup?intent=protect-agent&source=home",
    icon: UserRoundCheck,
  },
  {
    id: "actions",
    label: "Install protected actions",
    detail: "Choose the exact workflow actions Zroky should govern.",
    completeDetail: "A protected action pack is installed.",
    cta: "Choose actions",
    href: "/agents/setup?intent=protect-agent&source=home",
    icon: PackageCheck,
  },
  {
    id: "action",
    label: "Submit action",
    detail: "Create an action intent with a contract and digest.",
    completeDetail: "First action intent reached the control plane.",
    cta: "Send first action",
    href: "/agents/setup",
    icon: ShieldCheck,
  },
  {
    id: "proof",
    label: "Approve and prove",
    detail: "Use dashboard or Slack approval, then inspect the receipt.",
    completeDetail: "Approval, receipt, or outcome proof is available.",
    cta: "Review proof",
    href: "/evidence",
    icon: FileCheck2,
  },
] as const;

type StepState = "done" | "current" | "locked";

function stepState(stepId: (typeof STEPS)[number]["id"], signals: FirstRunSignals): StepState {
  if (stepId === "key") {
    return signals.hasProjectKey ? "done" : "current";
  }
  if (stepId === "agent") {
    if (signals.hasActiveAgent) return "done";
    return signals.hasProjectKey ? "current" : "locked";
  }
  if (stepId === "actions") {
    if (signals.hasInstalledActions) return "done";
    return signals.hasActiveAgent ? "current" : "locked";
  }
  if (stepId === "action") {
    if (signals.hasActionIntent) return "done";
    return signals.hasInstalledActions ? "current" : "locked";
  }
  if (signals.hasProofSignal) return "done";
  return signals.hasActionIntent ? "current" : "locked";
}

function stepDetail(step: (typeof STEPS)[number], state: StepState): string {
  if (state === "done") {
    return step.completeDetail;
  }
  if (step.id === "action" && state === "current") {
    return "Run the generated SDK example to submit the first intent.";
  }
  if (step.id === "proof" && state === "current") {
    return "Review the decision and inspect the signed evidence.";
  }
  return step.detail;
}

function stateLabel(state: StepState): string {
  if (state === "done") return "Done";
  if (state === "current") return "Now";
  return "Locked";
}

function stepHint(stepId: (typeof STEPS)[number]["id"], state: StepState): string {
  if (state === "done") {
    return "Completed";
  }
  if (state === "locked") {
    return "Unlocks after the previous step";
  }
  if (stepId === "key") {
    return "Create or reuse one active project key.";
  }
  if (stepId === "agent") {
    return "Create one enforced agent profile.";
  }
  if (stepId === "actions") {
    return "Install one launch-ready action pack.";
  }
  if (stepId === "action") {
    return "Run one protected action from your agent runtime.";
  }
  return "Approve the first hold and inspect the signed receipt.";
}

function stepHref(step: (typeof STEPS)[number], signals: FirstRunSignals): string {
  if (step.id === "key" || !signals.agentId) return step.href;
  return `/agents/setup?agentId=${encodeURIComponent(signals.agentId)}&source=home`;
}

export function FirstRunPanel({ signals }: { signals: FirstRunSignals }) {
  const states = STEPS.map((step) => stepState(step.id, signals));
  const currentIndex = states.findIndex((state) => state === "current");
  const completedCount = states.filter((state) => state === "done").length;

  return (
    <section className="mc-first-run" aria-label="First run setup">
      <div className="mc-first-run-copy">
        <div className="mc-first-run-status">
          <CheckCircle2 aria-hidden="true" size={15} />
          <span>Home unlocks after the first protected action signal</span>
        </div>
        <div>
          <p className="mc-eyebrow">First run</p>
          <h2>Protect your first agent action</h2>
          <p className="mc-muted">
            Finish this path once. The live Home dashboard behind this panel opens when Zroky sees the first action
            intent, approval, receipt, or verified outcome.
          </p>
        </div>
      </div>
      <ol className="mc-first-run-steps">
        {STEPS.map((step, index) => {
          const Icon = step.icon;
          const state = states[index];
          return (
            <li key={step.label}>
              <article className="mc-first-run-step-card" data-state={state}>
                <div className="mc-step-head">
                  <span className="mc-step-index">
                    {state === "done" ? <CheckCircle2 aria-hidden="true" size={14} /> : index + 1}
                  </span>
                  <span className="mc-step-icon" aria-hidden="true">
                    <Icon size={18} />
                  </span>
                  <span className="mc-step-state">{stateLabel(state)}</span>
                </div>
                <div className="mc-step-copy">
                  <strong>{step.label}</strong>
                  <span>{stepDetail(step, state)}</span>
                </div>
                <div className="mc-step-foot">
                  <span className="mc-step-hint">{stepHint(step.id, state)}</span>
                  {state === "current" ? (
                    <DashboardButtonLink href={stepHref(step, signals)} icon={<ArrowRight />} iconPosition="right" size="sm" variant="primary">
                      {step.cta}
                    </DashboardButtonLink>
                  ) : null}
                  {step.id === "key" && state === "current" ? (
                    <Link className="mc-step-text-link" href="/settings/keys">
                      Project keys
                    </Link>
                  ) : null}
                </div>
              </article>
            </li>
          );
        })}
      </ol>
      <div className="mc-first-run-footer">
        <div className="mc-first-run-progress" aria-label="First run progress">
          {STEPS.map((step, index) => {
            const state = states[index];
            return (
              <span
                className={`${state === "done" ? "is-done" : ""}${index === currentIndex ? " is-current" : ""}`.trim()}
                key={step.label}
              >
                {state === "done" ? <CheckCircle2 aria-hidden="true" size={13} /> : index + 1}
              </span>
            );
          })}
        </div>
        <p className="mc-first-run-help">{completedCount} of {STEPS.length} setup steps complete.</p>
      </div>
    </section>
  );
}
