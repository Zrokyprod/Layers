import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  Copy,
  DatabaseZap,
  DollarSign,
  FileDiff,
  GitBranch,
  Github,
  Loader2,
  LockKeyhole,
  PlugZap,
  ReceiptText,
  RefreshCw,
  Send,
  Server,
  ShieldAlert,
  ShieldCheck,
  Slack,
  Webhook,
  type LucideIcon,
} from 'lucide-react';
import type { IconType } from 'react-icons';
import { SiGithub, SiPostgresql, SiShopify, SiStripe, SiZendesk } from 'react-icons/si';
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
    <section id={id} className={`w-full scroll-mt-0 overflow-hidden px-4 py-14 text-[#171a15] sm:py-16 md:py-20 ${className}`}>
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
        <h2 className="mt-3 text-balance text-[1.9rem] font-semibold leading-[1.08] tracking-[-0.025em] text-[#151713] min-[380px]:text-[2.08rem] md:text-[2.65rem] md:leading-[1.06] md:tracking-[-0.026em]">
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
type OutcomeStage = 0 | 1 | 2 | 3;
type BypassStage = 0 | 1 | 2;

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

        <div className="mt-0.5 min-h-[59px] overflow-hidden">
          <motion.div
            aria-hidden={stage < 3}
            initial={false}
            animate={{
              opacity: stage >= 3 ? 1 : 0,
              y: stage >= 3 || reduce ? 0 : 8,
            }}
            transition={{ duration: 0.4, ease }}
            className={stage >= 3 ? '' : 'pointer-events-none'}
          >
            <div className="flex items-center gap-3 rounded-[9px] border border-[#cfe0dd] bg-[#eaf1ef] px-3.5 py-3">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-[8px] bg-[#2f5f66] text-white">
                <ShieldCheck size={14} />
              </span>
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#2f5f66]">Zroky verdict</p>
                <p className="mt-0.5 truncate text-[12.5px] font-semibold text-[#171a15]">Held for approval - privilege + sequence risk</p>
              </div>
            </div>
          </motion.div>
        </div>
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

      <div className="min-h-[126px] overflow-hidden sm:min-h-[132px]">
        <motion.div
          aria-hidden={stage < 4}
          initial={false}
          animate={{
            opacity: stage >= 4 ? 1 : 0,
            y: stage >= 4 || reduce ? 0 : 12,
          }}
          transition={{ duration: 0.4, ease }}
          className={stage >= 4 ? '' : 'pointer-events-none'}
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
      </div>

      <p className="mt-4 text-center text-[11.5px] leading-relaxed text-[#8a867a]">
        The same sequence-risk signal appears in the dashboard today.
      </p>
    </div>
  );
}

