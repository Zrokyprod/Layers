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

const STEPS = [
  {
    label: "Install SDK",
    detail: "Add the verified action client to one agent runtime.",
    href: "/settings/keys",
    icon: Code2,
  },
  {
    label: "Submit action",
    detail: "Create an action intent with a contract and digest.",
    href: "/agents/setup",
    icon: ShieldCheck,
  },
  {
    label: "Approve and prove",
    detail: "Use dashboard or Slack approval, then inspect the receipt.",
    href: "/evidence",
    icon: FileCheck2,
  },
] as const;

export function FirstRunPanel() {
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
            Finish this path once. The live Home dashboard behind this panel opens when Zroky sees a project key,
            active agent, action intent, approval, or receipt.
          </p>
        </div>
      </div>
      <ol className="mc-first-run-steps">
        {STEPS.map((step, index) => {
          const Icon = step.icon;
          return (
            <li key={step.label}>
              <Link className="mc-first-run-step-card" href={step.href}>
                <span className="mc-step-index">{index + 1}</span>
                <span className="mc-step-icon" aria-hidden="true">
                  <Icon size={18} />
                </span>
                <span className="mc-step-copy">
                  <strong>{step.label}</strong>
                  <span>{step.detail}</span>
                </span>
                <ArrowRight aria-hidden="true" className="mc-step-arrow" size={15} />
              </Link>
            </li>
          );
        })}
      </ol>
      <div className="mc-first-run-footer">
        <div className="mc-first-run-progress" aria-label="First run progress">
          {STEPS.map((step, index) => (
            <span className={index === 0 ? "is-current" : ""} key={step.label}>
              {index + 1}
            </span>
          ))}
        </div>
        <div className="mc-first-run-actions">
          <DashboardButtonLink href="/agents/setup" icon={<ShieldCheck />} variant="primary">
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
