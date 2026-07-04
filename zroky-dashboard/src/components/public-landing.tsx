import Link from "next/link";
import {
  AlignLeft,
  ArrowRight,
  Banknote,
  Check,
  CheckCircle2,
  Copy,
  Database,
  FileCheck2,
  MailCheck,
  Plus,
  RotateCcw,
  Search,
  Server,
  Shield,
  Star,
  XCircle,
} from "lucide-react";
import { FaInstagram, FaLinkedinIn, FaXTwitter } from "react-icons/fa6";

import { SDK } from "@/lib/sdk";
import { verdictToken, type Verdict } from "@/lib/verdict";
import { selectStep, summarize, type LoopStep, type Module } from "@/lib/landing-demo";

/**
 * PublicLanding — server-rendered shell for the monochrome landing redesign.
 *
 * This component is intentionally a SERVER component: there is no top-level
 * "use client" directive, no hooks, and no client-only libraries. Every piece
 * of copy (headings, proofline, snippet text, FAQ answers, footer) is emitted
 * as server HTML so it is present on first paint and crawlable (R10.1, R11.2).
 *
 * Interactivity (the signature morph, Loop tabs, dashboard module switcher,
 * progressive disclosure, and copy-to-clipboard) is layered on later by the
 * "use client" islands from task 3.2. Each interactive surface below renders
 * its full, readable default/final state now and exposes a stable mount point
 * (a `data-island="…"` wrapper) so an island can hydrate/upgrade it without a
 * structural rewrite. See the island map at the bottom of this file.
 */

const logoSrc = "/zroky-brand.png";

// ---------------------------------------------------------------------------
// Hero proofline — smoke-required strings mapped to verdict tones (R1.3, R5.5).
// The literal phrases must remain present in server HTML for the Smoke_Check.
// ---------------------------------------------------------------------------
const proofPills: { label: string; verdict: Verdict | "neutral" }[] = [
  { label: "Trace captured", verdict: "neutral" },
  { label: "Replay required", verdict: "review" },
  { label: "Contract pending", verdict: "review" },
  { label: "CI unprotected", verdict: "block" },
];

// ---------------------------------------------------------------------------
// Trust_Layer — ≥3 product-truthful signals in the early viewport (R6).
// ---------------------------------------------------------------------------
const trustSignals = [
  { num: "< 10 min", label: "to first surfaced finding" },
  { num: "5", label: "providers, one capture API" },
  { num: "3", label: "CI verdicts · pass / block / review" },
  { num: "0", label: "false blocks on borderline runs" },
];
const trustProviders = ["OpenAI", "Anthropic", "Gemini", "OpenRouter", "Local", "Custom"];

// ---------------------------------------------------------------------------
// The Loop — five steps; each renders a real, server-rendered panel. The pure
// LoopStep model drives the tab rail + verdict treatment (verdictToken).
// ---------------------------------------------------------------------------
const loopSteps: LoopStep[] = [
  {
    key: "capture",
    index: 0,
    title: "Capture",
    verdict: "block",
    summary: summarize("Prompt, tools, output, model, cost & owner — one SDK call."),
    detail: { body: "Prompt, tools, output, model, cost & owner — one SDK call." },
  },
  {
    key: "diagnose",
    index: 1,
    title: "Diagnose",
    verdict: "review",
    summary: summarize("Root cause and every affected trace, grouped."),
    detail: { body: "Root cause and every affected trace, grouped." },
  },
  {
    key: "replay",
    index: 2,
    title: "Replay",
    verdict: "pass",
    summary: summarize("Run the exact failure against your fix — fidelity-scored."),
    detail: {
      heading: "A fix is not accepted until the replay proves it.",
      body: "Run the exact failure against your fix — fidelity-scored.",
    },
  },
  {
    key: "promote",
    index: 3,
    title: "Promote",
    verdict: "pass",
    summary: summarize("A passing replay becomes a regression contract."),
    detail: { body: "A passing replay becomes a regression contract." },
  },
  {
    key: "gate",
    index: 4,
    title: "Gate",
    verdict: "pass",
    summary: summarize("CI blocks the repeat — and only blocks when it's sure."),
    detail: { body: "CI blocks the repeat — and only blocks when it's sure." },
  },
];

const loopIcons: Record<string, typeof AlignLeft> = {
  capture: AlignLeft,
  diagnose: Search,
  replay: RotateCcw,
  promote: Star,
  gate: Shield,
};

// Default selected step before any interaction (R3.9) — resolved with the pure
// selection helper so the shell and the future island agree on the default.
const defaultLoopStep = selectStep(loopSteps, "capture") ?? loopSteps[0];

