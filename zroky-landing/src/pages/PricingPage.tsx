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
    compatibility: Record<string, number | boolean | string>;
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
  starter: ShieldCheck,
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

function formatRetention(days: number) {
  if (days === UNLIMITED) {
    return 'Custom retention';
  }
  return `${numberFormatter.format(days)}-day evidence retention`;
}

function formatProjectSeats(projects: number, seats: number) {
  if (projects === UNLIMITED && seats === UNLIMITED) {
    return 'Unlimited projects and seats';
  }
  return `${formatLimit(projects, 'project')} and ${formatLimit(seats, 'seat')}`;
}

function formatControlLimit(value: unknown, label: string) {
  if (typeof value === 'boolean') {
    return value ? `${label} included` : `${label} locked`;
  }
  if (typeof value !== 'number') {
    return `${label} not configured`;
  }
  if (value === UNLIMITED) {
    return `Unlimited ${label}`;
  }
  return `${compactNumberFormatter.format(value)} ${label}`;
}

function buildPlanBullets(plan: PricingPlan) {
  const compatibility = plan.enforcement.compatibility;
  return [
    formatProjectSeats(plan.enforcement.limits.max_projects, plan.enforcement.limits.max_members),
    formatControlLimit(compatibility['agents.max'], 'managed agents'),
    formatControlLimit(compatibility['connectors.system_of_record.max'], 'system-of-record connectors'),
    formatControlLimit(compatibility['actions.protected.monthly_quota'], 'protected actions/mo'),
    formatControlLimit(compatibility['actions.receipts.monthly_quota'], 'signed receipts/mo'),
    formatControlLimit(compatibility['actions.verifications.monthly_quota'], 'verification checks/mo'),
    formatRetention(Number(compatibility['retention.days'] ?? plan.pricing.retention_days)),
  ];
}

const allPlans = pricingContract.plans as PricingPlan[];
const enterprisePlan = allPlans.find((plan) => plan.code === 'enterprise');

const plans = allPlans
  .filter((plan) => plan.code === 'free' || plan.code === 'pro')
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
    value: proPlan ? `${proPlan.price}/mo` : '$399/mo',
    body: 'Pro is priced below the cost of one material mistake for teams ready to gate production behavior.',
  },
];

const planFit = [
  {
    icon: Activity,
    plan: 'Free',
    fit: 'Try the control loop on one managed agent before handing it more authority.',
    trigger: 'Use when the team needs to see allow, hold, block, verification, and receipt behavior end to end.',
  },
  {
    icon: ShieldCheck,
    plan: 'Pro',
    fit: 'Gate production agents with approval, isolated execution, system-of-record verification, and signed receipts.',
    trigger: 'Use when a wrong action has real financial, operational, or customer impact.',
  },
  {
    icon: Server,
    plan: 'Enterprise',
    fit: 'Add private execution, SSO, custom retention, custom connector scope, and procurement-ready controls.',
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
    proof: 'Policy hold or block, approval trail, isolated runner execution, and receipt.',
    plan: 'Pro',
  },
  {
    icon: Database,
    agent: 'CRM and data mutation agents',
    action: 'Record merges, account updates, ownership changes',
    pain: 'Duplicate or corrupted records quietly break sales, support, and compliance workflows.',
    proof: 'Policy snapshot, system-of-record check, not_verified state when proof is missing.',
    plan: 'Free to Pro',
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
    title: 'BYOK for AI assist',
    body: 'Runtime policy, verification, and receipts are deterministic. Optional AI summaries or policy suggestions can use your provider key.',
  },
  {
    icon: CircleDollarSign,
    title: 'AI credits stay explicit',
    body: 'Heavy advisory analysis should use BYOK or metered AI credits so the Pro subscription is not silently consumed by model spend.',
  },
  {
    icon: Lock,
    title: 'Hard control-plane caps',
    body: 'Self-serve plans use explicit protected-action, receipt, runner, verification, connector, and agent limits before overage billing is enabled.',
  },
];

const overages = [
  ['Extra protected actions', 'Plan upgrade'],
  ['Extra receipts or verifications', 'Plan upgrade'],
  ['Optional AI assist spend', 'BYOK or metered credits'],
];

