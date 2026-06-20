import { type ReactNode } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Banknote,
  Check,
  CircleDollarSign,
  Database,
  FileCheck2,
  GitBranch,
  KeyRound,
  Lock,
  MailCheck,
  Rocket,
  Scale,
  Server,
  ShieldCheck,
  type LucideIcon,
  Zap,
} from 'lucide-react';
import pricingContract from '../data/pricing-plans.json';
import { buildSignUpUrl } from '../lib/links';

type PlanCode = 'free' | 'starter' | 'pro' | 'enterprise';

type PricingPlan = {
  code: PlanCode;
  name: string;
  price: {
    label: string;
    monthly_usd: number | null;
    period: string;
  };
  description: string;
  cta: {
    label: string;
    href: string;
  };
  featured: boolean;
  note: string;
  pricing: {
    calls_per_month: number;
    retention_days: number;
    replay_credits: number;
    golden_traces: number;
    golden_sets: number;
    non_blocking_ci: boolean;
    blocking_ci: boolean;
    provider_key_vault: boolean;
  };
  enforcement: {
    limits: {
      max_projects: number;
      max_members: number;
    };
  };
};

const UNLIMITED = pricingContract.unlimited;
const numberFormatter = new Intl.NumberFormat('en-US');
const compactNumberFormatter = new Intl.NumberFormat('en-US', {
  notation: 'compact',
  maximumFractionDigits: 0,
});

const planIcons: Record<PlanCode, LucideIcon> = {
  free: Activity,
  starter: Zap,
  pro: GitBranch,
  enterprise: Server,
};

function buildPricingSignUpUrl(plan: PlanCode, source = 'pricing') {
  return buildSignUpUrl({
    intent: 'protect-agent',
    plan,
    source,
  });
}

function formatLimit(value: number, singular: string, plural = `${singular}s`) {
  if (value === UNLIMITED) {
    return `Unlimited ${plural}`;
  }
  return `${numberFormatter.format(value)} ${value === 1 ? singular : plural}`;
}

function formatMonthlyCalls(value: number) {
  if (value === UNLIMITED) {
    return 'Unlimited captured calls/mo';
  }
  return `${compactNumberFormatter.format(value)} captured calls/mo`;
}

function formatRetention(days: number) {
  if (days === UNLIMITED) {
    return 'Custom retention';
  }
  return `${numberFormatter.format(days)}-day retention`;
}

function formatReplayCredits(credits: number) {
  if (credits === UNLIMITED) {
    return 'Unlimited replay credits/mo';
  }
  if (credits === 0) {
    return 'Replay credits locked';
  }
  return `${numberFormatter.format(credits)} replay credits/mo`;
}

function formatGoldens(traces: number, sets: number) {
  if (traces === UNLIMITED && sets === UNLIMITED) {
    return 'Unlimited Golden traces and sets';
  }
  if (traces === 0 && sets === 0) {
    return 'Goldens locked';
  }
  return `${numberFormatter.format(traces)} Golden traces across ${numberFormatter.format(sets)} sets`;
}

function formatCiGates(nonBlocking: boolean, blocking: boolean) {
  if (nonBlocking && blocking) {
    return 'Non-blocking and blocking CI gates';
  }
  if (nonBlocking) {
    return 'Non-blocking CI gates';
  }
  return 'CI gates locked';
}

function formatProviderVault(enabled: boolean) {
  return enabled ? 'Provider key vault included' : 'Provider key vault locked';
}

function formatProjectSeats(projects: number, seats: number) {
  if (projects === UNLIMITED && seats === UNLIMITED) {
    return 'Unlimited projects and seats';
  }
  return `${formatLimit(projects, 'project')} and ${formatLimit(seats, 'seat')}`;
}

function buildPlanBullets(plan: PricingPlan) {
  return [
    formatProjectSeats(plan.enforcement.limits.max_projects, plan.enforcement.limits.max_members),
    formatMonthlyCalls(plan.pricing.calls_per_month),
    formatRetention(plan.pricing.retention_days),
    formatReplayCredits(plan.pricing.replay_credits),
    formatGoldens(plan.pricing.golden_traces, plan.pricing.golden_sets),
    formatCiGates(plan.pricing.non_blocking_ci, plan.pricing.blocking_ci),
    formatProviderVault(plan.pricing.provider_key_vault),
  ];
}

