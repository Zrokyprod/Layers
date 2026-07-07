import { type ReactNode } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Check,
  CircleDollarSign,
  DatabaseZap,
  FileCheck2,
  GitBranch,
  KeyRound,
  Layers3,
  LockKeyhole,
  Scale,
  Server,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react';
import pricingContract from '../data/pricing-plans.json';
import { buildSignUpUrl, DEMO_URL } from '../lib/links';

type PlanCode = 'free' | 'starter' | 'team' | 'scale' | 'enterprise';

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
    protected_actions_per_month: number;
    managed_agents: number;
    connectors: number;
    approver_seats: number;
    evidence_retention_days: number;
    slack_approvals: boolean;
    scoped_policy_rules_dry_run: boolean;
    bypass_detection: 'none' | 'basic' | 'full' | 'custom';
    audit_manifest_export: boolean;
    overage_per_action_usd: number | null;
    overage_policy: 'hard_cap' | 'overage' | 'custom';
  };
  enforcement: {
    limits: {
      max_projects: number;
      max_members: number;
    };
    compatibility: Record<string, number | boolean | string>;
  };
};

const UNLIMITED = pricingContract.unlimited;
const numberFormatter = new Intl.NumberFormat('en-US');
const compactFormatter = new Intl.NumberFormat('en-US', {
  notation: 'compact',
  maximumFractionDigits: 0,
});

const revealEase = [0.16, 1, 0.3, 1] as const;

const planIcons: Record<PlanCode, LucideIcon> = {
  free: Activity,
  starter: ShieldCheck,
  team: GitBranch,
  scale: Layers3,
  enterprise: Server,
};

const planOrder: PlanCode[] = ['free', 'starter', 'team', 'scale', 'enterprise'];

const plans = (pricingContract.plans as PricingPlan[]).sort(
  (a, b) => planOrder.indexOf(a.code) - planOrder.indexOf(b.code),
);

function signUpHref(plan: PricingPlan, source = 'pricing') {
  if (plan.code === 'enterprise') {
    return plan.cta.href;
  }

  return buildSignUpUrl({
    intent: 'protect-agent',
    plan: plan.code,
    source,
  });
}

function formatNumber(value: number) {
  if (value === UNLIMITED) return 'Unlimited';
  return numberFormatter.format(value);
}

function formatCompact(value: number) {
  if (value === UNLIMITED) return 'Unlimited';
  return compactFormatter.format(value);
}

function planBullets(plan: PricingPlan) {
  const retention = plan.pricing.evidence_retention_days;
  const overage =
    plan.pricing.overage_policy === 'hard_cap'
      ? 'Hard cap on Free'
      : plan.pricing.overage_policy === 'custom'
        ? 'Custom usage terms'
        : `$${plan.pricing.overage_per_action_usd?.toFixed(3)}/action overage`;
  const bypass =
    plan.pricing.bypass_detection === 'none'
      ? null
      : plan.pricing.bypass_detection === 'basic'
        ? 'Basic bypass detection'
        : plan.pricing.bypass_detection === 'custom'
          ? 'Custom bypass detection'
          : 'Bypass detection';
  return [
    `${formatNumber(plan.pricing.protected_actions_per_month)} protected actions/mo`,
    `${formatCompact(plan.pricing.managed_agents)} managed agents`,
    `${formatCompact(plan.pricing.connectors)} connectors`,
    `${formatCompact(plan.pricing.approver_seats)} approver seats`,
    retention === UNLIMITED ? 'Custom evidence retention' : `${retention}-day evidence retention`,
    'Slack approvals included',
    ...(plan.pricing.scoped_policy_rules_dry_run ? ['Scoped policy rules + dry-run'] : []),
    ...(bypass ? [bypass] : []),
    ...(plan.pricing.audit_manifest_export ? ['Audit manifest export'] : []),
    overage,
  ];
}