const faqs = [
  {
    q: 'Should we buy Zroky only for refund agents?',
    a: 'No. Start where the action is expensive or irreversible. Refunds are a sharp wedge, but deploys, CRM mutations, purchase approvals, and mass messaging need the same action-accountability loop.',
  },
  {
    q: 'What counts as a protected action?',
    a: 'A protected action is one high-risk agent operation routed through Zroky for policy evaluation before the real system is mutated.',
  },
  {
    q: 'Why is BYOK the default?',
    a: 'Provider cost can multiply quickly when teams run heavy advisory analysis. BYOK keeps model spend visible in your provider account and keeps Zroky pricing predictable.',
  },
  {
    q: 'When do you ask for a provider key?',
    a: 'We only ask for a provider key when you enable optional AI assistance. Core policy decisions and system-of-record proof do not require an LLM provider key.',
  },
  {
    q: 'What happens when limits are reached?',
    a: 'Zroky shows usage alerts before the limit. You can upgrade or pause new protected actions while signed receipts and evidence remain available within your retention window.',
  },
  {
    q: 'When should we talk to sales?',
    a: 'Talk to sales when the protected agent needs private execution, custom retention, custom connectors, procurement review, or audit commitments beyond self-serve terms.',
  },
];

const revealEase = [0.16, 1, 0.3, 1] as const;

const eyebrowClass =
  'inline-flex items-center gap-2 text-sm font-semibold text-[#3f4942]';
const cardClass =
  'rounded-2xl border border-[#d8dbd2] bg-[#fbfcf8] shadow-[inset_0_1px_0_rgba(255,255,255,0.85),0_1px_2px_rgba(42,45,40,0.04),0_24px_48px_-30px_rgba(42,45,40,0.18)]';
const btnPrimaryClass =
  'inline-flex h-11 items-center justify-center gap-2 rounded-[10px] bg-[linear-gradient(180deg,#5f675f,#343a34)] px-5 text-sm font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_10px_24px_-12px_rgba(42,45,40,0.55)] transition duration-150 hover:-translate-y-px hover:bg-[#4f5a52] focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#4f5a52]/25 active:translate-y-0 active:scale-[0.98]';
