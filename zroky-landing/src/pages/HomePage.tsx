import { motion } from 'framer-motion';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Code2,
  GitBranch,
  PlayCircle,
  ShieldCheck,
  Sparkles,
  Timer,
} from 'lucide-react';
import { Link } from 'react-router-dom';

const loopSteps = [
  {
    icon: AlertTriangle,
    title: 'Capture failure',
    body: 'Production calls land in the Failure Inbox with trace evidence, affected calls, and blast radius.',
  },
  {
    icon: Sparkles,
    title: 'Diagnose cause',
    body: 'Zroky groups repeated patterns and explains why the agent missed the task.',
  },
  {
    icon: PlayCircle,
    title: 'Replay fix',
    body: 'Run the same failed scenario against a candidate prompt, model, tool, or config change.',
  },
  {
    icon: ShieldCheck,
    title: 'Verify proof',
    body: 'Only trusted replay proof can become a Golden or move into a release gate.',
  },
  {
    icon: GitBranch,
    title: 'Block regressions',
    body: 'Passing cases become CI Goldens so the same production failure cannot ship again.',
  },
];

const proofCards = [
  {
    label: 'Failure Inbox',
    title: 'The dashboard starts with the next action.',
    body: 'No generic metrics wall. Open issues are sorted by severity, impact, replay proof gaps, and Golden readiness.',
  },
  {
    label: 'Replay Lab',
    title: 'A fix is not trusted until replay proves it.',
    body: 'Original output, candidate output, tool behavior, cost delta, latency delta, and pass/fail verdict stay together.',
  },
  {
    label: 'CI Gates',
    title: 'Production memory becomes a release gate.',
    body: 'A protected Golden failure blocks the PR and includes a reviewer-facing regression summary.',
  },
];

const trustSignals = [
  { value: '<5ms', label: 'SDK p95 capture overhead target' },
  { value: 'real_llm', label: 'Trusted replay mode for verified fixes' },
  { value: '1 schema', label: 'Frozen ingest contract for API v1' },
  { value: 'CI gate', label: 'Goldens block repeated failures' },
];

const codeSample = `import zroky

zroky.init(api_key="zk-your-key", project_id="your-project")

@zroky.trace
async def call_agent(prompt: str):
    return await agent.run(prompt)`;