const riskRows = [
  {
    icon: LockKeyhole,
    label: 'Access and identity changes',
    examples: 'admin roles, permissions, seats',
    proof: 'Policy gate, owner approval, directory verification',
  },
  {
    icon: CircleDollarSign,
    label: 'Money movement',
    examples: 'refunds, credits, payouts',
    proof: 'Spend mandate, scoped execution, ledger match',
  },
  {
    icon: DatabaseZap,
    label: 'Customer or production state',
    examples: 'CRM updates, deploys, config edits',
    proof: 'Runner isolation, source comparison, signed receipt',
  },
];

const operatingRules = [
  {
    icon: ShieldCheck,
    title: 'Start free when you need proof of the loop.',
    body: 'Use Free to see one protected action move through policy, verification, and receipt state without procurement overhead.',
  },
  {
    icon: Scale,
    title: 'Choose Team when production risk is real.',
    body: 'Team is the self-serve plan for groups gating actions that touch money, access, customer state, or production systems.',
  },
  {
    icon: Server,
    title: 'Move Enterprise when deployment itself needs control.',
    body: 'Use Enterprise for private execution, custom retention, custom connector scope, procurement, audit, or self-hosting plans.',
  },
];

const faqs = [
  {
    q: 'Is Zroky priced only for refund agents?',
    a: 'No. Refunds are only one clear example. The same control loop protects access grants, deploys, CRM mutations, purchase approvals, and mass customer messages.',
  },
  {
    q: 'What counts as a protected action?',
    a: 'One high-risk operation routed through Zroky for policy evaluation before the real system is mutated. If it needs proof, approval, or a receipt, it should be protected.',
  },
  {
    q: 'Do core controls require an LLM key?',
    a: 'No. Policy decisions, controlled execution, source-of-record verification, and receipts are control-plane behavior. Optional AI assistance can use your provider key.',
  },
  {
    q: 'What happens when a plan limit is reached?',
    a: 'Zroky keeps receipts and evidence available within retention, shows usage state, and lets the team upgrade before new protected actions exceed the plan.',
  },
];

