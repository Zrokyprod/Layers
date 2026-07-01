import { motion, useReducedMotion } from 'framer-motion';
import type { ReactNode } from 'react';
import { useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Check,
  Copy,
  DatabaseZap,
  LockKeyhole,
  ShieldCheck,
} from 'lucide-react';
import Hero from '../components/hero/Hero';
import { FlowDiagram } from '../components/FlowDiagram';
import { RealtimeControl } from '../components/RealtimeControl';
import { ScaleFleet } from '../components/ScaleFleet';
import { DEMO_URL, SIGN_UP_URL } from '../lib/links';

const ease = [0.16, 1, 0.3, 1] as const;

function Reveal({ children, delay = 0, className = '' }: { children: ReactNode; delay?: number; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { y: 16 }}
      whileInView={{ y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.55, ease, delay }}
    >
      {children}
    </motion.div>
  );
}

function SectionHeader({
  eyebrow,
  title,
  copy,
  align = 'left',
}: {
  eyebrow: string;
  title: string;
  copy?: string;
  align?: 'left' | 'center';
}) {
  return (
    <Reveal>
      <div className={align === 'center' ? 'mx-auto max-w-2xl text-center' : 'max-w-2xl'}>
        <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#4f5a52]">{eyebrow}</p>
        <h2 className="mt-3 text-balance text-[2rem] font-semibold leading-[1.08] tracking-[-0.025em] text-[#20231f] md:text-[2.75rem]">
          {title}
        </h2>
        {copy ? <p className="mt-4 text-[1.02rem] leading-[1.6] text-[#5b615a]">{copy}</p> : null}
      </div>
    </Reveal>
  );
}

function Section({ children, className = '', id }: { children: ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={`w-full scroll-mt-28 px-4 py-16 text-[#20231f] md:py-20 ${className}`}>
      <div className="mx-auto max-w-[1340px]">{children}</div>
    </section>
  );
}

function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`group rounded-[16px] border border-[#d8dbd2] bg-[#fbfcf8] shadow-[inset_0_1px_0_rgba(255,255,255,0.85),0_1px_2px_rgba(42,45,40,0.04),0_24px_48px_-30px_rgba(42,45,40,0.18)] transition duration-200 hover:-translate-y-1 hover:border-[#c7cbc2] hover:shadow-[0_2px_4px_rgba(42,45,40,0.04),0_32px_60px_-32px_rgba(42,45,40,0.26)] ${className}`}
    >
      {children}
    </div>
  );
}

