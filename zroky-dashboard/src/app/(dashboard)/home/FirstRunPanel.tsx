"use client";

import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  Code2,
  FileCheck2,
  KeyRound,
  ShieldCheck,
} from "lucide-react";

import { DashboardButtonLink } from "@/components/dashboard-button";

export type FirstRunSignals = {
  hasProjectKey: boolean;
  hasActiveAgent: boolean;
  hasActionIntent: boolean;
  hasProofSignal: boolean;
};

const STEPS = [
  {
    id: "key",
    label: "Install SDK",
    detail: "Add the verified action client to one agent runtime.",
    completeDetail: "Project key is ready for the SDK runtime.",
    href: "/agents/setup?intent=protect-agent&source=home",
    icon: Code2,
  },
  {
    id: "action",
    label: "Submit action",
    detail: "Create an action intent with a contract and digest.",
    completeDetail: "First action intent reached the control plane.",
    href: "/agents/setup",
    icon: ShieldCheck,
  },
  {
    id: "proof",
    label: "Approve and prove",
    detail: "Use dashboard or Slack approval, then inspect the receipt.",
    completeDetail: "Approval, receipt, or outcome proof is available.",
    href: "/evidence",
    icon: FileCheck2,
  },
] as const;

type StepState = "done" | "current" | "locked";

function stepState(stepId: (typeof STEPS)[number]["id"], signals: FirstRunSignals): StepState {
  if (stepId === "key") {
    return signals.hasProjectKey ? "done" : "current";
  }
  if (stepId === "action") {
    if (signals.hasActionIntent) return "done";
    return signals.hasProjectKey ? "current" : "locked";
  }
  if (signals.hasProofSignal) return "done";
  return signals.hasActionIntent ? "current" : "locked";
}

function stepDetail(step: (typeof STEPS)[number], state: StepState, signals: FirstRunSignals): string {
  if (state === "done") {
    return step.completeDetail;
  }
  if (step.id === "action" && state === "current" && signals.hasActiveAgent) {
    return "Agent profile is active. Send the first verified action.";
  }
  if (step.id === "action" && state === "current") {
    return "Create an active agent profile, then submit the first intent.";
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

export function FirstRunPanel({ signals }: { signals: FirstRunSignals }) {
  const states = STEPS.map((step) => stepState(step.id, signals));
  const currentIndex = states.findIndex((state) => state === "current");

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
              <Link className="mc-first-run-step-card" href={step.href} data-state={state}>
                <span className="mc-step-index">
                  {state === "done" ? <CheckCircle2 aria-hidden="true" size={14} /> : index + 1}
                </span>
                <span className="mc-step-icon" aria-hidden="true">
                  <Icon size={18} />
                </span>
                <span className="mc-step-copy">
                  <strong>{step.label}</strong>
                  <span>{stepDetail(step, state, signals)}</span>
                </span>
                <span className="mc-step-state">{stateLabel(state)}</span>
                <ArrowRight aria-hidden="true" className="mc-step-arrow" size={15} />
              </Link>
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
        <div className="mc-first-run-actions">
          <DashboardButtonLink href="/agents/setup?intent=protect-agent&source=home" icon={<ShieldCheck />} variant="primary">
            Start agent setup
          </DashboardButtonLink>
          <DashboardButtonLink href="/settings/keys" icon={<KeyRound />} variant="soft">
            Project keys
          </DashboardButtonLink>
          <DashboardButtonLink href="/actions" icon={<ArrowRight />} iconPosition="right" variant="ghost">
            Actions
          </DashboardButtonLink>
        </div>
      </div>
    </section>
  );
}