const allPlans = pricingContract.plans as PricingPlan[];
const enterprisePlan = allPlans.find((plan) => plan.code === 'enterprise');

const plans = allPlans
  .filter((plan) => plan.code !== 'enterprise')
  .map((plan) => ({
    code: plan.code,
    name: plan.name,
    price: plan.price.label,
    period: plan.price.period,
    desc: plan.description,
    icon: planIcons[plan.code],
    cta: plan.cta.label,
    href: plan.cta.href === '/auth/register' ? buildPricingSignUpUrl(plan.code) : plan.cta.href,
    featured: plan.featured,
    bullets: buildPlanBullets(plan),
    note: plan.note,
  }));

const proPlan = plans.find((plan) => plan.code === 'pro');
const starterPlan = plans.find((plan) => plan.code === 'starter');

const riskMetrics = [
  {
    label: 'Example action value',
    value: '$250K/mo',
    body: 'Total monthly value handled by one protected agent, such as refunds, payouts, or purchase orders.',
  },
  {
    label: 'Example incident loss',
    value: '$8K',
    body: 'One wrong action can create direct loss, manual reconciliation, SLA impact, and customer trust damage.',
  },
  {
    label: 'Self-serve protection',
    value: proPlan ? `${proPlan.price}/mo` : '$199/mo',
    body: 'Pro is priced below the cost of one material mistake for teams ready to gate production behavior.',
  },
];

const planFit = [
  {
    icon: Activity,
    plan: 'Free',
    fit: 'Instrument real traffic and prove Zroky can see the action path.',
    trigger: 'Use before delegation, when the team still needs capture confidence.',
  },
  {
    icon: Zap,
    plan: 'Starter',
    fit: 'Protect the first serious agent with diagnosis, mocked replay, Goldens, and non-blocking CI.',
    trigger: `Use when ${starterPlan?.price ?? '$49'}/mo is easier than manual review for every run.`,
  },
  {
    icon: ShieldCheck,
    plan: 'Pro',
    fit: 'Gate unattended production agents with real replay, blocking CI, outcome attribution, and evidence exports.',
    trigger: 'Use when a wrong action has real financial, operational, or customer impact.',
  },
  {
    icon: Server,
    plan: 'Enterprise',
    fit: 'Add private execution, custom retention, custom detectors, and procurement-ready controls.',
    trigger: 'Use when risk, audit, or customer requirements need a contract and deployment plan.',
  },
];

const agentRiskRows: Array<{
  icon: LucideIcon;
  agent: string;
  action: string;
  pain: string;
  proof: string;
  plan: string;
}> = [
  {
    icon: Banknote,
    agent: 'Payment and refund agents',
    action: 'Refunds, payouts, reversals, credits',
    pain: 'Direct cash loss and painful reconciliation when success is reported but the ledger is wrong.',
    proof: 'Runtime hold or block, then ledger reconciliation and evidence hash.',
    plan: 'Pro or Enterprise',
  },
  {
    icon: Rocket,
    agent: 'DevOps and release agents',
    action: 'Deploys, rollbacks, infra edits, config changes',
    pain: 'A single bad tool call can ship broken code, leak config, or mutate production state.',
    proof: 'Blocking CI gate, replayable failure evidence, approval trail.',
    plan: 'Pro',
  },
  {
    icon: Database,
    agent: 'CRM and data mutation agents',
    action: 'Record merges, account updates, ownership changes',
    pain: 'Duplicate or corrupted records quietly break sales, support, and compliance workflows.',
    proof: 'Policy snapshot, system-of-record check, not_verified state when proof is missing.',
    plan: 'Starter to Pro',
  },
  {
    icon: MailCheck,
    agent: 'Lifecycle and outreach agents',
    action: 'Mass email, customer notifications, ticket replies',
    pain: 'Wrong recipients, bounced campaigns, or unauthorized messaging create brand and legal exposure.',
    proof: 'Mandate check before send, delivery outcome verification after send.',
    plan: 'Pro',
  },
  {
    icon: FileCheck2,
    agent: 'Procurement and expense agents',
    action: 'Vendor approvals, purchase orders, invoice routing',
    pain: 'Incorrect approval paths or duplicate invoices turn into cash leakage and audit exceptions.',
    proof: 'Approval audit, spend-limit policy, invoice or PO reconciliation.',
    plan: 'Enterprise',
  },
];

