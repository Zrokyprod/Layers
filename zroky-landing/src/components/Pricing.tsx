import { motion } from 'framer-motion';
import {
  ArrowRight,
  CheckCircle2,
  Database,
  Network,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { Link } from 'react-router-dom';

const pricingCards = [
  {
    name: 'Free',
    price: '$0',
    period: '/mo',
    description: 'Create a workspace, connect an agent, and explore the verified-fix workflow.',
    cta: 'Get Started',
    href: '/auth/register',
    icon: Database,
    featured: false,
    bullets: ['Agent capture setup', 'Issue queue (10 issues)', 'Replay workflow', 'CI guardrail planning'],
  },
  {
    name: 'Starter',
    price: '$49',
    period: '/mo',
    description: 'For small teams shipping production agents and building the reliability loop.',
    cta: 'Get Started',
    href: '/auth/register',
    icon: Zap,
    featured: false,
    bullets: ['Unlimited issue grouping', 'Replay proof workflow', 'Golden promotion', 'Ask Zroky Q&A'],
  },
  {
    name: 'Pro',
    price: '$299',
    period: '/mo',
    description: 'For teams validating Zroky on high-volume production agents and weekly release cycles.',
    cta: 'Get Started',
    href: '/auth/register',
    icon: ShieldCheck,
    featured: true,
    bullets: ['Everything in Starter', 'CI Golden gates', 'Root cause attribution', 'Drift + cost tracking'],
  },
  {
    name: 'Team',
    price: '$999',
    period: '/mo',
    description: 'For platform teams that need project-scoped controls, audit trails, and dedicated rollout.',
    cta: 'Contact sales',
    href: 'mailto:sales@zroky.ai?subject=Zroky%20Team%20plan',
    icon: Network,
    featured: false,
    bullets: ['Everything in Pro', 'Project-scoped access', 'Retention + audit trail', 'Dedicated rollout support'],
  },
];

const guarantees = [
  { icon: Zap, label: '<5ms overhead', desc: 'Capture never sits in your critical path' },
  { icon: ShieldCheck, label: 'Honest labels', desc: 'Stub replay is never shown as verified' },
  { icon: CheckCircle2, label: 'Free forever', desc: 'Free tier has no time limit, no card needed' },
  { icon: Network, label: 'No lock-in', desc: 'OSS SDK + Gateway run on any infrastructure' },
];

export default function Pricing() {
  return (
    <section id="pricing" className="relative w-full border-t border-panel-border bg-canvas py-24 md:py-28">
      <div className="mx-auto w-full max-w-[92rem] px-4 sm:px-5 lg:px-8">

        {/* Header */}
        <div className="mx-auto max-w-2xl text-center">
          <span className="eyebrow justify-center">
            <ShieldCheck className="h-3.5 w-3.5 text-gold" />
            Pricing
          </span>
          <h2 className="mt-5 text-balance text-4xl font-black leading-tight text-primary md:text-5xl">
            Simple. Transparent. No surprises.
          </h2>
          <p className="mt-5 text-lg leading-8 text-secondary">
            Start free and stay free. Upgrade when your team needs replay proof, CI gates, and controls.
          </p>
        </div>

        {/* Pricing cards */}
        <div className="mt-12 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {pricingCards.map((plan, i) => {
            const Icon = plan.icon;
            return (
              <motion.article
                key={plan.name}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.3, delay: i * 0.05 }}
                className={`flex flex-col rounded-[1.5rem] border p-6 shadow-sm ${
                  plan.featured
                    ? 'border-primary bg-primary text-white shadow-premium'
                    : 'border-panel-border bg-white text-primary'
                }`}
              >
                <div className="flex items-center justify-between gap-4">
                  <span className={`grid h-11 w-11 place-items-center rounded-2xl border ${
                    plan.featured ? 'border-white/15 bg-white/10 text-gold' : 'border-panel-border bg-canvas text-accent'
                  }`}>
                    <Icon className="h-5 w-5" />
                  </span>
                  {plan.featured && (
                    <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-gold">
                      Most popular
                    </span>
                  )}
                </div>
                <div className="flex flex-1 flex-col">
                  <h3 className="mt-5 text-xl font-black">{plan.name}</h3>
                  <div className="mt-1 flex items-baseline gap-0.5">
                    <span className={`text-4xl font-black ${plan.featured ? 'text-white' : 'text-primary'}`}>
                      {plan.price}
                    </span>
                    <span className={`ml-0.5 text-sm font-bold ${plan.featured ? 'text-slate-400' : 'text-tertiary'}`}>
                      {plan.period}
                    </span>
                  </div>
                  <p className={`mt-3 text-sm leading-6 ${plan.featured ? 'text-slate-300' : 'text-secondary'}`}>
                    {plan.description}
                  </p>
                  <div className="mt-5 flex flex-col gap-2.5">
                    {plan.bullets.map((bullet) => (
                      <div key={bullet} className="flex items-start gap-2.5 text-sm">
                        <CheckCircle2 className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${plan.featured ? 'text-gold' : 'text-accent'}`} />
                        <span className={plan.featured ? 'text-slate-200' : 'text-secondary'}>{bullet}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <a
                  href={plan.href}
                  className={`mt-8 inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-extrabold transition duration-200 focus:outline-none focus:ring-2 ${
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

        {/* Trust guarantees */}
        <div className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-[1.5rem] border border-panel-border bg-panel-border shadow-sm md:grid-cols-4">
          {guarantees.map(({ icon: Icon, label, desc }) => (
            <div key={label} className="flex flex-col items-center gap-2 bg-white px-5 py-6 text-center transition hover:bg-canvas">
              <span className="grid h-10 w-10 place-items-center rounded-xl border border-panel-border bg-canvas text-accent">
                <Icon className="h-4 w-4" />
              </span>
              <div className="text-sm font-black text-primary">{label}</div>
              <div className="text-xs font-bold text-secondary">{desc}</div>
            </div>
          ))}
        </div>

        {/* Link to full pricing page */}
        <div className="mt-6 flex flex-col items-center gap-2 text-center">
          <p className="text-sm font-bold text-secondary">
            Need a full feature comparison or have questions?
          </p>
          <Link
            to="/pricing"
            className="inline-flex items-center gap-1.5 text-sm font-extrabold text-accent hover:underline"
          >
            See full pricing breakdown
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>

      </div>
    </section>
  );
}
