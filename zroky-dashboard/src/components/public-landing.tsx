"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  Circle,
  CircleDashed,
  ClipboardCheck,
  Copy,
  TerminalSquare,
  XCircle,
} from "lucide-react";
import { motion, useReducedMotion, type Variants } from "motion/react";
import { FaInstagram, FaLinkedinIn, FaTwitter } from "react-icons/fa";

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 18 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.46, ease: "easeOut" },
  },
};

const stagger: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.065, delayChildren: 0.05 },
  },
};

const traceSteps = [
  { label: "User prompt", time: "10:21:14.101", detail: "How do I check my refund status?", state: "done" },
  { label: "Model response", time: "10:21:14.901", detail: "I'll look that up for you.", state: "done" },
  { label: "Tool call", time: "10:21:15.023", detail: "get_refund_status(order_id)", state: "done", meta: "1.2s" },
  { label: "Failure", time: "10:21:16.341", detail: "ToolExecutionError: timeout", state: "failed", meta: "5.3s" },
  { label: "Replay required", time: "No passing run for this change", detail: "Open in Replay", state: "pending" },
];

const proofRail = [
  { label: "Captured", time: "10:21:14", state: "done" },
  { label: "Diagnosed", time: "10:21:16", state: "done" },
  { label: "Replay needed", time: "10:21:16", state: "failed" },
  { label: "Golden pending", time: "-", state: "pending" },
  { label: "CI unprotected", time: "-", state: "failed" },
];

const evidenceChain = [
  ["01", "Capture", "Prompt, tools, output, model, owner"],
  ["02", "Diagnose", "Root cause and affected traces"],
  ["03", "Replay", "Original run against fixed behavior"],
  ["04", "Promote", "Passing replay becomes a golden"],
  ["05", "Gate", "CI blocks the repeated failure"],
];

const capturePayload = [
  ["prompt", "How do I check my refund status?"],
  ["model", "gpt-4.1"],
  ["tool_calls", "get_refund_status(order_id)"],
  ["output", "Your refund is being processed."],
  ["latency", "7.8s"],
  ["cost", "$0.0234"],
  ["owner", "CX Automation"],
  ["trace_id", "trc_8f3bd6e27a6b4cf1"],
  ["run_id", "run_01H82JK8709Q4Y20"],
];

const eventStream = [
  ["10:21:14.101", "user.prompt"],
  ["10:21:14.901", "model.response"],
  ["10:21:15.023", "tool.call", "get_refund_status"],
  ["10:21:16.341", "tool.error", "timeout"],
  ["10:21:16.341", "run.failed"],
];

const modelProviders = [
  { name: "OpenAI", detail: "Responses API, tools, usage, latency" },
  { name: "Anthropic", detail: "Messages, tool calls, token cost" },
  { name: "Gemini", detail: "Model output, safety metadata, traces" },
  { name: "OpenRouter", detail: "Provider routing and normalized runs" },
  { name: "Local model", detail: "Self-hosted endpoints and custom spans" },
  { name: "Custom provider", detail: "Bring any model through the capture API" },
];

const modelSignals = ["prompt", "model", "tool_calls", "latency", "tokens", "cost", "trace_id", "owner"];

const socialLinks = [
  { label: "LinkedIn", href: "#linkedin", Icon: FaLinkedinIn },
  { label: "Instagram", href: "#instagram", Icon: FaInstagram },
  { label: "Twitter", href: "#twitter", Icon: FaTwitter },
];

const footerLinks = [
  { label: "Privacy", href: "/privacy" },
  { label: "Security", href: "/security" },
  { label: "Contact", href: "/contact" },
];

