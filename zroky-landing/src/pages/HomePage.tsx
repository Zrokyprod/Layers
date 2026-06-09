import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import type { ReactNode } from 'react';
import { useState } from 'react';
import {
  ArrowRight, ArrowUpRight, EyeOff, HelpCircle, RotateCcw, Star,
  Search, FlaskConical, ShieldCheck, Check, Copy, Sparkles,
  Activity, GitBranch, Languages, FileSearch,
} from 'lucide-react';

const DASHBOARD_URL = 'https://app.zroky.com';
const GITHUB_URL = 'https://github.com/zroky/zroky-watch';

const ease = [0.16, 1, 0.3, 1] as const;

function Reveal({ children, delay = 0, className = '' }: { children: ReactNode; delay?: number; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.6, ease, delay }}
    >
      {children}
    </motion.div>
  );
}

/* ================================================================== */
/* HERO                                                                */
/* ================================================================== */

function DiscoveredChip() {
  return (
    <div className="w-[16rem] rounded-2xl border border-line-strong bg-ink-2/90 p-4 shadow-[0_30px_80px_-40px_rgba(0,0,0,0.95)] backdrop-blur-xl">
      <div className="flex items-center justify-between">
        <span className="badge badge-discovered">DISCOVERED</span>
        <span className="font-mono text-[10px] text-tertiary">no eval written</span>
      </div>
      <p className="mt-3 text-sm font-semibold text-primary">refund_agent skipped a critical tool</p>
      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {['96% of normal traces', 'outcome → failure', '×47'].map((t) => (
          <span key={t} className="rounded-md border border-line bg-white/[0.03] px-2 py-0.5 font-mono text-[9px] text-tertiary">{t}</span>
        ))}
      </div>
      <div className="mt-3 divider" />
      <p className="mt-2.5 font-mono text-[10px] text-tertiary">confidence 0.93 · anomaly ≠ failure (corroborated)</p>
    </div>
  );
}

function Hero() {
  const reduce = useReducedMotion();
  return (
    <section className="grain relative w-full overflow-hidden px-6 pt-36 pb-20 md:pt-44">
      <div className="mesh-glow pointer-events-none absolute inset-0 -z-10" />
      <div className="relative z-10 mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <Reveal>
            <span className="eyebrow"><Sparkles size={12} /> AI Agent Failure Discovery &amp; Regression Guard</span>
          </Reveal>
          <Reveal delay={0.05}>
            <h1 className="mt-6 text-balance text-5xl font-extrabold leading-[1.02] tracking-tight md:text-[4.2rem]">
              <span className="text-shimmer">Find the AI agent failures you didn't know to test.</span>
            </h1>
          </Reveal>
          <Reveal delay={0.12}>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-secondary">
              Zroky learns your agent's normal behavior in production, surfaces the abnormal —
              including failures you never wrote a test for — proves your fix with replay, and blocks the repeat in CI.
            </p>
          </Reveal>
          <Reveal delay={0.18}>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <a href={`${DASHBOARD_URL}/auth/register`} className="btn-primary !px-6 !py-3">Start free <ArrowUpRight size={16} /></a>
              <a href={GITHUB_URL} className="btn-ghost !px-6 !py-3"><Star size={15} /> zroky-watch — open source</a>
            </div>
          </Reveal>
          <Reveal delay={0.24}>
            <p className="mt-5 font-mono text-xs text-tertiary">
              5-min install · any framework · <span className="text-secondary">we never call a stub replay a verified fix.</span>
            </p>
          </Reveal>
        </div>

        <Reveal delay={0.1}>
          <motion.div
            className="relative"
            initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, rotateY: 6 }}
            animate={{ opacity: 1, scale: 1, rotateY: 0 }}
            transition={{ duration: 0.8, ease }}
            style={{ perspective: 1200 }}
          >
            <div className="device-frame device-fade rotate-[0.6deg]">
              <div className="browser-bar">
                <span className="browser-dot" /><span className="browser-dot" /><span className="browser-dot" />
                <span className="ml-3 font-mono text-[10px] text-tertiary">app.zroky.com · replay</span>
              </div>
              <img
                src="/product-replay-detail.png"
                alt="Zroky Replay Lab comparing the original failure to a candidate fix"
                className="device-shot max-h-[26rem]"
                loading="eager"
              />
            </div>
            <motion.div
              className="absolute -bottom-8 -left-6 hidden sm:block"
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease, delay: 0.5 }}
            >
              <DiscoveredChip />
            </motion.div>
          </motion.div>
        </Reveal>
      </div>
    </section>
  );
}

