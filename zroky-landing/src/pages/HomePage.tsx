import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Check,
  Copy,
  DatabaseZap,
  DollarSign,
  Loader2,
  LockKeyhole,
  Send,
  ShieldCheck,
} from 'lucide-react';
import Hero from '../components/hero/Hero';
import { ControlLoopDemo } from '../components/hero/ControlLoopDemo';
import { DEMO_URL, SIGN_UP_URL } from '../lib/links';

const ease = [0.16, 1, 0.3, 1] as const;

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
    <section id={id} className={`w-full scroll-mt-28 overflow-hidden px-4 py-14 text-[#171a15] sm:py-16 md:py-20 ${className}`}>
      <div className="mx-auto min-w-0 max-w-[1260px]">{children}</div>
    </section>
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
      <div className={align === 'center' ? 'mx-auto min-w-0 max-w-3xl text-center' : 'min-w-0 max-w-3xl'}>
        <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">{eyebrow}</p>
        <h2 className="mt-3 text-balance text-[1.9rem] font-semibold leading-[1.08] tracking-[-0.025em] text-[#151713] min-[380px]:text-[2.08rem] md:text-[3.15rem] md:leading-[1.05] md:tracking-[-0.03em]">
          {title}
        </h2>
        {copy ? <p className="mt-4 text-[0.98rem] leading-[1.62] text-[#5b615a] md:text-[1.04rem] md:leading-[1.65]">{copy}</p> : null}
      </div>
    </Reveal>
  );
}

