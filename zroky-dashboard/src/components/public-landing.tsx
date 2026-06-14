"use client";

import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  CheckCircle2,
  Code2,
  Database,
  GitBranch,
  Gauge,
  KeyRound,
  Layers3,
  LockKeyhole,
  PlayCircle,
  Radar,
  RefreshCcw,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { motion, useReducedMotion, type Variants } from "motion/react";

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 18 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.48, ease: "easeOut" },
  },
};

const stagger: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.07, delayChildren: 0.08 },
  },
};

const proofMetrics = [
  { label: "Failed runs captured", value: "18.4k", tone: "danger" },
  { label: "Replay proofs verified", value: "96.8%", tone: "success" },
  { label: "Golden contracts active", value: "412", tone: "amber" },
  { label: "CI gates protected", value: "37", tone: "neutral" },
];

const previewRows = [
  { label: "Run", value: "support-agent/tool-call-timeout", tone: "danger" },
  { label: "Owner", value: "CX Automation", tone: "neutral" },
  { label: "Replay", value: "Verified against fixed prompt", tone: "success" },
  { label: "Gate", value: "Blocking repeat failure in CI", tone: "amber" },
];

const workflowSteps = [
  {
    icon: Radar,
    title: "Capture",
    copy: "Collect the full failed run: prompt, model, tools, latency, cost, output, and owner.",
  },
  {
    icon: Activity,
    title: "Diagnose",
    copy: "Group noisy failures into the issue that matters, with evidence the team can inspect.",
  },
  {
    icon: PlayCircle,
    title: "Replay",
    copy: "Run the exact scenario again and prove whether a fix actually changes behavior.",
  },
  {
    icon: Database,
    title: "Promote",
    copy: "Turn a verified replay into a golden contract for the behavior you never want to lose.",
  },
  {
    icon: GitBranch,
    title: "Gate",
    copy: "Attach the contract to CI and release checks so regressions stop before users see them.",
  },
  {
    icon: Gauge,
    title: "Observe",
    copy: "Track ownership, drift, cost, and release readiness from one control plane.",
  },
] satisfies Array<{ icon: LucideIcon; title: string; copy: string }>;

const productPanels = [
  {
    icon: AlertTriangle,
    eyebrow: "Issues",
    title: "Turn scattered failures into owned incidents.",
    copy: "Zroky groups production agent failures, assigns severity, and keeps the evidence attached to the owner.",
    rows: ["Root cause summary", "Affected traces", "Owner and status", "Replay requirement"],
  },
  {
    icon: RefreshCcw,
    eyebrow: "Replay",
    title: "Verify fixes against the exact failure.",
    copy: "Replay runs make prompt, model, tool, and output changes visible before a team closes the issue.",
    rows: ["Original vs fixed output", "Tool-call diff", "Latency and cost delta", "Reviewer proof"],
  },
  {
    icon: ShieldCheck,
    eyebrow: "Goldens",
    title: "Promote proof into regression contracts.",
    copy: "Accepted replays become golden traces that protect behavior through CI and deploy readiness.",
    rows: ["Golden registry", "Contract drift", "CI gate status", "Release evidence"],
  },
];

const enterpriseControls = [
  { icon: KeyRound, title: "Protected access", copy: "Password and OAuth entry points with session-safe dashboard routing." },
  { icon: Code2, title: "SDK capture path", copy: "Instrument agents and push traces without changing the product workflow." },
  { icon: LockKeyhole, title: "Provider key flow", copy: "Keep model-provider credentials controlled while teams run diagnosis and replay." },
  { icon: Layers3, title: "Readiness evidence", copy: "Tie issues, replays, goldens, and CI status into the launch checklist." },
] satisfies Array<{ icon: LucideIcon; title: string; copy: string }>;

const plans = [
  {
    name: "Pilot",
    copy: "For one team proving the reliability loop on live agent traffic.",
    cta: "Start workspace",
    href: "/signup",
    features: ["Failure capture", "Issue triage", "Replay proof"],
  },
  {
    name: "Team",
    copy: "For product and platform teams shipping multiple agent workflows.",
    cta: "Start workspace",
    href: "/signup",
    features: ["Golden contracts", "CI gates", "Owner dashboards"],
    featured: true,
  },
  {
    name: "Enterprise",
    copy: "For regulated or high-scale AI-agent programs that need release evidence.",
    cta: "Sign in",
    href: "/login",
    features: ["Governance reviews", "Provider controls", "Readiness proof"],
  },
];

