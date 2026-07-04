import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import {
  ArrowRight,
  Check,
  FileText,
  GitBranch,
  KeyRound,
  Layers,
  Lock,
  PlayCircle,
  ShieldCheck,
  Terminal,
  Workflow,
} from 'lucide-react';
import { SIGN_UP_URL } from '../lib/links';

const releases = [
  {
    label: 'Replay safety',
    stage: 'Current',
    icon: KeyRound,
    title: 'Provider-key gate for verified replay.',
    summary:
      'Capture, traces, issues, and basic dashboard review stay usable without provider keys. Zroky asks for a provider key only when verified replay needs real provider execution.',
    shipped: [
      'Replay Lab prompts for a provider key before real replay modes.',
      'Issue replay entry points use the same verified replay gate.',
      'Stub replay remains available and clearly marked sanity-only.',
      'Pricing copy now explains that keys are requested only for verified replay.',
    ],
    proof: 'No signup key wall. No silent real replay failure.',
    href: '/docs#provider-keys',
    cta: 'Provider key docs',
  },
  {
    label: 'Docs',
    stage: 'Current',
    icon: FileText,
    title: 'Real docs path from capture to CI gates.',
    summary:
      'The docs overview now leads into dedicated implementation guides for SDK capture, Gateway capture, provider keys, replay, Goldens, CI gates, and troubleshooting.',
    shipped: [
      'Quickstart explains the full failure-to-release adoption path.',
      'Python and TypeScript SDK pages include real capture snippets.',
      'Gateway and GitHub Action guides cover routing and CI setup.',
      'Troubleshooting separates capture, replay, Golden, and CI failure modes.',
    ],
    proof: 'A new user can follow one ordered path instead of guessing where to start.',
    href: '/docs#quickstart',
    cta: 'Open quickstart',
  },
  {
    label: 'Pricing',
    stage: 'Current',
    icon: Lock,
    title: 'Predictable BYOK pricing model.',
    summary:
      'Pricing now starts with adoption-friendly plans and keeps model spend visible by default. Real replay and CI usage have explicit caps instead of hidden unlimited behavior.',
    shipped: [
      'Watch, Builder, Startup, and Team plans are framed by reliability stage.',
      'BYOK is default for real LLM replay.',
      'Managed replay is optional and explained as provider cost plus platform fee.',
      'Extra captured calls, replay credits, and CI executions have clear overage rules.',
    ],
    proof: 'Organizations can start cheap and scale only when replay and CI become business-critical.',
    href: '/pricing',
    cta: 'View pricing',
  },
  {
    label: 'Product OS',
    stage: 'Recent',
    icon: Workflow,
    title: 'Reliability loop becomes the core product story.',
    summary:
      'The product now presents Zroky as one operating loop: discover the unknown failure, prove the fix with replay, and guard the release in CI.',
    shipped: [
      'Home page uses the Discover, Prove, Guard loop as the main narrative.',
      'Each pillar maps to an outcome and evidence panel.',
      'Dashboard visuals focus on failure inbox, issues, replay, Goldens, CI gates, traces, and cost.',
      'Proof sections now describe decisions, not dashboard tourism.',
    ],
    proof: 'Every major page now points back to capture, proof, memory, and release decision.',
    href: '/#architecture',
    cta: 'View product loop',
  },
  {
    label: 'Onboarding',
    stage: 'Recent',
    icon: ShieldCheck,
    title: 'Dark auth flow aligned with product trust.',
    summary:
      'Login, registration, password recovery, email verification, and reset screens now use the same monochrome black/white Zroky system as the rest of the site.',
    shipped: [
      'Signup copy confirms capture-first onboarding.',
      'Auth forms use black inputs, white actions, and restrained accents.',
      'Recovery screens explain workspace access without mixing in provider credentials.',
      'Verification sends users to the real quickstart path.',
    ],
    proof: 'Auth no longer feels like a separate older product.',
    href: SIGN_UP_URL,
    cta: 'Create workspace',
  },
];

const principles = [
  {
    icon: Check,
    title: 'Verified means real proof',
    body: 'Stub replay can sanity-check structure, but verified proof needs real replay against the incident.',
  },
  {
    icon: KeyRound,
    title: 'Keys only when needed',
    body: 'Signup and capture stay open. Provider keys appear when verified replay, Golden replay, or CI replay needs them.',
  },
  {
    icon: GitBranch,
    title: 'CI remembers production',
    body: 'A passing replay can become a Golden so repeated failures are blocked before release.',
  },
];

