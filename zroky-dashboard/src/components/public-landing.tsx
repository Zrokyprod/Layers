import Link from "next/link";
import type { CSSProperties } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  CircleDot,
  Database,
  FileCheck2,
  Fingerprint,
  Gauge,
  KeyRound,
  LockKeyhole,
  Network,
  RadioTower,
  Route,
  ShieldCheck,
  Sparkles,
  Workflow,
  XCircle,
} from "lucide-react";

const controlSteps = [
  { label: "Intercept", detail: "MCP tool call enters Zroky", Icon: RadioTower, tone: "cyan" },
  { label: "Decide", detail: "Policy allows, holds, or denies", Icon: ShieldCheck, tone: "amber" },
  { label: "Execute", detail: "Approved call reaches the SOR", Icon: Workflow, tone: "green" },
  { label: "Verify", detail: "Connector observes the real outcome", Icon: Database, tone: "blue" },
  { label: "Receipt", detail: "Evidence is signed and retained", Icon: Fingerprint, tone: "violet" },
] as const;

const outcomes = [
  ["Matched", "The system of record confirms the intended change.", "matched"],
  ["Mismatched", "The agent claimed success, but the record disagrees.", "mismatched"],
  ["Pending", "The source is still inside its consistency window.", "pending"],
  ["Unverifiable", "The connector or source is currently unreachable.", "unverifiable"],
  ["Partial", "Only part of the expected change is present.", "partial"],
] as const;

const enterpriseControls = [
  { title: "Fail-closed where it matters", copy: "Protected writes stop when policy or required audit is unavailable.", Icon: LockKeyhole },
  { title: "Tenant-safe execution", copy: "Bounded concurrency, retry budgets, and shared circuit breakers contain noisy neighbors.", Icon: Gauge },
  { title: "Credential custody", copy: "Secret references, rotation posture, and audit trails keep connector access controlled.", Icon: KeyRound },
  { title: "Causal evidence", copy: "Actor, correlation, timing, and field-level proof distinguish state match from action proof.", Icon: Fingerprint },
];

const connectorTiers = [
  ["Certified packs", "Zroky-maintained connectors for common enterprise systems."],
  ["Declarative connectors", "Define endpoint, auth reference, match keys, and proof rules without custom product code."],
  ["Private runner", "Verify internal APIs and databases through an outbound-only, least-authority runner."],
] as const;

const faq = [
  ["Does Zroky sit inline with every agent action?", "Zroky uses a hybrid model. High-risk writes and approval-required actions are gated inline. Lower-risk actions can execute and be verified asynchronously, preserving throughput without weakening the critical boundary."],
  ["What happens when Zroky denies a tool call?", "The agent receives structured feedback with the reason, violated boundary, and safe next action. A denial is an input the agent can correct, not a generic failure."],
  ["How is this different from agent observability?", "Observability tells you what the agent attempted. Zroky can intercept before a protected write, enforce policy, verify the result against the real system of record, and issue a signed receipt."],
  ["Do credentials have to leave our network?", "Not always. Public SaaS connectors can use managed secret references. Private systems can use the outbound-only runner so verification stays inside your trust boundary."],
];

function Brand() {
  return (
    <Link href="/" className="zlp2-brand" aria-label="Zroky home">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/zroky-brand.png" alt="Zroky" />
    </Link>
  );
}

