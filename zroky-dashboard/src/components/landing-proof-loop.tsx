"use client";

import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  CircleDollarSign,
  Code2,
  Database,
  Frown,
  Lock,
  Play,
  PlayCircle,
  Search,
  Shield,
  Timer,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type FailureRun = {
  title: string;
  agent: string;
  age: string;
  icon: LucideIcon;
};

type EvidenceTab = {
  label: string;
  title: string;
  status: string;
  summary: string;
  body: React.ReactNode;
};

const failedRuns: FailureRun[] = [
  { title: "Tool failed", agent: "RefundAgent", age: "2m ago", icon: Wrench },
  { title: "Bad output", agent: "SupportAgent", age: "18m ago", icon: Frown },
  { title: "Timeout loop", agent: "SchedulerAgent", age: "1h ago", icon: Timer },
  { title: "Policy leak", agent: "ContentAgent", age: "3h ago", icon: Lock },
];

const outcomes = [
  { title: "Root cause found", body: "Invalid refund amount format", icon: Search },
  { title: "Replay passed", body: "Exact scenario verified", icon: Play },
  { title: "Golden locked", body: "gld_refund_amount_v1", icon: Database },
  { title: "CI gate ready", body: "Will block regressions", icon: Shield },
  { title: "Cost risk reduced", body: "Est. $1,240/mo saved", icon: CircleDollarSign },
];

const evidenceTabs: EvidenceTab[] = [
  {
    label: "Trace",
    title: "RefundAgent / Run • 9f3a...7c1b",
    status: "Failed",
    summary: "The agent called the tool `process_refund` with an invalid amount format causing a 400 error.",
    body: (
      <>
        <div className="zl-code-block">
          <div>
            <span>Tool call</span>
            <pre>{`{
  "tool": "process_refund",
  "args": {
    "amount": "12,50.00",
    "currency": "USD",
    "order_id": "ord_88321"
  }
}`}</pre>
          </div>
          <div className="zl-code-meta">
            <span>Response</span>
            <strong>400 Bad Request</strong>
            <span>Latency</span>
            <strong>2.48s</strong>
            <span>Cost</span>
            <strong>$0.0321</strong>
          </div>
        </div>
      </>
    ),
  },
  {
    label: "Diagnosis",
    title: "Issue #47 • refund amount schema",
    status: "Root cause",
    summary: "The payment tool changed amount parsing while the agent still emits localized decimal strings.",
    body: (
      <div className="zl-diagnosis-grid">
        <div>
          <span>Root cause</span>
          <strong>Tool contract drift</strong>
          <p>Amount must be canonical decimal, not localized currency text.</p>
        </div>
        <div>
          <span>Blast radius</span>
          <strong>43 failed calls</strong>
          <p>Refund workflows across SupportAgent and RefundAgent.</p>
        </div>
      </div>
    ),
  },
  {
    label: "Replay",
    title: "Replay run • candidate fix",
    status: "Passed",
    summary: "The exact failed scenario was replayed against the candidate prompt/tool guard and matched expected output.",
    body: (
      <div className="zl-diff-grid">
        <div>
          <span>Before</span>
          <strong>400 error, failed task, retry loop</strong>
        </div>
        <div>
          <span>After</span>
          <strong>Refund completed, user notified</strong>
        </div>
      </div>
    ),
  },
  {
    label: "CI Gate",
    title: "Golden suite • refund_v1",
    status: "Ready",
    summary: "The verified replay is promoted to a golden trace and runs as a blocking check before deploy.",
    body: (
      <div className="zl-ci-grid">
        <span>18/18 goldens passing</span>
        <span>Required PR check</span>
        <span>Regression blocked</span>
      </div>
    ),
  },
];

const proofSteps = [
  { title: "Capture", body: "Capture every run with full context, cost and outcome.", icon: Code2 },
  { title: "Diagnose", body: "Group failures and pinpoint the root cause.", icon: Search },
  { title: "Replay", body: "Replay the exact scenario and compare results.", icon: Play },
  { title: "Golden", body: "Promote verified traces as golden behavior.", icon: Database },
  { title: "Gate", body: "Run in CI and block regressions before ship.", icon: Shield },
  { title: "Cost", body: "Reduce repeat failures and save on token spend.", icon: CircleDollarSign },
];

