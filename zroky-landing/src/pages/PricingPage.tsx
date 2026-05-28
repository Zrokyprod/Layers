import { motion } from 'framer-motion';
import {
  ArrowRight,
  CheckCircle2,
  CircleDollarSign,
  Database,
  Minus,
  Network,
  ShieldCheck,
  Zap,
} from 'lucide-react';

const plans = [
  {
    name: 'Free',
    price: '$0',
    period: '/mo',
    desc: 'Try the full workflow. No time limit.',
    icon: Database,
    cta: 'Get Started',
    href: '/auth/register',
    featured: false,
    bullets: [
      '10 issues per workspace',
      'Agent capture (SDK + Gateway)',
      'Basic replay (stub mode)',
      'Issue queue',
      '30-day trace retention',
    ],
  },
  {
    name: 'Starter',
    price: '$49',
    period: '/mo',
    desc: 'For small teams shipping production agents.',
    icon: Zap,
    cta: 'Get Started',
    href: '/auth/register',
    featured: false,
    bullets: [
      'Unlimited issues',
      'real_llm + stub replay modes',
      'Ask Zroky Q&A',
      'Golden promotion',
      '90-day trace retention',
    ],
  },
  {
    name: 'Pro',
    price: '$299',
    period: '/mo',
    desc: 'For teams with high-volume production agents.',
    icon: ShieldCheck,
    cta: 'Get Started',
    href: '/auth/register',
    featured: true,
    bullets: [
      'Everything in Starter',
      'CI Golden gates',
      'Root cause attribution (ablation)',
      'Cost of failure analytics',
      'Model and provider drift detection',
      '180-day trace retention',
    ],
  },
  {
    name: 'Team',
    price: '$999',
    period: '/mo',
    desc: 'For platform teams that need controls and dedicated rollout.',
    icon: Network,
    cta: 'Contact sales',
    href: 'mailto:sales@zroky.ai?subject=Zroky%20Team%20plan',
    featured: false,
    bullets: [
      'Everything in Pro',
      'Project-scoped access controls',
      'Audit trail',
      'Custom trace retention',
      'Dedicated rollout support',
      'SLA and priority support',
    ],
  },
];

const comparison = [
  {
    feature: 'Agent capture (SDK + Gateway)',
    free: true, starter: true, pro: true, team: true,
  },
  {
    feature: 'Issue grouping and diagnosis',
    free: '10 issues', starter: 'Unlimited', pro: 'Unlimited', team: 'Unlimited',
  },
  {
    feature: 'Stub replay (sanity check)',
    free: true, starter: true, pro: true, team: true,
  },
  {
    feature: 'real_llm replay (verified fix)',
    free: false, starter: true, pro: true, team: true,
  },
  {
    feature: 'Ask Zroky Q&A',
    free: false, starter: true, pro: true, team: true,
  },
  {
    feature: 'CI Golden gates',
    free: false, starter: false, pro: true, team: true,
  },
  {
    feature: 'Root cause attribution',
    free: false, starter: false, pro: true, team: true,
  },
  {
    feature: 'Cost of failure analytics',
    free: false, starter: false, pro: true, team: true,
  },
  {
    feature: 'Model + provider drift detection',
    free: false, starter: false, pro: true, team: true,
  },
  {
    feature: 'Project-scoped access',
    free: false, starter: false, pro: false, team: true,
  },
  {
    feature: 'Audit trail',
    free: false, starter: false, pro: false, team: true,
  },
  {
    feature: 'Trace retention',
    free: '30 days', starter: '90 days', pro: '180 days', team: 'Custom',
  },
  {
    feature: 'Dedicated rollout support',
    free: false, starter: false, pro: false, team: true,
  },
];

const faqs = [
  {
    q: 'How does the Free tier work?',
    a: 'Free is not a trial — it is a permanent tier. You get 10 issues per workspace, basic stub replay, and 30 days of trace retention. No credit card required and no time limit.',
  },
  {
    q: 'What is the difference between stub and real_llm replay?',
    a: 'Stub replay runs the candidate fix without calling a real LLM — it is a structural sanity check. real_llm replay calls the actual LLM provider against the original incident. Only real_llm replay shows the "Verified" badge.',
  },
  {
    q: 'Can I self-host the data plane?',
    a: 'Yes. The SDK, Gateway, and Replay Worker are open source (FSL-1.1-MIT) and free to self-host. The Zroky dashboard (diagnosis, replay management, CI gates) is the paid control plane.',
  },
  {
    q: 'What is a CI Golden?',
    a: 'A Golden is a past incident that was fixed with a verified replay. It runs in CI before every deploy so the same regression cannot ship twice. CI Goldens are available on Pro and Team plans.',
  },
  {
    q: 'How do I upgrade or change plans?',
    a: 'You can upgrade at any time from the workspace settings. Downgrades take effect at the next billing cycle. Contact sales@zroky.ai for Team plan invoicing.',
  },
];

function Cell({ val }: { val: boolean | string }) {
  if (val === true) return <CheckCircle2 className="mx-auto h-4 w-4 text-success" />;
  if (val === false) return <Minus className="mx-auto h-4 w-4 text-tertiary" />;
  return <span className="text-xs font-bold text-secondary">{val}</span>;
}