export function PublicLanding() {
  return (
    <div className="zlp2">
      <nav className="zlp2-nav" aria-label="Public navigation">
        <div className="zlp2-shell zlp2-nav-inner">
          <Brand />
          <div className="zlp2-nav-links">
            <a href="#control-loop">Product</a>
            <a href="#proof">Proof</a>
            <a href="#connectors">Connectors</a>
            <a href="#security">Security</a>
            <Link href="/pricing">Pricing</Link>
          </div>
          <div className="zlp2-nav-actions">
            <Link href="/login" className="zlp2-text-link">Sign in</Link>
            <Link href="/signup" className="zlp2-button zlp2-button-light">Start workspace <ArrowRight /></Link>
          </div>
        </div>
      </nav>

      <main>
        <section className="zlp2-hero" aria-labelledby="zlp2-title">
          <div className="zlp2-hero-grid" aria-hidden="true" />
          <div className="zlp2-hero-glow" aria-hidden="true" />
          <div className="zlp2-shell zlp2-hero-content">
            <div className="zlp2-kicker"><CircleDot /> MCP-native agent action control</div>
            <h1 id="zlp2-title">The control plane for AI agent actions.</h1>
            <p className="zlp2-hero-lead">
              Intercept risky tool calls before they reach business systems. Apply policy, route approvals, verify the
              real outcome, and issue durable proof for every protected action.
            </p>
            <div className="zlp2-hero-actions">
              <Link href="/signup" className="zlp2-button zlp2-button-accent">Protect an agent <ArrowRight /></Link>
              <a href="#control-loop" className="zlp2-button zlp2-button-outline">See the control loop</a>
            </div>
            <div className="zlp2-hero-assurance" aria-label="Product assurances">
              <span><Check /> Any agent framework</span>
              <span><Check /> MCP interception</span>
              <span><Check /> Source-of-record proof</span>
            </div>

            <div className="zlp2-rail" aria-label="Protected action moving through the Zroky control loop">
              <div className="zlp2-rail-head">
                <span><span className="zlp2-live-dot" /> Live protected action</span>
                <code>refund.create / req_8f3bd6</code>
              </div>
              <div className="zlp2-rail-track">
                <span className="zlp2-rail-signal" aria-hidden="true" />
                {controlSteps.map(({ label, detail, Icon, tone }, index) => (
                  <article key={label} className={`zlp2-rail-step is-${tone}`} style={{ "--step": index } as CSSProperties}>
                    <span className="zlp2-step-icon"><Icon /></span>
                    <small>0{index + 1}</small>
                    <strong>{label}</strong>
                    <p>{detail}</p>
                  </article>
                ))}
              </div>
              <div className="zlp2-rail-result">
                <span><CheckCircle2 /> Verified against Stripe</span>
                <code>receipt_01JZ...A91C</code>
              </div>
            </div>
          </div>
        </section>

        <section className="zlp2-proofline" aria-label="Zroky operating model">
          <div className="zlp2-shell zlp2-proofline-grid">
            <div><strong>Inline</strong><span>Gate high-risk writes before damage</span></div>
            <div><strong>Asynchronous</strong><span>Verify lower-risk outcomes at scale</span></div>
            <div><strong>Fail-closed</strong><span>Protect writes when control is unavailable</span></div>
            <div><strong>Framework-neutral</strong><span>One MCP rail across agent stacks</span></div>
          </div>
        </section>

        <section className="zlp2-section" id="control-loop">
          <div className="zlp2-shell">
            <header className="zlp2-section-head zlp2-reveal">
              <span className="zlp2-eyebrow">One action, one accountable path</span>
              <h2>Control before execution. Proof after it.</h2>
              <p>Zroky combines a latency-critical safety boundary with an evidence loop that continues after the tool returns.</p>
            </header>
            <div className="zlp2-loop-grid">
              {controlSteps.map(({ label, detail, Icon, tone }, index) => (
                <article key={label} className={`zlp2-loop-card zlp2-reveal is-${tone}`}>
                  <div><span>0{index + 1}</span><Icon /></div>
                  <h3>{label}</h3>
                  <p>{detail}</p>
                  <small>{index < 2 ? "Inline boundary" : "Execution and proof"}</small>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="zlp2-section zlp2-section-dark" id="proof">
          <div className="zlp2-shell zlp2-mismatch-grid">
            <div className="zlp2-mismatch-copy zlp2-reveal">
              <span className="zlp2-eyebrow">The moment that matters</span>
              <h2>The agent said success. The system of record said otherwise.</h2>
              <p>
                Zroky does not treat an HTTP 200 or an agent message as proof. It checks the real record inside a bounded
                verification window and keeps mismatch, delay, and connector failure distinct.
              </p>
              <Link href="/signup" className="zlp2-inline-link">Build your first proof path <ArrowRight /></Link>
            </div>
            <div className="zlp2-evidence" aria-label="Example outcome mismatch evidence">
              <div className="zlp2-evidence-top"><span>Outcome reconciliation</span><code>action_40804514</code></div>
              <div className="zlp2-claim-row">
                <span>Agent claim</span><strong><CheckCircle2 /> Refund completed</strong>
              </div>
              <div className="zlp2-claim-row is-danger">
                <span>Stripe record</span><strong><XCircle /> Refund not found</strong>
              </div>
              <div className="zlp2-evidence-fields">
                <div><span>amount</span><code>$250.00 = $250.00</code><b>match</b></div>
                <div><span>refund_id</span><code>rf_92K != null</code><b>mismatch</b></div>
                <div><span>observed_at</span><code>12:41:09 UTC</code><b>causal</b></div>
              </div>
              <div className="zlp2-mismatch-result"><AlertTriangle /><div><strong>MISMATCHED</strong><span>Alert raised with rollback guidance and evidence.</span></div></div>
            </div>
          </div>
          <div className="zlp2-shell zlp2-outcome-row">
            {outcomes.map(([label, copy, tone]) => (
              <article key={label} className={`is-${tone}`}><strong>{label}</strong><p>{copy}</p></article>
            ))}
          </div>
        </section>

        <section className="zlp2-section" id="connectors">
          <div className="zlp2-shell zlp2-connectors-layout">
            <header className="zlp2-section-head zlp2-reveal">
              <span className="zlp2-eyebrow">Connector fabric</span>
              <h2>Verify any business system without an integrations treadmill.</h2>
              <p>Contracts bind to capabilities. The fabric routes proof through a certified pack, declarative connector, or private runner.</p>
            </header>
            <div className="zlp2-connector-map" aria-label="Connector routing architecture">
              <article className="zlp2-map-source"><Sparkles /><strong>Protected action</strong><code>verify:refund</code></article>
              <span className="zlp2-map-line" aria-hidden="true" />
              <article className="zlp2-map-core"><Route /><strong>Capability router</strong><span>tenant + contract + proof window</span></article>
              <span className="zlp2-map-line" aria-hidden="true" />
              <div className="zlp2-map-targets">
                {connectorTiers.map(([title, copy], index) => <article key={title}><span>0{index + 1}</span><strong>{title}</strong><p>{copy}</p></article>)}
              </div>
            </div>
          </div>
        </section>

        <section className="zlp2-section zlp2-security" id="security">
          <div className="zlp2-shell">
            <header className="zlp2-section-head zlp2-reveal">
              <span className="zlp2-eyebrow">Enterprise operating posture</span>
              <h2>Designed for the blast radius of autonomous software.</h2>
              <p>The control plane is explicit about degraded states, credential custody, tenant isolation, and what its proof actually establishes.</p>
            </header>
            <div className="zlp2-control-grid">
              {enterpriseControls.map(({ title, copy, Icon }) => <article key={title} className="zlp2-reveal"><Icon /><h3>{title}</h3><p>{copy}</p></article>)}
            </div>
            <div className="zlp2-architecture">
              <div><Network /><span><strong>Agent framework</strong><small>Any MCP client or gateway</small></span></div>
              <ArrowRight />
              <div><ShieldCheck /><span><strong>Zroky control rail</strong><small>Policy, approval, audit</small></span></div>
              <ArrowRight />
              <div><Database /><span><strong>Business system</strong><small>Stripe, Okta, ServiceNow, internal</small></span></div>
              <ArrowRight />
              <div><FileCheck2 /><span><strong>Proof ledger</strong><small>Outcome, evidence, receipt</small></span></div>
            </div>
          </div>
        </section>

        <section className="zlp2-section zlp2-faq-section" id="faq">
          <div className="zlp2-shell zlp2-faq-layout">
            <header className="zlp2-section-head"><span className="zlp2-eyebrow">Questions</span><h2>Built for real agent operations.</h2></header>
            <div className="zlp2-faq">
              {faq.map(([question, answer], index) => <details key={question} open={index === 0}><summary>{question}<span>+</span></summary><p>{answer}</p></details>)}
            </div>
          </div>
        </section>

        <section className="zlp2-final">
          <div className="zlp2-shell zlp2-final-inner">
            <div><span className="zlp2-eyebrow">Start with one dangerous action</span><h2>Put your agent on a rail you can prove.</h2><p>Intercept one protected workflow, connect its system of record, and see the full decision-to-receipt path.</p></div>
            <div className="zlp2-final-actions"><Link href="/signup" className="zlp2-button zlp2-button-accent">Start workspace <ArrowRight /></Link><Link href="/pilot" className="zlp2-button zlp2-button-outline">Plan a pilot</Link></div>
          </div>
        </section>
      </main>

      <footer className="zlp2-footer">
        <div className="zlp2-shell zlp2-footer-inner">
          <div><Brand /><p>Control and proof for AI agent actions.</p></div>
          <nav aria-label="Legal and company links"><Link href="/security">Security</Link><Link href="/privacy">Privacy</Link><Link href="/contact">Contact</Link><Link href="/pricing">Pricing</Link></nav>
          <span>Copyright 2026 Zroky</span>
        </div>
      </footer>
    </div>
  );
}
