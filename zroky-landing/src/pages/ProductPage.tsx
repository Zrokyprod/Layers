import { type ReactNode } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import {
  ArrowRight,
  Bot,
  Code2,
  DatabaseZap,
  FileCheck2,
  Fingerprint,
  LockKeyhole,
  MessageSquare,
  ReceiptText,
  Route,
  SlidersHorizontal,
  Sparkles,
  Terminal,
  UserCheck,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { DEMO_URL, SIGN_UP_URL } from '../lib/links';

const ease = [0.16, 1, 0.3, 1] as const;

const stageAnchors = [
  { id: 'declare', label: 'Declare' },
  { id: 'decide', label: 'Decide' },
  { id: 'approve', label: 'Approve' },
  { id: 'execute', label: 'Execute' },
  { id: 'verify', label: 'Verify' },
  { id: 'prove', label: 'Prove' },
];

const stages: Array<{
  id: string;
  eyebrow: string;
  title: string;
  copy: string;
  line: string;
  icon: LucideIcon;
  visual: 'declare' | 'decide' | 'approve' | 'execute' | 'verify' | 'prove';
}> = [
  {
    id: 'declare',
    eyebrow: 'Declare',
    title: 'Agents do not get tools. They get contracts.',
    copy: 'Define the actions an agent is allowed to request, the shape of the payload, the source of truth, and the environment where it may run.',
    line: 'Start with support-ops-v1 or devops-release-v1, then add your own action contracts.',
    icon: Code2,
    visual: 'declare',
  },
  {
    id: 'decide',
    eyebrow: 'Decide',
    title: 'Policy decides before anything touches production.',
    copy: 'Thresholds, allowlists, sequence-risk rules, kill switch state, and dry-run checks all evaluate before the runner receives authority.',
    line: 'Dry-run a scenario first: a $600 refund can be tested without recording a live action.',
    icon: SlidersHorizontal,
    visual: 'decide',
  },
  {
    id: 'approve',
    eyebrow: 'Approve',
    title: 'Approval is bound to the exact payload.',
    copy: 'When a human approves a risky action, the approval belongs to that action, those parameters, that actor, and that policy decision.',
    line: 'Approve a $500 refund, and only that $500 refund can run.',
    icon: UserCheck,
    visual: 'approve',
  },
  {
    id: 'execute',
    eyebrow: 'Execute',
    title: 'The agent never holds a production secret.',
    copy: 'Zroky hands execution to a scoped runner with the credential reference and policy context needed for one approved operation.',
    line: 'The runner executes the approved action path; the agent keeps proposing, not owning credentials.',
    icon: LockKeyhole,
    visual: 'execute',
  },
  {
    id: 'verify',
    eyebrow: 'Verify',
    title: 'A tool response is compared with reality.',
    copy: 'Outcomes are checked field-by-field against Stripe, Postgres, REST APIs, GitHub, Slack, and other source-of-record connectors.',
    line: 'The claim can succeed while the verified outcome stays mismatched or not verified.',
    icon: DatabaseZap,
    visual: 'verify',
  },
  {
    id: 'prove',
    eyebrow: 'Prove',
    title: 'The action becomes a receipt, not a memory.',
    copy: 'Zroky packages actor chain, policy decision, approval, runner event, source comparison, evidence hash, and timeline into a signed receipt.',
    line: 'Keep the record in Evidence, export it for review, or use it inside an audit pack.',
    icon: ReceiptText,
    visual: 'prove',
  },
];

function Reveal({ children, delay = 0, className = '' }: { children: ReactNode; delay?: number; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.58, ease, delay }}
    >
      {children}
    </motion.div>
  );
}