export function PublicLanding() {
  const shouldReduceMotion = useReducedMotion();
  const revealProps = shouldReduceMotion
    ? { initial: false as const }
    : {
        initial: "hidden",
        whileInView: "visible",
        viewport: { once: true, amount: 0.22 },
        variants: fadeUp,
      };
  const staggerProps = shouldReduceMotion
    ? { initial: false as const }
    : {
        initial: "hidden",
        whileInView: "visible",
        viewport: { once: true, amount: 0.18 },
        variants: stagger,
      };
  const heroMotion = shouldReduceMotion
    ? { initial: false as const }
    : {
        initial: { opacity: 0, y: 20 },
        animate: { opacity: 1, y: 0 },
        transition: { duration: 0.55, ease: "easeOut" as const },
      };

  return (
    <div className="zroky-public">
      <nav className="zlp-nav" aria-label="Public navigation">
        <Link href="/" className="zlp-brand" aria-label="Zroky home">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/zroky-dashboard-logo.png" alt="Zroky" />
        </Link>
        <div className="zlp-nav-links">
          <a href="#product">Product</a>
          <a href="#workflow">Workflow</a>
          <a href="#enterprise">Enterprise</a>
          <a href="#pricing">Pricing</a>
          <a href="#docs">Docs</a>
        </div>
        <div className="zlp-nav-actions">
          <Link href="/login" className="zlp-link-button">Sign in</Link>
          <Link href="/signup" className="zlp-primary-button">
            Start workspace
            <ArrowRight aria-hidden="true" />
          </Link>
        </div>
      </nav>

      <main>
        <section className="zlp-hero" aria-labelledby="zroky-hero-title">
          <motion.div className="zlp-hero-copy" {...heroMotion}>
            <span className="zlp-kicker">Built for AI-agent reliability teams</span>
            <h1 id="zroky-hero-title">AI Agent Reliability Control Plane</h1>
            <p>
              Zroky turns failed production agent runs into trace evidence, replay proof, golden contracts, and release
              gates so teams can ship AI systems with control.
            </p>
            <div className="zlp-hero-actions">
              <Link href="/signup" className="zlp-primary-button zlp-primary-button-lg">
                Create reliability workspace
                <ArrowRight aria-hidden="true" />
              </Link>
              <a href="#workflow" className="zlp-secondary-button">
                See the proof loop
              </a>
            </div>
            <div className="zlp-proof-strip" aria-label="Reliability proof metrics">
              {proofMetrics.map((metric) => (
                <span key={metric.label} className={`zlp-proof-chip is-${metric.tone}`}>
                  <strong>{metric.value}</strong>
                  {metric.label}
                </span>
              ))}
            </div>
          </motion.div>

          <motion.div className="zlp-hero-product" aria-label="Zroky product preview" {...heroMotion}>
            <div className="zlp-preview-toolbar">
              <div>
                <span>Command center</span>
                <strong>Release readiness</strong>
              </div>
              <BadgeCheck aria-hidden="true" />
            </div>
            <div className="zlp-preview-grid">
              <div className="zlp-preview-main">
                <div className="zlp-incident-head">
                  <span>P1 reliability issue</span>
                  <strong>Checkout agent repeated bad refund policy answer</strong>
                </div>
                <div className="zlp-preview-rows">
                  {previewRows.map((row, index) => (
                    <motion.div
                      key={row.label}
                      className={`zlp-preview-row is-${row.tone}`}
                      initial={shouldReduceMotion ? false : { opacity: 0, x: -14 }}
                      animate={shouldReduceMotion ? undefined : { opacity: 1, x: 0 }}
                      transition={{ duration: 0.42, delay: 0.16 + index * 0.08, ease: "easeOut" as const }}
                    >
                      <span>{row.label}</span>
                      <strong>{row.value}</strong>
                    </motion.div>
                  ))}
                </div>
              </div>
              <div className="zlp-preview-side">
                <span>Replay proof</span>
                <strong>Passed</strong>
                <p>Fixed prompt now preserves policy and asks for missing order context.</p>
              </div>
            </div>
            <div className="zlp-preview-footer">
              <span>Golden promoted</span>
              <span>CI gate active</span>
              <span>Owner notified</span>
            </div>
          </motion.div>
        </section>

        <motion.section id="workflow" className="zlp-section zlp-workflow-section" {...staggerProps}>
          <motion.div className="zlp-section-heading" variants={fadeUp}>
            <span className="zlp-section-label">Reliability loop</span>
            <h2>One product flow from incident to protected release.</h2>
            <p>
              The page does not sell abstract AI observability. It shows the operational path your team needs when an
              agent fails in front of a real customer.
            </p>
          </motion.div>
          <div className="zlp-workflow-grid">
            {workflowSteps.map((step, index) => (
              <motion.article key={step.title} className="zlp-workflow-card" variants={fadeUp}>
                <span className="zlp-step-index">{String(index + 1).padStart(2, "0")}</span>
                <step.icon aria-hidden="true" />
                <h3>{step.title}</h3>
                <p>{step.copy}</p>
              </motion.article>
            ))}
          </div>
        </motion.section>

        <motion.section id="product" className="zlp-section" {...staggerProps}>
          <motion.div className="zlp-section-heading" variants={fadeUp}>
            <span className="zlp-section-label">Product surface</span>
            <h2>Designed around the evidence senior teams actually review.</h2>
            <p>
              Zroky keeps the problem, the proof, and the release decision in the same workspace instead of scattering
              them across logs, prompts, spreadsheets, and CI output.
            </p>
          </motion.div>
          <div className="zlp-product-grid">
            {productPanels.map((panel) => (
              <motion.article key={panel.title} className="zlp-product-panel" variants={fadeUp}>
                <div className="zlp-panel-icon">
                  <panel.icon aria-hidden="true" />
                </div>
                <span>{panel.eyebrow}</span>
                <h3>{panel.title}</h3>
                <p>{panel.copy}</p>
                <ul>
                  {panel.rows.map((row) => (
                    <li key={row}>
                      <CheckCircle2 aria-hidden="true" />
                      {row}
                    </li>
                  ))}
                </ul>
              </motion.article>
            ))}
          </div>
        </motion.section>

        <motion.section id="enterprise" className="zlp-section zlp-enterprise-section" {...revealProps}>
          <div className="zlp-enterprise-copy">
            <span className="zlp-section-label">Enterprise controls</span>
            <h2>The control plane layer between agent code and production risk.</h2>
            <p>
              The landing page should make one thing obvious: Zroky is not a prompt playground. It is the operating
              layer for teams accountable for AI-agent behavior, regressions, cost, and release evidence.
            </p>
          </div>
          <div className="zlp-control-list">
            {enterpriseControls.map((control) => (
              <article key={control.title}>
                <control.icon aria-hidden="true" />
                <div>
                  <h3>{control.title}</h3>
                  <p>{control.copy}</p>
                </div>
              </article>
            ))}
          </div>
        </motion.section>

        <motion.section id="pricing" className="zlp-section" {...staggerProps}>
          <motion.div className="zlp-section-heading" variants={fadeUp}>
            <span className="zlp-section-label">Plans</span>
            <h2>Start with the reliability loop, then scale to release governance.</h2>
            <p>
              The commercial story stays simple: capture failures, prove fixes, promote goldens, and gate releases.
            </p>
          </motion.div>
          <div className="zlp-plan-grid">
            {plans.map((plan) => (
              <motion.article key={plan.name} className={plan.featured ? "zlp-plan-card is-featured" : "zlp-plan-card"} variants={fadeUp}>
                <span>{plan.name}</span>
                <h3>{plan.name === "Team" ? "Scale agent reliability" : plan.name === "Pilot" ? "Prove the loop" : "Govern at release"}</h3>
                <p>{plan.copy}</p>
                <ul>
                  {plan.features.map((feature) => (
                    <li key={feature}>
                      <CheckCircle2 aria-hidden="true" />
                      {feature}
                    </li>
                  ))}
                </ul>
                <Link href={plan.href} className={plan.featured ? "zlp-primary-button" : "zlp-secondary-button"}>
                  {plan.cta}
                </Link>
              </motion.article>
            ))}
          </div>
        </motion.section>

        <motion.section id="docs" className="zlp-section zlp-docs-section" {...revealProps}>
          <div>
            <span className="zlp-section-label">Developer path</span>
            <h2>Instrument once. Review failures in the workspace.</h2>
            <p>
              The developer path is intentionally short: add the SDK capture, route traces to Zroky, and let the product
              create evidence your team can replay, promote, and gate.
            </p>
          </div>
          <div className="zlp-code-surface" aria-label="SDK capture example">
            <div className="zlp-code-top">
              <span>agent.ts</span>
              <strong>capture enabled</strong>
            </div>
            <pre>{`import { zroky } from "@zroky/sdk";

await zroky.captureRun({
  agent: "checkout-agent",
  owner: "CX Automation",
  trace: run.trace,
  result: run.output,
});`}</pre>
          </div>
        </motion.section>

        <motion.section className="zlp-final-cta" {...revealProps}>
          <ShieldCheck aria-hidden="true" />
          <h2>Build the reliability layer before the next agent failure becomes a release blocker.</h2>
          <p>
            Start with one production agent, capture real failures, and turn the first verified fix into a golden gate.
          </p>
          <div className="zlp-hero-actions">
            <Link href="/signup" className="zlp-primary-button zlp-primary-button-lg">
              Start Zroky
              <ArrowRight aria-hidden="true" />
            </Link>
            <Link href="/login" className="zlp-secondary-button">
              Sign in
            </Link>
          </div>
        </motion.section>
      </main>

      <footer className="zlp-footer">
        <div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/zroky-dashboard-logo.png" alt="Zroky" />
          <p>AI-agent reliability control plane for traces, replay proof, goldens, CI gates, and release readiness.</p>
        </div>
        <nav aria-label="Footer navigation">
          <a href="#product">Product</a>
          <a href="#workflow">Workflow</a>
          <a href="#enterprise">Enterprise</a>
          <a href="#pricing">Pricing</a>
          <a href="#docs">Docs</a>
        </nav>
      </footer>
    </div>
  );
}
