"use client";

import { ArrowRight } from "lucide-react";

import { DashboardButtonLink } from "@/components/dashboard-button";

const STEPS = [
  { label: "Install SDK", detail: "Add the verified action client to one agent runtime." },
  { label: "Submit action", detail: "Create an action intent with a contract and digest." },
  { label: "Approve and prove", detail: "Use dashboard or Slack approval, then inspect the receipt." },
] as const;

export function FirstRunPanel() {
  return (
    <section className="mc-first-run" aria-label="First run setup">
      <div>
        <p className="mc-eyebrow">First run</p>
        <h2>Protect your first agent action</h2>
        <p className="mc-muted">
          Start with one real business action. Zroky will hold, approve, execute, verify, and receipt it through the kernel path.
        </p>
      </div>
      <ol className="mc-first-run-steps">
        {STEPS.map((step) => (
          <li key={step.label}>
            <strong>{step.label}</strong>
            <span>{step.detail}</span>
          </li>
        ))}
      </ol>
      <DashboardButtonLink href="/agents/setup" icon={<ArrowRight />} iconPosition="right" variant="primary">
        Set up agent
      </DashboardButtonLink>
    </section>
  );
}