const btnGhostClass =
  'inline-flex h-11 items-center justify-center gap-2 rounded-[10px] border border-[#d8dbd2] bg-[#fbfcf8] px-5 text-sm font-semibold text-[#20231f] shadow-[0_1px_2px_rgba(42,45,40,0.04)] transition duration-150 hover:-translate-y-px hover:border-[#c7cbc2] hover:bg-[#f7f8f4] focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#4f5a52]/25 active:translate-y-0 active:scale-[0.98]';

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
    <div className="w-full overflow-x-hidden bg-[#fbfcfa] text-[#20231f]">
      <section className="relative isolate border-b border-[#e3e5de] px-4 pb-12 pt-28 sm:px-6 sm:pb-16 sm:pt-32 lg:px-8">
        <div className="pointer-events-none absolute inset-0 -z-10">
          <div
            className="absolute inset-0"
            style={{ background: 'radial-gradient(60% 45% at 50% 0%, rgba(79,90,82,0.07), transparent 70%)' }}
          />
        </div>

        <div className="mx-auto grid max-w-[92rem] items-start gap-10 lg:grid-cols-2">
          <div>
            <span className={eyebrowClass}>
              <CircleDollarSign className="h-4 w-4 text-[#4f5a52]" />
              Risk-value pricing
            </span>
            <h1 className="mt-6 max-w-4xl text-balance text-4xl font-semibold leading-[1.04] tracking-[-0.025em] text-[#20231f] sm:text-6xl">
              Price Zroky against the action it protects.
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-8 text-[#5b615a] sm:text-lg">
              Stop unsafe actions before they commit, then prove the outcome in the system of record.
            </p>

            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <a href={heroSignUpUrl} className={btnPrimaryClass}>
                Start free
                <ArrowRight className="h-4 w-4" />
              </a>
              <a href="#plan-fit" className={btnGhostClass}>
                Match a plan to risk
              </a>
            </div>

            <div className="mt-8 grid grid-cols-3 gap-2">
              {['Allow', 'Hold for approval', 'Block'].map((status) => (
                <div key={status} className="rounded-xl border border-[#d8dbd2] bg-[#f4f6f1] px-3 py-3 sm:px-4">
                  <div className="font-mono text-[9px] uppercase tracking-wider text-[#8b9288] sm:text-[10px]">
                    <span className="sm:hidden">Decision</span>
                    <span className="hidden sm:inline">Runtime decision</span>
                  </div>
                  <p className="mt-2 text-xs font-semibold leading-5 text-[#20231f] sm:text-sm">{status}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="hidden overflow-hidden rounded-[16px] border border-[#d8dbd2] bg-[#fbfcf8] p-2 shadow-[0_30px_70px_-40px_rgba(42,45,40,0.28)] lg:block">
            <img
              src="/product-ci-gate.png"
              alt="Zroky product screen showing protected agent action controls"
              className="max-h-[460px] w-full rounded-xl border border-[#e3e5de] object-cover object-top"
            />
          </div>
        </div>
      </section>

      <SectionReveal className="border-b border-[#e3e5de] bg-[#f4f6f1] px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="mx-auto grid max-w-[92rem] gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-2xl border border-[#d8dbd2] bg-white p-5 sm:p-7">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <span className={eyebrowClass}>
                  <Banknote className="h-4 w-4 text-[#4f5a52]" />
                  Dollar anchor
                </span>
                <h2 className="mt-4 max-w-3xl text-balance text-3xl font-semibold leading-tight text-[#20231f] md:text-5xl">
                  The right plan is cheaper than one bad autonomous action.
                </h2>
              </div>
              <span className="rounded-full border border-[#d8dbd2] bg-[#f4f6f1] px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-[#8b9288]">
                Example, not a claim
              </span>
            </div>

            <div className="mt-8 grid gap-3 md:grid-cols-3">
              {riskMetrics.map((metric) => (
                <div key={metric.label} className="rounded-xl border border-[#e0e2db] bg-[#f7f8f4] p-4">
                  <div className="font-mono text-[10px] uppercase tracking-wider text-[#8b9288]">{metric.label}</div>
                  <div className="mt-3 text-3xl font-semibold text-[#20231f]">{metric.value}</div>
                  <p className="mt-3 text-sm leading-6 text-[#5b615a]">{metric.body}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-[#d8dbd2] bg-white p-5 sm:p-7">
            <span className={eyebrowClass}>
              <ShieldCheck className="h-4 w-4 text-[#4f5a52]" />
              Buying rule
            </span>
            <p className="mt-5 text-2xl font-semibold leading-tight text-[#20231f]">
              Buy when a human is still approving the agent because the consequence is too expensive to trust blindly.
            </p>
            <div className="mt-6 h-px bg-[#e3e5de]" />
            <div className="mt-6 grid gap-3">
              {[
                'One wrong action has a direct dollar cost.',
                'The team cannot prove what happened after the agent says done.',
                'Risk, audit, or an enterprise customer requires accountability evidence.',
              ].map((item) => (
                <div key={item} className="flex items-start gap-3">
                  <Check className="mt-1 h-4 w-4 shrink-0 text-[#4f5a52]" />
                  <p className="text-sm font-semibold leading-6 text-[#5b615a]">{item}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="border-b border-[#e3e5de] px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <div className="max-w-3xl">
            <span className={eyebrowClass}>
              <Scale className="h-4 w-4 text-[#4f5a52]" />
              Plan fit
            </span>
            <h2 id="plan-fit" className="mt-4 text-balance text-4xl font-semibold leading-tight text-[#20231f] md:text-5xl">
              Start with evidence. Upgrade when the agent can hurt the business.
            </h2>
          </div>

          <div className="mt-10 grid gap-3 md:grid-cols-3">
            {planFit.map((item) => {
              const Icon = item.icon;

              return (
                <article key={item.plan} className="rounded-2xl border border-[#d8dbd2] bg-[#fbfcf8] p-5">
                  <span className="grid h-11 w-11 place-items-center rounded-xl border border-[#e0e2db] bg-[#f4f6f1] text-[#4f5a52]">
                    <Icon className="h-5 w-5" />
                  </span>
                  <h3 className="mt-5 text-xl font-semibold text-[#20231f]">{item.plan}</h3>
                  <p className="mt-3 text-sm leading-7 text-[#5b615a]">{item.fit}</p>
                  <p className="mt-4 rounded-xl border border-[#e0e2db] bg-[#f4f6f1] px-3 py-3 text-xs font-semibold leading-5 text-[#8b9288]">
                    {item.trigger}
                  </p>
                </article>
              );
            })}
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="border-b border-[#e3e5de] bg-[#f4f6f1] px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
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
                  className={`flex min-h-[35rem] flex-col rounded-2xl border p-5 ${
                    plan.featured
                      ? 'border-[#c7cbc2] bg-white shadow-[0_1px_2px_rgba(42,45,40,0.05),0_34px_64px_-34px_rgba(42,45,40,0.3)]'
                      : 'border-[#d8dbd2] bg-[#fbfcf8] shadow-[0_1px_2px_rgba(42,45,40,0.04),0_24px_48px_-30px_rgba(42,45,40,0.18)]'
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <span
                      className={`grid h-11 w-11 place-items-center rounded-xl border ${
                        plan.featured ? 'border-[#c7cbc2] bg-[#eef0eb]' : 'border-[#e0e2db] bg-[#f4f6f1]'
                      } text-[#4f5a52]`}
                    >
                      <Icon className="h-5 w-5" />
                    </span>
                    {plan.featured && (
                      <span className="rounded-full border border-[#c7cbc2] bg-[#eef0eb] px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-[#3f4942]">
                        Main plan
                      </span>
                    )}
                  </div>

                  <h2 className="mt-6 text-2xl font-semibold text-[#20231f]">{plan.name}</h2>
                  <div className="mt-3 flex items-end gap-1">
                    <span className="text-5xl font-semibold tracking-normal text-[#20231f]">{plan.price}</span>
                    <span className="pb-1 text-sm font-semibold text-[#8b9288]">{plan.period}</span>
                  </div>
                  <p className="mt-4 min-h-14 text-sm leading-7 text-[#5b615a]">{plan.desc}</p>

                  <div className="mt-5 h-px bg-[#e3e5de]" />

                  <div className="mt-5 grid gap-3">
                    {plan.bullets.map((bullet) => (
                      <div key={bullet} className="flex items-start gap-2 text-sm leading-6">
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-[#4f5a52]" />
                        <span className="font-semibold text-[#5b615a]">{bullet}</span>
                      </div>
                    ))}
                  </div>

                  <p className="mt-5 rounded-xl border border-[#e0e2db] bg-[#f4f6f1] px-3 py-3 text-xs font-semibold leading-5 text-[#8b9288]">
                    {plan.note}
                  </p>

                  <a
                    href={plan.href}
                    className={`mt-auto w-full ${plan.featured ? btnPrimaryClass : btnGhostClass}`}
                  >
                    {plan.cta}
                    <ArrowRight className="h-4 w-4" />
                  </a>
                </motion.article>
              );
            })}
          </div>

          <div className="mt-4 grid gap-4 rounded-2xl border border-[#d8dbd2] bg-white p-5 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
            <div>
              <span className={eyebrowClass}>
                <Server className="h-4 w-4 text-[#4f5a52]" />
                Enterprise
              </span>
              <h3 className="mt-3 text-2xl font-semibold text-[#20231f]">For agents that need audit, private execution, or custom connectors.</h3>
            </div>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
              <p className="text-sm leading-7 text-[#5b615a]">
                Enterprise maps to contract entitlements: custom protected-action volume, private runners, custom retention, SSO, self-hosting, and system-of-record integration planning.
              </p>
              <a href={enterpriseHref} className={btnGhostClass}>
                Talk to Zroky
                <ArrowRight className="h-4 w-4" />
              </a>
            </div>
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="border-b border-[#e3e5de] px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <div className="grid gap-10 lg:grid-cols-[0.82fr_1.18fr]">
            <div>
              <span className={eyebrowClass}>
                <Activity className="h-4 w-4 text-[#4f5a52]" />
                Highest-pain agents
              </span>
              <h2 className="mt-4 text-balance text-4xl font-semibold leading-tight text-[#20231f] md:text-5xl">
                Not just refunds. Protect every agent that mutates reality.
              </h2>
              <p className="mt-5 text-base leading-8 text-[#5b615a]">
                The first paid wedge should be where error cost is obvious, but the same loop covers any autonomous agent with irreversible operations.
              </p>
            </div>

            <div className="grid gap-3">
              {agentRiskRows.map((row) => {
                const Icon = row.icon;

                return (
                  <article key={row.agent} className="rounded-2xl border border-[#d8dbd2] bg-[#fbfcf8] p-4">
                    <div className="grid gap-4 lg:grid-cols-[2.1fr_1.35fr_1.1fr] lg:items-start">
                      <div className="flex gap-4">
                        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-[#e0e2db] bg-[#f4f6f1] text-[#4f5a52]">
                          <Icon className="h-5 w-5" />
                        </span>
                        <div>
                          <h3 className="text-base font-semibold text-[#20231f]">{row.agent}</h3>
                          <p className="mt-1 text-sm leading-6 text-[#8b9288]">{row.action}</p>
                          <p className="mt-3 text-sm leading-6 text-[#5b615a]">{row.pain}</p>
                        </div>
                      </div>
                      <div>
                        <div className="font-mono text-[10px] uppercase tracking-wider text-[#8b9288]">Zroky proof</div>
                        <p className="mt-2 text-sm font-semibold leading-6 text-[#5b615a]">{row.proof}</p>
                      </div>
                      <div className="rounded-xl border border-[#e0e2db] bg-[#f4f6f1] px-3 py-3">
                        <div className="font-mono text-[10px] uppercase tracking-wider text-[#8b9288]">Plan</div>
                        <p className="mt-2 text-sm font-semibold text-[#20231f]">{row.plan}</p>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="border-b border-[#e3e5de] bg-[#f4f6f1] px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <div className="grid gap-10 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
            <div className="overflow-hidden rounded-[16px] border border-[#d8dbd2] bg-[#fbfcf8] p-2 shadow-[0_30px_70px_-40px_rgba(42,45,40,0.28)]">
              <img
                src="/product-replay-detail.png"
                alt="Zroky evidence screen showing verified proof for an agent action"
                className="h-full w-full rounded-xl border border-[#e3e5de] object-cover"
              />
            </div>

            <div>
              <span className={eyebrowClass}>
                <FileCheck2 className="h-4 w-4 text-[#4f5a52]" />
                Proof chain
              </span>
              <h2 className="mt-4 text-balance text-4xl font-semibold leading-tight text-[#20231f] md:text-5xl">
                Every paid claim has to end in evidence.
              </h2>
              <div className="mt-8 grid gap-3">
                {proofSteps.map((step) => {
                  const Icon = step.icon;

                  return (
                    <div key={step.title} className="flex gap-4 rounded-2xl border border-[#d8dbd2] bg-white p-4">
                      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-[#e0e2db] bg-[#f4f6f1] text-[#4f5a52]">
                        <Icon className="h-5 w-5" />
                      </span>
                      <div>
                        <h3 className="text-sm font-semibold text-[#20231f]">{step.title}</h3>
                        <p className="mt-2 text-sm leading-6 text-[#5b615a]">{step.body}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="border-b border-[#e3e5de] px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <div className="max-w-3xl">
            <span className={eyebrowClass}>
              <KeyRound className="h-4 w-4 text-[#4f5a52]" />
              Predictable usage
            </span>
            <h2 className="mt-4 text-balance text-4xl font-semibold leading-tight text-[#20231f] md:text-5xl">
              Subscription covers the protection system. Usage covers the parts that can spike.
            </h2>
          </div>

          <div className="mt-10 grid gap-4 lg:grid-cols-3">
            {usageRules.map((rule) => {
              const Icon = rule.icon;

              return (
                <div key={rule.title} className={`${cardClass} p-6`}>
                  <span className="grid h-11 w-11 place-items-center rounded-xl border border-[#e0e2db] bg-[#f4f6f1] text-[#4f5a52]">
                    <Icon className="h-5 w-5" />
                  </span>
                  <h3 className="mt-5 text-xl font-semibold text-[#20231f]">{rule.title}</h3>
                  <p className="mt-3 text-sm leading-7 text-[#5b615a]">{rule.body}</p>
                </div>
              );
            })}
          </div>

          <div className="mt-5 rounded-2xl border border-[#d8dbd2] bg-[#f4f6f1] p-4">
            <div className="grid gap-3 md:grid-cols-2">
              {overages.map(([label, price]) => (
                <div key={label} className="flex min-h-20 items-center justify-between gap-4 rounded-xl border border-[#e0e2db] bg-white px-4 py-3">
                  <span className="text-sm font-semibold text-[#5b615a]">{label}</span>
                  <span className="font-mono text-sm text-[#20231f]">{price}</span>
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
              <span className={eyebrowClass}>
                <ShieldCheck className="h-4 w-4 text-[#4f5a52]" />
                FAQ
              </span>
              <h2 className="mt-4 text-balance text-4xl font-semibold leading-tight text-[#20231f] md:text-5xl">
                Clear rules before the team depends on it.
              </h2>
              <p className="mt-5 text-base leading-8 text-[#5b615a]">
                Zroky is priced to be easy to start and safe to scale. The expensive model execution path stays explicit.
              </p>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              {faqs.map((faq) => (
                <article key={faq.q} className={`${cardClass} p-5`}>
                  <h3 className="text-base font-semibold leading-6 text-[#20231f]">{faq.q}</h3>
                  <p className="mt-3 text-sm leading-7 text-[#5b615a]">{faq.a}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </SectionReveal>
    </div>
  );
}
