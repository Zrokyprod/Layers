"use client";

import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  FileSearch,
  FileCheck2,
  RadioTower,
  ShieldCheck,
} from "lucide-react";

import { DashboardButtonLink } from "@/components/dashboard-button";

export type FirstRunSignals = {
  hasProjectKey: boolean;
  hasActiveAgent: boolean;
  hasRunnerConnected: boolean;
  hasVerificationConnected: boolean;
  hasActionIntent: boolean;
  hasProofSignal: boolean;
  hasReceiptGenerated: boolean;
};

const STEPS = [
  {
    id: "runner",
    label: "Connect runner",
    detail: "Connect the execution path that will run approved actions.",
    completeDetail: "Runner connected.",
    cta: "Connect runner",
    href: "/agents/setup?intent=connect-runner&source=home",
    icon: RadioTower,
  },
  {
    id: "verification",
    label: "Connect source-of-record",
    detail: "Connect the system Zroky checks after an action runs.",
    completeDetail: "Verification connected.",
    cta: "Connect verification",
    href: "/integrations",
    icon: FileSearch,
  },
  {
    id: "action",
    label: "Run first protected action",
    detail: "Send one real action through policy before execution.",
    completeDetail: "First action reached Zroky.",
    cta: "Run first action",
    href: "/agents/setup",
    icon: ShieldCheck,
  },
  {
    id: "receipt",
    label: "Generate first receipt",
    detail: "Verify the action and create the first signed receipt.",
    completeDetail: "Receipt generated.",
    cta: "Review receipt",
    href: "/evidence",
    icon: FileCheck2,
  },
] as const;

type StepState = "done" | "current" | "locked";

function stepState(stepId: (typeof STEPS)[number]["id"], signals: FirstRunSignals): StepState {
  if (stepId === "runner") {
    return signals.hasRunnerConnected ? "done" : "current";
  }
  if (stepId === "verification") {
    if (signals.hasVerificationConnected) return "done";
    return signals.hasRunnerConnected ? "current" : "locked";
  }
  if (stepId === "action") {
    if (signals.hasActionIntent) return "done";
    return signals.hasRunnerConnected && signals.hasVerificationConnected ? "current" : "locked";
  }
  if (signals.hasReceiptGenerated) return "done";
  return signals.hasActionIntent ? "current" : "locked";
}

function stepDetail(step: (typeof STEPS)[number], state: StepState, signals: FirstRunSignals): string {
  if (state === "done") {
    return step.completeDetail;
  }
  if (step.id === "action" && state === "current" && signals.hasActiveAgent) {
    return "Agent is protected. Run the first controlled action.";
  }
  if (step.id === "action" && state === "current") {
    return "Connect one agent, then run the first action.";
  }
  if (step.id === "receipt" && state === "current") {
    return "Verify the outcome and generate the receipt.";
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
  if (stepId === "runner") {
    return "Runner connected";
  }
  if (stepId === "verification") {
    return "Verification connected";
  }
  if (stepId === "action") {
    return "Action controlled";
  }
  return "Receipt generated";
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
          <span>Setup checklist</span>
        </div>
        <div>
          <p className="mc-eyebrow">First run</p>
          <h2>Get Home reporting real activity</h2>
          <p className="mc-muted">
            Connect the runtime and verification path, then run one protected action and generate its receipt.
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
                  <span>{stepDetail(step, state, signals)}</span>
                </div>
                <div className="mc-step-foot">
                  <span className="mc-step-hint">{stepHint(step.id, state)}</span>
                  {state === "current" ? (
                    <DashboardButtonLink href={step.href} icon={<ArrowRight />} iconPosition="right" size="sm" variant="primary">
                      {step.cta}
                    </DashboardButtonLink>
                  ) : null}
                  {step.id === "runner" && state === "current" ? (
                    <Link className="mc-step-text-link" href="/agents">
                      Agents protected
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