function ButtonRow({ centered = false }: { centered?: boolean }) {
  return (
    <div className={`mt-8 flex flex-col items-stretch gap-3 sm:flex-row sm:flex-wrap sm:items-center ${centered ? 'sm:justify-center' : ''}`}>
      <a
        href={DEMO_URL}
        className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-[10px] bg-[linear-gradient(180deg,#376f77,#2f5f66)] px-5 text-sm font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.2),0_14px_28px_-16px_rgba(47,95,102,0.75)] transition duration-150 hover:-translate-y-px active:translate-y-0 sm:w-auto"
      >
        Book a demo <ArrowRight size={16} />
      </a>
      <a
        href={SIGN_UP_URL}
        className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-[10px] border border-[#d4d0c4] bg-[#fffdfa] px-5 text-sm font-semibold text-[#252821] shadow-[0_1px_2px_rgba(32,35,31,0.05)] transition hover:-translate-y-px hover:border-[#c4bfb2] sm:w-auto"
      >
        Start free <ArrowUpRight size={16} />
      </a>
    </div>
  );
}

type TraceStage = 0 | 1 | 2 | 3;
type SequenceStage = 0 | 1 | 2 | 3 | 4;

function wait(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

/** A single living "aha" moment: the tool says 200 OK immediately, then after
 *  a beat, the source-of-record check reveals it never actually matched. */
function TraceCard() {
  const reduce = useReducedMotion();
  const [stage, setStage] = useState<TraceStage>(reduce ? 3 : 0);

  useEffect(() => {
    if (reduce) return undefined;
    let cancelled = false;
    async function loop() {
      while (!cancelled) {
        setStage(0);
        await wait(600);
        if (cancelled) return;
        setStage(1);
        await wait(1500);
        if (cancelled) return;
        setStage(2);
        await wait(1300);
        if (cancelled) return;
        setStage(3);
        await wait(3600);
      }
    }
    void loop();
    return () => {
      cancelled = true;
    };
  }, [reduce]);

  const rows = [
    {
      key: 'tool',
      label: 'Tool response',
      resolved: stage >= 1,
      pending: { text: 'Sending', tone: 'idle' as const },
      done: { text: '200 OK', tone: 'ok' as const, icon: Check },
    },
    {
      key: 'source',
      label: 'Source of record',
      resolved: stage >= 2,
      pending: { text: 'Checking', tone: 'checking' as const, icon: Loader2 },
      done: { text: 'Not verified', tone: 'bad' as const, icon: AlertTriangle },
    },
  ] as const;

  const toneStyles: Record<string, { bg: string; border: string; text: string }> = {
    idle: { bg: '#f5f4ee', border: '#e4e0d3', text: '#8a867a' },
    checking: { bg: '#fff8ea', border: '#eedaae', text: '#8a6a1c' },
    ok: { bg: '#eaf5ee', border: '#c9e2d2', text: '#1f7a45' },
    bad: { bg: '#fbebe9', border: '#f0c6bf', text: '#b3402f' },
  };

  const stepDone = [stage >= 1, stage >= 2, stage >= 3];

  return (
    <div className="relative mx-auto w-full max-w-[480px] overflow-hidden rounded-[14px] border border-[#d6d3c8] bg-[#fffdfa] p-4 shadow-[0_1px_2px_rgba(28,31,26,0.05),0_34px_70px_-50px_rgba(28,31,26,0.5)] sm:rounded-[16px] sm:p-6 sm:shadow-[0_1px_2px_rgba(28,31,26,0.05),0_44px_90px_-54px_rgba(28,31,26,0.54)]">
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-2 font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#8a867a]">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#df7c66] opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-[#df7c66]" />
          </span>
          Example action
        </span>
      </div>

      {/* stepper: Request -> Check -> Verdict, synced to stage */}
      <div className="mt-4 flex items-center gap-1.5">
        {['Request', 'Check', 'Verdict'].map((label, i) => (
          <div key={label} className="flex flex-1 items-center gap-1.5">
            <div className="flex-1">
              <p
                className="text-[9.5px] font-semibold uppercase tracking-[0.08em] transition-colors duration-300"
                style={{ color: stepDone[i] ? '#2f5f66' : '#b3ae9f' }}
              >
                {label}
              </p>
              <div className="mt-1.5 h-[3px] rounded-full" style={{ background: '#e4e0d3' }}>
                <motion.div
                  className="h-full rounded-full"
                  style={{ background: '#2f5f66' }}
                  initial={false}
                  animate={{ width: stepDone[i] ? '100%' : '0%' }}
                  transition={{ duration: 0.35, ease }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-5 rounded-[10px] border border-[#e4e0d3] bg-[#f5f4ee] p-4">
        <p className="font-mono text-[12px] leading-relaxed text-[#3a3d36]">
          <span className="text-[#8a867a]">POST</span> /v1/access/grant
          <br />
          role: <span className="text-[#2f5f66]">admin</span>
          <br />
          subject: user_881
        </p>
      </div>

      <div className="mt-5 grid gap-2.5">
        {rows.map((row) => {
          const state = row.resolved ? row.done : row.pending;
          const tone = toneStyles[state.tone];
          const Icon = 'icon' in state ? state.icon : null;
          return (
            <div
              key={row.key}
              className="flex min-w-0 items-center justify-between gap-3 rounded-[9px] border border-[#e6e2d7] bg-[#fbfaf5] px-3 py-2.5 sm:px-3.5"
            >
              <span className="min-w-0 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#8a867a] sm:text-[11px]">{row.label}</span>
              <AnimatePresence mode="wait" initial={false}>
                <motion.span
                  key={state.text}
                  initial={reduce ? false : { opacity: 0, y: 4, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ duration: 0.28, ease }}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold sm:text-[11.5px]"
                  style={{ background: tone.bg, borderColor: tone.border, color: tone.text }}
                >
                  {Icon ? <Icon size={12} className={state.tone === 'checking' ? 'animate-spin' : ''} /> : null}
                  {state.text}
                </motion.span>
              </AnimatePresence>
            </div>
          );
        })}

        <AnimatePresence>
          {stage >= 3 && (
            <motion.div
              initial={reduce ? false : { opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.4, ease }}
              className="overflow-hidden"
            >
              <div className="mt-0.5 flex items-center gap-3 rounded-[9px] border border-[#cfe0dd] bg-[#eaf1ef] px-3.5 py-3">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-[8px] bg-[#2f5f66] text-white">
                  <ShieldCheck size={14} />
                </span>
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#2f5f66]">Zroky verdict</p>
                  <p className="mt-0.5 truncate text-[12.5px] font-semibold text-[#171a15]">Held for approval - privilege + sequence risk</p>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <p className="mt-4 text-center text-[11.5px] leading-relaxed text-[#8a867a]">
        Same check applies to access grants, payouts, deploys, and customer messages.
      </p>
    </div>
  );
}

function SequenceRiskTraceCard() {
  const reduce = useReducedMotion();
  const [stage, setStage] = useState<SequenceStage>(reduce ? 4 : 0);

  useEffect(() => {
    if (reduce) return undefined;
    let cancelled = false;
    async function loop() {
      while (!cancelled) {
        setStage(0);
        await wait(450);
        if (cancelled) return;
        setStage(1);
        await wait(850);
        if (cancelled) return;
        setStage(2);
        await wait(850);
        if (cancelled) return;
        setStage(3);
        await wait(950);
        if (cancelled) return;
        setStage(4);
        await wait(3400);
      }
    }
    void loop();
    return () => {
      cancelled = true;
    };
  }, [reduce]);

  const actions = [
    { label: 'Bulk customer read', detail: '50 enterprise accounts', icon: DatabaseZap },
    { label: 'External message sent', detail: 'security exception requested', icon: Send },
    { label: 'Privilege grant', detail: 'admin access requested', icon: LockKeyhole },
  ];

  return (
    <div className="relative mx-auto w-full max-w-[520px] overflow-hidden rounded-[14px] border border-[#d6d3c8] bg-[#fffdfa] p-4 shadow-[0_1px_2px_rgba(28,31,26,0.05),0_34px_70px_-50px_rgba(28,31,26,0.5)] sm:rounded-[16px] sm:p-6 sm:shadow-[0_1px_2px_rgba(28,31,26,0.05),0_44px_90px_-54px_rgba(28,31,26,0.54)]">
      <div className="flex flex-wrap items-center justify-between gap-2 sm:gap-3">
        <span className="inline-flex items-center gap-2 font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#8a867a]">
          <span className="h-2 w-2 rounded-full bg-[#2f5f66]" />
          Sequence monitor
        </span>
        <span className="rounded-[8px] border border-[#cfe0dd] bg-[#eaf1ef] px-3 py-1.5 text-[11px] font-semibold text-[#2f5f66]">
          live policy signal
        </span>
      </div>

      <div className="relative mt-5">
        <AnimatePresence>
          {stage >= 4 && (
            <motion.div
              aria-hidden="true"
              className="absolute -inset-1.5 rounded-[15px] border border-[#dfc899] bg-[#fff8ea]/40 shadow-[0_0_0_6px_rgba(223,200,153,0.12)] sm:-inset-2"
              initial={reduce ? false : { opacity: 0, scale: 0.985 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.35, ease }}
            />
          )}
        </AnimatePresence>

        <div className="relative grid gap-2.5">
          {actions.map((action, index) => {
            const visible = stage >= index + 1;
            const Icon = action.icon;
            return (
              <motion.div
                key={action.label}
                initial={reduce ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: visible ? 1 : 0.34, y: visible ? 0 : 10 }}
                transition={{ duration: 0.32, ease }}
                className="flex min-w-0 items-center justify-between gap-2 rounded-[10px] border border-[#e1ddd3] bg-[#fbfaf5] px-3 py-2.5 sm:gap-3 sm:px-3.5 sm:py-3"
              >
                <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[8px] border border-[#d8e2df] bg-[#eaf1ef] text-[#2f5f66] sm:h-9 sm:w-9">
                    <Icon size={16} />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-[#171a15]">{action.label}</p>
                    <p className="mt-0.5 truncate font-mono text-[10.5px] text-[#777266]">{action.detail}</p>
                  </div>
                </div>
                <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-[#c2e4cf] bg-[#e7f5ec] px-2 py-1 text-[10.5px] font-semibold text-[#256b45] sm:gap-1.5 sm:px-2.5 sm:text-[11px]">
                  <Check size={12} />
                  Allowed
                </span>
              </motion.div>
            );
          })}
        </div>
      </div>

      <AnimatePresence>
        {stage >= 4 && (
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 12, height: 0 }}
            animate={{ opacity: 1, y: 0, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.4, ease }}
            className="overflow-hidden"
          >
            <div className="mt-4 rounded-[12px] border border-[#dfc899] bg-[#fff8ea] p-3.5 sm:mt-5 sm:p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[9px] bg-[#8a5a16] text-white">
                    <AlertTriangle size={16} />
                  </span>
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#8a5a16]">Sequence risk detected</p>
                    <p className="mt-1 text-sm font-semibold leading-relaxed text-[#171a15]">
                      Individually safe actions formed an unsafe pattern.
                    </p>
                  </div>
                </div>
                <span className="rounded-full border border-[#dfc899] bg-[#fffdfa] px-3 py-1 text-xs font-semibold text-[#8a5a16]">
                  Held
                </span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <p className="mt-4 text-center text-[11.5px] leading-relaxed text-[#8a867a]">
        The same sequence-risk signal appears in the dashboard today.
      </p>
    </div>
  );
}

function StakesSection() {
  const consequences = [
    { icon: DollarSign, text: 'Money can move to the wrong account.' },
    { icon: LockKeyhole, text: 'Access can be granted without approval.' },
    { icon: DatabaseZap, text: 'Production can change without an audit trail.' },
  ];

  return (
    <Section id="risk" className="bg-[#fbfcfa]">
      <div className="grid min-w-0 gap-10 sm:gap-14 lg:grid-cols-[0.85fr_1.15fr] lg:items-center">
        <Reveal>
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">The stakes</p>
          <h2 className="mt-3 text-balance text-[2.15rem] font-semibold leading-[1.08] tracking-[-0.03em] text-[#151713] md:text-[2.85rem]">
            <span className="block">A successful tool call</span>
            <span className="block text-[#2f5f66]">is not proof.</span>
          </h2>
          <p className="mt-5 max-w-md text-[1.02rem] leading-[1.65] text-[#5b615a]">
            Agents can move money, grant access, or change production state before anyone verifies the real outcome.
          </p>

          <div className="mt-7 grid gap-3.5">
            {consequences.map((item) => {
              const Icon = item.icon;
              return (
                <div key={item.text} className="flex items-center gap-3">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[9px] border border-[#dcd8ce] bg-[#f5f4ee] text-[#2f5f66]">
                    <Icon size={14} />
                  </span>
                  <p className="text-[13.5px] font-medium text-[#3a3d36]">{item.text}</p>
                </div>
              );
            })}
          </div>

          <a
            href="#architecture"
            className="mt-8 inline-flex items-center gap-1.5 text-[13.5px] font-semibold text-[#2f5f66] transition hover:gap-2.5"
          >
            See how the control loop closes this gap <ArrowRight size={14} />
          </a>
        </Reveal>

        <Reveal delay={0.12}>
          <TraceCard />
        </Reveal>
      </div>
    </Section>
  );
}

function ArchitectureDiagram() {
  return (
    <Section id="architecture" className="bg-[#f3f4ee]">
      <SectionHeader
        eyebrow="Control loop"
        title="Zroky sits between agent intent and real-world impact."
        copy="Nothing skips the line - not urgency, not scale, not a confident tool response."
        align="center"
      />

      <Reveal delay={0.06} className="mx-auto mt-9 max-w-5xl">
        <div className="grid gap-2 rounded-[14px] border border-[#d9d6ca] bg-[#fffdfa] p-2 text-center shadow-[0_20px_50px_-44px_rgba(28,31,26,0.35)] md:grid-cols-3">
          {[
            ['Authority', 'Who can act?'],
            ['Verification', 'Did reality match?'],
            ['Evidence', 'Can we prove it?'],
          ].map(([label, value]) => (
            <div key={label} className="rounded-[10px] border border-[#dedacf] bg-[#f7f6f1] p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8a867a]">{label}</p>
              <p className="mt-2 text-sm font-semibold text-[#242720]">{value}</p>
            </div>
          ))}
        </div>
      </Reveal>

      <Reveal delay={0.1} className="mt-10">
        <ControlLoopDemo />
      </Reveal>
    </Section>
  );
}

function SequenceRiskMoment() {
  return (
    <Section id="sequence-risk" className="bg-[#fbfcfa]">
      <div className="grid min-w-0 gap-8 sm:gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <SectionHeader
          eyebrow="Sequence risk"
          title="One safe action is safe. Three in sequence may not be."
          copy="Most guardrails judge actions one at a time. Zroky scores the sequence and catches unsafe patterns before they become production changes."
        />
        <Reveal delay={0.08}>
          <SequenceRiskTraceCard />
        </Reveal>
      </div>
    </Section>
  );
}

function PrintedReceiptArtifact() {
  const receiptClip =
    'polygon(0 14px,2.5% 0,5% 14px,7.5% 0,10% 14px,12.5% 0,15% 14px,17.5% 0,20% 14px,22.5% 0,25% 14px,27.5% 0,30% 14px,32.5% 0,35% 14px,37.5% 0,40% 14px,42.5% 0,45% 14px,47.5% 0,50% 14px,52.5% 0,55% 14px,57.5% 0,60% 14px,62.5% 0,65% 14px,67.5% 0,70% 14px,72.5% 0,75% 14px,77.5% 0,80% 14px,82.5% 0,85% 14px,87.5% 0,90% 14px,92.5% 0,95% 14px,97.5% 0,100% 14px,100% calc(100% - 14px),97.5% 100%,95% calc(100% - 14px),92.5% 100%,90% calc(100% - 14px),87.5% 100%,85% calc(100% - 14px),82.5% 100%,80% calc(100% - 14px),77.5% 100%,75% calc(100% - 14px),72.5% 100%,70% calc(100% - 14px),67.5% 100%,65% calc(100% - 14px),62.5% 100%,60% calc(100% - 14px),57.5% 100%,55% calc(100% - 14px),52.5% 100%,50% calc(100% - 14px),47.5% 100%,45% calc(100% - 14px),42.5% 100%,40% calc(100% - 14px),37.5% 100%,35% calc(100% - 14px),32.5% 100%,30% calc(100% - 14px),27.5% 100%,25% calc(100% - 14px),22.5% 100%,20% calc(100% - 14px),17.5% 100%,15% calc(100% - 14px),12.5% 100%,10% calc(100% - 14px),7.5% 100%,5% calc(100% - 14px),2.5% 100%,0 calc(100% - 14px))';

  const rows = [
    { code: '01', label: 'Policy snapshot', value: 'R4 approval > $500', status: 'HELD' },
    { code: '02', label: 'Approval trail', value: 'finance.owner', status: 'OK' },
    { code: '03', label: 'Execution event', value: 'scoped refund key', status: 'RUN' },
    { code: '04', label: 'Source comparison', value: 'ledger matched', status: 'MATCH' },
    { code: '05', label: 'Evidence hash', value: 'sha256:7f3a9e10...', status: 'SIGNED' },
  ];

  return (
    <div className="relative mx-auto w-full max-w-[315px] origin-top sm:max-w-[350px] lg:scale-[0.88]">
      <div className="absolute -inset-x-4 bottom-4 h-20 rounded-full bg-[#171a15]/12 blur-2xl sm:-inset-x-8" />
      <motion.div
        className="relative overflow-hidden border border-[#d4d0c4] bg-[#fffdf7] shadow-[0_1px_2px_rgba(28,31,26,0.06),0_42px_90px_-56px_rgba(28,31,26,0.58)]"
        style={{ clipPath: receiptClip }}
        initial={{ opacity: 0, y: 18, rotate: -0.5 }}
        whileInView={{ opacity: 1, y: 0, rotate: 0 }}
        viewport={{ once: true, margin: '-80px' }}
        transition={{ duration: 0.58, ease }}
      >
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(23,26,21,0.025)_1px,transparent_1px),linear-gradient(rgba(23,26,21,0.018)_1px,transparent_1px)] bg-[size:13px_13px]" />
        <div className="pointer-events-none absolute bottom-7 left-0 top-7 w-px bg-[repeating-linear-gradient(180deg,rgba(23,26,21,0.18)_0_3px,transparent_3px_7px)]" />
        <div className="pointer-events-none absolute bottom-7 right-0 top-7 w-px bg-[repeating-linear-gradient(180deg,rgba(23,26,21,0.18)_0_3px,transparent_3px_7px)]" />
        <motion.div
          className="pointer-events-none absolute right-7 top-[7.2rem] z-10 rotate-[-7deg] border-2 border-[#2f5f66]/35 px-4 py-1.5 font-mono text-[12px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]/70"
          initial={{ opacity: 0, scale: 0.82, rotate: -12 }}
          whileInView={{ opacity: 1, scale: 1, rotate: -7 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.32, ease, delay: 0.35 }}
        >
          Signed
        </motion.div>
        <div className="relative px-5 pb-7 pt-8 font-mono sm:px-6">
          <div className="text-center">
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#2f5f66]">Zroky</p>
            <h3 className="mt-1 text-[1.12rem] font-semibold uppercase tracking-[0.08em] text-[#171a15]">Action Receipt</h3>
            <p className="mt-2 text-[10.5px] uppercase tracking-[0.14em] text-[#8a867a]">refund.payment / matched</p>
            <p className="mt-1 text-[10.5px] text-[#8a867a]">Receipt No. zrk_rc_9f2c41</p>
          </div>

          <div className="my-4 border-t border-dashed border-[#bfb9aa]" />

          <div className="grid grid-cols-2 gap-y-1 text-[11px] text-[#3a3d36]">
            <span className="uppercase tracking-[0.1em] text-[#8a867a]">Action</span>
            <span className="text-right font-semibold">refund.payment</span>
            <span className="uppercase tracking-[0.1em] text-[#8a867a]">Amount</span>
            <span className="text-right font-semibold">$4,200.00</span>
            <span className="uppercase tracking-[0.1em] text-[#8a867a]">Status</span>
            <span className="text-right font-semibold text-[#256b45]">matched</span>
          </div>

          <div className="my-4 border-t border-dashed border-[#bfb9aa]" />

          <div className="border-y border-dashed border-[#bfb9aa] py-2">
            <div className="grid grid-cols-[2rem_1fr_3.5rem] gap-2 pb-1.5 text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8a867a]">
              <span>No.</span>
              <span>Check</span>
              <span className="text-right">State</span>
            </div>
            <div className="divide-y divide-dotted divide-[#d7d2c5]">
              {rows.map((row) => (
                <div key={row.label} className="grid grid-cols-[2rem_1fr_3.5rem] gap-2 py-2">
                  <span className="text-[10px] font-semibold text-[#8a867a]">{row.code}</span>
                  <div className="min-w-0">
                    <p className="truncate text-[10px] font-semibold uppercase tracking-[0.1em] text-[#8a867a]">{row.label}</p>
                    <p className="mt-0.5 truncate text-[12px] font-semibold text-[#171a15]">{row.value}</p>
                  </div>
                  <span className="self-center text-right text-[10px] font-semibold uppercase tracking-[0.08em] text-[#2f5f66]">{row.status}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="my-4 border-t border-dashed border-[#bfb9aa]" />

          <div className="grid grid-cols-[1fr_3.75rem] gap-3">
            <div>
              <p className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#777266]">Independent verification</p>
              <p className="mt-1 break-all text-[11px] font-semibold leading-relaxed text-[#171a15]">verify.zroky.com/receipt/zrk_rc_9f2c41</p>
              <div
                className="mt-3 h-7 w-full opacity-80"
                style={{
                  backgroundImage:
                    'repeating-linear-gradient(90deg,#171a15 0 2px,transparent 2px 5px,#171a15 5px 6px,transparent 6px 10px,#171a15 10px 13px,transparent 13px 17px)',
                }}
              />
            </div>
            <div className="grid h-[3.75rem] w-[3.75rem] grid-cols-5 grid-rows-5 gap-1 border border-[#d7d4ca] bg-[#f8f7f2] p-1">
              {Array.from({ length: 25 }).map((_, index) => (
                <span
                  key={index}
                  className={`block ${[0, 1, 2, 5, 10, 12, 14, 16, 18, 20, 21, 23, 24].includes(index) ? 'bg-[#171a15]' : 'bg-transparent'}`}
                />
              ))}
            </div>
          </div>

          <div className="mt-4 border-t border-dashed border-[#bfb9aa] pt-3 text-center">
            <p className="text-[10px] uppercase tracking-[0.18em] text-[#8a867a]">Signature valid</p>
            <p className="mt-1 text-[10.5px] uppercase tracking-[0.16em] text-[#2f5f66]">Independently verifiable</p>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

function ProofStandard() {
  return (
    <Section id="receipts" className="bg-[#f3f4ee] py-10 md:py-12">
      <Reveal delay={0.08}>
        <div className="grid min-w-0 gap-8 md:gap-12 lg:grid-cols-[1.08fr_0.92fr] lg:items-center">
          <PrintedReceiptArtifact />
          <div>
            <SectionHeader
              eyebrow="Proof standard"
              title="A receipt is the product, not an afterthought."
              copy="Zroky does not treat model output as proof. Policy, execution, and the real system all have to agree before a receipt is signed."
            />
            <Reveal delay={0.1}>
              <div className="mt-6 rounded-[12px] border border-[#cfe0dd] bg-[#eaf1ef] p-4">
                <div className="flex items-start gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[9px] border border-[#cfe0dd] bg-[#fffdfa] text-[#2f5f66]">
                    <ShieldCheck size={17} />
                  </span>
                  <p className="text-sm font-semibold leading-relaxed text-[#2f5f66]">
                    Every hash is independently verifiable - not just visible in your dashboard.
                  </p>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </Reveal>
    </Section>
  );
}

function EnterpriseReadiness() {
  const actionClasses = [
    ['Money movement', 'payouts, credits, reversals'],
    ['Access changes', 'roles, permissions, seats'],
    ['Production changes', 'deploys, config, data jobs'],
    ['Customer contact', 'messages, tickets, notifications'],
  ];

  const readinessRows = [
    {
      icon: LockKeyhole,
      label: 'Identity mapped',
      detail: 'Agent, owner, role, environment, and expiry are attached before execution.',
      signal: 'owner + role',
    },
    {
      icon: ShieldCheck,
      label: 'Policy gates',
      detail: 'High-risk action classes fail closed when approval, runner, or verifier state is missing.',
      signal: 'fail closed',
    },
    {
      icon: DatabaseZap,
      label: 'Source systems',
      detail: 'Outcomes are checked against the systems your business already treats as truth.',
      signal: 'matched',
    },
    {
      icon: Check,
      label: 'Evidence export',
      detail: 'Receipt hashes, policy context, and approval trails stay ready for review.',
      signal: 'signed',
    },
  ];

  return (
    <Section id="trust" className="bg-[#fbfcfa] py-14 md:py-20">
      <div className="grid min-w-0 gap-10 sm:gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <div>
          <SectionHeader
            eyebrow="Enterprise readiness"
            title="Scale agents through policy, not blind trust."
            copy="Zroky fits around your agents, runners, approval owners, and source-of-record systems so high-risk autonomy can move faster without becoming invisible."
          />
          <Reveal delay={0.08}>
            <div className="mt-7 grid gap-2 sm:grid-cols-2">
              {actionClasses.map(([label, value]) => (
                <div key={label} className="rounded-[10px] border border-[#dedacf] bg-[#f7f6f1] px-4 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#2f5f66]">{label}</p>
                  <p className="mt-1 text-sm font-semibold text-[#34362f]">{value}</p>
                </div>
              ))}
            </div>
          </Reveal>
        </div>

        <Reveal delay={0.08}>
          <div className="min-w-0 overflow-hidden rounded-[18px] border border-[#d5d2c7] bg-[#fffdfa] shadow-[0_1px_2px_rgba(28,31,26,0.05),0_34px_70px_-52px_rgba(28,31,26,0.42)] sm:rounded-[20px] sm:shadow-[0_1px_2px_rgba(28,31,26,0.05),0_42px_90px_-54px_rgba(28,31,26,0.48)]">
            <div className="border-b border-[#dedacf] bg-[#f8f7f2] px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">Production readiness board</p>
                  <h3 className="mt-1 text-xl font-semibold text-[#151713]">Controls ready before scale-up</h3>
                </div>
                <span className="inline-flex items-center gap-2 rounded-[9px] border border-[#cfe0dd] bg-[#eaf1ef] px-3 py-1.5 text-[12px] font-semibold text-[#2f5f66]">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#2f5f66]" />
                  live posture
                </span>
              </div>
            </div>

            <div className="px-5 py-5">
              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  ['6', 'control checks'],
                  ['4', 'risk surfaces'],
                  ['0', 'blind writes'],
                ].map(([value, label]) => (
                  <div key={label} className="rounded-[11px] border border-[#e1ddd3] bg-[#f7f6f1] px-4 py-3">
                    <p className="text-2xl font-semibold leading-none text-[#171a15]">{value}</p>
                    <p className="mt-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-[#8a867a]">{label}</p>
                  </div>
                ))}
              </div>

              <div className="mt-5 divide-y divide-[#e4e0d6] border-y border-[#e4e0d6]">
                {readinessRows.map((row, index) => {
                  const Icon = row.icon;
                  return (
                    <motion.div
                      key={row.label}
                      className="grid gap-3 py-4 sm:grid-cols-[2.5rem_1fr_auto] sm:items-center"
                      initial={{ opacity: 0, x: 12 }}
                      whileInView={{ opacity: 1, x: 0 }}
                      viewport={{ once: true, margin: '-80px' }}
                      transition={{ duration: 0.42, ease, delay: 0.12 + index * 0.05 }}
                    >
                      <span className="grid h-10 w-10 place-items-center rounded-[10px] border border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]">
                        <Icon size={17} />
                      </span>
                      <div>
                        <p className="text-sm font-semibold text-[#171a15]">{row.label}</p>
                        <p className="mt-1 max-w-[33rem] text-[13px] leading-relaxed text-[#5b615a]">{row.detail}</p>
                      </div>
                      <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-[#cfe0dd] bg-[#eef6f3] px-2.5 py-1 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[#2f5f66]">
                        <Check size={12} />
                        {row.signal}
                      </span>
                    </motion.div>
                  );
                })}
              </div>

              <div className="mt-5">
                <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#8a867a]">Deployment path</p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {['Agent intent', 'Policy gate', 'Scoped runner', 'System proof', 'Signed receipt'].map((step, index) => (
                    <div key={step} className="flex items-center gap-2">
                      <span className="rounded-full border border-[#dcd8ce] bg-[#f8f7f2] px-3 py-1.5 text-[11px] font-semibold text-[#34362f]">{step}</span>
                      {index < 4 ? <ArrowRight size={13} className="text-[#a29c8f]" /> : null}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </Section>
  );
}

const SNIPPET = `decision = zroky.verified_action(
    agent_id="ops_agent",
    action_type="access.grant",
    parameters={"role": "admin", "target_user": "user_881"},
)

proof = zroky.await_action_proof(decision["action_id"])
assert proof["proof_status"] == "matched"`;

function Quickstart() {
  const [copied, setCopied] = useState(false);
  const flow = [
    ['Before', 'agent tool call', 'A direct mutation reaches the system before governance is visible.'],
    ['Wrap', 'zroky.verified_action()', 'The risky operation enters policy, approval, runner, and verifier control.'],
    ['After', 'signed receipt', 'Teams see what ran, what changed, and how the outcome was proven.'],
  ];
  const results = [
    ['policy', 'held'],
    ['approval', 'approved'],
    ['runner', 'scoped'],
    ['proof', 'matched'],
    ['receipt', 'signed'],
  ];
  const copy = () => {
    void navigator.clipboard?.writeText(SNIPPET);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <Section id="quickstart" className="bg-[#f3f4ee] py-14 md:py-20">
      <div className="grid min-w-0 items-center gap-10 sm:gap-12 lg:grid-cols-[1.18fr_0.82fr]">
        <div className="min-w-0 lg:order-2">
          <SectionHeader
            eyebrow="Implementation"
            title="Wrap the action that can hurt you first."
            copy="Start with one high-risk tool call. Zroky adds policy, approval, scoped execution, source-of-record verification, and receipt state without replacing your agent framework."
          />
          <Reveal delay={0.08}>
            <div className="mt-7 grid gap-2">
              {[
                'No framework rewrite',
                'One protected action first',
                'Expand by policy once proof is working',
              ].map((item) => (
                <div key={item} className="flex items-center gap-3 text-sm font-semibold text-[#34362f]">
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]">
                    <Check size={13} />
                  </span>
                  {item}
                </div>
              ))}
            </div>
          </Reveal>
        </div>

        <Reveal delay={0.08} className="min-w-0 lg:order-1">
          <div className="min-w-0 overflow-hidden rounded-[18px] border border-[#d5d2c7] bg-[#fffdfa] shadow-[0_1px_2px_rgba(28,31,26,0.05),0_34px_70px_-52px_rgba(28,31,26,0.42)] sm:rounded-[20px] sm:shadow-[0_1px_2px_rgba(28,31,26,0.05),0_42px_90px_-54px_rgba(28,31,26,0.48)]">
            <div className="border-b border-[#dedacf] bg-[#f8f7f2] px-4 py-4 sm:px-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">Control wrapper</p>
                  <h3 className="mt-1 text-xl font-semibold text-[#151713]">Keep your agent. Govern the action.</h3>
                </div>
                <span className="rounded-[9px] border border-[#dcd8ce] bg-[#fffdfa] px-3 py-1.5 text-[11px] font-semibold text-[#34362f]">
                  Python SDK
                </span>
              </div>
            </div>

            <div className="px-4 py-4 sm:px-5 sm:py-5">
              <div className="grid gap-2 md:grid-cols-3">
                {flow.map(([label, title, detail], index) => (
                  <div key={label} className="relative rounded-[12px] border border-[#e1ddd3] bg-[#f7f6f1] p-3.5">
                    <p className="font-mono text-[9.5px] font-semibold uppercase tracking-[0.14em] text-[#8a867a]">{label}</p>
                    <p className="mt-1 text-sm font-semibold text-[#171a15]">{title}</p>
                    <p className="mt-2 text-[12px] leading-relaxed text-[#5b615a]">{detail}</p>
                    {index < 2 ? (
                      <span className="absolute -right-4 top-1/2 z-10 hidden h-7 w-7 -translate-y-1/2 place-items-center rounded-full border border-[#d7d4ca] bg-[#fffdfa] text-[#8a867a] md:grid">
                        <ArrowRight size={14} />
                      </span>
                    ) : null}
                  </div>
                ))}
              </div>

              <div className="mt-4 min-w-0 overflow-hidden rounded-[14px] bg-[#252922]">
                <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
                  <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-[#d9ded4]">python</span>
                  <button
                    type="button"
                    onClick={copy}
                    className="inline-flex items-center gap-1.5 rounded-[8px] border border-white/15 bg-white/5 px-2.5 py-1.5 font-mono text-[11px] text-[#f4f6f1] transition hover:bg-white/10"
                  >
                    {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? 'copied' : 'copy'}
                  </button>
                </div>
                <pre className="max-w-full overflow-x-auto p-4 font-mono text-[11.5px] leading-relaxed text-[#eef1ec] sm:p-5 sm:text-[12.5px]">{SNIPPET}</pre>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                {results.map(([label, value]) => (
                  <div key={label} className="rounded-[10px] border border-[#cfe0dd] bg-[#eaf1ef] px-3 py-2">
                    <p className="font-mono text-[9.5px] font-semibold uppercase tracking-[0.12em] text-[#2f5f66]">{label}</p>
                    <p className="mt-1 text-[12px] font-semibold text-[#171a15]">{value}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </Section>
  );
}

function FinalCTA() {
  const rollout = [
    ['1', 'Identify first high-risk action'],
    ['2', 'Connect policy owner'],
    ['3', 'Verify source of record'],
    ['4', 'Ship first signed receipt'],
  ];

  return (
    <section className="w-full bg-[#fbfcfa] px-4 py-20 text-[#171a15] md:py-24">
      <Reveal>
        <div className="mx-auto max-w-6xl rounded-[20px] border border-[#d7d4ca] bg-[#fffdfa] p-5 text-center shadow-[0_34px_78px_-54px_rgba(28,31,26,0.34)] sm:p-8 md:rounded-[24px] md:p-14 md:shadow-[0_40px_90px_-52px_rgba(28,31,26,0.38)]">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">Operationalize autonomy</p>
          <h2 className="mx-auto mt-3 max-w-3xl text-balance text-[1.95rem] font-semibold leading-[1.08] tracking-[-0.025em] text-[#151713] min-[380px]:text-[2.15rem] md:text-[3.4rem] md:leading-[1.05] md:tracking-[-0.03em]">
            Give agents authority only when your business can prove the outcome.
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-[1.02rem] leading-relaxed text-[#5b615a]">
            Start with one protected action. Expand once the proof trail is working.
          </p>
          <div className="mt-8 grid gap-2 text-left sm:grid-cols-2 lg:grid-cols-4">
            {rollout.map(([step, label]) => (
              <div key={step} className="rounded-[12px] border border-[#dedacf] bg-[#f8f7f2] p-4">
                <span className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-[#cfe0dd] bg-[#eaf1ef] font-mono text-[11px] font-semibold text-[#2f5f66]">
                  {step}
                </span>
                <p className="mt-3 text-sm font-semibold leading-snug text-[#171a15]">{label}</p>
              </div>
            ))}
          </div>
          <ButtonRow centered />
        </div>
      </Reveal>
    </section>
  );
}

export default function HomePage() {
  return (
    <div className="w-full bg-[#fbfcfa]">
      <Hero />
      <StakesSection />
      <ArchitectureDiagram />
      <SequenceRiskMoment />
      <ProofStandard />
      <EnterpriseReadiness />
      <Quickstart />
      <FinalCTA />
    </div>
  );
}