function Section({ children, id, className = '' }: { children: ReactNode; id?: string; className?: string }) {
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

function ProductHeroVisual() {
  const loop = ['Declare', 'Decide', 'Approve', 'Execute', 'Verify', 'Prove'];
  return (
    <div className="overflow-hidden rounded-[20px] border border-[#d7d4ca] bg-[#fffdfa] shadow-[0_1px_2px_rgba(28,31,26,0.05),0_40px_90px_-58px_rgba(28,31,26,0.46)]">
      <div className="border-b border-[#dedacf] bg-[#f8f7f2] px-4 py-4 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">Control loop</p>
            <h3 className="mt-1 text-xl font-semibold text-[#151713]">From intent to receipt</h3>
          </div>
          <span className="rounded-[9px] border border-[#cfe0dd] bg-[#eaf1ef] px-3 py-1.5 text-[12px] font-semibold text-[#2f5f66]">
            matched
          </span>
        </div>
      </div>
      <div className="p-4 sm:p-5">
        <div className="grid gap-2 md:grid-cols-6">
          {loop.map((item, index) => (
            <div key={item} className="relative rounded-[12px] border border-[#e1ddd3] bg-[#fbfaf5] p-3.5">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-[#cfe0dd] bg-[#eaf1ef] font-mono text-[10px] font-semibold text-[#2f5f66]">
                {index + 1}
              </span>
              <p className="mt-3 text-sm font-semibold text-[#171a15]">{item}</p>
              <p className="mt-1 text-[12px] leading-relaxed text-[#6b6f68]">
                {['contract', 'policy', 'human', 'runner', 'source', 'receipt'][index]}
              </p>
              {index < loop.length - 1 ? (
                <span className="absolute -right-3 top-1/2 z-10 hidden h-6 w-6 -translate-y-1/2 place-items-center rounded-full border border-[#d7d4ca] bg-[#fffdfa] text-[#8a867a] md:grid">
                  <ArrowRight size={13} />
                </span>
              ) : null}
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-[14px] border border-[#d9d6ca] bg-[#f8f7f2] p-4">
          <div className="grid gap-3 md:grid-cols-[1fr_auto_1fr] md:items-center">
            <div className="rounded-[12px] border border-[#e1ddd3] bg-[#fffdfa] p-4">
              <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8a867a]">agent intent</p>
              <p className="mt-2 font-mono text-sm text-[#171a15]">customer.access.grant</p>
              <p className="mt-1 text-xs text-[#6b6f68]">role: admin / user_881</p>
            </div>
            <div className="hidden text-[#9a9689] md:block">
              <ArrowRight size={18} />
            </div>
            <div className="rounded-[12px] border border-[#cfe0dd] bg-[#eaf1ef] p-4">
              <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">receipt</p>
              <p className="mt-2 font-mono text-sm text-[#171a15]">proof_status: matched</p>
              <p className="mt-1 text-xs text-[#4d6b65]">policy + runner + source bound</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="w-full bg-[linear-gradient(180deg,#fbfaf6_0%,#f4f2eb_54%,#fbfcfa_100%)] px-4 pb-14 pt-28 text-[#171a15] md:pb-20 md:pt-36">
      <div className="mx-auto grid max-w-[1260px] items-center gap-10 lg:grid-cols-[0.9fr_1.1fr]">
        <Reveal>
          <div className="max-w-3xl">
            <Eyebrow icon={Workflow}>Product</Eyebrow>
            <h1 className="mt-4 text-[2.45rem] font-semibold leading-[1.02] tracking-[-0.032em] text-[#11130f] min-[380px]:text-[2.8rem] md:text-[4.6rem]">
              From agent intent to signed receipt.
            </h1>
            <p className="mt-5 text-[1.02rem] leading-[1.68] text-[#555b53] md:text-[1.15rem]">
              See how Zroky turns risky tool calls into governed, verified, receipted actions without replacing your agent framework.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <PrimaryButton href={DEMO_URL}>Book a demo <ArrowRight size={16} /></PrimaryButton>
              <GhostButton href={SIGN_UP_URL}>Start free <ArrowRight size={16} /></GhostButton>
            </div>
          </div>
        </Reveal>
        <Reveal delay={0.08}>
          <ProductHeroVisual />
        </Reveal>
      </div>
    </section>
  );
}

function StageNav() {
  return (
    <div className="sticky top-[82px] z-30 hidden w-full border-y border-[#dedbd1] bg-[#fbfcf8]/88 px-4 py-3 backdrop-blur-xl lg:block">
      <nav className="mx-auto flex max-w-[1260px] items-center justify-between gap-2" aria-label="Product stages">
        {stageAnchors.map((item, index) => (
          <a
            key={item.id}
            href={`#${item.id}`}
            className="inline-flex min-w-0 flex-1 items-center justify-center gap-2 rounded-[10px] border border-[#dedbd1] bg-[#fffdfa] px-3 py-2 text-sm font-semibold text-[#4f554d] transition hover:border-[#cfe0dd] hover:bg-[#eaf1ef] hover:text-[#2f5f66]"
          >
            <span className="font-mono text-[11px] text-[#8a867a]">0{index + 1}</span>
            {item.label}
          </a>
        ))}
      </nav>
    </div>
  );
}

function MiniPill({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'teal' | 'amber' | 'red' }) {
  const styles = {
    neutral: 'border-[#dedbd1] bg-[#fbfaf5] text-[#5b615a]',
    teal: 'border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]',
    amber: 'border-[#dfc899] bg-[#fff8ea] text-[#8a5a16]',
    red: 'border-[#f0c6bf] bg-[#fbebe9] text-[#b3402f]',
  };
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold ${styles[tone]}`}>{children}</span>;
}

function StageVisual({ type }: { type: (typeof stages)[number]['visual'] }) {
  if (type === 'declare') {
    return (
      <div className="rounded-[16px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.05)]">
        <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">action pack</p>
        <h3 className="mt-2 text-xl font-semibold text-[#151713]">support-ops-v1</h3>
        <div className="mt-4 grid gap-2">
          {['customer.access.grant', 'customer.message.send', 'refund.payment'].map((action) => (
            <div key={action} className="flex items-center justify-between rounded-[10px] border border-[#e1ddd3] bg-[#fbfaf5] px-3 py-2.5">
              <span className="font-mono text-[12px] text-[#34362f]">{action}</span>
              <MiniPill tone="teal">contract</MiniPill>
            </div>
          ))}
        </div>
        <pre className="mt-4 overflow-x-auto rounded-[12px] bg-[#252922] p-4 font-mono text-[12px] leading-relaxed text-[#eef1ec]">{`receipt = zroky.protect(
  action="refund.payment",
  params={"amount": 4200},
)`}</pre>
      </div>
    );
  }

  if (type === 'decide') {
    return (
      <div className="rounded-[16px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.05)]">
        <div className="flex items-center justify-between">
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">policy dry-run</p>
          <MiniPill tone="amber">held</MiniPill>
        </div>
        <div className="mt-4 rounded-[12px] border border-[#e1ddd3] bg-[#fbfaf5] p-4">
          <p className="text-sm font-semibold text-[#151713]">refund.payment / $600</p>
          <p className="mt-1 text-xs text-[#6b6f68]">customer_tier: enterprise / region: US</p>
        </div>
        <div className="mt-4 grid gap-2">
          {[
            ['threshold', 'requires owner approval'],
            ['sequence', 'no risky sequence detected'],
            ['allowlist', 'runner allowed'],
          ].map(([label, value]) => (
            <div key={label} className="grid grid-cols-[88px_1fr] gap-3 rounded-[10px] border border-[#e1ddd3] bg-[#fbfaf5] px-3 py-2.5 text-sm">
              <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-[#8a867a]">{label}</span>
              <span className="font-semibold text-[#34362f]">{value}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (type === 'approve') {
    return (
      <div className="rounded-[16px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.05)]">
        <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">approval inbox</p>
        <div className="mt-4 rounded-[12px] border border-[#dfc899] bg-[#fff8ea] p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-[#151713]">refund.payment held</p>
              <p className="mt-1 text-xs text-[#6b6f68]">exact payload hash: 7f3a...</p>
            </div>
            <MiniPill tone="amber">risk</MiniPill>
          </div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          <button className="rounded-[10px] border border-[#cfe0dd] bg-[#eaf1ef] px-3 py-2 text-sm font-semibold text-[#2f5f66]">Approve exact payload</button>
          <button className="rounded-[10px] border border-[#f0c6bf] bg-[#fbebe9] px-3 py-2 text-sm font-semibold text-[#b3402f]">Deny</button>
        </div>
        <div className="mt-3 rounded-[10px] border border-[#e1ddd3] bg-[#fbfaf5] px-3 py-2 text-xs text-[#6b6f68]">
          Slack approval carries the same action digest and policy reason.
        </div>
      </div>
    );
  }

  if (type === 'execute') {
    return (
      <div className="rounded-[16px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.05)]">
        <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">scoped runner</p>
        <div className="mt-4 grid gap-2">
          {[
            ['credential_ref', 'stripe_refunds_prod'],
            ['action_scope', 'refund.payment only'],
            ['runner_state', 'executed'],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center justify-between gap-3 rounded-[10px] border border-[#e1ddd3] bg-[#fbfaf5] px-3 py-2.5">
              <span className="font-mono text-[11px] text-[#8a867a]">{label}</span>
              <span className="text-sm font-semibold text-[#34362f]">{value}</span>
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-[12px] border border-[#cfe0dd] bg-[#eaf1ef] p-4 text-sm font-semibold text-[#2f5f66]">
          The agent proposed the action. The runner owned the execution boundary.
        </div>
      </div>
    );
  }

  if (type === 'verify') {
    return (
      <div className="rounded-[16px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.05)]">
        <div className="flex items-center justify-between">
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">claim vs record</p>
          <MiniPill tone="red">mismatch</MiniPill>
        </div>
        <div className="mt-4 overflow-hidden rounded-[12px] border border-[#e1ddd3]">
          {[
            ['field', 'claimed', 'actual'],
            ['refund_id', 'rf_8841', 'rf_8841'],
            ['currency', 'USD', 'USD'],
            ['amount', '$500', '$5,000'],
          ].map((row, index) => (
            <div
              key={row.join('-')}
              className={`grid grid-cols-3 gap-2 px-3 py-2.5 text-sm ${index === 0 ? 'bg-[#f8f7f2] font-mono text-[10px] uppercase tracking-[0.1em] text-[#8a867a]' : row[0] === 'amount' ? 'bg-[#fbebe9] font-semibold text-[#b3402f]' : 'bg-[#fffdfa] text-[#34362f]'}`}
            >
              {row.map((cell) => <span key={cell}>{cell}</span>)}
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {['Stripe', 'Postgres', 'REST', 'GitHub', 'Slack'].map((item) => <MiniPill key={item}>{item}</MiniPill>)}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-[16px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.05)]">
      <div className="rounded-[14px] border border-[#dedbd1] bg-[#fbfaf5] p-5">
        <p className="text-center font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-[#2f5f66]">Zroky action receipt</p>
        <div className="mt-5 grid gap-2 font-mono text-sm">
          {[
            ['action', 'refund.payment'],
            ['policy', 'held -> approved'],
            ['approver', 'finance.owner'],
            ['runner', 'scoped credential'],
            ['outcome', 'matched'],
            ['evidence_hash', 'sha256:7f3a...'],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center justify-between gap-4 border-b border-dashed border-[#d8d4ca] pb-2">
              <span className="text-[#8a867a]">{label}</span>
              <span className={label === 'outcome' ? 'font-semibold text-[#1f7a45]' : 'text-[#171a15]'}>{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StageSection({ stage, index }: { stage: (typeof stages)[number]; index: number }) {
  const Icon = stage.icon;
  return (
    <Section id={stage.id} className={index % 2 === 0 ? 'bg-[#fbfcfa]' : 'bg-[#f3f4ee]'}>
      <div className={`grid gap-8 lg:grid-cols-2 lg:items-center ${index % 2 === 1 ? 'lg:[&>*:first-child]:order-2' : ''}`}>
        <Reveal>
          <div className="max-w-xl">
            <Eyebrow icon={Icon}>{stage.eyebrow}</Eyebrow>
            <h2 className="mt-3 text-[2rem] font-semibold leading-[1.07] tracking-[-0.028em] text-[#151713] md:text-[3rem]">{stage.title}</h2>
            <p className="mt-4 text-[1.02rem] leading-[1.65] text-[#5b615a]">{stage.copy}</p>
            <div className="mt-6 rounded-[12px] border border-[#cfe0dd] bg-[#eaf1ef] p-4">
              <p className="text-sm font-semibold leading-relaxed text-[#2f5f66]">{stage.line}</p>
            </div>
          </div>
        </Reveal>
        <Reveal delay={0.08}>
          <StageVisual type={stage.visual} />
        </Reveal>
      </div>
    </Section>
  );
}

function ReceiptAnatomy() {
  const callouts = [
    ['Who acted, on whose authority', 'principal + actor chain + purpose'],
    ['What policy decided, and why', 'decision snapshot + hold reasons'],
    ['Which human approved', 'approval bound to this exact payload'],
    ['What actually happened', 'source-of-record comparison, field by field'],
    ['Why you can trust it', 'signed receipt + event timeline digests'],
  ];
  return (
    <Section id="receipt-anatomy" className="bg-[#fbfcfa]">
      <Reveal>
        <div className="grid gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <div className="rounded-[20px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.05),0_34px_70px_-54px_rgba(28,31,26,0.36)] sm:p-8">
            <p className="text-center font-mono text-[12px] font-semibold uppercase tracking-[0.22em] text-[#2f5f66]">Zroky</p>
            <h2 className="mt-2 text-center font-mono text-2xl tracking-[0.06em] text-[#151713]">ACTION RECEIPT</h2>
            <div className="mt-7 border-t border-dashed border-[#cfcac0] pt-5 font-mono text-sm sm:text-base">
              {[
                ['action', 'refund.payment'],
                ['principal', 'refund-agent'],
                ['policy', 'held -> approved'],
                ['approver', 'finance.owner'],
                ['runner', 'scoped credential'],
                ['outcome', 'matched'],
                ['signature', 'sha256:7f3a...'],
              ].map(([label, value]) => (
                <div key={label} className="flex items-center justify-between gap-4 py-1.5">
                  <span className="text-[#8a867a]">{label}</span>
                  <span className={label === 'outcome' ? 'font-semibold text-[#1f7a45]' : 'text-[#171a15]'}>{value}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <Eyebrow icon={ReceiptText}>Anatomy of a receipt</Eyebrow>
            <h2 className="mt-3 text-[2rem] font-semibold leading-[1.07] tracking-[-0.028em] text-[#151713] md:text-[3rem]">
              The evidence is readable before anyone opens JSON.
            </h2>
            <p className="mt-4 text-[1.02rem] leading-[1.65] text-[#5b615a]">
              A receipt explains authority, policy, approval, execution, verification, and evidence in one artifact.
            </p>
            <div className="mt-7 grid gap-4">
              {callouts.map(([title, body]) => (
                <div key={title} className="border-l-4 border-[#9fc7c2] pl-4">
                  <h3 className="text-base font-semibold text-[#171a15]">{title}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-[#5b615a]">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Reveal>
    </Section>
  );
}

function FleetBypass() {
  return (
    <Section id="fleet-bypass" className="bg-[#f3f4ee]">
      <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <Reveal>
          <div>
            <Eyebrow icon={Bot}>Fleet + bypass</Eyebrow>
            <h2 className="mt-3 text-[2rem] font-semibold leading-[1.07] tracking-[-0.028em] text-[#151713] md:text-[3rem]">
              Zroky shows the agents you manage and the paths you still need to control.
            </h2>
            <p className="mt-4 text-[1.02rem] leading-[1.65] text-[#5b615a]">
              Managed agents get risk limits and action contracts. Unreceipted source mutations become visible so teams can promote legacy paths into governed coverage.
            </p>
          </div>
        </Reveal>
        <Reveal delay={0.08}>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              ['Refund agent', 'managed', 'approval > $500', 'teal'],
              ['Release agent', 'managed', 'deploys require approval', 'teal'],
              ['legacy-export-agent', 'unmanaged', 'observed mutation path', 'amber'],
              ['policy_bypass', 'classified', 'unreceipted CRM update', 'red'],
            ].map(([name, status, detail, tone]) => (
              <div key={name} className={`rounded-[14px] border p-4 ${tone === 'teal' ? 'border-[#cfe0dd] bg-[#eaf1ef]' : tone === 'amber' ? 'border-[#dfc899] bg-[#fff8ea]' : 'border-[#f0c6bf] bg-[#fbebe9]'}`}>
                <div className="flex items-start justify-between gap-3">
                  <h3 className="text-sm font-semibold text-[#171a15]">{name}</h3>
                  <MiniPill tone={tone === 'teal' ? 'teal' : tone === 'amber' ? 'amber' : 'red'}>{status}</MiniPill>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-[#5b615a]">{detail}</p>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </Section>
  );
}

function ArchitectureDeploy() {
  const frameworks = ['OpenAI Agents SDK', 'LangGraph', 'CrewAI', 'AutoGen', 'MCP', 'Custom'];
  const path = ['Agent', 'SDK / Gateway', 'Policy', 'Runner', 'Verifier', 'Receipt'];
  return (
    <Section id="architecture-deploy" className="bg-[#fbfcfa]">
      <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
        <Reveal>
          <div className="rounded-[20px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.05)]">
            <div className="grid gap-2 md:grid-cols-6">
              {path.map((item, index) => (
                <div key={item} className="relative rounded-[12px] border border-[#e1ddd3] bg-[#fbfaf5] p-3 text-center">
                  <span className="text-sm font-semibold text-[#171a15]">{item}</span>
                  {index < path.length - 1 ? (
                    <span className="absolute -right-3 top-1/2 z-10 hidden h-6 w-6 -translate-y-1/2 place-items-center rounded-full border border-[#d7d4ca] bg-[#fffdfa] text-[#8a867a] md:grid">
                      <ArrowRight size={13} />
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              {frameworks.map((item) => <MiniPill key={item}>{item}</MiniPill>)}
            </div>
          </div>
        </Reveal>
        <Reveal delay={0.08}>
          <div>
            <Eyebrow icon={Route}>Architecture + deploy</Eyebrow>
            <h2 className="mt-3 text-[2rem] font-semibold leading-[1.07] tracking-[-0.028em] text-[#151713] md:text-[3rem]">
              No framework rewrite. Wrap one action first.
            </h2>
            <p className="mt-4 text-[1.02rem] leading-[1.65] text-[#5b615a]">
              Use the SDK when you own the code path, the gateway when routing is easier, and connectors when the source of record must prove the final state.
            </p>
          </div>
        </Reveal>
      </div>
    </Section>
  );
}

function PersonasCTA() {
  const personas = [
    [Terminal, 'Engineering', 'Wrap one guarded call, keep your framework, remove agent-held secrets from high-risk actions.'],
    [MessageSquare, 'Operations', 'See approvals, fleet state, bypass warnings, and kill-switch posture in one command view.'],
    [FileCheck2, 'Compliance', 'Export evidence packs, receipts, policy decisions, source comparisons, and retention-ready audit trails.'],
  ] as const;
  return (
    <Section id="personas" className="bg-[#f3f4ee]">
      <Reveal>
        <div className="mx-auto max-w-3xl text-center">
          <Eyebrow icon={Fingerprint}>Stakeholders</Eyebrow>
          <h2 className="mt-3 text-[2rem] font-semibold leading-[1.07] tracking-[-0.028em] text-[#151713] md:text-[3rem]">
            One control loop, three internal buyers.
          </h2>
          <p className="mt-4 text-[1.02rem] leading-[1.65] text-[#5b615a]">
            Engineering ships the wrapper. Operations governs the workflow. Compliance gets the artifact.
          </p>
        </div>
      </Reveal>
      <Reveal delay={0.08} className="mt-9">
        <div className="grid gap-3 md:grid-cols-3">
          {personas.map(([Icon, title, body]) => (
            <div key={title} className="rounded-[16px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.04)]">
              <span className="grid h-10 w-10 place-items-center rounded-[10px] border border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]">
                <Icon size={18} />
              </span>
              <h3 className="mt-4 text-lg font-semibold text-[#151713]">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[#5b615a]">{body}</p>
            </div>
          ))}
        </div>
      </Reveal>
      <Reveal delay={0.12}>
        <div className="mx-auto mt-10 max-w-4xl rounded-[20px] border border-[#d7d4ca] bg-[#fffdfa] p-6 text-center shadow-[0_32px_72px_-54px_rgba(28,31,26,0.36)] md:p-10">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">Start narrow</p>
          <h3 className="mx-auto mt-3 max-w-2xl text-[1.9rem] font-semibold leading-[1.08] tracking-[-0.025em] text-[#151713] md:text-[2.7rem]">
            Protect the first action that can hurt the business.
          </h3>
          <div className="mt-7 flex flex-col justify-center gap-3 sm:flex-row">
            <PrimaryButton href={DEMO_URL}>Book a demo <ArrowRight size={16} /></PrimaryButton>
            <GhostButton href={SIGN_UP_URL}>Start free <ArrowRight size={16} /></GhostButton>
          </div>
        </div>
      </Reveal>
    </Section>
  );
}

export default function ProductPage() {
  return (
    <div className="w-full bg-[#fbfcfa]">
      <Hero />
      <StageNav />
      <Section id="loop" className="bg-[#fbfcfa]">
        <Reveal>
          <div className="mx-auto max-w-3xl text-center">
            <Eyebrow icon={Sparkles}>The loop, stage by stage</Eyebrow>
            <h2 className="mt-3 text-[2rem] font-semibold leading-[1.07] tracking-[-0.028em] text-[#151713] md:text-[3rem]">
              Six product surfaces, one governed action.
            </h2>
            <p className="mt-4 text-[1.02rem] leading-[1.65] text-[#5b615a]">
              Each step maps to a real Zroky module: setup, policies, approvals, runners, outcomes, and evidence.
            </p>
          </div>
        </Reveal>
      </Section>
      {stages.map((stage, index) => <StageSection key={stage.id} stage={stage} index={index} />)}
      <ReceiptAnatomy />
      <FleetBypass />
      <ArchitectureDeploy />
      <PersonasCTA />
    </div>
  );
}