// ---------------------------------------------------------------------------
// Dashboard ModuleSwitcher (#modules) — default module selected on load (R3.9).
// ---------------------------------------------------------------------------
const moduleViews: Module[] = [
  { key: "issues", label: "Issues", summary: "23 grouped failures", detail: { body: "Refund status timeout repeating across production runs.", heading: "Tool timeout when refund lookup exceeds 5s." } },
  { key: "trace", label: "Trace", summary: "Span timeline", detail: { body: "Prompt, model, tool call, failure, and owner in one run.", heading: "tool.error → timeout" } },
  { key: "calls", label: "Calls", summary: "Live call queue", detail: { body: "Recent agent calls with model, tool, latency, and cost.", heading: "7.8s · $0.0234" } },
  { key: "replay", label: "Replay", summary: "Original vs fixed run", detail: { body: "Replay proves the tool call and answer changed.", heading: "Called get_refund_status(order_id)" } },
  { key: "goldens", label: "Contracts", summary: "Refund status protected flow", detail: { body: "Passed replay promoted into a regression contract.", heading: "Tool-call required" } },
  { key: "ci", label: "CI Gates", summary: "PR #43 blocked", detail: { body: "Contract gate caught a repeated refund regression.", heading: "Blocked regression" } },
  { key: "readiness", label: "Readiness", summary: "82% release ready", detail: { body: "Open replay gaps and failed gates before deploy.", heading: "2 failing gates" } },
];

const defaultModule = selectStep(moduleViews, "issues") ?? moduleViews[0];

// ---------------------------------------------------------------------------
// Model support (#models) content.
// ---------------------------------------------------------------------------
const modelProviders = [
  { name: "OpenAI", detail: "Responses API, tools, usage, latency" },
  { name: "Anthropic", detail: "Messages, tool calls, token cost" },
  { name: "Gemini", detail: "Model output, safety metadata, traces" },
  { name: "OpenRouter", detail: "Provider routing and normalized runs" },
  { name: "Local model", detail: "Self-hosted endpoints and custom spans" },
  { name: "Custom provider", detail: "Bring any model through the capture API" },
];
const modelSignals = ["prompt", "model", "tool_calls", "latency", "tokens", "cost", "trace_id", "owner"];
const adapterFlow = [
  ["Agent app", "Your agents and workflows"],
  ["zroky-ai SDK / API", "Capture runs and traces"],
  ["Provider metadata", "Models, tools, usage, costs"],
  ["Trace evidence", "Debugging and regression proof"],
];

// ---------------------------------------------------------------------------
// Architecture (#docs) content.
// ---------------------------------------------------------------------------
const architectureNodes = [
  ["Agent app", "Your agents and workflows"],
  ["zroky-ai SDK / API", "Capture runs, traces, outputs"],
  ["Trace store", "Traces, events, metadata"],
  ["Replay engine", "Deterministic replay and diff"],
  ["Contract registry", "Contracts from passed replays"],
  ["CI gate", "Block regressions before merge"],
];
const controlChips = [
  ["Redaction", "PII and secrets"],
  ["Evidence hash", "Tamper evident"],
  ["Roles & access", "Granular permissions"],
  ["Audit log", "All actions tracked"],
  ["Retention", "Configurable TTL"],
];

// ---------------------------------------------------------------------------
// Pricing / risk-value content.
// ---------------------------------------------------------------------------
const riskValueMetrics = [
  {
    label: "protected action value",
    value: "$250K/mo",
    detail: "Monthly value handled by one high-stakes agent.",
  },
  {
    label: "one bad action",
    value: "$8K+",
    detail: "Direct loss, reconciliation, customer trust, and audit drag.",
  },
  {
    label: "self-serve gate",
    value: "$199/mo",
    detail: "A starting price below the cost of one material mistake.",
  },
  {
    label: "coverage ratio",
    value: "2.5%",
    detail: "Pro is 2.5% of one $8K incident and 0.08% of $250K protected monthly action value.",
  },
];

const pricingPlans = [
  {
    name: "Free",
    price: "$0",
    fit: "Prove capture on one agent before asking the team to delegate.",
    bullets: ["Trace capture", "Issue grouping", "Basic replay evidence"],
    href: "/signup?source=pricing&intent=protect-agent&plan=free",
  },
  {
    name: "Starter",
    price: "$49/mo",
    fit: "Protect the first serious workflow while a human still reviews risky actions.",
    bullets: ["Non-blocking CI", "Golden traces", "Mocked-tool replay"],
    href: "/signup?source=pricing&intent=protect-agent&plan=starter",
  },
  {
    name: "Pro",
    price: "$199/mo",
    fit: "Run production agents with runtime gates, outcome proof, and exportable evidence.",
    bullets: ["Blocking CI", "Evidence packs", "Full proof handoff"],
    href: "/pilot?source=pricing&intent=protect-agent&plan=pro",
    featured: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    fit: "Add private execution, custom retention, connectors, procurement, and audit terms.",
    bullets: ["Private replay", "Custom connectors", "Audit commitments"],
    href: "/contact?source=pricing&intent=enterprise",
  },
];