const focus = [
  ['Capture first', 'Production evidence enters Zroky through SDK or Gateway.'],
  ['Replay proof', 'Fixes run against the original incident before trust.'],
  ['Golden memory', 'Passing proof becomes reusable release protection.'],
  ['CI verdict', 'Pull requests get pass, warn, or block decisions.'],
];

const revealEase = [0.16, 1, 0.3, 1] as const;

function SectionReveal({
  className,
  children,
  delay = 0,
}: {
  className?: string;
  children: ReactNode;
  delay?: number;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.section
      initial={reduceMotion ? false : { opacity: 0, y: 22 }}
      whileInView={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.14, margin: '-80px' }}
      transition={{ duration: 0.52, delay, ease: revealEase }}
      className={className}
    >
      {children}
    </motion.section>
  );
}

export default function ChangelogPage() {
  const reduceMotion = useReducedMotion();

  return (
    <div className="w-full overflow-x-hidden">
      <section className="relative isolate border-b border-line px-4 pb-14 pt-40 sm:px-6 sm:pb-20 sm:pt-44 lg:px-8">
        <div className="pointer-events-none absolute inset-0 -z-10">
          <div className="grid-bg absolute inset-x-0 top-0 h-[32rem] opacity-70" />
          <motion.div
            aria-hidden="true"
            animate={reduceMotion ? undefined : { rotate: 360 }}
            transition={{ duration: 36, repeat: Infinity, ease: 'linear' }}
            className="absolute left-1/2 top-28 h-72 w-72 -ml-36 rounded-full border border-line bg-[conic-gradient(from_130deg,transparent,rgba(255,255,255,0.18),transparent,rgba(255,255,255,0.1),transparent)] blur-2xl"
          />
        </div>

        <div className="mx-auto grid max-w-[92rem] items-end gap-10 lg:grid-cols-[1fr_0.9fr]">
          <div>
            <span className="eyebrow">
              <Layers className="h-3.5 w-3.5" />
              Product changelog
            </span>
            <h1 className="mt-6 max-w-5xl text-balance text-4xl font-semibold leading-[1.04] text-primary sm:text-6xl lg:text-7xl">
              Release notes for the agent reliability loop.
            </h1>
            <p className="mt-6 max-w-3xl text-base leading-8 text-secondary sm:text-lg">
              Zroky ships changes when they make capture, replay proof, Golden memory, CI gates, pricing, or onboarding clearer for production AI teams.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link to="/docs#quickstart" className="btn-primary">
                Start with docs
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link to="/#architecture" className="btn-ghost">
                View product loop
                <Workflow className="h-4 w-4" />
              </Link>
            </div>
          </div>

          <motion.div
            initial={reduceMotion ? false : { opacity: 0, y: 18 }}
            animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
            transition={{ duration: 0.58, ease: revealEase }}
            className="card p-4"
          >
            <div className="rounded-xl border border-line bg-ink p-4">
              <div className="mb-4 flex items-center justify-between gap-3">
                <span className="font-mono text-[10px] uppercase tracking-wider text-tertiary">release focus</span>
                <span className="rounded-md border border-line px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-tertiary">current</span>
              </div>
              <div className="grid gap-2">
                {focus.map(([title, body], index) => (
                  <div key={title} className="rounded-lg border border-line bg-white/[0.03] p-3">
                    <div className="flex items-center gap-3">
                      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md border border-line bg-white/[0.04] font-mono text-[10px] text-secondary">
                        {index + 1}
                      </span>
                      <div>
                        <p className="text-sm font-semibold text-primary">{title}</p>
                        <p className="mt-0.5 text-xs leading-5 text-tertiary">{body}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      <SectionReveal className="border-b border-line px-4 py-14 sm:px-6 sm:py-16 lg:px-8">
        <div className="mx-auto grid max-w-[92rem] gap-4 lg:grid-cols-3">
          {principles.map((principle) => {
            const Icon = principle.icon;
            return (
              <div key={principle.title} className="card p-5">
                <span className="grid h-11 w-11 place-items-center rounded-xl border border-line bg-white/[0.04]">
                  <Icon className="h-5 w-5 text-primary" />
                </span>
                <h2 className="mt-5 text-xl font-semibold text-primary">{principle.title}</h2>
                <p className="mt-3 text-sm leading-6 text-secondary">{principle.body}</p>
              </div>
            );
          })}
        </div>
      </SectionReveal>

      <SectionReveal className="px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <div className="max-w-3xl">
            <span className="eyebrow">
              <span className="h-1.5 w-1.5 rounded-full bg-primary" />
              Release stream
            </span>
            <h2 className="mt-5 text-balance text-3xl font-semibold leading-tight text-primary sm:text-4xl lg:text-5xl">
              Every note maps to a product decision.
            </h2>
            <p className="mt-4 text-base leading-8 text-secondary sm:text-lg">
              We keep the changelog focused on changes that alter how teams capture evidence, prove fixes, control spend, or block repeat regressions.
            </p>
          </div>

          <div className="relative mt-10 grid gap-5">
            <div className="absolute bottom-0 left-5 top-0 hidden w-px bg-line md:block" />
            {releases.map((release, index) => {
              const Icon = release.icon;
              return (
                <motion.article
                  key={release.title}
                  initial={reduceMotion ? false : { opacity: 0, x: -16 }}
                  whileInView={reduceMotion ? { opacity: 1 } : { opacity: 1, x: 0 }}
                  viewport={{ once: true, amount: 0.12, margin: '-80px' }}
                  transition={{ duration: 0.44, delay: index * 0.03, ease: revealEase }}
                  className="relative md:pl-16"
                >
                  <span className="absolute left-0 top-6 hidden h-10 w-10 place-items-center rounded-xl border border-line bg-ink md:grid">
                    <Icon className="h-5 w-5 text-primary" />
                  </span>

                  <div className="card overflow-hidden p-0">
                    <div className="border-b border-line bg-white/[0.03] p-5">
                      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded-full border border-line bg-white/[0.04] px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-secondary">
                              {release.label}
                            </span>
                            <span className="rounded-full border border-line bg-ink px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-tertiary">
                              {release.stage}
                            </span>
                          </div>
                          <h3 className="mt-4 text-2xl font-semibold leading-tight text-primary">{release.title}</h3>
                          <p className="mt-3 max-w-4xl text-sm leading-7 text-secondary">{release.summary}</p>
                        </div>
                        <a href={release.href} className="btn-ghost shrink-0">
                          {release.cta}
                          <ArrowRight className="h-4 w-4" />
                        </a>
                      </div>
                    </div>

                    <div className="grid gap-5 p-5 lg:grid-cols-[1fr_18rem]">
                      <div className="grid gap-3">
                        {release.shipped.map((item) => (
                          <div key={item} className="flex gap-3 rounded-lg border border-line bg-ink p-4">
                            <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                            <p className="text-sm font-semibold leading-6 text-secondary">{item}</p>
                          </div>
                        ))}
                      </div>
                      <div className="rounded-xl border border-line bg-ink p-4">
                        <div className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-tertiary">
                          <PlayCircle className="h-3.5 w-3.5" />
                          Decision proof
                        </div>
                        <p className="text-sm font-semibold leading-6 text-primary">{release.proof}</p>
                      </div>
                    </div>
                  </div>
                </motion.article>
              );
            })}
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="px-4 pb-24 pt-4 sm:px-6 lg:px-8">
        <div className="card mx-auto max-w-[92rem] p-6 sm:p-8 lg:p-10">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <span className="eyebrow">
                <Terminal className="h-3.5 w-3.5" />
                Start from evidence
              </span>
              <h2 className="mt-5 text-balance text-3xl font-semibold leading-tight text-primary sm:text-5xl">
                Capture one failure, then block it before it ships twice.
              </h2>
              <p className="mt-4 text-base leading-8 text-secondary">
                The release log is useful only if the product path is clear: capture, replay, Golden, and CI gate.
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <a href={SIGN_UP_URL} className="btn-primary">
                Protect an agent
                <ArrowRight className="h-4 w-4" />
              </a>
              <Link to="/docs#ci-gates" className="btn-ghost">
                CI gate docs
                <GitBranch className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </div>
      </SectionReveal>
    </div>
  );
}