const moduleViews = [
  {
    key: "issues",
    label: "Issues",
    headline: "23 grouped failures",
    subline: "Refund status timeout repeating across production runs.",
    left: "Root cause",
    right: "Tool timeout when refund lookup exceeds 5s.",
    status: "Review",
  },
  {
    key: "trace",
    label: "Trace",
    headline: "Span timeline",
    subline: "Prompt, model, tool call, failure, and owner in one run.",
    left: "Failed span",
    right: "tool.error to timeout",
    status: "Failed",
  },
  {
    key: "calls",
    label: "Calls",
    headline: "Live call queue",
    subline: "Recent agent calls with model, tool, latency, and cost.",
    left: "support-agent",
    right: "7.8s - $0.0234",
    status: "Captured",
  },
  {
    key: "replay",
    label: "Replay",
    headline: "Original vs fixed run",
    subline: "Replay proves the tool call and answer changed.",
    left: "Skipped get_refund_status(order_id)",
    right: "Called get_refund_status(order_id)",
    status: "Passed",
  },
  {
    key: "goldens",
    label: "Goldens",
    headline: "Refund status protected flow",
    subline: "Passed replay promoted into a regression contract.",
    left: "Contract",
    right: "Tool-call required",
    status: "Promoted",
  },
  {
    key: "ci",
    label: "CI Gates",
    headline: "PR #43 blocked",
    subline: "Golden gate caught a repeated refund regression.",
    left: "zroky/golden-gate",
    right: "Blocked regression",
    status: "Failed",
  },
  {
    key: "readiness",
    label: "Readiness",
    headline: "82% release ready",
    subline: "Open replay gaps and failed gates before deploy.",
    left: "Open risks",
    right: "2 failing gates",
    status: "Needs work",
  },
];

const replayDiff = [
  ["Tool call", "Skipped: get_refund_status", "Called: get_refund_status"],
  ["Model output", "Generic answer about refund process.", "Account-specific refund status."],
  ["Result", "Failed (timeout)", "Passed"],
];

const goldenRows = [
  ["Refund status protected flow", "Ensures refund status is fetched via tool call", "May 22, 10:27 AM", "Passed", "Promoted from replay"],
  ["Tool-call required", "Disallows generic answers when tool is available", "May 21, 4:12 PM", "Passed", "Promoted from replay"],
  ["Policy wording preserved", "Protects required policy phrasing in responses", "May 20, 1:05 PM", "Passed", "Promoted from replay"],
];

const architectureNodes = [
  ["Agent app", "Your agents and workflows"],
  ["Zroky SDK / API", "Capture runs, traces, outputs"],
  ["Trace store", "Traces, events, metadata"],
  ["Replay engine", "Deterministic replay and diff"],
  ["Golden registry", "Contracts from passed replays"],
  ["CI gate", "Block regressions before merge"],
];

const controlChips = [
  ["Redaction", "PII and secrets"],
  ["Provider keys", "Customer managed"],
  ["Roles & access", "Granular permissions"],
  ["Audit log", "All actions tracked"],
  ["Retention", "Configurable TTL"],
];

const logoSrc = "/logo.png?v=landing-white";

function StatusIcon({ state }: { state: string }) {
  if (state === "done" || state === "passed") {
    return <CheckCircle2 aria-hidden="true" />;
  }
  if (state === "failed") {
    return <XCircle aria-hidden="true" />;
  }
  if (state === "pending") {
    return <CircleDashed aria-hidden="true" />;
  }
  return <Circle aria-hidden="true" />;
}

function SectionShell({
  id,
  label,
  title,
  children,
  className = "",
}: {
  id?: string;
  label: string;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.section
      id={id}
      className={`zlp-section ${className}`}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.18 }}
      variants={stagger}
    >
      <motion.div className="zlp-section-intro" variants={fadeUp}>
        <span>{label}</span>
        <h2>{title}</h2>
      </motion.div>
      {children}
    </motion.section>
  );
}