export default function PricingPage() {
  return (
    <div className="w-full px-4 pb-24 pt-44 sm:px-5 lg:px-8">
      <div className="mx-auto max-w-[92rem]">

        {/* Header */}
        <div className="mx-auto max-w-2xl text-center">
          <span className="eyebrow justify-center">
            <CircleDollarSign className="h-3.5 w-3.5 text-accent" />
            Pricing
          </span>
          <h1 className="mt-5 text-balance text-4xl font-black leading-tight text-primary md:text-6xl">
            Simple pricing. No surprises.
          </h1>
          <p className="mt-5 text-lg leading-8 text-secondary">
            Start free and stay free. Upgrade when your team needs replay proof, CI gates, and controls.
          </p>
        </div>

        {/* Cards */}
        <div className="mt-14 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {plans.map((plan, i) => {
            const Icon = plan.icon;
            return (
              <motion.article
                key={plan.name}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: i * 0.05 }}
                className={`flex flex-col rounded-[1.5rem] border p-6 shadow-sm ${
                  plan.featured
                    ? 'border-primary bg-primary text-white shadow-premium'
                    : 'border-panel-border bg-white text-primary'
                }`}
              >
                <div className="flex items-center justify-between gap-4">
                  <span className={`grid h-10 w-10 place-items-center rounded-xl border ${
                    plan.featured ? 'border-white/15 bg-white/10 text-gold' : 'border-panel-border bg-canvas text-accent'
                  }`}>
                    <Icon className="h-4 w-4" />
                  </span>
                  {plan.featured && (
                    <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-gold">
                      Most popular
                    </span>
                  )}
                </div>
                <h2 className="mt-5 text-xl font-black">{plan.name}</h2>
                <div className="mt-1 flex items-baseline gap-0.5">
                  <span className={`text-4xl font-black ${plan.featured ? 'text-white' : 'text-primary'}`}>
                    {plan.price}
                  </span>
                  <span className={`text-sm font-bold ${plan.featured ? 'text-slate-400' : 'text-tertiary'}`}>
                    {plan.period}
                  </span>
                </div>
                <p className={`mt-3 text-sm leading-6 ${plan.featured ? 'text-slate-300' : 'text-secondary'}`}>
                  {plan.desc}
                </p>
                <div className="mt-5 flex flex-col gap-2">
                  {plan.bullets.map((b) => (
                    <div key={b} className="flex items-start gap-2 text-sm leading-6">
                      <CheckCircle2 className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${plan.featured ? 'text-gold' : 'text-accent'}`} />
                      <span className={plan.featured ? 'text-slate-200' : 'text-secondary'}>{b}</span>
                    </div>
                  ))}
                </div>
                <a
                  href={plan.href}
                  className={`mt-auto pt-6 inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-extrabold transition duration-200 focus:outline-none focus:ring-2 ${
                    plan.featured
                      ? 'bg-white text-primary hover:bg-gold/20 hover:text-white focus:ring-gold/40'
                      : 'border border-panel-border bg-white text-primary hover:border-accent/40 hover:bg-accent/10 focus:ring-accent/35'
                  }`}
                >
                  {plan.cta}
                  <ArrowRight className="h-4 w-4" />
                </a>
              </motion.article>
            );
          })}
        </div>

        {/* Comparison table */}
        <div className="mt-20">
          <h2 className="mb-8 text-2xl font-black text-primary">Full feature comparison</h2>
          <div className="overflow-hidden rounded-[1.5rem] border border-panel-border">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px]">
                <thead>
                  <tr className="border-b border-panel-border bg-canvas">
                    <th className="px-5 py-4 text-left text-xs font-black uppercase tracking-[0.12em] text-tertiary">Feature</th>
                    {['Free', 'Starter', 'Pro', 'Team'].map((h) => (
                      <th key={h} className="px-4 py-4 text-center text-xs font-black uppercase tracking-[0.12em] text-primary">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-panel-border">
                  {comparison.map((row) => (
                    <tr key={row.feature} className="bg-white transition hover:bg-canvas">
                      <td className="px-5 py-3.5 text-sm font-bold text-secondary">{row.feature}</td>
                      <td className="px-4 py-3.5 text-center"><Cell val={row.free} /></td>
                      <td className="px-4 py-3.5 text-center"><Cell val={row.starter} /></td>
                      <td className="px-4 py-3.5 text-center"><Cell val={row.pro} /></td>
                      <td className="px-4 py-3.5 text-center"><Cell val={row.team} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* FAQ */}
        <div className="mt-20">
          <h2 className="mb-8 text-2xl font-black text-primary">Frequently asked questions</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {faqs.map((faq) => (
              <div key={faq.q} className="rounded-[1.5rem] border border-panel-border bg-white p-6 shadow-sm">
                <h3 className="text-base font-black text-primary">{faq.q}</h3>
                <p className="mt-3 text-sm leading-7 text-secondary">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Enterprise CTA */}
        <div className="mt-12 overflow-hidden rounded-[1.5rem] border border-panel-border bg-primary p-8 text-center text-white">
          <h2 className="text-2xl font-black">Need something larger?</h2>
          <p className="mt-3 text-sm font-bold text-slate-400">
            Custom seats, self-hosted control plane, compliance requirements, or a dedicated rollout engineer.
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <a
              href="mailto:sales@zroky.ai?subject=Zroky%20Enterprise"
              className="inline-flex min-h-11 items-center gap-2 rounded-full bg-white px-6 py-2.5 text-sm font-extrabold text-primary transition hover:bg-gold/20 hover:text-white"
            >
              Contact sales
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>
        </div>

      </div>
    </div>
  );
}