const proofSteps = [
  {
    icon: AlertTriangle,
    title: '1. Price the risky action',
    body: 'Pick the agent whose wrong action creates the clearest dollar, compliance, or customer impact.',
  },
  {
    icon: Scale,
    title: '2. Set the mandate',
    body: 'Define what it may do, when approval is required, and what must be blocked by default.',
  },
  {
    icon: ShieldCheck,
    title: '3. Gate the action',
    body: 'Zroky returns allow, hold, or block before the irreversible operation commits.',
  },
  {
    icon: FileCheck2,
    title: '4. Prove the outcome',
    body: 'The evidence pack shows decision, policy snapshot, approval audit, reconciliation, and hash.',
  },
];

const usageRules = [
  {
    icon: KeyRound,
    title: 'Bring your provider key',
    body: 'Real LLM replay defaults to your OpenAI, Anthropic, or Gemini key. Zroky charges for protection workflow, not hidden model spend.',
  },
  {
    icon: CircleDollarSign,
    title: 'Managed replay is optional',
    body: 'If Zroky pays the provider bill, usage is provider token cost plus a 30% platform fee for billing, retries, limits, and support.',
  },
  {
    icon: Lock,
    title: 'Caps protect both sides',
    body: 'Self-serve plans use explicit replay and CI limits. Organizations get alerts before limits, then upgrade or pause new safety execution.',
  },
];

const overages = [
  ['Extra captured calls', 'Plan upgrade'],
  ['Extra verified replay', 'Quoted add-on'],
  ['Managed provider spend', 'Provider cost + service fee'],
];