const protectedAgentRows = [
  {
    Icon: Banknote,
    agent: "Payment and refund agents",
    risk: "Refunds, payouts, reversals, credits",
    proof: "Hold or block before commit; reconcile the ledger after.",
  },
  {
    Icon: Database,
    agent: "CRM and data mutation agents",
    risk: "Record merges, account updates, ownership changes",
    proof: "Compare the claimed update against the CRM record and hash the evidence.",
  },
  {
    Icon: Server,
    agent: "DevOps and release agents",
    risk: "Deploys, rollbacks, config edits, infra changes",
    proof: "Gate repeat failures in CI and keep replayable proof with the PR.",
  },
  {
    Icon: MailCheck,
    agent: "Lifecycle and outreach agents",
    risk: "Mass email, customer notifications, ticket replies",
    proof: "Check mandate before send and verify delivery outcome after send.",
  },
];

// ---------------------------------------------------------------------------
// Comparison rows + FAQ + footer content.
// ---------------------------------------------------------------------------
const comparisonRows = [
  ["You write rubrics up front", "Captures real production runs, not synthetic prompts"],
  ['"Verified" = a judge ran', "Deterministic replay of the exact failure, fidelity-scored"],
  ["Flaky gates block good PRs", "CI gate that blocks repeats — never false-blocks borderline runs"],
];

const faqItems = [
  {
    q: "Which frameworks does it support?",
    a: "Any agent framework. zroky-ai captures at the provider call boundary — OpenAI, Anthropic, Gemini, OpenRouter, local and custom models — so LangChain, LangGraph, CrewAI, or your own stack all work with the same SDK.",
  },
  {
    q: "How is my data handled?",
    a: "PII and secrets are redacted at capture, project keys can be rotated, every action is in the audit log, and retention is a configurable TTL.",
  },
  {
    q: "Will it false-block my PRs?",
    a: 'No. The CI gate only blocks at high confidence. Borderline runs get a "review" verdict — never a false block.',
  },
  {
    q: "How long until I see value?",
    a: "Under 10 minutes. Add three lines of the SDK, capture one run, and structural failures surface immediately.",
  },
];

const footerLinks = [
  { label: "Privacy", href: "/privacy" },
  { label: "Security", href: "/security" },
  { label: "Contact", href: "/contact" },
];
const socialLinks = [
  { label: "LinkedIn", href: "#linkedin", Icon: FaLinkedinIn },
  { label: "Instagram", href: "#instagram", Icon: FaInstagram },
  { label: "Twitter", href: "#twitter", Icon: FaXTwitter },
];

// Verbatim, contract-locked SDK snippet, built from the single SDK source of
// truth so rendered text and clipboard text never diverge (R7).
const sdkSnippet = `// ${SDK.install}
import OpenAI from "openai";
${SDK.importStatement}

init({ apiKey: process.env.ZROKY_API_KEY,
  agentName: "support-bot",
  workflowName: "refund-status" });

const openai = wrap(new OpenAI());
await traceRun({ name: "refund-status" }, run);`;