function ConnectorWall() {
  const connectors: Array<{
    name: string;
    status: 'Live' | 'Beta' | 'On request';
    description: string;
    icon: IconType | LucideIcon;
    color: string;
  }> = [
    {
      name: 'Stripe',
      status: 'Live',
      description: 'Payouts, refunds, and balance events',
      icon: SiStripe,
      color: '#635bff',
    },
    {
      name: 'PostgreSQL',
      status: 'Live',
      description: 'Read-only proof against internal tables',
      icon: SiPostgresql,
      color: '#4169e1',
    },
    {
      name: 'REST APIs',
      status: 'Live',
      description: 'HTTPS JSON records and business systems',
      icon: Webhook,
      color: '#2f5f66',
    },
    {
      name: 'GitHub',
      status: 'Live',
      description: 'Repos, deploy checks, and workflow state',
      icon: SiGithub,
      color: '#181717',
    },
    {
      name: 'Slack',
      status: 'Live',
      description: 'Approval signals and incident channels',
      icon: Slack,
      color: '#4a154b',
    },
    {
      name: 'Zendesk',
      status: 'Beta',
      description: 'Ticket state and customer support records',
      icon: SiZendesk,
      color: '#03363d',
    },
    {
      name: 'Shopify',
      status: 'Beta',
      description: 'Commerce orders, refunds, and inventory',
      icon: SiShopify,
      color: '#7ab55c',
    },
    {
      name: 'NetSuite',
      status: 'On request',
      description: 'Ledger and ERP reconciliation',
      icon: Server,
      color: '#2f5f66',
    },
  ];

  return (
    <Section id="connectors" className="bg-[#fbfcfa] py-12 md:py-16">
      <SectionHeader
        eyebrow="Systems of record"
        title="Verified against the systems your business already trusts."
        copy="Zroky turns production systems into proof sources after an agent acts. Live connectors are shown plainly; beta and on-request connectors are labelled."
        align="center"
      />

      <Reveal delay={0.08} className="mx-auto mt-9 max-w-6xl">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {connectors.map((connector) => {
            const Icon = connector.icon;
            const live = connector.status === 'Live';
            return (
              <div
                key={connector.name}
                className={`min-w-0 rounded-[14px] border bg-[#fffdfa] p-4 shadow-[0_1px_2px_rgba(28,31,26,0.04)] ${
                  live ? 'border-[#d9d6ca]' : 'border-[#e1d7bd] opacity-90'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <span
                    className={`grid h-10 w-10 shrink-0 place-items-center rounded-[10px] border ${
                      live ? 'border-[#cfe0dd] bg-[#fffdfa]' : 'border-[#dfc899] bg-[#fff8ea]'
                    }`}
                    style={{ color: connector.color }}
                  >
                    <Icon size={18} />
                  </span>
                  <span
                    className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] ${
                      live ? 'border-[#c2e4cf] bg-[#e7f5ec] text-[#256b45]' : 'border-[#dfc899] bg-[#fff8ea] text-[#8a5a16]'
                    }`}
                  >
                    {connector.status}
                  </span>
                </div>
                <h3 className="mt-4 text-[1rem] font-semibold text-[#171a15]">{connector.name}</h3>
                <p className="mt-1.5 text-[13px] leading-relaxed text-[#5b615a]">{connector.description}</p>
              </div>
            );
          })}
        </div>
        <p className="mt-5 text-center text-[12.5px] leading-relaxed text-[#777266]">
          Proof connectors run with scoped read access. Agent-held credentials are not treated as source-of-record proof.
        </p>
      </Reveal>
    </Section>
  );
}