export function PublicLanding() {
  const shouldReduceMotion = useReducedMotion();
  const [activeModule, setActiveModule] = useState("replay");
  const [copyState, setCopyState] = useState<"idle" | "copied">("idle");
  const [dashboardAction, setDashboardAction] = useState("Replay diff is selected.");

  useEffect(() => {
    if (shouldReduceMotion) {
      return;
    }

    const interval = window.setInterval(() => {
      setActiveModule((current) => {
        const index = moduleViews.findIndex((view) => view.key === current);
        return moduleViews[(index + 1) % moduleViews.length].key;
      });
    }, 3400);

    return () => window.clearInterval(interval);
  }, [shouldReduceMotion]);

  const selectedModule = useMemo(
    () => moduleViews.find((view) => view.key === activeModule) ?? moduleViews[3],
    [activeModule],
  );
  const sdkSnippet = `import OpenAI from "openai";
import { init, traceRun, wrap } from "@zroky-ai/sdk";

init({
  apiKey: process.env.ZROKY_API_KEY,
  projectId: process.env.ZROKY_PROJECT_ID,
  endpoint: "https://api.zroky.com/v1/ingest",
  agentName: "support-bot",
  workflowName: "refund-status",
  environment: "production",
});

const openai = wrap(new OpenAI());

await traceRun({ name: "refund-status-check", userInput: "Where is my refund?" }, async () => {
  const response = await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [{ role: "user", content: "Check refund status for order 1421." }],
  });
  return response.choices[0]?.message?.content ?? "";
});`;

  const copySdkSnippet = async () => {
    try {
      await navigator.clipboard?.writeText(sdkSnippet);
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 1800);
    } catch {
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 1800);
    }
  };

  const heroMotion = shouldReduceMotion
    ? { initial: false as const }
    : {
        initial: { opacity: 0, y: 18 },
        animate: { opacity: 1, y: 0 },
        transition: { duration: 0.5, ease: "easeOut" as const },
      };

  return (
    <div className="zroky-public">
      <nav className="zlp-nav" aria-label="Public navigation">
        <Link href="/" className="zlp-brand" aria-label="Zroky home">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={logoSrc} alt="Zroky" />
        </Link>
        <div className="zlp-nav-links">
          <a href="#capture">Product</a>
          <a href="#models">Models</a>
          <a href="#modules">Modules</a>
          <a href="#docs">Docs</a>
        </div>
        <div className="zlp-nav-actions">
          <Link href="/login" className="zlp-link-button">
            Sign in
          </Link>
          <Link href="/signup" className="zlp-primary-button">
            Start workspace
          </Link>
        </div>
      </nav>

      <main>
        <section className="zlp-hero" aria-labelledby="zroky-hero-title">
          <motion.div className="zlp-hero-copy" {...heroMotion}>
            <span className="zlp-hero-kicker">AI agent reliability control plane</span>
            <h1 id="zroky-hero-title">Fix failed agent runs before they ship again</h1>
            <p>Capture the exact run, replay the fix, promote a golden, and block regressions in CI.</p>
            <div className="zlp-hero-actions">
              <Link href="/signup" className="zlp-primary-button zlp-primary-button-lg">
                Start workspace
              </Link>
              <a href="#docs" className="zlp-secondary-button">
                View docs
                <ArrowRight aria-hidden="true" />
              </a>
            </div>
            <div className="zlp-hero-proofline" aria-label="Reliability workflow preview">
              <span>Trace captured</span>
              <span>Replay required</span>
              <span>Golden pending</span>
              <span>CI unprotected</span>
            </div>
          </motion.div>

          <motion.div className="zlp-hero-product" aria-label="Failed agent run debugger" {...heroMotion}>
            <div className="zlp-product-statusbar">
              <span>live run monitor</span>
              <strong>support-bot failed on refund status</strong>
              <em>Replay required</em>
            </div>
            <div className="zlp-theatre-rail" aria-label="Active reliability route">
              <span>production trace</span>
              <strong>Failure routed to Replay</strong>
              <span>golden gate waiting</span>
            </div>
            <div className="zlp-debugger-grid">
              <article className="zlp-code-panel">
                <div className="zlp-panel-top">
                  <span>SDK (TypeScript)</span>
                  <button type="button" aria-label="Copy SDK snippet" onClick={copySdkSnippet}>
                    {copyState === "copied" ? <ClipboardCheck aria-hidden="true" /> : <Copy aria-hidden="true" />}
                    {copyState === "copied" ? "Copied" : "Copy"}
                  </button>
                </div>
                <pre>{sdkSnippet}</pre>
              </article>

              <article className="zlp-timeline-panel">
                <div className="zlp-panel-top">
                  <span>Trace timeline</span>
                  <strong>auto focus</strong>
                </div>
                <div className="zlp-timeline">
                  {traceSteps.map((step) => (
                    <div key={step.label} className={`zlp-timeline-row is-${step.state}`}>
                      <StatusIcon state={step.state} />
                      <div>
                        <div className="zlp-timeline-head">
                          <strong>{step.label}</strong>
                          {step.meta ? <span>{step.meta}</span> : null}
                        </div>
                        <small>{step.time}</small>
                        <p>{step.detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </article>

              <article className="zlp-inspector-panel">
                <div className="zlp-panel-top">
                  <span>Failure details</span>
                  <strong className="is-failed">Failed</strong>
                </div>
                <dl>
                  <div><dt>Status</dt><dd>Failed</dd></div>
                  <div><dt>Trace ID</dt><dd>trc_8f3bd6e27a6b4cf1</dd></div>
                  <div><dt>Provider</dt><dd>OpenAI</dd></div>
                  <div><dt>Model</dt><dd>gpt-4.1</dd></div>
                  <div><dt>Owner</dt><dd>CX Automation</dd></div>
                  <div><dt>Latency</dt><dd>7.8s</dd></div>
                  <div><dt>Cost</dt><dd>$0.0234</dd></div>
                </dl>
                <div className="zlp-root-cause">
                  <span>Root cause</span>
                  <code>ToolExecutionError: timeout get_refund_status took &gt; 5s</code>
                </div>
                <div className="zlp-inspector-actions">
                  <a href="#modules" className="zlp-primary-button">
                    Open in Replay
                  </a>
                  <a href="#capture" className="zlp-secondary-button">
                    Add to issues
                  </a>
                </div>
              </article>
            </div>

            <div className="zlp-proof-rail" aria-label="Run protection status">
              {proofRail.map((item, index) => (
                <div key={item.label} className={`zlp-proof-step is-${item.state}`}>
                  <StatusIcon state={item.state} />
                  <div>
                    <strong>{item.label}</strong>
                    <span>{item.time}</span>
                  </div>
                  {index < proofRail.length - 1 ? <ArrowRight aria-hidden="true" /> : null}
                </div>
              ))}
            </div>
          </motion.div>
        </section>

        <motion.section
          className="zlp-evidence-chain"
          aria-label="Zroky reliability workflow"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.28 }}
          variants={stagger}
        >
          {evidenceChain.map(([step, title, copy]) => (
            <motion.article key={step} variants={fadeUp}>
              <span>{step}</span>
              <strong>{title}</strong>
              <p>{copy}</p>
            </motion.article>
          ))}
        </motion.section>

        <SectionShell id="capture" label="SDK capture" title="Capture real agent runs with one SDK call.">
          <motion.div className="zlp-capture-grid" variants={fadeUp}>
            <div className="zlp-mini-code">
              <div className="zlp-panel-top">
                <span>captureRun(...)</span>
                <TerminalSquare aria-hidden="true" />
              </div>
              <pre>{`await zroky.captureRun({
  agent: "support-bot",
  provider: "openai",
  model: "gpt-4.1",
  trace: true,
  output: true
});`}</pre>
            </div>
            <div className="zlp-payload-panel">
              <h3>Captured run payload</h3>
              <dl>
                {capturePayload.map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="zlp-event-panel">
              <div className="zlp-table-head">
                <h3>Event stream</h3>
                <a href="#modules">View full trace</a>
              </div>
              <div className="zlp-event-list">
                {eventStream.map(([time, event, meta]) => (
                  <div key={`${time}-${event}`}>
                    <span>{time}</span>
                    <strong>{event}</strong>
                    {meta ? <small>{meta}</small> : null}
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        </SectionShell>

        <SectionShell id="models" label="Model support" title="One reliability layer across your model stack.">
          <motion.div className="zlp-model-row" variants={fadeUp}>
            {modelProviders.map((provider) => (
              <article key={provider.name}>
                <strong>{provider.name}</strong>
                <span>{provider.detail}</span>
              </article>
            ))}
          </motion.div>
          <motion.div className="zlp-model-contract" variants={fadeUp}>
            <span>Normalized evidence fields</span>
            <div>
              {modelSignals.map((signal) => (
                <code key={signal}>{signal}</code>
              ))}
            </div>
          </motion.div>
          <motion.div className="zlp-adapter-flow" variants={fadeUp}>
            {[
              ["Agent app", "Your agents and workflows"],
              ["Zroky SDK / API", "Capture runs and traces"],
              ["Provider metadata", "Models, tools, usage, costs"],
              ["Trace evidence", "Debugging and regression proof"],
            ].map(([title, copy], index, items) => (
              <div key={title} className="zlp-flow-item">
                <article>
                  <strong>{title}</strong>
                  <span>{copy}</span>
                </article>
                {index < items.length - 1 ? <ArrowRight aria-hidden="true" /> : null}
              </div>
            ))}
          </motion.div>
        </SectionShell>

        <SectionShell id="modules" label="Dashboard" title="The dashboard zooms into the part that matters.">
          <motion.div className="zlp-module-stage" variants={fadeUp}>
            <div className="zlp-module-notes">
              <div>
                <span>auto zoom</span>
                <p>Selected module: <strong>{selectedModule.label}</strong></p>
              </div>
              <small>{selectedModule.subline}</small>
            </div>
            <div className="zlp-dashboard-shell" aria-live="polite">
              <aside>
                <strong>Zroky</strong>
                <small>acme-cx</small>
                <nav aria-label="Dashboard modules">
                  {moduleViews.map((module) => (
                    <button
                      key={module.key}
                      type="button"
                      className={module.key === activeModule ? "is-active" : ""}
                      onClick={() => setActiveModule(module.key)}
                    >
                      {module.label}
                    </button>
                  ))}
                </nav>
              </aside>
              <section className="zlp-dashboard-main">
                <div className="zlp-table-head">
                  <div>
                    <span>{selectedModule.label}</span>
                    <h3>{selectedModule.headline}</h3>
                  </div>
                  <div className="zlp-dashboard-actions">
                    <button type="button" onClick={() => setDashboardAction("Replay comparison is open.")}>
                      Compare
                    </button>
                    <button type="button" onClick={() => setDashboardAction("Shareable proof link is ready.")}>
                      Share
                    </button>
                  </div>
                </div>
                <p>{selectedModule.subline}</p>
                <div className={`zlp-focus-panel is-${selectedModule.key}`}>
                  <div>
                    <span>Original</span>
                    <code>{selectedModule.left}</code>
                  </div>
                  <div>
                    <span>Fixed / state</span>
                    <code>{selectedModule.right}</code>
                  </div>
                  <strong>{selectedModule.status}</strong>
                </div>
                <div className="zlp-delta-grid">
                  <div><span>Latency</span><strong>7.8s to 2.1s</strong><small>-73%</small></div>
                  <div><span>Cost</span><strong>$0.0234 to $0.0061</strong><small>-74%</small></div>
                  <div><span>Tokens</span><strong>1,284 to 612</strong><small>-52%</small></div>
                </div>
                <div className="zlp-dashboard-live-note" role="status">{dashboardAction}</div>
              </section>
            </div>
            <div className="zlp-module-tabs">
              {moduleViews.map((module) => (
                <button
                  key={module.key}
                  type="button"
                  className={module.key === activeModule ? "is-active" : ""}
                  onClick={() => setActiveModule(module.key)}
                >
                  <span>{module.headline}</span>
                  <strong>{module.label}</strong>
                </button>
              ))}
            </div>
          </motion.div>
        </SectionShell>

        <SectionShell id="proof" label="Replay proof" title="A fix is not accepted until the replay proves it.">
          <motion.div className="zlp-replay-proof" variants={fadeUp}>
            <div className="zlp-table-head">
              <div>
                <span>Original run (failed)</span>
                <h3>run_01H82JK8709Q4Y20</h3>
              </div>
              <strong className="is-failed">Failed</strong>
              <div>
                <span>Replayed run (fixed)</span>
                <h3>run_01H82L189P9QSX11</h3>
              </div>
              <strong className="is-passed">Passed</strong>
            </div>
            <div className="zlp-diff-table">
              {replayDiff.map(([label, before, after]) => (
                <div key={label}>
                  <span>{label}</span>
                  <code className="is-before">{before}</code>
                  <code className="is-after">{after}</code>
                </div>
              ))}
            </div>
          </motion.div>
        </SectionShell>

        <section className="zlp-section zlp-proof-split" aria-label="Golden contracts and release gates">
          <motion.article
            className="zlp-golden-panel"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.18 }}
            variants={fadeUp}
          >
            <span className="zlp-small-label">Golden contracts</span>
            <h2>Passed replays become regression contracts.</h2>
            <div className="zlp-contract-table">
              {goldenRows.map(([name, desc, replay, status, source]) => (
                <div key={name}>
                  <div className="zlp-contract-main">
                    <strong>{name}</strong>
                    <span>{desc}</span>
                  </div>
                  <div className="zlp-contract-meta">
                    <small>{replay}</small>
                    <em>{status}</em>
                    <small>{source}</small>
                  </div>
                </div>
              ))}
            </div>
            <a href="#modules" className="zlp-text-link">
              View all goldens <ArrowRight aria-hidden="true" />
            </a>
          </motion.article>

          <motion.article
            className="zlp-ci-panel"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.18 }}
            variants={fadeUp}
          >
            <span className="zlp-small-label">CI / Release gate</span>
            <h2>Regressions stop before merge.</h2>
            <div className="zlp-pr-check is-failed">
              <XCircle aria-hidden="true" />
              <div>
                <strong>PR #43 - Update refund flow</strong>
                <span>zroky/golden-gate - Blocked regression</span>
                <small>Failed golden: Refund status protected flow</small>
              </div>
              <button type="button">View details</button>
            </div>
            <div className="zlp-pr-check is-passed">
              <CheckCircle2 aria-hidden="true" />
              <div>
                <strong>PR #42 - Improve policy wording</strong>
                <span>zroky/golden-gate - All goldens passed</span>
                <small>2 goldens run - 0 failed</small>
              </div>
              <button type="button">View details</button>
            </div>
          </motion.article>
        </section>

        <SectionShell id="docs" label="Architecture" title="Built to fit your stack.">
          <motion.div className="zlp-architecture" variants={fadeUp}>
            <div className="zlp-architecture-flow">
              {architectureNodes.map(([title, copy], index) => (
                <div key={title} className="zlp-architecture-node">
                  <article>
                    <strong>{title}</strong>
                    <span>{copy}</span>
                  </article>
                  {index < architectureNodes.length - 1 ? <ArrowRight aria-hidden="true" /> : null}
                </div>
              ))}
            </div>
            <div className="zlp-control-chips">
              {controlChips.map(([label, copy]) => (
                <span key={label}>
                  <strong>{label}</strong>
                  {copy}
                </span>
              ))}
            </div>
          </motion.div>
        </SectionShell>

        <motion.section
          className="zlp-final-cta"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.22 }}
          variants={fadeUp}
        >
          <h2>Start with one failing agent run</h2>
          <p>Add the SDK, capture a run, and fix the root cause in minutes.</p>
          <div className="zlp-hero-actions">
            <Link href="/signup" className="zlp-primary-button zlp-primary-button-lg">
              Start workspace
            </Link>
            <a href="#docs" className="zlp-secondary-button">
              SDK docs
            </a>
          </div>
        </motion.section>
      </main>

      <footer className="zlp-footer">
        <span>© 2026 Zroky</span>
        <nav className="zlp-footer-links" aria-label="Footer links">
          {footerLinks.map(({ label, href }) => (
            <Link key={label} href={href}>
              {label}
            </Link>
          ))}
        </nav>
        <nav className="zlp-footer-social" aria-label="Social media">
          {socialLinks.map(({ label, href, Icon }) => (
            <a key={label} href={href} aria-label={label}>
              <Icon aria-hidden="true" />
            </a>
          ))}
        </nav>
      </footer>
    </div>
  );
}