export default function LandingProofLoop() {
  const [active, setActive] = useState(0);
  const activeTab = evidenceTabs[active];

  useEffect(() => {
    const timer = window.setInterval(() => {
      setActive((current) => (current + 1) % evidenceTabs.length);
    }, 4200);
    return () => window.clearInterval(timer);
  }, []);

  const activeRun = useMemo(() => active % failedRuns.length, [active]);

  return (
    <>
      <section className="zl-hero" id="product">
        <div className="zl-hero-copy">
          <span className="zl-badge">AI agent reliability platform</span>
          <h1>
            AI agents fail in production. <span>Zroky</span> proves the fix.
          </h1>
          <p>
            Capture failed runs, find root cause, replay the exact scenario, lock the fix as a golden trace, and block
            regressions in CI.
          </p>
          <div className="zl-actions">
            <Link href="/signup" className="zl-button zl-button-primary">
              Start free
              <ArrowRight aria-hidden="true" />
            </Link>
            <a href="#proof-loop" className="zl-button zl-button-secondary">
              <PlayCircle aria-hidden="true" />
              Watch replay proof
            </a>
          </div>
          <div className="zl-trust">
            <Shield aria-hidden="true" />
            <span>For teams shipping AI agents into production.</span>
          </div>
        </div>

        <div className="zl-hero-system" aria-label="Zroky failure to proof flow">
          <div className="zl-failed-runs">
            <span>Failed runs</span>
            {failedRuns.map((run, index) => {
              const Icon = run.icon;
              return (
                <button
                  key={run.title}
                  type="button"
                  className={index === activeRun ? "zl-run-card is-active" : "zl-run-card"}
                  onClick={() => setActive(index % evidenceTabs.length)}
                >
                  <Icon aria-hidden="true" />
                  <strong>{run.title}</strong>
                  <span>{run.agent}</span>
                  <em>{run.age}</em>
                </button>
              );
            })}
          </div>

          <div className="zl-evidence-panel">
            <div className="zl-tabs" role="tablist" aria-label="Evidence tabs">
              {evidenceTabs.map((tab, index) => (
                <button
                  key={tab.label}
                  type="button"
                  className={index === active ? "is-active" : undefined}
                  onClick={() => setActive(index)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="zl-evidence-head">
              <span>{activeTab.title}</span>
              <strong>{activeTab.status}</strong>
              <em>2m ago</em>
            </div>
            <div className="zl-summary">
              <span>Summary</span>
              <p>{activeTab.summary}</p>
            </div>
            <div className="zl-evidence-body">{activeTab.body}</div>
            <div className="zl-evidence-footer">
              <span>Evidence</span>
              <em>Prompt</em>
              <em>Tools 2</em>
              <em>Retrieval 6</em>
              <em>Logs</em>
              <em>Metrics</em>
            </div>
          </div>

          <div className="zl-outcome-stack">
            {outcomes.map((outcome, index) => {
              const Icon = outcome.icon;
              return (
                <article key={outcome.title} className={index <= active + 1 ? "is-lit" : undefined}>
                  <Icon aria-hidden="true" />
                  <div>
                    <strong>{outcome.title}</strong>
                    <span>{outcome.body}</span>
                  </div>
                  <CheckCircle2 aria-hidden="true" />
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="zl-proof-loop" id="proof-loop">
        <div className="zl-section-label">The proof loop</div>
        <div className="zl-proof-grid">
          {proofSteps.map((step, index) => {
            const Icon = step.icon;
            return (
              <article key={step.title} className={index === active ? "is-active" : undefined}>
                <span className="zl-step-number">{index + 1}</span>
                <div className="zl-step-icon">
                  <Icon aria-hidden="true" />
                </div>
                <h2>{step.title}</h2>
                <p>{step.body}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="zl-slim-section" id="pricing">
        <span className="zl-section-label">Pricing</span>
        <h2>Start free. Upgrade when replay proof protects releases.</h2>
        <div className="zl-pricing-grid">
          <article>
            <span>Free Watch</span>
            <strong>$0</strong>
            <p>Capture first failures and review issue evidence.</p>
          </article>
          <article>
            <span>Pro</span>
            <strong>$299/mo</strong>
            <p>Replay proof, golden traces, CI gates, and cost impact.</p>
          </article>
          <article>
            <span>Team</span>
            <strong>Custom</strong>
            <p>Controls, rollout support, audit, and custom retention.</p>
          </article>
        </div>
      </section>

      <section className="zl-slim-section" id="quickstart">
        <span className="zl-section-label">Docs</span>
        <h2>Connect an agent, capture a failed run, and turn it into proof.</h2>
        <div className="zl-doc-steps">
          <span>Install SDK</span>
          <span>Set project key</span>
          <span>Capture first run</span>
          <span>Replay failure</span>
        </div>
      </section>
    </>
  );
}