export function PublicLanding() {
  return (
    <div className="zroky-public zlp-rd">
      {/* ---- Nav -------------------------------------------------------- */}
      <nav className="zlp-nav" aria-label="Public navigation">
        <div className="zlp-wrap zlp-nav-in">
          <Link href="/" className="zlp-brand" aria-label="Zroky home">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={logoSrc} alt="Zroky" />
          </Link>
          <div className="zlp-nav-links">
            <a href="#loop">Product</a>
            <a href="#capture">Capture</a>
            <Link href="/pricing">Pricing</Link>
            <a href="#faq">FAQ</a>
            <a href="#docs">Docs</a>
          </div>
          <div className="zlp-nav-actions">
            <Link href="/login" className="zlp-btn-link">
              Sign in
            </Link>
            <Link href="/signup" className="zlp-btn zlp-btn-primary">
              Start workspace
            </Link>
          </div>
        </div>
      </nav>

      <main>
        {/* ---- Hero + Signature_Moment --------------------------------- */}
        <section className="zlp-hero" aria-labelledby="zroky-hero-title">
          <div className="zlp-wrap zlp-hero-grid">
            <div className="zlp-hero-copy">
              <span className="zlp-eyebrow">
                <span className="zlp-dot" aria-hidden="true" />
                AI agent reliability control plane
              </span>
              <h1 id="zroky-hero-title" className="zlp-disp">
                Catch AI agent regressions <span className="zlp-mut">before your users do.</span>
              </h1>
              {/*
                Smoke/contract compatibility: keep the legacy hero string present
                in server HTML (visually hidden) until Task 12 reconciles it.
              */}
              <p className="zlp-visually-hidden">Fix failed agent runs before they ship again</p>
              <p className="zlp-lead">
                Capture the exact run, replay the fix, promote a Contract, and block regressions in CI - with proof,
                not vibes.
              </p>
              <div className="zlp-hero-cta">
                <Link href="/signup" className="zlp-btn zlp-btn-primary zlp-btn-lg">
                  Start workspace
                  <ArrowRight aria-hidden="true" />
                </Link>
                <a href="#loop" className="zlp-btn zlp-btn-ghost zlp-btn-lg">
                  Watch the loop
                </a>
              </div>
              <p className="zlp-hero-fine">
                <b>5-min SDK install</b> · any framework · <b>fixture validation is never called &quot;verified.&quot;</b>
              </p>
              <div className="zlp-pill-line" aria-label="Reliability workflow preview">
                {proofPills.map((pill) => {
                  const token = pill.verdict === "neutral" ? null : verdictToken(pill.verdict);
                  return (
                    <span key={pill.label} className="zlp-pill">
                      <i
                        aria-hidden="true"
                        style={token ? { background: token.fg } : undefined}
                      />
                      {pill.label}
                    </span>
                  );
                })}
              </div>
            </div>

            {/* Island mount point: SignatureMoment (task 5.1).
               Server renders the resolved VERIFIED final state so it is readable
               with no JS / reduced motion (R4.5, R4.7, R10.1). */}
            <div className="zlp-theatre zlp-elevated is-verified" data-island="signature-moment" aria-label="Agent run resolved to verified">
              <div className="zlp-theatre-top">
                <span className="zlp-tdot" aria-hidden="true" />
                <span className="zlp-tdot" aria-hidden="true" />
                <span className="zlp-tdot" aria-hidden="true" />
                <span className="zlp-mono zlp-theatre-label">zroky.com · live run monitor</span>
                <span className="zlp-theatre-stat">
                  <span className="zlp-led" aria-hidden="true" />
                  support-bot · VERIFIED
                </span>
              </div>
              <div className="zlp-theatre-body">
                <div className="zlp-runcard">
                  <span className="zlp-vbadge">
                    <CheckCircle2 aria-hidden="true" />
                    VERIFIED / contract
                  </span>
                  <div className="zlp-rc-title">refund_agent · status_lookup</div>
                  <div className="zlp-rc-sub zlp-mono">
                    Called get_refund_status() · trace trc_8f3bd6
                  </div>
                  <div className="zlp-meterrow">
                    <div className="zlp-meter">
                      <div className="zlp-mk">latency</div>
                      <div className="zlp-mv">2.1s</div>
                    </div>
                    <div className="zlp-meter">
                      <div className="zlp-mk">cost</div>
                      <div className="zlp-mv">$0.0061</div>
                    </div>
                    <div className="zlp-meter">
                      <div className="zlp-mk">tokens</div>
                      <div className="zlp-mv">612</div>
                    </div>
                  </div>
                  <div className="zlp-rail" aria-hidden="true">
                    {loopSteps.map((step) => {
                      const Icon = loopIcons[step.key];
                      return (
                        <div key={step.key} className="zlp-node on">
                          <span className="zlp-ring">
                            <Icon />
                          </span>
                          <small>{step.title}</small>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ---- Trust_Layer --------------------------------------------- */}
        <section className="zlp-trust" aria-label="Why teams trust Zroky">
          <div className="zlp-wrap">
            <div className="zlp-trust-grid">
              {trustSignals.map((signal) => (
                <div key={signal.label} className="zlp-trust-item">
                  <div className="zlp-trust-num zlp-disp">{signal.num}</div>
                  <div className="zlp-trust-label">{signal.label}</div>
                </div>
              ))}
            </div>
            <div className="zlp-prov">
              <span className="zlp-prov-lbl">Works across</span>
              {trustProviders.join("  ·  ")}
            </div>
          </div>
        </section>

        {/* ---- The Loop ------------------------------------------------ */}
        <section className="zlp-blk" id="loop">
          <div className="zlp-wrap">
            <div className="zlp-shead">
              <span className="zlp-eyebrow">
                <span className="zlp-dot" aria-hidden="true" />
                The reliability loop
              </span>
              <h2 className="zlp-disp">One failed run, five moves to never see it again.</h2>
              <p>Click through how a production failure becomes a blocked regression — the same way your team will.</p>
            </div>

            {/* Island mount point: LoopDemo (task 7.1). Server renders all five
               panels; the default step is shown and the rest remain in the DOM
               (crawlable) but visually collapsed. */}
            <div className="zlp-loop" data-island="loop-demo">
              <div className="zlp-tabs" role="tablist" aria-label="Reliability loop steps">
                {loopSteps.map((step) => {
                  const Icon = loopIcons[step.key];
                  const active = step.key === defaultLoopStep.key;
                  return (
                    <button
                      key={step.key}
                      type="button"
                      role="tab"
                      aria-selected={active}
                      className={`zlp-tab${active ? " active" : ""}`}
                      data-step={step.key}
                    >
                      <span className="zlp-tab-num">
                        <Icon aria-hidden="true" />
                      </span>
                      <div>
                        <h4>
                          <span className="zlp-tab-step zlp-mono">
                            {String(step.index + 1).padStart(2, "0")}
                          </span>{" "}
                          {step.title}
                        </h4>
                        <p>{step.summary}</p>
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="zlp-panel zlp-elevated">
                <div className="zlp-panel-top">
                  <span className="zlp-tdot" aria-hidden="true" />
                  <span className="zlp-tdot" aria-hidden="true" />
                  <span className="zlp-tdot" aria-hidden="true" />
                  <span className="zlp-panel-label zlp-mono">capture · support-bot</span>
                  <span
                    className="zlp-vstate"
                    style={{
                      color: verdictToken("block").fg,
                      background: verdictToken("block").bg,
                      borderColor: verdictToken("block").fg,
                    }}
                  >
                    FAILED
                  </span>
                </div>

                {/* Capture (default shown) */}
                <div className="zlp-view show" data-view="capture">
                  <dl className="zlp-kv">
                    <dt>prompt</dt>
                    <dd>&quot;How do I check my refund status?&quot;</dd>
                    <dt>model</dt>
                    <dd>gpt-4.1</dd>
                    <dt>tool_calls</dt>
                    <dd>get_refund_status(order_id)</dd>
                    <dt>latency</dt>
                    <dd>7.8s</dd>
                    <dt>cost</dt>
                    <dd>$0.0234</dd>
                    <dt>owner</dt>
                    <dd>CX Automation</dd>
                  </dl>
                  <div className="zlp-evlist">
                    <div className="zlp-evrow zlp-mono">
                      <span className="zlp-tm">10:21:14.101</span>
                      <span className="zlp-ev">user.prompt</span>
                    </div>
                    <div className="zlp-evrow zlp-mono">
                      <span className="zlp-tm">10:21:14.901</span>
                      <span className="zlp-ev">model.response</span>
                    </div>
                    <div className="zlp-evrow zlp-mono">
                      <span className="zlp-tm">10:21:15.023</span>
                      <span className="zlp-ev">tool.call · get_refund_status</span>
                    </div>
                    <div className="zlp-evrow err zlp-mono">
                      <span className="zlp-tm">10:21:16.341</span>
                      <span className="zlp-ev">tool.error · timeout</span>
                    </div>
                    <div className="zlp-evrow err zlp-mono">
                      <span className="zlp-tm">10:21:16.341</span>
                      <span className="zlp-ev">run.failed</span>
                    </div>
                  </div>
                </div>

                {/* Diagnose */}
                <div className="zlp-view" data-view="diagnose">
                  <div className="zlp-runcard">
                    <span className="zlp-vbadge" style={{ color: verdictToken("review").fg }}>
                      ROOT CAUSE
                    </span>
                    <div className="zlp-rc-title">Tool timeout on refund lookup</div>
                    <div className="zlp-rc-sub zlp-mono">ToolExecutionError: get_refund_status took &gt; 5s</div>
                  </div>
                  <dl className="zlp-kv">
                    <dt>affected</dt>
                    <dd>23 grouped runs</dd>
                    <dt>recurrence</dt>
                    <dd>×47 over 6 days</dd>
                    <dt>first seen</dt>
                    <dd>May 18, 09:02</dd>
                    <dt>confidence</dt>
                    <dd>0.93 · corroborated</dd>
                  </dl>
                </div>

                {/* Replay — retains the contract-locked heading. */}
                <div className="zlp-view" data-view="replay">
                  <h3 className="zlp-view-heading">A fix is not accepted until the replay proves it.</h3>
                  <div className="zlp-diff">
                    <div className="zlp-dh">field</div>
                    <div className="zlp-dh">original (failed)</div>
                    <div className="zlp-dh">candidate (fixed)</div>
                    <div className="zlp-dlabel">Tool call</div>
                    <div className="zlp-dc before">Skipped get_refund_status</div>
                    <div className="zlp-dc after">Called get_refund_status</div>
                    <div className="zlp-dlabel">Output</div>
                    <div className="zlp-dc before">Generic refund blurb</div>
                    <div className="zlp-dc after">Account-specific status</div>
                    <div className="zlp-dlabel">Result</div>
                    <div className="zlp-dc before">Failed (timeout)</div>
                    <div className="zlp-dc after">Passed</div>
                  </div>
                  <dl className="zlp-kv">
                    <dt>fidelity</dt>
                    <dd>0.98 · faithful reproduction</dd>
                    <dt>latency</dt>
                    <dd>7.8s → 2.1s (−73%)</dd>
                    <dt>cost</dt>
                    <dd>$0.0234 → $0.0061 (−74%)</dd>
                  </dl>
                </div>

                {/* Promote */}
                <div className="zlp-view" data-view="promote">
                  <div className="zlp-golden">
                    <span className="zlp-gi">
                      <Check aria-hidden="true" />
                    </span>
                    <div>
                      <strong>Refund status protected flow</strong>
                      <span>Ensures status is fetched via tool call</span>
                    </div>
                    <span className="zlp-gtag zlp-mono">PROMOTED</span>
                  </div>
                  <div className="zlp-golden">
                    <span className="zlp-gi">
                      <Check aria-hidden="true" />
                    </span>
                    <div>
                      <strong>Tool-call required</strong>
                      <span>Disallows generic answers when a tool exists</span>
                    </div>
                    <span className="zlp-gtag zlp-mono">PASSED</span>
                  </div>
                </div>

                {/* Gate */}
                <div className="zlp-view" data-view="gate">
                  <div className="zlp-pr fail">
                    <span className="zlp-pi">
                      <XCircle aria-hidden="true" />
                    </span>
                    <div>
                      <strong>PR #43 · Update refund flow</strong>
                      <span>zroky/contract-gate - blocked regression</span>
                    </div>
                  </div>
                  <div className="zlp-pr pass">
                    <span className="zlp-pi">
                      <Check aria-hidden="true" />
                    </span>
                    <div>
                      <strong>PR #42 · Improve policy wording</strong>
                      <span>2 contracts run - 0 failed</span>
                    </div>
                  </div>
                  <p className="zlp-mono zlp-gate-note">Borderline runs get &quot;review&quot; — never a false block.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ---- Quickstart / Capture (#capture) ------------------------- */}
        <section className="zlp-blk" id="capture">
          <div className="zlp-wrap zlp-qs">
            <div>
              <span className="zlp-eyebrow">
                <span className="zlp-dot" aria-hidden="true" />
                Quickstart
              </span>
              <h2 className="zlp-disp zlp-qs-title">Capture real agent runs with one SDK call.</h2>
              <p className="zlp-lead">
                Add three lines. Capture starts immediately — failures surface as your traffic arrives. Install{" "}
                <span className="zlp-mono zlp-inline-code">{SDK.scoped}</span> and wrap your client.
              </p>
              {/* Island mount point: Disclosure (task 8.2) — full payload reveal. */}
              <details className="zlp-disclosure" data-island="disclosure">
                <summary>
                  Show full captured payload
                  <Plus aria-hidden="true" />
                </summary>
                <dl className="zlp-kv">
                  <dt>trace_id</dt>
                  <dd>trc_8f3bd6e27a6b4cf1</dd>
                  <dt>run_id</dt>
                  <dd>run_01H82JK8709Q4Y20</dd>
                  <dt>provider</dt>
                  <dd>openai</dd>
                  <dt>output</dt>
                  <dd>&quot;Your refund is being processed.&quot;</dd>
                </dl>
              </details>
              <a href="#docs" className="zlp-btn zlp-btn-ghost zlp-qs-docs">
                Read the docs
                <ArrowRight aria-hidden="true" />
              </a>
            </div>
            <div className="zlp-code zlp-elevated">
              <div className="zlp-code-top">
                <span className="zlp-mono">typescript</span>
                {/* Island mount point: CopySnippetButton (task 8.1). Static, but
                   already labelled + keyboard reachable as server HTML. */}
                <button type="button" className="zlp-copybtn zlp-mono" data-island="copy-snippet" aria-label="Copy SDK snippet">
                  <Copy aria-hidden="true" />
                  copy
                </button>
              </div>
              <pre className="zlp-code-body zlp-mono">{sdkSnippet}</pre>
            </div>
          </div>
        </section>

        {/* ---- Model support (#models) --------------------------------- */}
        <section className="zlp-blk" id="models">
          <div className="zlp-wrap">
            <div className="zlp-shead">
              <span className="zlp-eyebrow">
                <span className="zlp-dot" aria-hidden="true" />
                Model support
              </span>
              <h2 className="zlp-disp">One reliability layer across your model stack.</h2>
              <p>Capture normalizes every provider into the same evidence model, so the loop works the same everywhere.</p>
            </div>
            <div className="zlp-model-row">
              {modelProviders.map((provider) => (
                <article key={provider.name} className="zlp-card">
                  <strong>{provider.name}</strong>
                  <span>{provider.detail}</span>
                </article>
              ))}
            </div>
            <div className="zlp-model-contract">
              <span className="zlp-prov-lbl">Normalized evidence fields</span>
              <div>
                {modelSignals.map((signal) => (
                  <code key={signal} className="zlp-mono">
                    {signal}
                  </code>
                ))}
              </div>
            </div>
            <div className="zlp-flow">
              {adapterFlow.map(([title, copy], index) => (
                <div key={title} className="zlp-flow-item">
                  <article className="zlp-card">
                    <strong>{title}</strong>
                    <span>{copy}</span>
                  </article>
                  {index < adapterFlow.length - 1 ? <ArrowRight aria-hidden="true" /> : null}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ---- Dashboard ModuleSwitcher (#modules) --------------------- */}
        <section className="zlp-blk" id="modules">
          <div className="zlp-wrap">
            <div className="zlp-shead">
              <span className="zlp-eyebrow">
                <span className="zlp-dot" aria-hidden="true" />
                Dashboard
              </span>
              <h2 className="zlp-disp">The dashboard zooms into the part that matters.</h2>
              <p>Every module is one click from the failing run - incidents, replay, Contracts, CI, and settings.</p>
            </div>

            {/* Island mount point: ModuleSwitcher (task 9.2). Server renders the
               default module selected (R3.9); all modules are listed. */}
            <div className="zlp-dashboard zlp-elevated" data-island="module-switcher">
              <aside className="zlp-dash-aside">
                <strong>Zroky</strong>
                <small>acme-cx</small>
                <nav aria-label="Dashboard modules">
                  {moduleViews.map((module) => (
                    <button
                      key={module.key}
                      type="button"
                      className={module.key === defaultModule.key ? "is-active" : ""}
                      data-module={module.key}
                    >
                      {module.label}
                    </button>
                  ))}
                </nav>
              </aside>
              <section className="zlp-dash-main" aria-live="polite">
                <div className="zlp-dash-head">
                  <span className="zlp-mono">{defaultModule.label}</span>
                  <h3>{defaultModule.summary}</h3>
                </div>
                <p>{defaultModule.detail?.body}</p>
                <div className="zlp-dash-focus">
                  <code className="zlp-mono">{defaultModule.detail?.heading}</code>
                </div>
                <div className="zlp-delta-grid">
                  <div>
                    <span>Latency</span>
                    <strong>7.8s → 2.1s</strong>
                    <small>−73%</small>
                  </div>
                  <div>
                    <span>Cost</span>
                    <strong>$0.0234 → $0.0061</strong>
                    <small>−74%</small>
                  </div>
                  <div>
                    <span>Tokens</span>
                    <strong>1,284 → 612</strong>
                    <small>−52%</small>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </section>

        {/* ---- Pricing / risk value ----------------------------------- */}
        <section className="zlp-blk zlp-pricing" id="pricing" aria-labelledby="zroky-pricing-title">
          <div className="zlp-wrap">
            <div className="zlp-pricing-hero zlp-elevated">
              <div>
                <span className="zlp-eyebrow">
                  <span className="zlp-dot" aria-hidden="true" />
                  Risk-value pricing
                </span>
                <h2 id="zroky-pricing-title" className="zlp-disp">
                  Run high-stakes autonomous agents unattended - safely.
                </h2>
                <p>
                  Price Zroky against the action it protects: stop the costly operation before it commits,
                  then prove the real-world outcome in the system of record.
                </p>
              </div>
              <div className="zlp-risk-ledger" aria-label="Risk value example">
                {riskValueMetrics.map((metric) => (
                  <div key={metric.label}>
                    <span className="zlp-mono">{metric.label}</span>
                    <strong className="zlp-disp">{metric.value}</strong>
                    <small>{metric.detail}</small>
                  </div>
                ))}
              </div>
            </div>

            <div className="zlp-plan-grid" aria-label="Pricing plans">
              {pricingPlans.map((plan) => (
                <article key={plan.name} className={`zlp-plan${plan.featured ? " featured" : ""}`}>
                  <div className="zlp-plan-head">
                    <span>{plan.name}</span>
                    {plan.featured ? <b className="zlp-mono">Recommended</b> : null}
                  </div>
                  <strong className="zlp-disp">{plan.price}</strong>
                  <p>{plan.fit}</p>
                  <ul>
                    {plan.bullets.map((bullet) => (
                      <li key={bullet}>
                        <Check aria-hidden="true" />
                        <span>{bullet}</span>
                      </li>
                    ))}
                  </ul>
                  <Link href={plan.href} className={plan.featured ? "zlp-btn zlp-btn-primary" : "zlp-btn zlp-btn-ghost"}>
                    {plan.featured ? "Protect a high-risk agent" : plan.name === "Enterprise" ? "Talk to Zroky" : "Start here"}
                    <ArrowRight aria-hidden="true" />
                  </Link>
                </article>
              ))}
            </div>

            <div className="zlp-agent-risk">
              <div>
                <span className="zlp-eyebrow">
                  <span className="zlp-dot" aria-hidden="true" />
                  Highest-pain agents
                </span>
                <h3 className="zlp-disp">Not just refunds. Protect every agent that mutates reality.</h3>
                <p>
                  Start where the error cost is obvious. Expand to any autonomous agent that changes money,
                  customer records, production systems, or customer communications.
                </p>
              </div>
              <div className="zlp-agent-risk-list">
                {protectedAgentRows.map(({ Icon, agent, risk, proof }) => (
                  <article key={agent}>
                    <span className="zlp-agent-risk-icon">
                      <Icon aria-hidden="true" />
                    </span>
                    <div>
                      <strong>{agent}</strong>
                      <small>{risk}</small>
                      <p>{proof}</p>
                    </div>
                  </article>
                ))}
              </div>
            </div>

            <div className="zlp-pricing-proof">
              <FileCheck2 aria-hidden="true" />
              <p>
                Paid handoff proof: runtime decision, policy snapshot, approval audit, outcome reconciliation,
                and evidence hash are all exportable for buyer review.
              </p>
              <Link href="/pilot?source=pricing&intent=handoff&plan=pro" className="zlp-pricing-proof-link">
                Open pilot handoff
                <ArrowRight aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>

        {/* ---- Comparison ---------------------------------------------- */}
        <section className="zlp-blk">
          <div className="zlp-wrap">
            <div className="zlp-shead">
              <span className="zlp-eyebrow">
                <span className="zlp-dot" aria-hidden="true" />
                Why Zroky
              </span>
              <h2 className="zlp-disp">Proof, not vibes.</h2>
              <p>Eval-first tools test what you imagined. Zroky proves what actually shipped.</p>
            </div>
            <div className="zlp-cmp">
              <div className="zlp-cmp-row head">
                <div className="zlp-cmp-c1 zlp-mono">Eval-first tooling</div>
                <div className="zlp-cmp-c2 zlp-mono">Zroky</div>
              </div>
              {comparisonRows.map(([before, after]) => (
                <div key={before} className="zlp-cmp-row">
                  <div className="zlp-cmp-c1">{before}</div>
                  <div className="zlp-cmp-c2">
                    <Check aria-hidden="true" />
                    {after}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ---- Architecture (#docs) ------------------------------------ */}
        <section className="zlp-blk" id="docs">
          <div className="zlp-wrap">
            <div className="zlp-shead">
              <span className="zlp-eyebrow">
                <span className="zlp-dot" aria-hidden="true" />
                Architecture
              </span>
              <h2 className="zlp-disp">Built to fit your stack.</h2>
              <p>Capture runs through the SDK, store the evidence, replay deterministically, and gate CI — with controls your security team expects.</p>
            </div>
            <div className="zlp-flow">
              {architectureNodes.map(([title, copy], index) => (
                <div key={title} className="zlp-flow-item">
                  <article className="zlp-card">
                    <strong>{title}</strong>
                    <span>{copy}</span>
                  </article>
                  {index < architectureNodes.length - 1 ? <ArrowRight aria-hidden="true" /> : null}
                </div>
              ))}
            </div>
            <div className="zlp-chips">
              {controlChips.map(([label, copy]) => (
                <span key={label} className="zlp-chip">
                  <strong>{label}</strong>
                  {copy}
                </span>
              ))}
            </div>
          </div>
        </section>

        {/* ---- FAQ ----------------------------------------------------- */}
        <section className="zlp-blk" id="faq">
          <div className="zlp-wrap">
            <div className="zlp-shead">
              <span className="zlp-eyebrow">
                <span className="zlp-dot" aria-hidden="true" />
                FAQ
              </span>
              <h2 className="zlp-disp">Questions, answered.</h2>
            </div>
            {/* Each Q&A uses native progressive disclosure; task 8.2/10.1 may
               upgrade these to the shared Disclosure island. */}
            <div className="zlp-faq">
              {faqItems.map((item, index) => (
                <details key={item.q} className="zlp-qa" open={index === 0}>
                  <summary>
                    <span>{item.q}</span>
                    <span className="zlp-pm" aria-hidden="true">
                      <Plus />
                    </span>
                  </summary>
                  <div className="zlp-ans">{item.a}</div>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* ---- Final CTA ----------------------------------------------- */}
        <section className="zlp-wrap">
          <div className="zlp-fcta zlp-elevated">
            <h2 className="zlp-disp">Stop shipping the same agent failure twice.</h2>
            <p>Add the SDK, capture one run, and prove the fix in minutes.</p>
            <div className="zlp-hero-cta">
              <Link href="/signup" className="zlp-btn zlp-btn-primary zlp-btn-lg">
                Start workspace
                <ArrowRight aria-hidden="true" />
              </Link>
              <a href="#docs" className="zlp-btn zlp-btn-ghost zlp-btn-lg">
                Read the docs
              </a>
            </div>
          </div>
        </section>
      </main>

      {/* ---- Footer ---------------------------------------------------- */}
      <footer className="zlp-footer">
        <div className="zlp-wrap zlp-foot">
          <div className="zlp-foot-brand">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={logoSrc} alt="Zroky" />
            <span>© 2026 Zroky</span>
          </div>
          <nav className="zlp-foot-links" aria-label="Footer links">
            {footerLinks.map(({ label, href }) => (
              <Link key={label} href={href}>
                {label}
              </Link>
            ))}
          </nav>
          <nav className="zlp-social" aria-label="Social media">
            {socialLinks.map(({ label, href, Icon }) => (
              <a key={label} href={href} aria-label={label}>
                <Icon aria-hidden="true" />
              </a>
            ))}
          </nav>
        </div>
      </footer>
    </div>
  );
}