function AgentFleetBoard() {
  const rows = [
    {
      name: 'Refund agent',
      detail: 'approval > $500 / deny > $5,000',
      state: 'managed',
      tone: 'ok' as const,
    },
    {
      name: 'Release agent',
      detail: 'production deploys hold for approval',
      state: 'managed',
      tone: 'ok' as const,
    },
    {
      name: 'legacy-export-agent',
      detail: 'observed in telemetry / not yet managed',
      state: 'unmanaged',
      tone: 'warn' as const,
    },
  ];

  const reduce = useReducedMotion();

  return (
    <div className="mx-auto w-full max-w-[640px] overflow-hidden rounded-[18px] border border-[#d5d2c7] bg-[#fffdfa] shadow-[0_1px_2px_rgba(28,31,26,0.05),0_38px_82px_-56px_rgba(28,31,26,0.48)]">
      <div className="border-b border-[#dedacf] bg-[#f8f7f2] px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">Agent fleet</p>
            <h3 className="mt-1 text-xl font-semibold text-[#151713]">Every agent, managed. Every action, gated.</h3>
          </div>
          <span className="inline-flex items-center gap-2 rounded-[9px] border border-[#cfe0dd] bg-[#eaf1ef] px-3 py-1.5 text-[12px] font-semibold text-[#2f5f66]">
            <Bot size={14} />
            fleet view
          </span>
        </div>
      </div>

      <div className="p-4 sm:p-5">
        <div className="grid gap-2.5">
          {rows.map((row, index) => {
            const unmanaged = row.tone === 'warn';
            return (
              <motion.div
                key={row.name}
                className={`group grid min-w-0 gap-3 rounded-[12px] border px-3.5 py-3 transition sm:grid-cols-[1fr_auto] sm:items-center ${
                  unmanaged
                    ? 'border-[#dfab3f] bg-[#fff2cc]'
                    : 'border-[#e1ddd3] bg-[#fbfaf5]'
                }`}
                initial={reduce ? false : { opacity: 0, y: 10 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-80px' }}
                animate={
                  unmanaged && !reduce
                    ? {
                        boxShadow: [
                          '0 0 0 0 rgba(223,171,63,0)',
                          '0 0 0 6px rgba(223,171,63,0.12)',
                          '0 0 0 0 rgba(223,171,63,0)',
                        ],
                      }
                    : undefined
                }
                transition={{ duration: 0.42, ease, delay: 0.08 + index * 0.05, repeat: unmanaged && !reduce ? Infinity : 0, repeatDelay: 2.8 }}
              >
                <div className="flex min-w-0 items-start gap-3">
                  <span
                    className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-[9px] border ${
                      unmanaged ? 'border-[#dfab3f] bg-[#fff8ea] text-[#8a5a16]' : 'border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]'
                    }`}
                  >
                    {unmanaged ? <ShieldAlert size={16} /> : <Bot size={16} />}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-[#171a15]">{row.name}</p>
                    <p className="mt-0.5 truncate font-mono text-[11px] text-[#777266]">{row.detail}</p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span
                    className={`rounded-full border px-3 py-1 text-[11px] font-semibold ${
                      unmanaged ? 'border-[#dfab3f] bg-[#fffdfa] text-[#8a5a16]' : 'border-[#c2e4cf] bg-[#e7f5ec] text-[#256b45]'
                    }`}
                  >
                    {row.state}
                  </span>
                  {unmanaged ? (
                    <span className="hidden rounded-[8px] border border-[#d9d6ca] bg-[#fffdfa] px-3 py-1.5 text-[11px] font-semibold text-[#34362f] opacity-0 transition group-hover:opacity-100 sm:inline-flex">
                      Promote to managed
                    </span>
                  ) : null}
                </div>
              </motion.div>
            );
          })}
        </div>

        <div className="mt-5 grid gap-2 sm:grid-cols-3">
          {[
            ['18', 'observed agents'],
            ['94%', 'managed coverage'],
            ['1', 'unmanaged identity'],
          ].map(([value, label]) => (
            <div key={label} className="rounded-[11px] border border-[#e1ddd3] bg-[#f7f6f1] px-4 py-3">
              <p className="text-2xl font-semibold leading-none text-[#171a15]">{value}</p>
              <p className="mt-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-[#8a867a]">{label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function AgentFleetSection() {
  return (
    <Section id="agents" className="bg-[#f3f4ee]">
      <div className="grid min-w-0 gap-9 sm:gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <SectionHeader
          eyebrow="Agent fleet"
          title="Manage known agents and catch the ones acting outside the line."
          copy="The landing now shows the fleet concept directly: managed profiles, policy coverage, and telemetry-only identities that need promotion before they can be trusted with high-risk work."
        />
        <Reveal delay={0.08}>
          <AgentFleetBoard />
        </Reveal>
      </div>
    </Section>
  );
}

function OutcomeDiffCard() {
  const reduce = useReducedMotion();
  const [stage, setStage] = useState<OutcomeStage>(reduce ? 3 : 0);

  useEffect(() => {
    if (reduce) return undefined;
    let cancelled = false;
    async function loop() {
      while (!cancelled) {
        setStage(0);
        await wait(700);
        if (cancelled) return;
        setStage(1);
        await wait(1200);
        if (cancelled) return;
        setStage(2);
        await wait(950);
        if (cancelled) return;
        setStage(3);
        await wait(3400);
      }
    }
    void loop();
    return () => {
      cancelled = true;
    };
  }, [reduce]);

  const rows = [
    { field: 'refund_id', claimed: 'rf_8841', actual: 'rf_8841', verdict: 'matched' },
    { field: 'currency', claimed: 'USD', actual: 'USD', verdict: 'matched' },
    { field: 'amount', claimed: '$500', actual: '$5,000', verdict: stage >= 3 ? 'mismatched' : 'checking' },
  ];

  return (
    <div className="mx-auto w-full max-w-[620px] overflow-hidden rounded-[18px] border border-[#d5d2c7] bg-[#fffdfa] shadow-[0_1px_2px_rgba(28,31,26,0.05),0_38px_82px_-56px_rgba(28,31,26,0.48)]">
      <div className="border-b border-[#dedacf] bg-[#f8f7f2] px-4 py-4 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">Outcomes / field diff</p>
            <h3 className="mt-1 text-xl font-semibold text-[#151713]">Agent claim vs source-of-record reality</h3>
          </div>
          <span
            className={`inline-flex items-center gap-2 rounded-[9px] border px-3 py-1.5 text-[12px] font-semibold ${
              stage >= 3 ? 'border-[#f0c6bf] bg-[#fbebe9] text-[#b3402f]' : 'border-[#dfc899] bg-[#fff8ea] text-[#8a5a16]'
            }`}
          >
            {stage >= 3 ? <AlertTriangle size={14} /> : <Loader2 size={14} className="animate-spin" />}
            {stage >= 3 ? 'mismatched' : 'checking'}
          </span>
        </div>
      </div>

      <div className="p-4 sm:p-5">
        <div className="rounded-[12px] border border-[#e1ddd3] bg-[#f7f6f1] p-3.5">
          <div className="grid grid-cols-[1fr_auto] gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#8a867a]">Action claim</p>
              <p className="mt-1 font-mono text-[12px] text-[#34362f]">refund.payment / customer acct_1028</p>
            </div>
            <span className="h-fit rounded-full border border-[#dcd8ce] bg-[#fffdfa] px-3 py-1 text-[11px] font-semibold text-[#34362f]">
              200 OK
            </span>
          </div>
        </div>

        <div className="mt-4 overflow-hidden rounded-[12px] border border-[#dedacf]">
          <div className="grid grid-cols-[0.8fr_1fr_1fr_0.85fr] bg-[#f4f2eb] px-3 py-2.5 font-mono text-[9.5px] font-semibold uppercase tracking-[0.12em] text-[#8a867a]">
            <span>Field</span>
            <span>Claimed</span>
            <span>Actual</span>
            <span className="text-right">Verdict</span>
          </div>
          <div className="divide-y divide-[#e4e0d6] bg-[#fffdfa]">
            {rows.map((row, index) => {
              const mismatch = row.verdict === 'mismatched';
              const pending = row.verdict === 'checking';
              return (
                <motion.div
                  key={row.field}
                  className={`grid grid-cols-[0.8fr_1fr_1fr_0.85fr] gap-2 px-3 py-3 text-[12px] font-semibold ${
                    mismatch ? 'bg-[#fbebe9] text-[#4e2019]' : 'text-[#34362f]'
                  }`}
                  initial={reduce ? false : { opacity: 0, y: 8 }}
                  animate={{ opacity: stage >= index + 1 ? 1 : 0.38, y: stage >= index + 1 ? 0 : 8 }}
                  transition={{ duration: 0.3, ease }}
                >
                  <span className="min-w-0 truncate">{row.field}</span>
                  <span className="min-w-0 truncate font-mono">{row.claimed}</span>
                  <span className="min-w-0 truncate font-mono">{stage >= index + 1 ? row.actual : '...'}</span>
                  <span className={`text-right font-mono ${mismatch ? 'text-[#b3402f]' : pending ? 'text-[#8a5a16]' : 'text-[#256b45]'}`}>
                    {row.verdict}
                  </span>
                </motion.div>
              );
            })}
          </div>
        </div>

        <div
          className={`mt-4 rounded-[12px] border p-3.5 ${
            stage >= 3 ? 'border-[#f0c6bf] bg-[#fbebe9]' : 'border-[#dfc899] bg-[#fff8ea]'
          }`}
        >
          <div className="flex items-start gap-3">
            <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-[9px] text-white ${stage >= 3 ? 'bg-[#b3402f]' : 'bg-[#8a5a16]'}`}>
              {stage >= 3 ? <FileDiff size={16} /> : <Loader2 size={16} className="animate-spin" />}
            </span>
            <div>
              <p className={`text-[11px] font-semibold uppercase tracking-[0.1em] ${stage >= 3 ? 'text-[#b3402f]' : 'text-[#8a5a16]'}`}>
                {stage >= 3 ? 'Zroky verdict' : 'Source comparison'}
              </p>
              <p className="mt-1 text-sm font-semibold leading-relaxed text-[#171a15]">
                {stage >= 3
                  ? 'The tool succeeded, but the system of record proves the outcome is different.'
                  : 'Waiting for the system of record before a receipt can be trusted.'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ClaimVsRealitySection() {
  return (
    <Section id="claim-vs-reality" className="bg-[#fbfcfa]">
      <div className="grid min-w-0 gap-9 sm:gap-12 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
        <Reveal delay={0.08} className="lg:order-1">
          <OutcomeDiffCard />
        </Reveal>
        <div className="lg:order-2">
          <SectionHeader
            eyebrow="Claim vs reality"
            title="Do not trust a successful call until the real record agrees."
            copy="The Outcomes view compares exact fields from the agent's claim with the source-of-record record. A mismatch becomes visible proof, not a buried log line."
          />
        </div>
      </div>
    </Section>
  );
}

function BypassDetectionCard() {
  const reduce = useReducedMotion();
  const [stage, setStage] = useState<BypassStage>(reduce ? 2 : 0);

  useEffect(() => {
    if (reduce) return undefined;
    let cancelled = false;
    async function loop() {
      while (!cancelled) {
        setStage(0);
        await wait(900);
        if (cancelled) return;
        setStage(1);
        await wait(1100);
        if (cancelled) return;
        setStage(2);
        await wait(3600);
      }
    }
    void loop();
    return () => {
      cancelled = true;
    };
  }, [reduce]);

  const timeline = [
    ['Telemetry', 'legacy-export-agent touched customer export'],
    ['Receipt lookup', 'No Zroky receipt found for mutation window'],
    ['Classification', 'Unreceipted mutation / bypass risk'],
  ];

  return (
    <div className="mx-auto w-full max-w-[590px] overflow-hidden rounded-[18px] border border-[#d5d2c7] bg-[#fffdfa] shadow-[0_1px_2px_rgba(28,31,26,0.05),0_38px_82px_-56px_rgba(28,31,26,0.48)]">
      <div className="border-b border-[#dedacf] bg-[#f8f7f2] px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">Bypass detection</p>
            <h3 className="mt-1 text-xl font-semibold text-[#151713]">What if the agent skipped Zroky?</h3>
          </div>
          <span className="inline-flex items-center gap-2 rounded-[9px] border border-[#dfc899] bg-[#fff8ea] px-3 py-1.5 text-[12px] font-semibold text-[#8a5a16]">
            <ShieldAlert size={14} />
            watchlist
          </span>
        </div>
      </div>

      <div className="p-4 sm:p-5">
        <div className="rounded-[14px] border border-[#dfc899] bg-[#fff8ea] p-4">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-[10px] bg-[#8a5a16] text-white">
              <PlugZap size={17} />
            </span>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#8a5a16]">Unreceipted mutation</p>
              <p className="mt-1 text-sm font-semibold leading-relaxed text-[#171a15]">customer_export.created outside protected-action path</p>
              <p className="mt-1 font-mono text-[11px] text-[#777266]">source: telemetry / actor: legacy-export-agent</p>
            </div>
          </div>
        </div>

        <div className="mt-4 grid gap-2.5">
          {timeline.map(([label, value], index) => {
            const active = stage >= index;
            const final = index === 2 && active;
            return (
              <motion.div
                key={label}
                className={`grid gap-2 rounded-[11px] border px-3.5 py-3 sm:grid-cols-[8rem_1fr_auto] sm:items-center ${
                  final ? 'border-[#f0c6bf] bg-[#fbebe9]' : 'border-[#e1ddd3] bg-[#fbfaf5]'
                }`}
                initial={false}
                animate={{ opacity: active ? 1 : 0.42 }}
                transition={{ duration: 0.25, ease }}
              >
                <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8a867a]">{label}</span>
                <span className="min-w-0 text-[13px] font-semibold text-[#34362f]">{value}</span>
                <span
                  className={`w-fit rounded-full border px-2.5 py-1 text-[10.5px] font-semibold ${
                    final ? 'border-[#f0c6bf] bg-[#fffdfa] text-[#b3402f]' : 'border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]'
                  }`}
                >
                  {active ? (final ? 'bypass' : 'seen') : 'waiting'}
                </span>
              </motion.div>
            );
          })}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {['Observed mutation', 'No receipt', 'Owner alert', 'Promote or block'].map((step, index) => (
            <div key={step} className="flex items-center gap-2">
              <span className="rounded-full border border-[#dcd8ce] bg-[#f8f7f2] px-3 py-1.5 text-[11px] font-semibold text-[#34362f]">{step}</span>
              {index < 3 ? <ArrowRight size={13} className="text-[#a29c8f]" /> : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function BypassDetectionSection() {
  return (
    <Section id="bypass-detection" className="bg-[#f3f4ee]">
      <div className="grid min-w-0 gap-9 sm:gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <SectionHeader
          eyebrow="Bypass detection"
          title="If an agent mutates state outside Zroky, the gap should be visible."
          copy="Zroky should not pretend every action is protected. The landing now handles the skeptical buyer question directly: unreceipted mutations become classified telemetry, not invisible exceptions."
        />
        <Reveal delay={0.08}>
          <BypassDetectionCard />
        </Reveal>
      </div>
    </Section>
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
              <p className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#777266]">Evidence seal</p>
              <p className="mt-1 break-words text-[11px] font-semibold leading-relaxed text-[#171a15]">Evidence hash sealed with policy, runner, and verifier context</p>
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
            <p className="text-[10px] uppercase tracking-[0.18em] text-[#8a867a]">Evidence sealed</p>
            <p className="mt-1 text-[10.5px] uppercase tracking-[0.16em] text-[#2f5f66]">Tamper-evident</p>
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
                    Every receipt binds the policy decision, runner event, source comparison, and evidence hash.
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

const FAQ_ITEMS = [
  {
    question: 'What happens when a policy check fails?',
    answer: 'Zroky fails closed. If policy, approval, runner, verifier, or receipt state is missing for a high-risk action, the action is held or blocked instead of silently executing.',
  },
  {
    question: 'Can agents bypass Zroky?',
    answer: 'Agents can still mutate systems through paths you have not protected. Zroky treats that as a product surface: telemetry can classify unreceipted mutations so owners can promote the agent to managed coverage or block the path.',
  },
  {
    question: 'What counts as proof?',
    answer: 'A successful tool response is not proof. Zroky compares the claimed outcome with a source-of-record connector and keeps the policy, runner, verifier, and receipt context together.',
  },
  {
    question: 'Do we need to rewrite our agent framework?',
    answer: 'No. Start by wrapping one high-risk operation with zroky.protect(), attach policy and a source-of-record check, then expand coverage by action class.',
  },
  {
    question: 'Which systems can Zroky verify against?',
    answer: 'Live connector paths cover Stripe, PostgreSQL, generic REST APIs, GitHub, and Slack. Zendesk, Shopify, and NetSuite-style ERP flows are labelled beta or on request until they are verified end to end.',
  },
  {
    question: 'How are receipts different from logs?',
    answer: 'Logs show what an app said happened. A Zroky receipt packages the decision, approval state, scoped runner event, source comparison, and evidence hash for later review.',
  },
];

function TrustAndFAQ() {
  const trustFacts = [
    {
      icon: LockKeyhole,
      title: 'Fail closed',
      body: 'Policy missing means the action is held or blocked.',
    },
    {
      icon: Bot,
      title: 'Unlimited approvers',
      body: 'Safety reviewers should not become a pricing bottleneck.',
    },
    {
      icon: ReceiptText,
      title: 'Tamper-evident receipts',
      body: 'Receipts bind policy, runner, source comparison, and evidence hash.',
    },
  ];

  const openLinks = [
    { icon: Github, label: 'GitHub', href: 'https://github.com/zroky-ai' },
    { icon: GitBranch, label: 'Changelog', href: '/changelog' },
    { icon: RefreshCw, label: 'Docs', href: '/docs' },
  ];

  const faqSchema = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: FAQ_ITEMS.map((item) => ({
      '@type': 'Question',
      name: item.question,
      acceptedAnswer: {
        '@type': 'Answer',
        text: item.answer,
      },
    })),
  };

  return (
    <Section id="trust" className="bg-[#fbfcfa]">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }} />

      <SectionHeader
        eyebrow="Trust posture"
        title="Simple rules for production autonomy."
        copy="No fake customer counts. No unlabeled beta surface. Just the controls a buyer needs to see before letting agents touch money, access, customer state, or production."
        align="center"
      />

      <Reveal delay={0.08} className="mx-auto mt-9 max-w-6xl">
        <div className="grid gap-3 md:grid-cols-3">
          {trustFacts.map((fact) => {
            const Icon = fact.icon;
            return (
              <div key={fact.title} className="rounded-[14px] border border-[#d9d6ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.04)]">
                <span className="grid h-10 w-10 place-items-center rounded-[10px] border border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]">
                  <Icon size={18} />
                </span>
                <h3 className="mt-4 text-[1.05rem] font-semibold text-[#171a15]">{fact.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-[#5b615a]">{fact.body}</p>
              </div>
            );
          })}
        </div>
      </Reveal>

      <Reveal delay={0.12} className="mx-auto mt-6 max-w-6xl">
        <div className="flex flex-col gap-4 rounded-[16px] border border-[#d9d6ca] bg-[#f8f7f2] p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
          <div>
            <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">Built in the open</p>
            <p className="mt-1 text-sm font-semibold text-[#34362f]">Follow product progress through code, release notes, and implementation docs.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {openLinks.map((link) => {
              const Icon = link.icon;
              return (
                <a
                  key={link.label}
                  href={link.href}
                  className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-[#d4d0c4] bg-[#fffdfa] px-3.5 text-sm font-semibold text-[#34362f] transition hover:border-[#c4bfb2]"
                >
                  <Icon size={15} />
                  {link.label}
                </a>
              );
            })}
          </div>
        </div>
      </Reveal>

      <Reveal delay={0.14} className="mx-auto mt-12 max-w-5xl">
        <div id="faq" className="scroll-mt-6">
          <div className="text-center">
            <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">FAQ</p>
            <h3 className="mt-3 text-balance text-[1.85rem] font-semibold leading-[1.08] tracking-[-0.025em] text-[#151713] md:text-[2.45rem]">
              Questions buyers ask before agents get authority.
            </h3>
          </div>

          <div className="mt-7 divide-y divide-[#e4e0d6] overflow-hidden rounded-[16px] border border-[#d9d6ca] bg-[#fffdfa]">
            {FAQ_ITEMS.map((item) => (
              <details key={item.question} className="group px-4 py-4 open:bg-[#fbfaf5] sm:px-5">
                <summary className="flex cursor-pointer list-none items-start justify-between gap-4 text-left text-sm font-semibold text-[#171a15]">
                  <span>{item.question}</span>
                  <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border border-[#d9d6ca] bg-[#f8f7f2] text-[#2f5f66] transition group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="mt-3 max-w-3xl text-sm leading-relaxed text-[#5b615a]">{item.answer}</p>
              </details>
            ))}
          </div>
        </div>
      </Reveal>
    </Section>
  );
}

const SNIPPET = `receipt = zroky.protect(
    action="customer.access.grant",
    params={"role": "admin", "target_user": "user_881"},
    agent_id="ops_agent",
    wait_for_receipt=True,
)

assert receipt["proof_status"] == "matched"`;

function Quickstart() {
  const [copied, setCopied] = useState(false);
  const flow = [
    ['Before', 'agent tool call', 'A direct mutation reaches the system before governance is visible.'],
    ['Wrap', 'zroky.protect()', 'The risky operation enters policy, approval, runner, and verifier control.'],
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
      <ConnectorWall />
      <StakesSection />
      <ArchitectureDiagram />
      <AgentFleetSection />
      <SequenceRiskMoment />
      <ProofStandard />
      <ClaimVsRealitySection />
      <BypassDetectionSection />
      <Quickstart />
      <TrustAndFAQ />
      <FinalCTA />
    </div>
  );
}