function StatusChip({
  tone,
  children,
}: {
  tone: 'success' | 'warning' | 'danger' | 'accent' | 'neutral';
  children: string;
}) {
  const classes = {
    success: 'border-[#2f7d50]/25 bg-[#2f7d50]/10 text-[#276844]',
    warning: 'border-[#b87922]/25 bg-[#b87922]/10 text-[#8a5a16]',
    danger: 'border-[#c35145]/25 bg-[#c35145]/10 text-[#9f3f36]',
    accent: 'border-[#4f5a52]/25 bg-[#4f5a52]/10 text-[#3f4942]',
    neutral: 'border-[#d8dbd2] bg-[#e8ebe4] text-[#5b615a]',
  }[tone];
  const dot = {
    success: 'bg-[#2f7d50]',
    warning: 'bg-[#b87922]',
    danger: 'bg-[#c35145]',
    accent: 'bg-[#4f5a52]',
    neutral: 'bg-[#7c837b]',
  }[tone];
  return (
    <span className={`inline-flex h-7 items-center gap-2 rounded-full border px-3 text-[11px] font-semibold uppercase tracking-[0.04em] ${classes}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {children}
    </span>
  );
}

function ButtonRow({ centered = false }: { centered?: boolean }) {
  return (
    <div className={`mt-8 flex flex-wrap items-center gap-3 ${centered ? 'justify-center' : ''}`}>
      <a
        href={DEMO_URL}
        className="inline-flex h-11 items-center justify-center gap-2 rounded-[10px] bg-[linear-gradient(180deg,#5f675f,#343a34)] px-5 text-sm font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_10px_24px_-12px_rgba(42,45,40,0.55)] transition duration-150 hover:-translate-y-px hover:bg-[#4f5a52] focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#4f5a52]/25 active:translate-y-0 active:scale-[0.98]"
      >
        Book a demo <ArrowRight size={16} />
      </a>
      <a
        href={SIGN_UP_URL}
        className="inline-flex h-11 items-center justify-center gap-2 rounded-[10px] border border-[#d8dbd2] bg-[#fbfcf8] px-5 text-sm font-semibold text-[#20231f] shadow-[0_1px_2px_rgba(42,45,40,0.04)] transition duration-150 hover:-translate-y-px hover:border-[#c7cbc2] hover:bg-[#f7f8f4] focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#4f5a52]/25 active:translate-y-0 active:scale-[0.98]"
      >
        Start free <ArrowUpRight size={16} />
      </a>
    </div>
  );
}

function Problems() {
  const cards = [
    {
      icon: AlertTriangle,
      tag: 'Money',
      title: 'Agents move money.',
      copy: 'Refunds, payouts, invoices - executed with no threshold and no approval.',
      fix: 'Zroky holds it for approval.',
    },
    {
      icon: LockKeyhole,
      tag: 'Data',
      title: 'Agents mutate data.',
      copy: 'CRM records, access grants, internal state - changed with no scoped authority.',
      fix: 'Zroky scopes and audits it.',
    },
    {
      icon: DatabaseZap,
      tag: 'Proof',
      title: 'Agents claim success.',
      copy: 'A tool call returns 200 - but that is not proof the real outcome happened.',
      fix: 'Zroky verifies the system of record.',
    },
  ];

  return (
    <section id="risk" className="relative w-full scroll-mt-28 overflow-hidden bg-[#f4f6f1] px-4 py-20 text-[#20231f] md:py-24">
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(60% 50% at 50% 0%, rgba(79,90,82,0.06), transparent 70%)' }}
      />
      <div className="relative mx-auto max-w-[1340px]">
        <SectionHeader
          eyebrow="The control problem"
          title="An agent that can act can cause real damage."
          copy="One wrong refund, a duplicate payout, a deleted record - one bad action is enough. Autonomy without approval, verification, and a receipt is a liability, not a feature."
          align="center"
        />
        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {cards.map((card, index) => {
            const Icon = card.icon;
            return (
              <Reveal key={card.title} delay={index * 0.08}>
                <article className="group h-full rounded-[20px] border border-[#e0e2db] bg-white p-7 shadow-[0_1px_2px_rgba(42,45,40,0.04),0_22px_48px_-34px_rgba(42,45,40,0.22)] transition duration-300 hover:-translate-y-1.5 hover:border-[#c8ccc3] hover:shadow-[0_2px_4px_rgba(42,45,40,0.05),0_34px_64px_-34px_rgba(42,45,40,0.32)]">
                  <div className="flex items-center justify-between">
                    <span className="grid h-12 w-12 place-items-center rounded-[14px] border border-[#e0e2db] bg-[#f4f6f1] text-[#4f5a52] transition group-hover:bg-[#eaefe8]">
                      <Icon size={21} />
                    </span>
                    <span className="rounded-full border border-[#e0e2db] bg-[#f4f6f1] px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-[#8b9288]">
                      {card.tag}
                    </span>
                  </div>
                  <h3 className="mt-6 text-[1.35rem] font-semibold tracking-[-0.015em] text-[#20231f]">{card.title}</h3>
                  <p className="mt-2.5 text-[14px] leading-relaxed text-[#5b615a]">{card.copy}</p>
                  <div className="mt-6 flex items-center gap-2 border-t border-[#eef0eb] pt-4">
                    <ArrowRight size={14} className="text-[#4f5a52]" />
                    <span className="text-[12.5px] font-semibold text-[#3f4942]">{card.fix}</span>
                  </div>
                </article>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function ControlLoop() {
  return (
    <Section id="product" className="bg-[#fbfcfa]">
      <SectionHeader
        eyebrow="The loop"
        title="Policy decides. Runners execute. Systems of record prove."
        copy="Every high-risk action moves through the same authority path: a deterministic policy decision, an approval audit, isolated execution, verification, and a receipt."
        align="center"
      />
      <Reveal delay={0.1} className="mt-14">
        <div className="rounded-[24px] border border-[#d8dbd2] bg-[linear-gradient(180deg,#fbfcf8,#f4f6f1)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_30px_70px_-40px_rgba(42,45,40,0.28)] md:p-10">
          <FlowDiagram />
        </div>
      </Reveal>
    </Section>
  );
}

function ReceiptShowcase() {
  const rows = [
    ['Action', 'refund.payment - $4,200.00 USD'],
    ['Agent', 'billing-ops-agent'],
    ['Policy', 'R4 - approval above $500 - rule: finance-agent'],
    ['Approval', 'priya@acme.com - dual approval satisfied'],
    ['Execution', 'isolated credential - Razorpay runner'],
    ['Verification', 'Razorpay ledger - amount, currency, status matched'],
    ['Evidence hash', 'sha256:9f2c...b41'],
  ];

  return (
    <Section id="receipts" className="bg-[#f4f6f1]">
      <div className="grid gap-12 lg:grid-cols-[0.86fr_1.14fr] lg:items-center">
        <SectionHeader
          eyebrow="Signed receipt"
          title="The receipt is the artifact your auditor can inspect."
          copy="A receipt is not an AI-written summary. It is a signed proof bundle with policy, approval, execution, verification, evidence hash, and signature context."
        />
        <Reveal delay={0.08}>
          <Card className="overflow-hidden p-0 hover:translate-y-0">
            <div className="h-[3px] bg-[linear-gradient(90deg,#4f5a52,#343a34)]" />
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#d8dbd2] bg-[#f7f8f4] p-5">
              <div>
                <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8b9288]">ZROKY - ACTION RECEIPT</p>
                <h3 className="mt-2 text-xl font-semibold tracking-[-0.01em] text-[#20231f]">Signed proof, not model opinion</h3>
              </div>
              <StatusChip tone="success">Matched</StatusChip>
            </div>
            <div className="divide-y divide-[#e3e5de] p-5">
              {rows.map(([label, value]) => (
                <div key={label} className="grid gap-2 py-3 text-sm sm:grid-cols-[8rem_1fr]">
                  <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-[#8b9288]">{label}</span>
                  <span className="text-[#20231f]">{value}</span>
                </div>
              ))}
              <div className="mt-4 rounded-[12px] border border-[#4f5a52]/15 bg-[#f4f6f1] p-4">
                <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-[#4f5a52]">Signature</p>
                <p className="mt-2 break-all font-mono text-sm text-[#3f4942]">HMAC-SHA256 - key zrk_live_1 - 7f3a...d92c</p>
              </div>
            </div>
          </Card>
        </Reveal>
      </div>
    </Section>
  );
}

function TrustSection() {
  const controls = [
    ['Fail-closed gates', 'Missing policy, runner, or verifier does not become a fake success.'],
    ['Isolated credentials', 'Agents request actions; runners execute only with scoped credentials.'],
    ['Advisory AI boundary', 'AI can explain context, but policy decides and system proof wins.'],
    ['Honest proof states', 'Matched, mismatched, not_verified, and receipt pending mean different things.'],
  ];
  return (
    <Section id="trust" className="bg-[#f4f6f1]">
      <div className="grid gap-10 lg:grid-cols-[1fr_1fr]">
        <SectionHeader
          eyebrow="Security and trust"
          title="Built for operators who cannot accept model opinion as proof."
          copy="Authority, execution, verification, and receipt signing stay separated, so the audit trail is defensible."
        />
        <div className="grid gap-3">
          {controls.map(([title, copy], index) => (
            <Reveal key={title} delay={index * 0.04}>
              <Card className="p-5">
                <div className="flex items-start gap-4">
                  <div className="grid h-9 w-9 shrink-0 place-items-center rounded-[12px] border border-[#d8dbd2] bg-[#e8ebe4] text-[#4f5a52]">
                    <ShieldCheck size={18} />
                  </div>
                  <div>
                    <h3 className="text-base font-semibold text-[#20231f]">{title}</h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-[#5b615a]">{copy}</p>
                  </div>
                </div>
              </Card>
            </Reveal>
          ))}
        </div>
      </div>
    </Section>
  );
}

const SNIPPET = `decision = zroky.verified_action(
    agent_id="agent_billing_ops",
    action_type="refund.payment",
    parameters={"amount_minor": 420000, "currency": "USD"},
)

proof = zroky.await_action_proof(decision["action_id"])
print(proof["proof_status"], proof["receipt_status"])
# -> matched generated`;

function Quickstart() {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard?.writeText(SNIPPET);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <Section id="quickstart" className="bg-[#f4f6f1]">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <Reveal>
          <div>
            <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#4f5a52]">Quickstart</p>
            <h2 className="mt-3 max-w-md text-balance text-[2rem] font-semibold leading-[1.08] tracking-[-0.025em] text-[#20231f] md:text-[2.75rem]">
              One call. Held, verified, signed.
            </h2>
            <p className="mt-4 max-w-md text-[1.02rem] leading-[1.6] text-[#5b615a]">
              Wrap one high-risk tool call. Zroky handles approval, execution, verification, and the receipt.
            </p>
            <ButtonRow />
          </div>
        </Reveal>
        <Reveal delay={0.08}>
          <Card className="overflow-hidden p-0 hover:translate-y-0">
            <div className="flex items-center justify-between border-b border-[#4b514a] bg-[#30362f] px-4 py-3">
              <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-[#c5cbc1]">python</span>
              <button
                type="button"
                onClick={copy}
                className="inline-flex items-center gap-1.5 rounded-[8px] border border-white/15 bg-white/5 px-2.5 py-1.5 font-mono text-[11px] text-[#e7ebe4] transition hover:bg-white/10"
              >
                {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? 'copied' : 'copy'}
              </button>
            </div>
            <pre className="overflow-auto bg-[#30362f] p-5 font-mono text-[12.5px] leading-relaxed text-[#eef1ec]">
              {SNIPPET}
            </pre>
          </Card>
        </Reveal>
      </div>
    </Section>
  );
}

function FinalCTA() {
  return (
    <section className="w-full bg-[#fbfcfa] px-4 py-20 text-[#20231f]">
      <Reveal>
        <div className="relative mx-auto max-w-5xl overflow-hidden rounded-[24px] border border-[#d8dbd2] bg-[#fbfcf8] p-10 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_40px_80px_-40px_rgba(42,45,40,0.25)] md:p-16">
          <div className="mesh-rocket pointer-events-none absolute inset-0" />
          <div className="relative z-10">
            <h2 className="mx-auto max-w-3xl text-balance text-[2.25rem] font-semibold leading-[1.05] tracking-[-0.03em] text-[#20231f] md:text-[3.5rem]">
              Authority for your agents. <span className="text-[#566158]">A receipt for every action.</span>
            </h2>
            <ButtonRow centered />
          </div>
        </div>
      </Reveal>
    </section>
  );
}

export default function HomePage() {
  return (
    <div className="w-full bg-[#fbfcfa]">
      <Hero />
      <RealtimeControl />
      <Problems />
      <ControlLoop />
      <ScaleFleet />
      <ReceiptShowcase />
      <TrustSection />
      <Quickstart />
      <FinalCTA />
    </div>
  );
}
