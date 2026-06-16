import { type ReactNode } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import {
  Activity,
  ArrowRight,
  Check,
  CircleDollarSign,
  GitBranch,
  KeyRound,
  Lock,
  Server,
  ShieldCheck,
  type LucideIcon,
  Zap,
} from 'lucide-react';
import pricingContract from '../data/pricing-plans.json';
import { SIGN_UP_URL } from '../lib/links';

type PlanCode = 'free' | 'starter' | 'pro' | 'enterprise';

type PricingPlan = {
  code: PlanCode;
  name: string;
  price: {
    label: string;
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

const plans = (pricingContract.plans as PricingPlan[])
  .filter((plan) => plan.code !== 'enterprise')
  .map((plan) => ({
    name: plan.name,
    price: plan.price.label,
    period: plan.price.period,
    desc: plan.description,
    icon: planIcons[plan.code],
    cta: plan.cta.label,
    href: plan.cta.href === '/auth/register' ? SIGN_UP_URL : plan.cta.href,
    featured: plan.featured,
    bullets: buildPlanBullets(plan),
    note: plan.note,
  }));

const usageRules = [
  {
    icon: KeyRound,
    title: 'Bring your provider key',
    body: 'Real LLM replay defaults to your OpenAI, Anthropic, or Gemini key. Zroky charges for the reliability workflow, not hidden model spend.',
  },
  {
    icon: CircleDollarSign,
    title: 'Managed replay is optional',
    body: 'If Zroky pays the provider bill, usage is provider token cost plus a 30% platform fee for billing, retries, limits, and support.',
  },
  {
    icon: Lock,
    title: 'Caps protect both sides',
    body: 'Self-serve plans use explicit replay and CI limits. Teams get alerts before limits, then upgrade or pause new release-safety execution.',
  },
];

const overages = [
  ['Extra captured calls', 'Plan upgrade'],
  ['Extra verified replay', 'Quoted add-on'],
  ['Managed provider spend', 'Provider cost + service fee'],
];

const faqs = [
  {
    q: 'What counts as a replay run?',
    a: 'A replay run is one verified attempt against captured production evidence. Starter supports mocked-tool replay. Pro adds real LLM replay and live-sandbox replay through your provider key or optional Zroky-managed execution.',
  },
  {
    q: 'Why is BYOK the default?',
    a: 'Provider cost can multiply quickly when teams replay many failures or run Goldens in CI. BYOK keeps your model spend visible in your provider account and keeps Zroky pricing predictable.',
  },
  {
    q: 'When do you ask for a provider key?',
    a: 'We only ask for a provider key when you run verified replay, not during signup or capture. You can capture failures, inspect traces, and review issues before connecting a key.',
  },
  {
    q: 'What happens when limits are reached?',
    a: 'Zroky shows usage alerts before the limit. You can upgrade, buy overage, or pause new replay/CI execution while captured evidence remains available within your retention window.',
  },
  {
    q: 'Is CI blocking included?',
    a: 'Starter includes non-blocking CI preview. Pro includes blocking CI gates for protected releases.',
  },
  {
    q: 'Can we use Zroky-managed replay?',
    a: 'Yes. Zroky-managed replay is optional and billed at provider token cost plus a 30% platform fee. Most production teams should start with BYOK for clean cost control.',
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

  return (
    <div className="w-full overflow-x-hidden">
      <section className="relative isolate border-b border-line px-4 pb-12 pt-40 sm:px-6 sm:pb-16 sm:pt-44 lg:px-8">
        <div className="pointer-events-none absolute inset-0 -z-10">
          <div className="grid-bg absolute inset-x-0 top-0 h-[32rem] opacity-70" />
          <motion.div
            aria-hidden="true"
            animate={reduceMotion ? undefined : { rotate: 360 }}
            transition={{ duration: 34, repeat: Infinity, ease: 'linear' }}
            className="absolute left-1/2 top-24 h-72 w-72 -translate-x-1/2 rounded-full border border-line bg-[conic-gradient(from_130deg,transparent,rgba(255,255,255,0.18),transparent,rgba(255,255,255,0.1),transparent)] blur-2xl"
          />
        </div>

        <div className="mx-auto max-w-[92rem]">
          <div className="mx-auto max-w-4xl text-center">
            <span className="eyebrow">
              <CircleDollarSign className="h-3.5 w-3.5" />
              Pricing
            </span>
            <h1 className="mx-auto mt-6 max-w-5xl text-balance text-4xl font-semibold leading-[1.04] text-primary sm:text-6xl lg:text-7xl">
              Pricing that scales with agent reliability.
            </h1>
            <p className="mx-auto mt-6 max-w-3xl text-base leading-8 text-secondary sm:text-lg">
              Start free, bring your provider key for verified replay, and upgrade when Zroky starts protecting releases.
            </p>
          </div>

          <div className="mx-auto mt-8 grid max-w-4xl gap-2 rounded-2xl border border-line bg-white/[0.02] p-2 sm:mt-10 sm:grid-cols-3">
            {[
              ['Start free', '5K captured calls, traces, and issue grouping.'],
              ['Prove release safety', 'Starter adds diagnosis, mocked replay, Goldens, and CI preview.'],
              ['Gate production', 'Pro adds real replay, provider keys, blocking CI, and outcome attribution.'],
            ].map(([title, body]) => (
              <div key={title} className="rounded-xl border border-line bg-ink px-4 py-3">
                <div className="font-mono text-[10px] uppercase tracking-wider text-tertiary">{title}</div>
                <p className="mt-2 text-sm font-semibold leading-6 text-primary">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

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
                  className={`card flex min-h-[34rem] flex-col p-5 ${
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

                  <a
                    href={plan.href}
                    className={`mt-auto ${plan.featured ? 'btn-primary' : 'btn-ghost'} !w-full`}
                  >
                    {plan.cta}
                    <ArrowRight className="h-4 w-4" />
                  </a>
                </motion.article>
              );
            })}
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="border-b border-line px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <div className="max-w-3xl">
            <span className="inline-flex items-center gap-2 text-sm font-semibold text-primary">
              <KeyRound className="h-4 w-4" />
              How Zroky stays predictable
            </span>
            <h2 className="mt-4 text-balance text-4xl font-semibold leading-tight text-primary md:text-5xl">
              Subscription covers the reliability system. Usage covers the parts that can spike.
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
                Clear rules before your team depends on it.
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