export default function HomePage() {
  return (
    <div className="w-full bg-[#090b0f] text-white">
      <section className="relative isolate w-full overflow-hidden px-4 pb-10 pt-32 sm:px-6 lg:min-h-[84svh] lg:px-8 lg:pt-36">
        <img
          src="/product-replay-detail.png"
          alt="Zroky replay verification dashboard"
          className="absolute inset-0 -z-20 h-full w-full object-cover object-top opacity-[0.74]"
        />
        <div className="absolute inset-0 -z-10 bg-[linear-gradient(90deg,rgba(9,11,15,0.98)_0%,rgba(9,11,15,0.86)_36%,rgba(9,11,15,0.52)_66%,rgba(9,11,15,0.82)_100%)]" />
        <div className="absolute inset-x-0 bottom-0 -z-10 h-52 bg-gradient-to-t from-[#090b0f] to-transparent" />

        <div className="mx-auto flex max-w-[92rem] flex-col justify-center lg:min-h-[calc(84svh-12rem)]">
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
            className="max-w-4xl"
          >
            <div className="inline-flex items-center gap-2 rounded-full border border-orange-400/30 bg-orange-400/10 px-3 py-1.5 text-[11px] font-black uppercase tracking-[0.16em] text-orange-200">
              <ShieldCheck className="h-3.5 w-3.5" />
              AI agent failure replay
            </div>
            <h1 className="mt-6 max-w-4xl text-balance text-5xl font-black leading-[0.96] tracking-[-0.03em] text-white sm:text-6xl lg:text-7xl">
              Verified fixes for production AI agents.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-200 sm:text-xl">
              Zroky captures silent agent failures, replays the exact failed scenario, verifies whether the fix worked, and turns the case into a CI Golden.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <a
                href="/auth/register"
                className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-orange-500 px-6 py-3 text-sm font-black text-white shadow-[0_18px_45px_rgba(249,115,22,0.32)] transition duration-200 hover:bg-orange-400 focus:outline-none focus:ring-2 focus:ring-orange-300"
              >
                Start capturing failures
                <ArrowRight className="h-4 w-4" />
              </a>
              <Link
                to="/docs"
                className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full border border-white/[0.18] bg-white/[0.08] px-6 py-3 text-sm font-black text-white backdrop-blur transition duration-200 hover:bg-white/[0.14] focus:outline-none focus:ring-2 focus:ring-white/30"
              >
                Read docs
              </Link>
            </div>
            <div className="mt-10 grid max-w-3xl grid-cols-2 gap-3 sm:grid-cols-4">
              {trustSignals.map((signal) => (
                <div key={signal.label} className="border-l border-white/[0.18] pl-3">
                  <div className="font-mono text-lg font-black text-emerald-300">{signal.value}</div>
                  <div className="mt-1 text-xs font-bold leading-5 text-slate-300">{signal.label}</div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </section>

      <section className="border-y border-white/10 bg-[#101318] px-4 py-10 sm:px-6 lg:px-8">
        <div className="mx-auto grid max-w-[92rem] gap-4 md:grid-cols-5">
          {loopSteps.map((step, index) => {
            const Icon = step.icon;
            return (
              <article
                key={step.title}
                className="rounded-lg border border-white/10 bg-white/[0.035] p-4"
              >
                <div className="flex items-center justify-between">
                  <Icon className="h-5 w-5 text-orange-300" />
                  <span className="font-mono text-xs font-black text-slate-500">0{index + 1}</span>
                </div>
                <h2 className="mt-5 text-base font-black text-white">{step.title}</h2>
                <p className="mt-2 text-sm leading-6 text-slate-400">{step.body}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="bg-[#f6f7f9] px-4 py-24 text-[#101216] sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <div className="grid gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
            <div>
              <span className="eyebrow">
                <PlayCircle className="h-3.5 w-3.5 text-orange-500" />
                Product proof
              </span>
              <h2 className="mt-5 text-balance text-4xl font-black leading-tight tracking-[-0.02em] text-primary md:text-5xl">
                The landing page promise is visible inside the product.
              </h2>
              <p className="mt-5 text-lg leading-8 text-secondary">
                The dashboard is organized around one monetizable loop: failure inbox, issue diagnosis, trusted replay, verified fix, Golden creation, and CI regression gate.
              </p>
              <div className="mt-8 grid gap-4">
                {proofCards.map((card) => (
                  <article key={card.label} className="rounded-lg border border-panel-border bg-white p-5 shadow-premium">
                    <div className="text-[11px] font-black uppercase tracking-[0.14em] text-orange-600">{card.label}</div>
                    <h3 className="mt-2 text-xl font-black text-primary">{card.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-secondary">{card.body}</p>
                  </article>
                ))}
              </div>
            </div>
            <div className="overflow-hidden rounded-lg border border-slate-900/10 bg-[#0b0d11] shadow-[0_34px_90px_-45px_rgba(15,23,42,0.72)]">
              <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
                </div>
                <span className="font-mono text-xs font-bold text-emerald-300">VERIFIED_FIX</span>
              </div>
              <img
                src="/product-replay-detail.png"
                alt="Replay detail showing original failure, candidate replay, verification result, Golden eligibility, and CI gate"
                className="h-auto w-full"
                loading="lazy"
              />
            </div>
          </div>
        </div>
      </section>

      <section className="bg-white px-4 py-24 text-[#101216] sm:px-6 lg:px-8">
        <div className="mx-auto grid max-w-[92rem] gap-10 lg:grid-cols-[1fr_1fr] lg:items-start">
          <div>
            <span className="eyebrow">
              <GitBranch className="h-3.5 w-3.5 text-orange-500" />
              CI regression gate
            </span>
            <h2 className="mt-5 text-balance text-4xl font-black leading-tight tracking-[-0.02em] text-primary md:text-5xl">
              When replay fails, the PR gets blocked with evidence.
            </h2>
            <p className="mt-5 text-lg leading-8 text-secondary">
              Zroky is not a generic logs viewer. The end state is a release decision backed by the exact production behavior that regressed.
            </p>
            <div className="mt-8 grid gap-3">
              {[
                'Failed protected flows are named in plain language.',
                'Replay evidence explains why the verdict should block release.',
                'Reviewer comments can include blast radius, sample plan, and cost.',
              ].map((item) => (
                <div key={item} className="flex items-start gap-3 rounded-lg border border-panel-border bg-canvas px-4 py-3 text-sm font-bold text-secondary">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="overflow-hidden rounded-lg border border-panel-border bg-[#0b0d11] shadow-premium">
            <img
              src="/product-ci-gate.png"
              alt="CI gate detail showing a blocked regression run with replay evidence"
              className="h-auto w-full"
              loading="lazy"
            />
          </div>
        </div>
      </section>

      <section className="bg-[#101318] px-4 py-24 text-white sm:px-6 lg:px-8">
        <div className="mx-auto grid max-w-[92rem] gap-10 lg:grid-cols-[0.95fr_1.05fr] lg:items-center">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1.5 text-[11px] font-black uppercase tracking-[0.16em] text-emerald-200">
              <Code2 className="h-3.5 w-3.5" />
              Capture in minutes
            </span>
            <h2 className="mt-5 text-balance text-4xl font-black leading-tight tracking-[-0.02em] md:text-5xl">
              Add the SDK. Let production failures teach the gate.
            </h2>
            <p className="mt-5 text-lg leading-8 text-slate-300">
              Start with capture. The rest of the loop only matters when it is tied to real agent calls, real traces, and real failure evidence.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <a
                href="/auth/register"
                className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-orange-500 px-6 py-3 text-sm font-black text-white transition hover:bg-orange-400"
              >
                Create project
                <ArrowRight className="h-4 w-4" />
              </a>
              <Link
                to="/docs"
                className="inline-flex min-h-12 items-center justify-center rounded-full border border-white/15 bg-white/[0.08] px-6 py-3 text-sm font-black text-white transition hover:bg-white/[0.14]"
              >
                SDK docs
              </Link>
            </div>
          </div>
          <div className="overflow-hidden rounded-lg border border-white/10 bg-[#07090c] shadow-[0_34px_90px_-52px_rgba(16,185,129,0.5)]">
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
              <span className="font-mono text-xs font-bold text-slate-400">capture.py</span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/25 bg-emerald-400/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-emerald-300">
                <Timer className="h-3 w-3" />
                ready
              </span>
            </div>
            <pre className="overflow-x-auto p-5 text-sm leading-7 text-slate-200"><code>{codeSample}</code></pre>
          </div>
        </div>
      </section>

      <section className="bg-[#f6f7f9] px-4 py-24 text-[#101216] sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[92rem] rounded-lg border border-panel-border bg-white p-6 shadow-premium sm:p-8 lg:p-10">
          <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:items-center">
            <div>
              <h2 className="text-balance text-3xl font-black leading-tight tracking-[-0.02em] text-primary md:text-5xl">
                Built for the failure loop, not dashboard tourism.
              </h2>
              <p className="mt-4 text-lg leading-8 text-secondary">
                Every surface earns its place only if it helps answer: did the agent fail, why, can we replay it, did the fix work, and will it happen again?
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {[
                ['Observability dashboard', 'Shows traces, charts, and usage after the fact.'],
                ['Zroky', 'Turns the failed trace into a verified fix and a regression gate.'],
                ['Prompt playground', 'Tests new ideas away from production evidence.'],
                ['Zroky replay', 'Reuses the exact failed scenario before accepting the fix.'],
              ].map(([title, body]) => (
                <article key={title} className="rounded-lg border border-panel-border bg-canvas p-5">
                  <h3 className="text-base font-black text-primary">{title}</h3>
                  <p className="mt-2 text-sm leading-6 text-secondary">{body}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