function Reveal({
  children,
  className = '',
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.58, ease: revealEase, delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

function Section({
  children,
  id,
  className = '',
}: {
  children: ReactNode;
  id?: string;
  className?: string;
}) {
  return (
    <section id={id} className={`w-full scroll-mt-28 px-4 py-16 text-[#171a15] md:py-20 ${className}`}>
      <div className="mx-auto max-w-[1260px]">{children}</div>
    </section>
  );
}

function Eyebrow({ icon: Icon, children }: { icon: LucideIcon; children: ReactNode }) {
  return (
    <p className="inline-flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">
      <Icon size={14} />
      {children}
    </p>
  );
}

function PrimaryButton({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-[10px] bg-[linear-gradient(180deg,#376f77,#2f5f66)] px-5 text-sm font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.2),0_14px_28px_-16px_rgba(47,95,102,0.75)] transition duration-150 hover:-translate-y-px active:translate-y-0 sm:w-auto"
    >
      {children}
    </a>
  );
}

function GhostButton({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-[10px] border border-[#d4d0c4] bg-[#fffdfa] px-5 text-sm font-semibold text-[#252821] shadow-[0_1px_2px_rgba(32,35,31,0.05)] transition hover:-translate-y-px hover:border-[#c4bfb2] sm:w-auto"
    >
      {children}
    </a>
  );
}

function PricingHeroVisual() {
  return (
    <Reveal delay={0.08}>
      <div className="relative overflow-hidden rounded-[24px] border border-[#d7d4ca] bg-[#fffdfa] p-4 shadow-[0_1px_2px_rgba(28,31,26,0.05),0_42px_90px_-54px_rgba(28,31,26,0.5)]">
        <div className="rounded-[18px] border border-[#dedacf] bg-[#f8f7f2] p-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#dedacf] pb-4">
            <div>
              <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">Control-plane value</p>
              <h3 className="mt-1 text-xl font-semibold tracking-[-0.02em] text-[#151713]">Price against what agents can change.</h3>
            </div>
            <span className="rounded-full border border-[#cfe0dd] bg-[#eaf1ef] px-3 py-1.5 text-[11px] font-semibold text-[#2f5f66]">
              fail closed
            </span>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {[
              ['Action value', '$250K/mo', 'money, access, production'],
              ['One incident', '$8K+', 'loss, rework, audit noise'],
              ['Team plan', '$199/mo', 'governed execution'],
            ].map(([label, value, body]) => (
              <div key={label} className="rounded-[14px] border border-[#dedacf] bg-[#fffdfa] p-4">
                <p className="font-mono text-[9.5px] font-semibold uppercase tracking-[0.14em] text-[#8a867a]">{label}</p>
                <p className="mt-3 text-2xl font-semibold leading-none text-[#171a15]">{value}</p>
                <p className="mt-2 text-[12px] leading-relaxed text-[#5b615a]">{body}</p>
              </div>
            ))}
          </div>

          <div className="mt-4 rounded-[16px] border border-[#cfe0dd] bg-[#eaf1ef] p-4">
            <div className="grid gap-2 sm:grid-cols-[1fr_auto_1fr_auto_1fr] sm:items-center">
              {[
                ['Policy', 'who can act'],
                ['Runner', 'how it executes'],
                ['Receipt', 'what really happened'],
              ].map(([title, body], index) => (
                <div key={title} className="contents">
                  <div className="rounded-[12px] border border-[#cfe0dd] bg-[#fffdfa] px-4 py-3">
                    <p className="text-sm font-semibold text-[#171a15]">{title}</p>
                    <p className="mt-1 text-[12px] text-[#5b615a]">{body}</p>
                  </div>
                  {index < 2 ? <ArrowRight className="mx-auto hidden h-4 w-4 text-[#2f5f66] sm:block" /> : null}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </Reveal>
  );
}

function PlanCard({ plan, index }: { plan: PricingPlan; index: number }) {
  const Icon = planIcons[plan.code];
  const featured = plan.code === 'team';
  const enterprise = plan.code === 'enterprise';
  const href = signUpHref(plan);

  return (
    <Reveal delay={index * 0.04}>
      <article
        className={`flex h-full min-h-[34rem] flex-col rounded-[18px] border p-5 ${
          featured
            ? 'border-[#b8d3cf] bg-[#fffdfa] shadow-[0_1px_2px_rgba(28,31,26,0.06),0_42px_90px_-56px_rgba(47,95,102,0.58)]'
            : 'border-[#d7d4ca] bg-[#fffdfa] shadow-[0_1px_2px_rgba(28,31,26,0.04),0_26px_56px_-44px_rgba(28,31,26,0.32)]'
        }`}
      >
        <div className="flex items-start justify-between gap-4">
          <span
            className={`grid h-11 w-11 place-items-center rounded-[12px] border ${
              featured ? 'border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]' : 'border-[#dedacf] bg-[#f8f7f2] text-[#5b615a]'
            }`}
          >
            <Icon size={20} />
          </span>
          {featured ? (
            <span className="rounded-full border border-[#cfe0dd] bg-[#eaf1ef] px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-[#2f5f66]">
              Main plan
            </span>
          ) : null}
        </div>

        <h2 className="mt-6 text-2xl font-semibold tracking-[-0.02em] text-[#171a15]">{plan.name}</h2>
        <div className="mt-3 flex items-end gap-1">
          <span className="text-[2.8rem] font-semibold leading-none tracking-[-0.03em] text-[#171a15]">{plan.price.label}</span>
          {plan.price.period ? <span className="pb-1 text-sm font-semibold text-[#8a867a]">{plan.price.period}</span> : null}
        </div>
        <p className="mt-4 min-h-20 text-sm leading-relaxed text-[#5b615a]">{plan.description}</p>

        <div className="mt-5 h-px bg-[#e4e0d6]" />

        <div className="mt-5 grid gap-3">
          {planBullets(plan).map((bullet) => (
            <div key={bullet} className="flex items-start gap-2 text-sm leading-6">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-[#2f5f66]" />
              <span className="font-semibold text-[#4e554d]">{bullet}</span>
            </div>
          ))}
        </div>

        <p className="mt-5 rounded-[12px] border border-[#dedacf] bg-[#f8f7f2] px-3 py-3 text-xs font-semibold leading-5 text-[#777266]">
          {plan.note}
        </p>

        <div className="mt-auto pt-5">
          {featured ? (
            <PrimaryButton href={href}>
              {plan.cta.label} <ArrowRight size={15} />
            </PrimaryButton>
          ) : (
            <GhostButton href={enterprise ? DEMO_URL : href}>
              {enterprise ? 'Book enterprise demo' : plan.cta.label} <ArrowRight size={15} />
            </GhostButton>
          )}
        </div>
      </article>
    </Reveal>
  );
}

function PricingPage() {
  return (
    <div className="w-full overflow-x-hidden bg-[#fbfcfa] text-[#171a15]">
      <section
        className="relative overflow-hidden px-4 pb-14 pt-28 md:pb-16 md:pt-32"
        style={{
          background: 'linear-gradient(180deg,#fbfaf6 0%,#f3f4ee 58%,#fbfcfa 100%)',
          fontFeatureSettings: "'ss01','cv01'",
        }}
      >
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-[520px]"
          style={{
            background:
              'radial-gradient(60% 38% at 50% 0%, rgba(255,255,255,0.95), transparent 76%), linear-gradient(180deg, rgba(234,231,220,0.72), transparent 64%)',
          }}
        />

        <div className="relative z-10 mx-auto grid max-w-[1260px] gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
          <Reveal>
            <div>
              <Eyebrow icon={CircleDollarSign}>Pricing</Eyebrow>
              <h1 className="mt-6 max-w-4xl text-[2.65rem] font-semibold leading-[1] tracking-[-0.035em] text-[#12140f] sm:text-[3.4rem] md:text-[4.35rem]">
                Price the control plane against the risk it removes.
              </h1>
              <p className="mt-6 max-w-2xl text-[1.06rem] leading-[1.7] text-[#555b53] md:text-[1.16rem]">
                Start with one protected action. Move production agents to Team when money, access, customer state, or production changes need policy, verification, and receipts.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <PrimaryButton href={buildSignUpUrl({ intent: 'protect-agent', plan: 'free', source: 'pricing-hero' })}>
                  Start free <ArrowRight size={15} />
                </PrimaryButton>
                <GhostButton href="#plans">Compare plans</GhostButton>
              </div>
            </div>
          </Reveal>

          <PricingHeroVisual />
        </div>
      </section>

      <Section id="plans" className="bg-[#fbfcfa] py-14 md:py-20">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <Reveal>
            <div className="max-w-3xl">
              <Eyebrow icon={Layers3}>Plans</Eyebrow>
              <h2 className="mt-3 text-[2.15rem] font-semibold leading-[1.05] tracking-[-0.03em] text-[#151713] md:text-[3.15rem]">
                Simple tiers for a staged agent rollout.
              </h2>
            </div>
          </Reveal>
          <Reveal delay={0.08}>
            <p className="max-w-md text-sm font-semibold leading-relaxed text-[#5b615a]">
              Every plan follows the same product model: decide before execution, prove after execution, preserve the evidence.
            </p>
          </Reveal>
        </div>

        <div className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {plans.map((plan, index) => (
            <PlanCard key={plan.code} plan={plan} index={index} />
          ))}
        </div>
      </Section>

      <Section className="bg-[#f3f4ee] py-14 md:py-20">
        <div className="grid gap-10 lg:grid-cols-[0.86fr_1.14fr] lg:items-start">
          <Reveal>
            <div>
              <Eyebrow icon={AlertTriangle}>Buying signal</Eyebrow>
              <h2 className="mt-3 text-[2.1rem] font-semibold leading-[1.05] tracking-[-0.03em] text-[#151713] md:text-[3.05rem]">
                Buy when a wrong action is more expensive than the control.
              </h2>
              <p className="mt-5 text-[1.04rem] leading-[1.7] text-[#5b615a]">
                Zroky should sit in front of actions where a successful tool response is not enough. If the business needs to know who allowed it, what changed, and whether reality matched, it belongs behind the control loop.
              </p>
            </div>
          </Reveal>

          <div className="grid gap-3">
            {riskRows.map((row, index) => {
              const Icon = row.icon;
              return (
                <Reveal key={row.label} delay={0.06 + index * 0.04}>
                  <article className="grid gap-4 rounded-[16px] border border-[#d7d4ca] bg-[#fffdfa] p-4 shadow-[0_1px_2px_rgba(28,31,26,0.04)] sm:grid-cols-[2.75rem_1fr_1fr] sm:items-start">
                    <span className="grid h-11 w-11 place-items-center rounded-[12px] border border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]">
                      <Icon size={19} />
                    </span>
                    <div>
                      <h3 className="text-base font-semibold text-[#171a15]">{row.label}</h3>
                      <p className="mt-1 text-sm leading-relaxed text-[#777266]">{row.examples}</p>
                    </div>
                    <div className="rounded-[12px] border border-[#dedacf] bg-[#f8f7f2] px-3 py-3">
                      <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8a867a]">Zroky proof</p>
                      <p className="mt-2 text-sm font-semibold leading-relaxed text-[#4e554d]">{row.proof}</p>
                    </div>
                  </article>
                </Reveal>
              );
            })}
          </div>
        </div>
      </Section>

      <Section className="bg-[#fbfcfa] py-14 md:py-20">
        <div className="grid gap-10 lg:grid-cols-[1fr_1fr] lg:items-start">
          <Reveal>
            <div>
              <Eyebrow icon={KeyRound}>Operating rules</Eyebrow>
              <h2 className="mt-3 text-[2.1rem] font-semibold leading-[1.05] tracking-[-0.03em] text-[#151713] md:text-[3.05rem]">
                Upgrade by control maturity, not seat count.
              </h2>
            </div>
          </Reveal>

          <div className="grid gap-3">
            {operatingRules.map((rule, index) => {
              const Icon = rule.icon;
              return (
                <Reveal key={rule.title} delay={0.05 + index * 0.04}>
                  <article className="rounded-[16px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.04)]">
                    <div className="flex gap-4">
                      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-[11px] border border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]">
                        <Icon size={18} />
                      </span>
                      <div>
                        <h3 className="text-base font-semibold text-[#171a15]">{rule.title}</h3>
                        <p className="mt-2 text-sm leading-relaxed text-[#5b615a]">{rule.body}</p>
                      </div>
                    </div>
                  </article>
                </Reveal>
              );
            })}
          </div>
        </div>
      </Section>

      <Section className="bg-[#f3f4ee] py-14 md:py-20">
        <div className="grid gap-10 lg:grid-cols-[0.72fr_1.28fr]">
          <Reveal>
            <div>
              <Eyebrow icon={FileCheck2}>FAQ</Eyebrow>
              <h2 className="mt-3 text-[2.1rem] font-semibold leading-[1.05] tracking-[-0.03em] text-[#151713] md:text-[3.05rem]">
                Clear rules before the team depends on it.
              </h2>
            </div>
          </Reveal>
          <div className="grid gap-3 md:grid-cols-2">
            {faqs.map((faq, index) => (
              <Reveal key={faq.q} delay={0.04 + index * 0.03}>
                <article className="h-full rounded-[16px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.04)]">
                  <h3 className="text-base font-semibold leading-6 text-[#171a15]">{faq.q}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-[#5b615a]">{faq.a}</p>
                </article>
              </Reveal>
            ))}
          </div>
        </div>
      </Section>
    </div>
  );
}

export default PricingPage;
