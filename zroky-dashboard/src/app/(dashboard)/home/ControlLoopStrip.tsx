"use client";

import Link from "next/link";
import {
  ArrowRight,
  Bot,
  FileCheck2,
  PlayCircle,
  ReceiptText,
  Route,
  ShieldCheck,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import { formatCount } from "@/lib/format";

type LoopStep = {
  id: string;
  label: string;
  detail: string;
  href: string;
  stat: string;
  Icon: LucideIcon;
};

export type ControlLoopStats = {
  actionCount: number;
  approvalCount: number;
  verifiedCount: number;
  receiptCount: number;
  bypassCount: number;
  sequenceRiskCount: number;
};

const LOOP_LINKS = [
  { label: "Agents", href: "/agents" },
  { label: "Policies", href: "/policies" },
  { label: "Approvals", href: "/approvals" },
  { label: "Outcomes", href: "/outcomes" },
  { label: "Evidence", href: "/evidence" },
  { label: "Connectors", href: "/integrations" },
] as const;

export function ControlLoopStrip({
  actionCount,
  approvalCount,
  verifiedCount,
  receiptCount,
  bypassCount,
  sequenceRiskCount,
}: ControlLoopStats) {
  const sequenceRiskLabel = sequenceRiskCount > 0 ? "Sequence risk caught" : "Sequence risk watch";
  const steps: LoopStep[] = [
    {
      id: "propose",
      label: "Propose",
      detail: "Agent submits an intent with contract and digest.",
      href: "/actions",
      stat: `${formatCount(actionCount)} intents`,
      Icon: Bot,
    },
    {
      id: "policy",
      label: "Policy",
      detail: "Runtime rules score the action before execution.",
      href: "/policies",
      stat: "Live gate",
      Icon: ShieldCheck,
    },
    {
      id: "approve",
      label: "Approve",
      detail: "Risky calls pause for human or Slack approval.",
      href: "/approvals",
      stat: `${formatCount(approvalCount)} holds`,
      Icon: Route,
    },
    {
      id: "run",
      label: "Run",
      detail: "Approved actions are handed to a trusted runner.",
      href: "/agents",
      stat: "Runner path",
      Icon: PlayCircle,
    },
    {
      id: "verify",
      label: "Verify",
      detail: "Source-of-record checks compare claim to reality.",
      href: "/outcomes",
      stat: `${formatCount(verifiedCount)} verified`,
      Icon: FileCheck2,
    },
    {
      id: "receipt",
      label: "Receipt",
      detail: "Signed receipts prove what was allowed and why.",
      href: "/actions",
      stat: `${formatCount(receiptCount)} receipts`,
      Icon: ReceiptText,
    },
    {
      id: "evidence",
      label: "Evidence",
      detail: "Audit artifacts turn every decision into proof.",
      href: "/evidence",
      stat: "Exportable",
      Icon: FileCheck2,
    },
  ];

  return (
    <section className="mc-loop-panel" aria-labelledby="mc-loop-title">
      <div className="mc-loop-main">
        <div className="mc-loop-head">
          <div>
            <p className="mc-eyebrow">Verified action loop</p>
            <h2 id="mc-loop-title">Propose to evidence, with policy in the middle</h2>
          </div>
          <p>
            Every agent action moves through one control loop: propose, policy, approve, run,
            verify, receipt, evidence.
          </p>
        </div>

        <div className="mc-loop-diagram" aria-label="Verified action control loop">
          {steps.map((step, index) => {
            const Icon = step.Icon;
            return (
              <div className="mc-loop-node-wrap" key={step.id}>
                <Link href={step.href} className="mc-loop-node">
                  <span className="mc-loop-icon">
                    <Icon aria-hidden="true" size={16} />
                  </span>
                  <span className="mc-loop-node-copy">
                    <strong>{step.label}</strong>
                    <span>{step.detail}</span>
                    <em>{step.stat}</em>
                  </span>
                </Link>
                {index < steps.length - 1 ? (
                  <span className="mc-loop-arrow" aria-hidden="true">
                    <ArrowRight size={15} />
                  </span>
                ) : null}
              </div>
            );
          })}
        </div>

        <nav className="mc-loop-nav" aria-label="Control loop modules">
          {LOOP_LINKS.map((item) => (
            <Link href={item.href} key={item.href}>
              {item.label}
            </Link>
          ))}
        </nav>
      </div>

      <aside className="mc-risk-card" aria-label="Sequence risk control">
        <span className="mc-risk-badge">
          <TriangleAlert aria-hidden="true" size={15} />
          {sequenceRiskLabel}
        </span>
        <h3>Stops safe-looking steps that become unsafe together.</h3>
        <p>
          Bulk read, external send, repeated money movement, or credential change can be held
          even when each single action looks normal.
        </p>
        <div className="mc-risk-chain" aria-label="Example risk sequence">
          <span>bulk read</span>
          <ArrowRight aria-hidden="true" size={14} />
          <span>external send</span>
          <ArrowRight aria-hidden="true" size={14} />
          <strong>hold</strong>
        </div>
        <div className="mc-risk-stats">
          <Link href="/approvals">
            <strong>{formatCount(sequenceRiskCount)}</strong>
            <span>sequence holds</span>
          </Link>
          <Link href="/outcomes">
            <strong>{formatCount(bypassCount)}</strong>
            <span>bypass signals</span>
          </Link>
        </div>
      </aside>
    </section>
  );
}
