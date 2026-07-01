"use client";

import type { ProofChainStep } from "@/lib/action-view";

type ProofChainStepperProps = {
  steps: ProofChainStep[];
  onStepSelect?: (step: ProofChainStep) => void;
  variant?: "default" | "compact" | "evidence";
};

export function ProofChainStepper({ onStepSelect, steps, variant = "default" }: ProofChainStepperProps) {
  const className = variant === "default"
    ? "evidence-receipt-stepper"
    : `evidence-receipt-stepper evidence-receipt-stepper--${variant}`;

  return (
    <nav className={className} aria-label="Proof chain">
      {steps.map((step) => (
        <button
          key={step.step}
          type="button"
          className="evidence-receipt-step"
          data-tone={step.tone}
          aria-label={`${step.label}: ${step.status}`}
          onClick={() => onStepSelect?.(step)}
        >
          <span className="evidence-receipt-step-dot" aria-hidden="true" />
          <span className="evidence-receipt-step-label">{step.label}</span>
          <span className="evidence-receipt-step-status">{step.status}</span>
        </button>
      ))}
    </nav>
  );
}