/* ================================================================== */
/* LOGO MARQUEE                                                         */
/* ================================================================== */

function Marquee() {
  const logos = ['OpenAI', 'Anthropic', 'Google', 'LangChain', 'LangGraph', 'CrewAI', 'OpenTelemetry', 'Vercel AI SDK'];
  const row = [...logos, ...logos];
  return (
    <section className="w-full border-y border-line py-8">
      <p className="mb-6 text-center font-mono text-[11px] uppercase tracking-[0.2em] text-tertiary">
        Works with any agent framework
      </p>
      <div className="marquee-mask relative w-full overflow-hidden">
        <div className="marquee-track gap-12 px-6">
          {row.map((l, i) => (
            <span key={`${l}-${i}`} className="whitespace-nowrap text-lg font-semibold text-secondary/70">{l}</span>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ================================================================== */
/* STATS BAND                                                           */
/* ================================================================== */

function Stats() {
  const stats = [
    ['<10 min', 'to first surfaced finding'],
    ['90%+', 'precision target before we surface'],
    ['3', 'CI verdicts — pass / block / review'],
    ['0', 'false blocks on borderline cases'],
  ];
  return (
    <section className="w-full px-6 py-16">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line lg:grid-cols-4">
        {stats.map(([n, label], i) => (
          <Reveal key={label} delay={i * 0.06}>
            <div className="h-full bg-ink p-7">
              <div className="font-mono text-4xl font-bold tracking-tight text-primary md:text-5xl">{n}</div>
              <p className="mt-3 text-sm leading-relaxed text-tertiary">{label}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ================================================================== */
/* PROBLEM                                                              */
/* ================================================================== */

function Problem() {
  const cards = [
    { icon: EyeOff, title: 'Silent failures', body: 'Valid-looking output, wrong result. No error fired. You find out when the customer complains.' },
    { icon: HelpCircle, title: "Can't test the unknown", body: 'Eval-first tools only catch failures you already wrote a rubric for. The dangerous ones are the unknowns.' },
    { icon: RotateCcw, title: 'The same bug ships twice', body: 'Fixed last sprint, regressed this one. Nobody caught it until production did.' },
  ];
  return (
    <section className="w-full px-6 py-20">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <h2 className="max-w-2xl text-balance text-3xl font-bold tracking-tight md:text-4xl">
            Your agent returns <span className="font-mono text-secondary">200 OK</span> — and still fails the task.
          </h2>
        </Reveal>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {cards.map((c, i) => (
            <Reveal key={c.title} delay={i * 0.08}>
              <div className="card h-full p-6">
                <div className="grid h-10 w-10 place-items-center rounded-xl border border-line bg-white/[0.04]">
                  <c.icon size={18} className="text-secondary" />
                </div>
                <h3 className="mt-4 text-lg font-semibold">{c.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-tertiary">{c.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ================================================================== */
/* PRODUCT SHOWCASE — tabbed, single frame                             */
/* ================================================================== */

type Tab = {
  id: string; name: string; icon: typeof Search; cls: string;
  title: string; body: string; points: string[];
  media: ReactNode; caption: string;
};

function MockDiscover() {
  return (
    <div className="p-6">
      <div className="card p-5">
        <div className="flex items-center justify-between">
          <span className="badge badge-discovered">DISCOVERED</span>
          <span className="font-mono text-[10px] text-tertiary">no eval written</span>
        </div>
        <p className="mt-3 text-sm font-semibold">refund_agent · status_lookup</p>
        <p className="mt-1 text-sm text-secondary">
          Skipped <span className="font-mono text-primary">get_refund_status</span>, present in
          <span className="text-primary"> 96%</span> of normal traces — outcome flipped to failure.
        </p>
        <div className="mt-4 flex flex-wrap gap-1.5">
          {['missing critical tool', 'outcome mismatch', 'recurrence ×47'].map((t) => (
            <span key={t} className="rounded-md border border-line bg-white/[0.03] px-2 py-0.5 font-mono text-[10px] text-tertiary">{t}</span>
          ))}
        </div>
        <div className="mt-4 divider" />
        <p className="mt-3 font-mono text-[11px] text-tertiary">confidence 0.93 · tier: surfaced · anomaly ≠ failure (corroborated)</p>
      </div>
    </div>
  );
}

function ProductShowcase() {
  const [active, setActive] = useState(0);
  const reduce = useReducedMotion();

  const tabs: Tab[] = [
    {
      id: 'discover', name: 'Discover', icon: Search, cls: 'badge-discovered',
      title: 'Catch the failures your tests miss.',
      body: "Zroky learns each workflow's normal behavior — tool sequences, output shape, outcomes — and surfaces deviations that matter. No rubric required.",
      points: [
        'Behavioral baseline learned from production, no labels needed.',
        'Anomaly ≠ Failure — surfaced only when corroborated.',
        'Every finding explains its own "why".',
      ],
      media: <MockDiscover />, caption: 'Discover — a surfaced finding with its evidence',
    },
    {
      id: 'prove', name: 'Prove', icon: FlaskConical, cls: 'badge-verified',
      title: 'Prove the fix works — honestly.',
      body: 'Replay the exact failed scenario against your candidate fix. Before/after, tool-behavior diff, cost & latency delta — and a fidelity score for how faithfully we reproduced it.',
      points: [
        'Real-LLM, mocked-tool, sandbox and shadow replay modes.',
        'Fidelity score on every run — including honest "cannot reproduce".',
        '"Verified" only ever means verified.',
      ],
      media: <img src="/product-replay-detail.png" alt="Replay Lab original vs candidate" className="device-shot max-h-[24rem]" loading="lazy" />,
      caption: 'Replay Lab — original vs candidate, fidelity-scored',
    },
    {
      id: 'guard', name: 'Guard', icon: ShieldCheck, cls: 'badge-blocked',
      title: 'Stop the same failure from shipping twice.',
      body: 'Promote a verified fix into a Golden. Zroky runs it on every PR and blocks regressions — and only blocks when it is sure. Borderline gets "review", never a false block.',
      points: [
        'Goldens: production-derived regression tests.',
        'Three verdicts — pass / block / review — flake-resistant.',
        'not_verified is never counted as a pass.',
      ],
      media: <img src="/product-ci-gate.png" alt="CI gate blocking a regressing PR" className="device-shot max-h-[24rem]" loading="lazy" />,
      caption: 'CI Gate — blocking a regressing PR with replay evidence',
    },
  ];

  const t = tabs[active];

  return (
    <section id="product" className="w-full px-6 py-20">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <p className="eyebrow">The loop</p>
          <h2 className="mt-5 text-balance text-3xl font-bold tracking-tight md:text-5xl">Discover → Prove → Guard</h2>
          <p className="mt-4 max-w-2xl text-lg text-secondary">One loop, three jobs. Click through how a production failure becomes a blocked regression.</p>
        </Reveal>

        {/* tab bar */}
        <Reveal delay={0.08}>
          <div className="mt-10 inline-flex rounded-full border border-line bg-white/[0.03] p-1">
            {tabs.map((tab, i) => (
              <button
                key={tab.id}
                onClick={() => setActive(i)}
                className={`relative flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold transition ${active === i ? 'text-ink' : 'text-secondary hover:text-primary'}`}
              >
                {active === i && (
                  <motion.span layoutId="tabPill" className="absolute inset-0 -z-10 rounded-full bg-primary" transition={{ type: 'spring', stiffness: 400, damping: 32 }} />
                )}
                <tab.icon size={15} /> {tab.name}
              </button>
            ))}
          </div>
        </Reveal>

        {/* content */}
        <div className="mt-8 grid items-center gap-10 lg:grid-cols-[0.85fr_1.15fr]">
          <AnimatePresence mode="wait">
            <motion.div
              key={`text-${t.id}`}
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, y: -8 }}
              transition={{ duration: 0.32, ease }}
            >
              <span className={`badge ${t.cls}`}>{t.name.toUpperCase()}</span>
              <h3 className="mt-4 text-balance text-2xl font-bold tracking-tight md:text-3xl">{t.title}</h3>
              <p className="mt-4 text-base leading-relaxed text-secondary">{t.body}</p>
              <ul className="mt-6 space-y-3">
                {t.points.map((p) => (
                  <li key={p} className="flex items-start gap-3 text-sm text-secondary">
                    <Check size={16} className="mt-0.5 shrink-0 text-primary" /> <span>{p}</span>
                  </li>
                ))}
              </ul>
            </motion.div>
          </AnimatePresence>

          <AnimatePresence mode="wait">
            <motion.figure
              key={`media-${t.id}`}
              initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.99 }}
              transition={{ duration: 0.35, ease }}
            >
              <div className="device-frame device-fade">
                <div className="browser-bar">
                  <span className="browser-dot" /><span className="browser-dot" /><span className="browser-dot" />
                  <span className="ml-3 font-mono text-[10px] text-tertiary">app.zroky.com</span>
                </div>
                {t.media}
              </div>
              <figcaption className="mt-3 text-center font-mono text-[11px] text-tertiary">{t.caption}</figcaption>
            </motion.figure>
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
}

/* ================================================================== */
/* BENTO CAPABILITIES                                                   */
/* ================================================================== */

function Bento() {
  return (
    <section className="w-full px-6 py-20">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <h2 className="text-balance text-3xl font-bold tracking-tight md:text-4xl">Under the hood</h2>
          <p className="mt-4 max-w-2xl text-lg text-secondary">The engine behind the loop — built for precision, not noise.</p>
        </Reveal>

        <div className="mt-10 grid auto-rows-[minmax(11rem,auto)] gap-4 md:grid-cols-3">
          {/* wide cell */}
          <Reveal className="md:col-span-2 md:row-span-1">
            <div className="bento grain h-full p-7">
              <div className="relative z-10">
                <div className="flex items-center gap-2">
                  <Activity size={18} className="text-discovered" />
                  <span className="badge badge-discovered">BASELINE</span>
                </div>
                <h3 className="mt-4 text-xl font-bold">Behavioral baseline, learned from production</h3>
                <p className="mt-2 max-w-lg text-sm leading-relaxed text-secondary">
                  Tool sequences, output shape, latency, and outcomes per workflow. No labels, no rubric —
                  the baseline warms as your traffic arrives, and only corroborated deviations surface.
                </p>
              </div>
            </div>
          </Reveal>

          <Reveal delay={0.06}>
            <div className="bento h-full p-7">
              <FlaskConical size={18} className="text-verified" />
              <h3 className="mt-4 text-lg font-bold">Fidelity-scored replay</h3>
              <p className="mt-2 text-sm leading-relaxed text-secondary">Every replay reports how faithfully it reproduced the incident — including honest "cannot reproduce".</p>
            </div>
          </Reveal>

          <Reveal delay={0.04}>
            <div className="bento h-full p-7">
              <ShieldCheck size={18} className="text-primary" />
              <h3 className="mt-4 text-lg font-bold">Goldens</h3>
              <p className="mt-2 text-sm leading-relaxed text-secondary">Verified fixes become production-derived regression tests that protect the release.</p>
            </div>
          </Reveal>

          <Reveal delay={0.06}>
            <div className="bento h-full p-7">
              <GitBranch size={18} className="text-blocked" />
              <h3 className="mt-4 text-lg font-bold">CI verdict</h3>
              <p className="mt-2 text-sm leading-relaxed text-secondary">Pass, block, or review on every PR — flake-resistant, no false blocks.</p>
            </div>
          </Reveal>

          <Reveal delay={0.04}>
            <div className="bento h-full p-7">
              <Languages size={18} className="text-secondary" />
              <h3 className="mt-4 text-lg font-bold">Multilingual</h3>
              <p className="mt-2 text-sm leading-relaxed text-secondary">Failures surface across languages, not just English traffic.</p>
            </div>
          </Reveal>

          <Reveal delay={0.06}>
            <div className="bento h-full p-7">
              <FileSearch size={18} className="text-secondary" />
              <h3 className="mt-4 text-lg font-bold">Evidence trail</h3>
              <p className="mt-2 text-sm leading-relaxed text-secondary">Every finding ships with the trace, the why, and the recurrence count behind it.</p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

/* ================================================================== */
/* COMPARISON                                                          */
/* ================================================================== */

function Comparison() {
  const rows = [
    ['You write rubrics / evals upfront', 'Learns normal from production'],
    ['Catches known failure modes', 'Surfaces unknown failures'],
    ['Day 1 = blank (no labels)', 'Value as traffic arrives'],
    ['"Verified" = a judge ran', 'Fidelity-scored, honest verdicts'],
  ];
  return (
    <section className="w-full px-6 py-20">
      <div className="mx-auto max-w-4xl">
        <Reveal>
          <h2 className="text-balance text-center text-3xl font-bold tracking-tight md:text-4xl">
            Eval-first tools test what you imagine. Zroky finds what you didn't.
          </h2>
        </Reveal>
        <Reveal delay={0.1}>
          <div className="mt-12 overflow-hidden rounded-2xl border border-line">
            <div className="grid grid-cols-2 border-b border-line bg-white/[0.02]">
              <div className="p-4 font-mono text-xs uppercase tracking-wider text-tertiary">Eval-first tooling</div>
              <div className="p-4 font-mono text-xs uppercase tracking-wider text-primary">Zroky</div>
            </div>
            {rows.map((r, i) => (
              <div key={i} className={`grid grid-cols-2 ${i < rows.length - 1 ? 'border-b border-line' : ''}`}>
                <div className="p-4 text-sm text-tertiary">{r[0]}</div>
                <div className="flex items-center gap-2 p-4 text-sm text-secondary">
                  <Check size={15} className="shrink-0 text-primary" /> {r[1]}
                </div>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ================================================================== */
/* TRUST                                                               */
/* ================================================================== */

function Trust() {
  const chips = [
    'Stub replay is never reported as "verified".',
    'CI blocks only at high confidence — borderline gets "review", never a false block.',
    'We show replay fidelity, including when we cannot reproduce a case.',
  ];
  return (
    <section id="trust" className="w-full px-6 py-16">
      <div className="mx-auto max-w-5xl">
        <Reveal>
          <h2 className="text-balance text-center text-3xl font-bold tracking-tight md:text-4xl">
            Built to earn trust, not inflate it.
          </h2>
        </Reveal>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {chips.map((c, i) => (
            <Reveal key={c} delay={i * 0.08}>
              <div className="card h-full p-5">
                <ShieldCheck size={18} className="text-primary" />
                <p className="mt-3 text-sm leading-relaxed text-secondary">{c}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ================================================================== */
/* QUICKSTART                                                          */
/* ================================================================== */

const SNIPPET = `import zroky
zroky.init(api_key=..., project="refund-agent-prod")

@zroky.trace(agent="refund_agent", workflow="status_lookup")
async def handle(query):
    return await agent.run(query)`;

function Quickstart() {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(SNIPPET);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };
  return (
    <section className="w-full px-6 py-20">
      <div className="mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-2">
        <Reveal>
          <div>
            <p className="eyebrow">Quickstart</p>
            <h2 className="mt-5 text-3xl font-bold tracking-tight md:text-4xl">Live in 5 minutes.</h2>
            <p className="mt-4 text-lg leading-relaxed text-secondary">
              Add three lines. Capture starts immediately — structural failures surface now, and behavioral
              discovery unlocks as Zroky learns your normal.
            </p>
            <a href="/docs" className="btn-ghost mt-6">Read the docs <ArrowRight size={15} /></a>
          </div>
        </Reveal>
        <Reveal delay={0.1}>
          <div className="card overflow-hidden p-0">
            <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
              <span className="font-mono text-[11px] text-tertiary">python</span>
              <button onClick={copy} className="flex items-center gap-1.5 rounded-md border border-line px-2 py-1 font-mono text-[10px] text-secondary transition hover:text-primary">
                {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? 'copied' : 'copy'}
              </button>
            </div>
            <pre className="overflow-x-auto p-5 font-mono text-[13px] leading-relaxed text-secondary">{SNIPPET}</pre>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ================================================================== */
/* FINAL CTA                                                           */
/* ================================================================== */

function FinalCTA() {
  return (
    <section className="w-full px-6 py-24">
      <Reveal>
        <div className="card grain relative mx-auto max-w-4xl overflow-hidden p-12 text-center">
          <div className="mesh-glow pointer-events-none absolute inset-0 -z-10" />
          <h2 className="relative z-10 text-balance text-4xl font-extrabold tracking-tight md:text-5xl">
            Stop shipping the same agent failure twice.
          </h2>
          <p className="relative z-10 mx-auto mt-4 max-w-xl text-secondary">
            Discover what your tests miss. Prove the fix. Guard against the repeat.
          </p>
          <div className="relative z-10 mt-8 flex flex-wrap items-center justify-center gap-3">
            <a href={`${DASHBOARD_URL}/auth/register`} className="btn-primary !px-6 !py-3">Start free <ArrowUpRight size={16} /></a>
            <a href={GITHUB_URL} className="btn-ghost !px-6 !py-3"><Star size={15} /> Star zroky-watch</a>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

/* ================================================================== */

export default function HomePage() {
  return (
    <div className="w-full">
      <Hero />
      <Marquee />
      <Stats />
      <Problem />
      <ProductShowcase />
      <Bento />
      <Comparison />
      <Trust />
      <Quickstart />
      <FinalCTA />
    </div>
  );
}
