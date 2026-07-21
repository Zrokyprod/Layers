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
  hasAssurancePack: boolean;
  hasActionIntent: boolean;
  hasProofSignal: boolean;
  hasReceiptGenerated: boolean;
};

const STEPS = [
  {
    id: "source",
    label: "Connect source-of-record",
    detail: "Connect the system Zroky checks after an action runs.",
    completeDetail: "Source-of-record connected.",
    cta: "Connect source",
    href: "/integrations",
    icon: FileSearch,
  },
  {
    id: "pack",
    label: "Define Assurance Pack",
    detail: "Define what correct means before Zroky verifies outcomes.",
    completeDetail: "Assurance Pack signal found.",
    cta: "Define pack",
    href: "/workflows",
    icon: ShieldCheck,
  },
  {
    id: "agent",
    label: "Connect agent",
    detail: "Connect the agent or issuer whose actions will be governed.",
    completeDetail: "Agent connected.",
    cta: "Connect agent",
    href: "/operations",
    icon: RadioTower,
  },
  {
    id: "verified",
    label: "See first verified run",
    detail: "Run one protected action and verify it against the source of truth.",
    completeDetail: "First verified run found.",
    cta: "View evidence",
    href: "/evidence",
    icon: FileCheck2,
  },
] as const;

type StepState = "done" | "current" | "locked";

function stepState(stepId: (typeof STEPS)[number]["id"], signals: FirstRunSignals): StepState {
  if (stepId === "source") {
    return signals.hasVerificationConnected ? "done" : "current";
  }
  if (stepId === "pack") {
    if (signals.hasAssurancePack) return "done";
    return signals.hasVerificationConnected ? "current" : "locked";
  }
  if (stepId === "agent") {
    if (signals.hasActiveAgent || signals.hasRunnerConnected) return "done";
    return signals.hasVerificationConnected && signals.hasAssurancePack ? "current" : "locked";
  }
  if (signals.hasReceiptGenerated || signals.hasProofSignal) return "done";
  return (signals.hasActiveAgent || signals.hasRunnerConnected) && signals.hasAssurancePack ? "current" : "locked";
}

function stepDetail(step: (typeof STEPS)[number], state: StepState, signals: FirstRunSignals): string {
  if (state === "done") {
    return step.completeDetail;
  }
  if (step.id === "agent" && state === "current") {
    return "Bring one agent onto the governed rail.";
  }
  if (step.id === "verified" && state === "current") {
    return "Generate one proven outcome and signed evidence.";
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
  if (stepId === "source") {
    return "Connect source now";
  }
  if (stepId === "pack") {
    return "Define policy now";
  }
  if (stepId === "agent") {
    return "Connect agent now";
  }
  return "Verify first run now";
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
            Connect proof, define correctness, bring one agent onto the rail, then verify the first run.
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
                  {step.id === "agent" && state === "current" ? (
                    <Link className="mc-step-text-link" href="/operations">
                      Open Operations
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