const faqs = [
  {
    q: 'Should we buy Zroky only for refund agents?',
    a: 'No. Start where the action is expensive or irreversible. Refunds are a sharp wedge, but deploys, CRM mutations, purchase approvals, and mass messaging need the same action-accountability loop.',
  },
  {
    q: 'What counts as a replay run?',
    a: 'A replay run is one verified attempt against captured production evidence. Starter supports mocked-tool replay. Pro adds real LLM replay and live-sandbox replay through your provider key or optional Zroky-managed execution.',
  },
  {
    q: 'Why is BYOK the default?',
    a: 'Provider cost can multiply quickly when teams replay many failures or run Goldens in CI. BYOK keeps model spend visible in your provider account and keeps Zroky pricing predictable.',
  },
  {
    q: 'When do you ask for a provider key?',
    a: 'We only ask for a provider key when you run verified replay, not during signup or capture. You can capture failures, inspect traces, and review issues before connecting a key.',
  },
  {
    q: 'What happens when limits are reached?',
    a: 'Zroky shows usage alerts before the limit. You can upgrade, buy overage, or pause new replay or CI execution while captured evidence remains available within your retention window.',
  },
  {
    q: 'When should we talk to sales?',
    a: 'Talk to sales when the protected agent needs private execution, custom retention, custom connectors, procurement review, or audit commitments beyond self-serve terms.',
  },
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

export default function PricingPage() {
  const reduceMotion = useReducedMotion();
  const enterpriseHref = enterprisePlan?.cta.href ?? 'mailto:sales@zroky.com?subject=Zroky%20Enterprise';
  const heroSignUpUrl = buildPricingSignUpUrl('pro', 'pricing-hero');

  return (
    <div className="w-full overflow-x-hidden">
      <section className="relative isolate border-b border-line px-4 pb-12 pt-28 sm:px-6 sm:pb-16 sm:pt-32 lg:px-8">
        <div className="pointer-events-none absolute inset-0 -z-10">
          <div className="grid-bg absolute inset-x-0 top-0 h-[34rem] opacity-70" />
          <motion.div
            aria-hidden="true"
            animate={reduceMotion ? undefined : { rotate: 360 }}
            transition={{ duration: 34, repeat: Infinity, ease: 'linear' }}
            className="absolute right-[8%] top-24 h-72 w-72 rounded-full border border-line bg-[conic-gradient(from_130deg,transparent,rgba(255,255,255,0.18),transparent,rgba(255,255,255,0.1),transparent)] blur-2xl"
          />
        </div>

        <div className="mx-auto grid max-w-[92rem] items-start gap-10 lg:grid-cols-2">
          <div>
            <span className="eyebrow">
              <CircleDollarSign className="h-3.5 w-3.5" />
              Risk-value pricing
            </span>
            <h1 className="mt-6 max-w-4xl text-balance text-4xl font-semibold leading-[1.04] text-primary sm:text-6xl">
              Price Zroky against the action it protects.
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-8 text-secondary sm:text-lg">
              Stop unsafe actions before they commit, then prove the outcome in the system of record.
            </p>

            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <a href={heroSignUpUrl} className="btn-primary">
                Start free
                <ArrowRight className="h-4 w-4" />
              </a>
              <a href="#plan-fit" className="btn-ghost">
                Match a plan to risk
              </a>
            </div>

            <div className="mt-8 grid grid-cols-3 gap-2">
              {['Allow', 'Hold for approval', 'Block'].map((status) => (
                <div key={status} className="rounded-xl border border-line bg-ink px-3 py-3 sm:px-4">
                  <div className="font-mono text-[9px] uppercase tracking-wider text-tertiary sm:text-[10px]">
                    <span className="sm:hidden">Decision</span>
                    <span className="hidden sm:inline">Runtime decision</span>
                  </div>
                  <p className="mt-2 text-xs font-semibold leading-5 text-primary sm:text-sm">{status}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="browser-frame hidden overflow-hidden p-2 lg:block">
            <img
              src="/product-ci-gate.png"
              alt="Zroky product screen showing a CI gate connected to captured agent evidence"
              className="max-h-[460px] w-full rounded-xl border border-line object-cover object-top"
            />
          </div>
        </div>
      </section>

      <SectionReveal className="border-b border-line px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="mx-auto grid max-w-[92rem] gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-2xl border border-line bg-white/[0.03] p-5 sm:p-7">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <span className="inline-flex items-center gap-2 text-sm font-semibold text-primary">
                  <Banknote className="h-4 w-4" />
                  Dollar anchor
                </span>
                <h2 className="mt-4 max-w-3xl text-balance text-3xl font-semibold leading-tight text-primary md:text-5xl">
                  The right plan is cheaper than one bad autonomous action.
                </h2>
              </div>
              <span className="rounded-full border border-line bg-ink px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-tertiary">
                Example, not a claim
              </span>
            </div>

            <div className="mt-8 grid gap-3 md:grid-cols-3">
              {riskMetrics.map((metric) => (
                <div key={metric.label} className="rounded-xl border border-line bg-ink p-4">
                  <div className="font-mono text-[10px] uppercase tracking-wider text-tertiary">{metric.label}</div>
                  <div className="mt-3 text-3xl font-semibold text-primary">{metric.value}</div>
                  <p className="mt-3 text-sm leading-6 text-secondary">{metric.body}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-line bg-ink p-5 sm:p-7">
            <span className="inline-flex items-center gap-2 text-sm font-semibold text-primary">
              <ShieldCheck className="h-4 w-4" />
              Buying rule
            </span>
            <p className="mt-5 text-2xl font-semibold leading-tight text-primary">
              Buy when a human is still approving the agent because the consequence is too expensive to trust blindly.
            </p>
            <div className="mt-6 divider" />
            <div className="mt-6 grid gap-3">
              {[
                'One wrong action has a direct dollar cost.',
                'The team cannot prove what happened after the agent says done.',
                'Risk, audit, or an enterprise customer requires accountability evidence.',
              ].map((item) => (
                <div key={item} className="flex items-start gap-3">
                  <Check className="mt-1 h-4 w-4 shrink-0 text-primary" />
                  <p className="text-sm font-semibold leading-6 text-secondary">{item}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="border-b border-line px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <div className="max-w-3xl">
            <span className="inline-flex items-center gap-2 text-sm font-semibold text-primary">
              <Scale className="h-4 w-4" />
              Plan fit
            </span>
            <h2 id="plan-fit" className="mt-4 text-balance text-4xl font-semibold leading-tight text-primary md:text-5xl">
              Start with evidence. Upgrade when the agent can hurt the business.
            </h2>
          </div>

          <div className="mt-10 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {planFit.map((item) => {
              const Icon = item.icon;

              return (
                <article key={item.plan} className="rounded-2xl border border-line bg-white/[0.03] p-5">
                  <span className="grid h-11 w-11 place-items-center rounded-xl border border-line bg-ink">
                    <Icon className="h-5 w-5 text-primary" />
                  </span>
                  <h3 className="mt-5 text-xl font-semibold text-primary">{item.plan}</h3>
                  <p className="mt-3 text-sm leading-7 text-secondary">{item.fit}</p>
                  <p className="mt-4 rounded-xl border border-line bg-ink px-3 py-3 text-xs font-semibold leading-5 text-tertiary">
                    {item.trigger}
                  </p>
                </article>
              );
            })}
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="border-b border-line px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <div className="grid gap-3 md:grid-cols-3">
            {plans.map((plan, index) => {
              const Icon = plan.icon;

              return (
                <motion.article
                  key={plan.name}
                  initial={reduceMotion ? false : { opacity: 0, y: 18 }}
                  whileInView={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.2 }}
                  transition={{ duration: 0.44, delay: index * 0.05, ease: revealEase }}
                  className={`card flex min-h-[35rem] flex-col p-5 ${
                    plan.featured ? 'border-line-strong bg-white/[0.06]' : ''
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <span
                      className={`grid h-11 w-11 place-items-center rounded-xl border ${
                        plan.featured ? 'border-line-strong bg-white/[0.08]' : 'border-line bg-white/[0.04]'
                      }`}
                    >
                      <Icon className={plan.featured ? 'h-5 w-5 text-primary' : 'h-5 w-5 text-secondary'} />
                    </span>
                    {plan.featured && (
                      <span className="rounded-full border border-line-strong bg-white/[0.06] px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-primary">
                        Main plan
                      </span>
                    )}
                  </div>

                  <h2 className="mt-6 text-2xl font-semibold text-primary">{plan.name}</h2>
                  <div className="mt-3 flex items-end gap-1">
                    <span className="text-5xl font-semibold tracking-normal text-primary">{plan.price}</span>
                    <span className="pb-1 text-sm font-semibold text-tertiary">{plan.period}</span>
                  </div>
                  <p className="mt-4 min-h-14 text-sm leading-7 text-secondary">{plan.desc}</p>

                  <div className="mt-5 divider" />

                  <div className="mt-5 grid gap-3">
                    {plan.bullets.map((bullet) => (
                      <div key={bullet} className="flex items-start gap-2 text-sm leading-6">
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                        <span className="font-semibold text-secondary">{bullet}</span>
                      </div>
                    ))}
                  </div>

                  <p className="mt-5 rounded-xl border border-line bg-ink px-3 py-3 text-xs font-semibold leading-5 text-tertiary">
                    {plan.note}
                  </p>

                  <a href={plan.href} className={`mt-auto ${plan.featured ? 'btn-primary' : 'btn-ghost'} !w-full`}>
                    {plan.cta}
                    <ArrowRight className="h-4 w-4" />
                  </a>
                </motion.article>
              );
            })}
          </div>

          <div className="mt-4 grid gap-4 rounded-2xl border border-line bg-ink p-5 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
            <div>
              <span className="inline-flex items-center gap-2 text-sm font-semibold text-primary">
                <Server className="h-4 w-4" />
                Enterprise
              </span>
              <h3 className="mt-3 text-2xl font-semibold text-primary">For agents that need audit, private execution, or custom connectors.</h3>
            </div>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
              <p className="text-sm leading-7 text-secondary">
                Enterprise maps to contract entitlements: unlimited limits, private replay workers, custom retention, custom detectors, and system-of-record integration planning.
              </p>
              <a href={enterpriseHref} className="btn-ghost">
                Talk to Zroky
                <ArrowRight className="h-4 w-4" />
              </a>
            </div>
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="border-b border-line px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <div className="grid gap-10 lg:grid-cols-[0.82fr_1.18fr]">
            <div>
              <span className="inline-flex items-center gap-2 text-sm font-semibold text-primary">
                <Activity className="h-4 w-4" />
                Highest-pain agents
              </span>
              <h2 className="mt-4 text-balance text-4xl font-semibold leading-tight text-primary md:text-5xl">
                Not just refunds. Protect every agent that mutates reality.
              </h2>
              <p className="mt-5 text-base leading-8 text-secondary">
                The first paid wedge should be where error cost is obvious, but the same loop covers any autonomous agent with irreversible operations.
              </p>
            </div>

            <div className="grid gap-3">
              {agentRiskRows.map((row) => {
                const Icon = row.icon;

                return (
                  <article key={row.agent} className="rounded-2xl border border-line bg-white/[0.03] p-4">
                    <div className="grid gap-4 lg:grid-cols-[2.1fr_1.35fr_1.1fr] lg:items-start">
                      <div className="flex gap-4">
                        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-line bg-ink">
                          <Icon className="h-5 w-5 text-primary" />
                        </span>
                        <div>
                          <h3 className="text-base font-semibold text-primary">{row.agent}</h3>
                          <p className="mt-1 text-sm leading-6 text-tertiary">{row.action}</p>
                          <p className="mt-3 text-sm leading-6 text-secondary">{row.pain}</p>
                        </div>
                      </div>
                      <div>
                        <div className="font-mono text-[10px] uppercase tracking-wider text-tertiary">Zroky proof</div>
                        <p className="mt-2 text-sm font-semibold leading-6 text-secondary">{row.proof}</p>
                      </div>
                      <div className="rounded-xl border border-line bg-ink px-3 py-3">
                        <div className="font-mono text-[10px] uppercase tracking-wider text-tertiary">Plan</div>
                        <p className="mt-2 text-sm font-semibold text-primary">{row.plan}</p>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="border-b border-line px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <div className="grid gap-10 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
            <div className="browser-frame overflow-hidden p-2">
              <img
                src="/product-replay-detail.png"
                alt="Zroky replay detail screen showing verified evidence for an agent failure"
                className="h-full w-full rounded-xl border border-line object-cover"
              />
            </div>

            <div>
              <span className="inline-flex items-center gap-2 text-sm font-semibold text-primary">
                <FileCheck2 className="h-4 w-4" />
                Proof chain
              </span>
              <h2 className="mt-4 text-balance text-4xl font-semibold leading-tight text-primary md:text-5xl">
                Every paid claim has to end in evidence.
              </h2>
              <div className="mt-8 grid gap-3">
                {proofSteps.map((step) => {
                  const Icon = step.icon;

                  return (
                    <div key={step.title} className="flex gap-4 rounded-2xl border border-line bg-white/[0.03] p-4">
                      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-line bg-ink">
                        <Icon className="h-5 w-5 text-primary" />
                      </span>
                      <div>
                        <h3 className="text-sm font-semibold text-primary">{step.title}</h3>
                        <p className="mt-2 text-sm leading-6 text-secondary">{step.body}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="border-b border-line px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <div className="max-w-3xl">
            <span className="inline-flex items-center gap-2 text-sm font-semibold text-primary">
              <KeyRound className="h-4 w-4" />
              Predictable usage
            </span>
            <h2 className="mt-4 text-balance text-4xl font-semibold leading-tight text-primary md:text-5xl">
              Subscription covers the protection system. Usage covers the parts that can spike.
            </h2>
          </div>

          <div className="mt-10 grid gap-4 lg:grid-cols-3">
            {usageRules.map((rule) => {
              const Icon = rule.icon;

              return (
                <div key={rule.title} className="card p-6">
                  <span className="grid h-11 w-11 place-items-center rounded-xl border border-line bg-white/[0.04]">
                    <Icon className="h-5 w-5 text-primary" />
                  </span>
                  <h3 className="mt-5 text-xl font-semibold text-primary">{rule.title}</h3>
                  <p className="mt-3 text-sm leading-7 text-secondary">{rule.body}</p>
                </div>
              );
            })}
          </div>

          <div className="mt-5 rounded-2xl border border-line bg-ink p-4">
            <div className="grid gap-3 md:grid-cols-3">
              {overages.map(([label, price]) => (
                <div key={label} className="flex min-h-20 items-center justify-between gap-4 rounded-xl border border-line bg-white/[0.03] px-4 py-3">
                  <span className="text-sm font-semibold text-secondary">{label}</span>
                  <span className="font-mono text-sm text-primary">{price}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <div className="grid gap-10 lg:grid-cols-[0.72fr_1.28fr]">
            <div>
              <span className="inline-flex items-center gap-2 text-sm font-semibold text-primary">
                <ShieldCheck className="h-4 w-4" />
                FAQ
              </span>
              <h2 className="mt-4 text-balance text-4xl font-semibold leading-tight text-primary md:text-5xl">
                Clear rules before the team depends on it.
              </h2>
              <p className="mt-5 text-base leading-8 text-secondary">
                Zroky is priced to be easy to start and safe to scale. The expensive model execution path stays explicit.
              </p>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              {faqs.map((faq) => (
                <article key={faq.q} className="card p-5">
                  <h3 className="text-base font-semibold leading-6 text-primary">{faq.q}</h3>
                  <p className="mt-3 text-sm leading-7 text-secondary">{faq.a}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </SectionReveal>
    </div>
  );
}
