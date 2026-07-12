import { motion, useReducedMotion } from 'framer-motion';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  Cloud,
  Copy,
  DatabaseZap,
  GitBranch,
  Loader2,
  LockKeyhole,
  ReceiptText,
  ShieldAlert,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react';
import type { IconType } from 'react-icons';
import {
  SiCrewai,
  SiFresh,
  SiHubspot,
  SiIntercom,
  SiJira,
  SiLangchain,
  SiLinear,
  SiPostgresql,
  SiQuickbooks,
  SiRazorpay,
  SiShopify,
  SiStripe,
  SiZendesk,
  SiZoho,
} from 'react-icons/si';
import Hero from '../components/hero/Hero';
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
    <section id={id} className={`section-lines w-full scroll-mt-0 overflow-hidden px-4 py-14 text-[#171a15] sm:py-16 md:py-20 ${className}`}>
      <div className="relative z-10 mx-auto min-w-0 max-w-[1260px]">{children}</div>
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

type OutcomeStage = 0 | 1 | 2 | 3;

function wait(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function ControlFlowSection() {
  const reduce = Boolean(useReducedMotion());
  const [activeStep, setActiveStep] = useState(0);
  const steps = [
    {
      icon: Bot,
      label: 'Protected action',
      title: 'refund.create',
      meta: 'contract · finance.refund.v4',
    },
    {
      icon: ShieldCheck,
      label: 'Policy decision',
      title: 'ALLOW · HOLD · DENY',
      meta: 'evaluated before execution',
    },
    {
      icon: LockKeyhole,
      label: 'Controlled execution',
      title: 'MCP upstream or runner',
      meta: 'execution state recorded',
    },
    {
      icon: DatabaseZap,
      label: 'Outcome verification',
      title: 'System of record',
      meta: 'matched · mismatched · pending',
    },
    {
      icon: ReceiptText,
      label: 'Signed evidence',
      title: 'Ed25519 receipt',
      meta: 'audit trail preserved',
    },
  ];
  const activeStates = [
    'INTENT CAPTURED',
    'POLICY · ALLOW',
    'EXECUTION RECORDED',
    'SOR · MATCHED',
    'RECEIPT SIGNED',
  ];
  const visibleStep = reduce ? steps.length - 1 : activeStep;
  const progress = (visibleStep / (steps.length - 1)) * 100;

  useEffect(() => {
    if (reduce) return undefined;
    const id = window.setInterval(() => {
      setActiveStep((current) => (current + 1) % steps.length);
    }, 1700);
    return () => window.clearInterval(id);
  }, [reduce, steps.length]);

  const stageState = (index: number) => {
    if (visibleStep === index) return 'active';
    if (visibleStep > index) return 'complete';
    return 'pending';
  };

  return (
    <Section id="control-flow" className="bg-[#fbfaf6] py-16 md:py-20">
      <SectionHeader
        eyebrow="Control flow"
        title="From protected action to verified outcome."
        copy="Zroky binds each protected action to a versioned contract, applies policy before execution, verifies the result in the system of record, and records the evidence in a signed receipt."
        align="center"
      />

      <Reveal delay={0.08} className="mx-auto mt-10 max-w-[1180px]">
        <div className="relative overflow-hidden rounded-[6px] border border-[#d8d4c9] bg-[#fffefa]/92 shadow-[0_34px_90px_-70px_rgba(23,25,22,0.62)] backdrop-blur">
          <div className="flex min-h-12 flex-col gap-2 border-b border-[#ded9cf] px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <div className="flex min-w-0 items-center gap-3">
              <span className="relative flex h-2.5 w-2.5 shrink-0 items-center justify-center">
                {!reduce ? <span className="absolute h-2.5 w-2.5 rounded-full bg-[#3a747c]/20 motion-safe:animate-ping" /> : null}
                <span className="relative h-1.5 w-1.5 rounded-full bg-[#3a747c]" />
              </span>
              <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">Control path</span>
              <span className="h-4 w-px bg-[#d8d4c9]" />
              <span className="min-w-0 truncate font-mono text-[10.5px] text-[#777266]">finance.refund.v4</span>
            </div>
            <motion.span
              key={activeStates[visibleStep]}
              aria-live="polite"
              className="font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-[#2f5f66]"
              initial={reduce ? false : { opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
            >
              {activeStates[visibleStep]}
            </motion.span>
          </div>

          <div className="relative hidden xl:block">
            <div aria-hidden className="absolute left-[10%] right-[10%] top-[66px] h-px bg-[#d8d4c9]" />
            <motion.div
              aria-hidden
              className="absolute left-[10%] top-[66px] h-px bg-[#3a747c]"
              initial={false}
              animate={{ width: `${progress * 0.8}%` }}
              transition={{ duration: 0.55, ease }}
            />

            <ol aria-label="Zroky protected action control flow" className="grid grid-cols-5">
              {steps.map((step, index) => {
                const Icon = step.icon;
                const state = stageState(index);
                const active = state === 'active';
                const complete = state === 'complete';
                return (
                  <li key={step.label} className={`relative min-w-0 px-5 pb-7 pt-7 ${index > 0 ? 'border-l border-[#e6e2d8]/80' : ''}`}>
                    <div className="flex items-center justify-between gap-3">
                      <motion.span
                        className={`relative z-10 grid h-11 w-11 shrink-0 place-items-center rounded-[5px] border transition-colors duration-300 ${
                          active
                            ? 'border-[#7ca5aa] bg-[#2f5f66] text-white shadow-[0_10px_24px_-14px_rgba(47,95,102,0.8)]'
                            : complete
                              ? 'border-[#bdd2cf] bg-[#eaf1ef] text-[#2f5f66]'
                              : 'border-[#d9d5ca] bg-[#fbfaf6] text-[#969084]'
                        }`}
                        animate={active && !reduce ? { y: [0, -2, 0] } : { y: 0 }}
                        transition={{ duration: 1.7, repeat: active && !reduce ? Infinity : 0, ease: 'easeInOut' }}
                      >
                        {complete ? <Check size={17} strokeWidth={2.2} /> : <Icon size={18} strokeWidth={1.8} />}
                      </motion.span>
                      <span className="font-mono text-[10px] font-semibold text-[#9b9588]">0{index + 1}</span>
                    </div>

                    <div className="mt-7 min-w-0">
                      <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">{step.label}</p>
                      <h3 className="mt-2 min-h-[2.75rem] [overflow-wrap:anywhere] text-[0.96rem] font-semibold leading-[1.38] text-[#171a15]">{step.title}</h3>
                      <p className="mt-3 [overflow-wrap:anywhere] font-mono text-[10.5px] leading-[1.55] text-[#777266]">{step.meta}</p>
                    </div>

                    {index === 1 ? (
                      <div className={`mt-5 border-l-2 pl-3 transition-colors duration-300 ${active ? 'border-[#3a747c]' : 'border-[#d8d4c9]'}`}>
                        <p className="font-mono text-[9px] font-semibold uppercase tracking-[0.13em] text-[#9a9488]">Conditional</p>
                        <p className="mt-1 text-[0.78rem] font-medium text-[#51564f]">HOLD → human approval</p>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          </div>

          <div className="relative px-4 py-1 xl:hidden">
            <div aria-hidden className="absolute bottom-8 left-[38px] top-8 w-px bg-[#d8d4c9]" />
            <motion.div
              aria-hidden
              className="absolute left-[38px] top-8 w-px bg-[#3a747c]"
              initial={false}
              animate={{ height: `calc((100% - 4rem) * ${progress / 100})` }}
              transition={{ duration: 0.55, ease }}
            />
            <ol aria-label="Zroky protected action control flow" className="relative">
              {steps.map((step, index) => {
                const Icon = step.icon;
                const state = stageState(index);
                const active = state === 'active';
                const complete = state === 'complete';
                return (
                  <li key={step.label} className={`grid grid-cols-[2.9rem_1fr] gap-3 py-5 ${index < steps.length - 1 ? 'border-b border-[#e6e2d8]/80' : ''}`}>
                    <span
                      className={`relative z-10 grid h-11 w-11 place-items-center rounded-[5px] border transition-colors duration-300 ${
                        active
                          ? 'border-[#7ca5aa] bg-[#2f5f66] text-white shadow-[0_10px_24px_-14px_rgba(47,95,102,0.8)]'
                          : complete
                            ? 'border-[#bdd2cf] bg-[#eaf1ef] text-[#2f5f66]'
                            : 'border-[#d9d5ca] bg-[#fbfaf6] text-[#969084]'
                      }`}
                    >
                      {complete ? <Check size={17} strokeWidth={2.2} /> : <Icon size={18} strokeWidth={1.8} />}
                    </span>
                    <div className="min-w-0 pt-0.5">
                      <div className="flex items-center justify-between gap-3">
                        <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.13em] text-[#2f5f66]">{step.label}</p>
                        <span className="font-mono text-[9.5px] font-semibold text-[#9b9588]">0{index + 1}</span>
                      </div>
                      <h3 className="mt-1.5 [overflow-wrap:anywhere] text-[0.92rem] font-semibold leading-snug text-[#171a15]">{step.title}</h3>
                      <p className="mt-1.5 [overflow-wrap:anywhere] font-mono text-[10.5px] leading-relaxed text-[#777266]">{step.meta}</p>
                      {index === 1 ? (
                        <div className={`mt-3 border-l-2 pl-3 transition-colors duration-300 ${active ? 'border-[#3a747c]' : 'border-[#d8d4c9]'}`}>
                          <p className="font-mono text-[9px] font-semibold uppercase tracking-[0.13em] text-[#9a9488]">Conditional</p>
                          <p className="mt-1 text-xs font-medium text-[#51564f]">HOLD → human approval</p>
                        </div>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>

          <div className="flex flex-col gap-1.5 border-t border-[#ded9cf] bg-[#f8f7f2]/72 px-4 py-3 font-mono text-[9.5px] text-[#777266] sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <span>Decision is durable before execution.</span>
            <span>Verification and receipt run after execution.</span>
          </div>
        </div>
      </Reveal>
    </Section>
  );
}

function ConnectorWall() {
  type LogoWallItem = {
    name: string;
    icon?: IconType | LucideIcon;
    mark?: string;
    color: string;
  };
  const connectors: LogoWallItem[] = [
    { name: 'PostgreSQL', icon: SiPostgresql, color: '#4169e1' },
    { name: 'HubSpot', icon: SiHubspot, color: '#ff5c35' },
    { name: 'Salesforce', icon: Cloud, color: '#1798c1' },
    { name: 'Zendesk', icon: SiZendesk, color: '#03363d' },
    { name: 'Intercom', icon: SiIntercom, color: '#0a7cff' },
    { name: 'Freshdesk', icon: SiFresh, color: '#14a46f' },
    { name: 'Jira', icon: SiJira, color: '#0052cc' },
    { name: 'Linear', icon: SiLinear, color: '#5e6ad2' },
    { name: 'Stripe', icon: SiStripe, color: '#635bff' },
    { name: 'Razorpay', icon: SiRazorpay, color: '#0b72e7' },
    { name: 'Shopify', icon: SiShopify, color: '#7ab55c' },
    { name: 'NetSuite', mark: 'NS', color: '#315b62' },
    { name: 'QuickBooks', icon: SiQuickbooks, color: '#2ca01c' },
    { name: 'Zoho', icon: SiZoho, color: '#d9232e' },
  ];
  const frameworks: LogoWallItem[] = [
    { name: 'OpenAI Agents SDK', icon: Bot, color: '#171a15' },
    { name: 'LangGraph', icon: SiLangchain, color: '#1c7c54' },
    { name: 'CrewAI', icon: SiCrewai, color: '#171a15' },
    { name: 'AutoGen', icon: GitBranch, color: '#2f5f66' },
  ];
  const tileBackground = {
    backgroundImage:
      'repeating-linear-gradient(-45deg, rgba(32,35,31,0.026) 0, rgba(32,35,31,0.026) 1px, transparent 1px, transparent 7px)',
  };
  const LogoTile = ({ item, framework = false }: { item: LogoWallItem; framework?: boolean }) => {
    const Icon = item.icon;
    return (
      <div
        className="group relative -ml-px -mt-px flex min-h-[80px] items-center justify-center border border-[#ded9cf] bg-[#fffefa]/78 px-4 transition duration-200 hover:bg-[#fffdfa]"
        style={tileBackground}
        title={item.name}
        aria-label={item.name}
      >
        <div className="flex max-w-full items-center gap-2.5 text-[#60645d] opacity-[0.82] grayscale transition duration-200 group-hover:text-[#20241e] group-hover:opacity-100">
          {Icon ? (
            <Icon size={framework ? 19 : 20} className="shrink-0" style={{ color: 'currentColor' }} />
          ) : (
            <span className="shrink-0 font-mono text-[13px] font-semibold tracking-[0.08em] text-current">
              {item.mark}
            </span>
          )}
          <span className="truncate text-[0.88rem] font-semibold leading-none tracking-normal text-current">
            {item.name}
          </span>
        </div>
      </div>
    );
  };

  return (
    <Section id="connectors" className="bg-[#fbfcfa] py-14 md:py-20">
      <SectionHeader
        eyebrow="Connectors + agents"
        title="Connect every agent to governed proof."
        copy="Zroky wraps agent frameworks and verifies outcomes against the systems they touch, so enterprises can scale autonomous work without losing policy, approval, or evidence control."
        align="center"
      />

      <Reveal delay={0.08} className="mx-auto mt-10 max-w-6xl">
        <div className="relative overflow-hidden border border-[#ded9cf] bg-[#fffefa]/72 shadow-[0_28px_80px_-64px_rgba(23,25,22,0.52)] backdrop-blur">
          <span className="absolute -left-1.5 -top-1.5 h-3 w-3 border-l border-t border-[#cfc9bd]" />
          <span className="absolute -right-1.5 -top-1.5 h-3 w-3 border-r border-t border-[#cfc9bd]" />
          <span className="absolute -bottom-1.5 -left-1.5 h-3 w-3 border-b border-l border-[#cfc9bd]" />
          <span className="absolute -bottom-1.5 -right-1.5 h-3 w-3 border-b border-r border-[#cfc9bd]" />

          <div className="relative z-10">
            <div className="flex items-center justify-between border-b border-[#ded9cf] px-4 py-3 sm:px-5">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">Connectors</span>
              <span className="hidden font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#8a867a] sm:inline">Systems of record</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7">
              {connectors.map((item) => (
                <LogoTile key={item.name} item={item} />
              ))}
            </div>

            <div className="flex items-center justify-between border-y border-[#ded9cf] px-4 py-3 sm:px-5">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">Agent frameworks</span>
              <span className="hidden font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#8a867a] sm:inline">Existing execution path</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
              {frameworks.map((item) => (
                <LogoTile key={item.name} item={item} framework />
              ))}
            </div>
          </div>
        </div>
      </Reveal>
    </Section>
  );
}

function RecordAgreementFlow() {
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

  const records = [
    { system: 'Stripe', icon: SiStripe, field: 'refund.amount', value: '$500 matched' },
    { system: 'Salesforce', icon: Cloud, field: 'account.balance', value: 'updated' },
    { system: 'NetSuite', mark: 'NS', field: 'ledger.entry', value: 'posted once' },
    { system: 'Zendesk', icon: SiZendesk, field: 'ticket.reply', value: 'state aligned' },
  ];

  const checks = [
    ['Requested state', 'refund $500 to acct_1028'],
    ['Source lookup', 'Stripe + ledger queried'],
    ['Record verdict', stage >= 3 ? 'matched' : 'waiting for agreement'],
  ];

  return (
    <div className="relative mx-auto max-w-6xl overflow-hidden border border-[#ded9cf] bg-[#fffefa]/88 shadow-[0_28px_80px_-64px_rgba(23,25,22,0.52)] backdrop-blur">
      <span className="absolute -left-1.5 -top-1.5 h-3 w-3 border-l border-t border-[#cfc9bd]" />
      <span className="absolute -right-1.5 -top-1.5 h-3 w-3 border-r border-t border-[#cfc9bd]" />
      <span className="absolute -bottom-1.5 -left-1.5 h-3 w-3 border-b border-l border-[#cfc9bd]" />
      <span className="absolute -bottom-1.5 -right-1.5 h-3 w-3 border-b border-r border-[#cfc9bd]" />

      <svg className="pointer-events-none absolute inset-0 z-10 hidden h-full w-full lg:block" viewBox="0 0 1000 430" preserveAspectRatio="none" aria-hidden="true">
        <path d="M 166 152 H 444" stroke="#cfe0dd" strokeWidth="1.2" />
        <path d="M 556 152 H 834" stroke="#cfe0dd" strokeWidth="1.2" />
        <path d="M 500 225 V 342" stroke="#cfe0dd" strokeWidth="1.2" />
        {!reduce ? (
          <>
            <circle r="3.5" fill="#2f5f66">
              <animateMotion dur="3.4s" repeatCount="indefinite" path="M 166 152 H 444" />
            </circle>
            <circle r="3.5" fill="#2f5f66">
              <animateMotion dur="3.4s" begin="0.7s" repeatCount="indefinite" path="M 556 152 H 834" />
            </circle>
            <circle r="3.2" fill="#2f5f66">
              <animateMotion dur="2.7s" begin="1.2s" repeatCount="indefinite" path="M 500 225 V 342" />
            </circle>
          </>
        ) : null}
      </svg>

      <div className="relative z-20 grid lg:grid-cols-[1fr_0.95fr_1.08fr]">
        <div className="min-h-[300px] border-b border-[#ded9cf] p-5 sm:p-6 lg:border-b-0 lg:border-r">
          <div className="flex items-center justify-between gap-3">
            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">Agent response</p>
            <span className="border border-[#dfc899] bg-[#fff8ea] px-2.5 py-1 font-mono text-[10.5px] font-semibold text-[#8a5a16]">not proof</span>
          </div>

          <div className="mt-8 border border-[#ded9cf] bg-[#fbfaf6] p-4">
            <div className="flex items-start gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center border border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]">
                <Bot size={17} />
              </span>
              <div className="min-w-0">
                <p className="font-mono text-[12px] font-semibold text-[#171a15]">refund.payment</p>
                <p className="mt-1 text-sm leading-relaxed text-[#6b7068]">Agent says the refund tool returned successfully.</p>
              </div>
            </div>
            <motion.div
              className="mt-5 flex items-center justify-between border border-[#e1ddd3] bg-[#fffefa] px-3 py-2.5"
              initial={false}
              animate={{ opacity: stage >= 1 ? 1 : 0.45 }}
              transition={{ duration: 0.28, ease }}
            >
              <span className="font-mono text-[11px] font-semibold text-[#34362f]">HTTP response</span>
              <span className="font-mono text-[11px] font-semibold text-[#256b45]">200 OK</span>
            </motion.div>
          </div>

          <p className="mt-5 text-[13px] leading-relaxed text-[#6b7068]">
            The API response is treated as a claim until the business record confirms the same state.
          </p>
        </div>

        <div className="relative min-h-[300px] border-b border-[#ded9cf] bg-[#fbfcfa] p-5 text-center sm:p-6 lg:border-b-0 lg:border-r">
          <div className="mx-auto grid h-20 w-20 place-items-center overflow-hidden border border-[#cfe0dd] bg-[#eaf1ef]">
            <img src="/favicon.png" alt="Zroky" className="h-20 w-20 scale-[2.45] object-contain" />
          </div>
          <p className="mt-5 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">Zroky verifier</p>
          <h3 className="mx-auto mt-2 max-w-[260px] text-[1.18rem] font-semibold leading-tight text-[#171a15]">
            Compare the requested state with the real record.
          </h3>

          <div className="mt-6 grid gap-2 text-left">
            {checks.map(([label, value], index) => (
              <motion.div
                key={label}
                className="grid grid-cols-[1fr_auto] gap-3 border border-[#ded9cf] bg-[#fffefa] px-3 py-2.5"
                initial={false}
                animate={{ opacity: stage >= index + 1 ? 1 : 0.44 }}
                transition={{ duration: 0.28, ease }}
              >
                <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8a867a]">{label}</span>
                <span className={`min-w-0 text-right text-[11.5px] font-semibold ${stage >= index + 1 ? 'text-[#34362f]' : 'text-[#8a867a]'}`}>
                  {value}
                </span>
              </motion.div>
            ))}
          </div>
        </div>

        <div className="min-h-[300px] p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3">
            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">Systems of record</p>
            <span className="border border-[#cfe0dd] bg-[#eaf1ef] px-2.5 py-1 font-mono text-[10.5px] font-semibold text-[#2f5f66]">source truth</span>
          </div>

          <div className="mt-7 grid gap-2">
            {records.map((record, index) => {
              const Icon = record.icon;
              const visible = stage >= (index < 2 ? 2 : 3);
              return (
                <motion.div
                  key={record.system}
                  className="grid grid-cols-[2.65rem_1fr_auto] items-center gap-3 border border-[#ded9cf] bg-[#fffefa] px-3 py-3"
                  initial={false}
                  animate={{ opacity: visible ? 1 : 0.42, y: visible ? 0 : 4 }}
                  transition={{ duration: 0.28, ease }}
                >
                  <span className="grid h-9 w-9 place-items-center border border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]">
                    {Icon ? <Icon size={16} /> : <span className="font-mono text-[11px] font-semibold">{record.mark}</span>}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-[#171a15]">{record.system}</span>
                    <span className="block truncate font-mono text-[10.5px] text-[#777266]">{record.field}</span>
                  </span>
                  <span className={`font-mono text-[10.5px] font-semibold ${visible ? 'text-[#256b45]' : 'text-[#8a867a]'}`}>
                    {visible ? record.value : 'checking'}
                  </span>
                </motion.div>
              );
            })}
          </div>
        </div>
      </div>

      <motion.div
        className="relative z-20 border-t border-[#ded9cf] bg-[#fbfaf6] p-4 sm:p-5"
        initial={false}
        animate={{ opacity: stage >= 3 ? 1 : 0.56 }}
        transition={{ duration: 0.32, ease }}
      >
        <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
          <div className="flex min-w-0 items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center border border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]">
              {stage >= 3 ? <ReceiptText size={17} /> : <Loader2 size={17} className="animate-spin" />}
            </span>
            <div className="min-w-0">
              <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">Signed receipt</p>
              <p className="mt-1 text-sm font-semibold leading-relaxed text-[#171a15]">
                {stage >= 3 ? 'Receipt issued only after the source record agrees.' : 'Receipt waits until source records finish agreement checks.'}
              </p>
            </div>
          </div>
          <span className="w-fit border border-[#d4d0c4] bg-[#fffefa] px-3 py-2 font-mono text-[11px] font-semibold text-[#34362f]">
            rec_record_match_8f4c
          </span>
        </div>
      </motion.div>
    </div>
  );
}

function ClaimVsRealitySection() {
  return (
    <Section id="claim-vs-reality" className="bg-[#fbfcfa]">
      <SectionHeader
        eyebrow="Source-of-record verification"
        title="Trust the record, not the response."
        copy="A 200 OK only proves the tool returned. Zroky checks the real system of record, confirms the business state changed correctly, and attaches proof before the agent can move on."
        align="center"
      />

      <Reveal delay={0.08} className="mt-10">
        <RecordAgreementFlow />
      </Reveal>
    </Section>
  );
}

function ProtectedActionsSection() {
  const reduce = useReducedMotion();
  const actions = [
    {
      number: '01',
      title: 'Financial actions',
      image: '/assets/protected-actions/financial-lineart.png',
      body: 'Protect refunds, payouts, credits, and revenue changes with policy, approval, and source-of-record verification.',
    },
    {
      number: '02',
      title: 'Access and permissions',
      image: '/assets/protected-actions/access-lineart.png',
      body: 'Gate admin access, role changes, temporary grants, and app permissions before agents can expand authority.',
    },
    {
      number: '03',
      title: 'Customer communications',
      image: '/assets/protected-actions/messages-lineart.png',
      body: 'Review sensitive replies, escalations, refunds, commitments, and customer-facing updates before they are sent.',
    },
    {
      number: '04',
      title: 'Workflow changes',
      image: '/assets/protected-actions/workflow-lineart.png',
      body: 'Control deploys, ticket transitions, automation triggers, release steps, and business workflow mutations.',
    },
    {
      number: '05',
      title: 'CRM and ERP updates',
      image: '/assets/protected-actions/records-lineart.png',
      body: 'Verify account fields, opportunity changes, invoices, order state, and ledger-impacting record updates.',
    },
    {
      number: '06',
      title: 'Data exports and syncs',
      image: '/assets/protected-actions/sync-lineart.png',
      body: 'Limit bulk exports, external syncs, enrichment jobs, and data movement that can expose or change business state.',
    },
  ];

  return (
    <Section id="protected-actions" className="bg-[#fbfcfa]">
      <SectionHeader
        eyebrow="Protected actions"
        title="Protect the agent actions that change business state."
        copy="Zroky is built for the moments where an AI agent can move money, grant access, update customer state, trigger workflows, or touch production systems."
        align="center"
      />

      <Reveal delay={0.08} className="mx-auto mt-10 max-w-6xl">
        <div className="relative grid overflow-hidden border border-[#ded9cf] bg-[#fffefa]/72 md:grid-cols-2 lg:grid-cols-3">
          <span className="pointer-events-none absolute left-0 right-0 top-[230px] z-20 hidden h-px bg-[#ded9cf] lg:block" />
          <span className="pointer-events-none absolute left-0 right-0 top-[610px] z-20 hidden h-px bg-[#ded9cf] lg:block" />
          {actions.map((item, index) => {
            return (
              <motion.article
                key={item.title}
                className="-ml-px -mt-px grid h-[380px] min-w-0 grid-rows-[230px_150px] border border-[#ded9cf] bg-[#fffefa]/92"
                initial={reduce ? false : { opacity: 0, y: 14 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-80px' }}
                transition={{ duration: 0.48, ease, delay: index * 0.05 }}
              >
                <div className="grid place-items-center border-b border-[#ded9cf] bg-[#fffefa] p-5 lg:border-b-0">
                  <img
                    src={item.image}
                    alt=""
                    loading="lazy"
                    className="h-full max-h-[225px] w-full max-w-[260px] object-contain"
                  />
                </div>

                <div className="p-4 sm:p-5">
                  <h3 className="text-[0.95rem] font-semibold leading-tight text-[#171a15]">
                    <span className="font-mono text-[0.8rem] text-[#2f5f66]">{item.number}</span> {item.title}
                  </h3>
                  <p className="mt-2 text-[13px] leading-relaxed text-[#6b7068]">{item.body}</p>
                </div>
              </motion.article>
            );
          })}
        </div>
      </Reveal>
    </Section>
  );
}

function PrintedReceiptArtifact() {
  const reduce = useReducedMotion();
  const fragments = [
    { icon: Bot, label: 'Agent intent', value: 'refund.payment', meta: 'captured before execution' },
    { icon: ShieldCheck, label: 'Policy decision', value: 'finance.refund.v4', meta: 'approval required' },
    { icon: LockKeyhole, label: 'Approval path', value: 'finance.owner', meta: 'human gate recorded' },
    { icon: DatabaseZap, label: 'System outcome', value: 'Stripe + ledger', meta: 'source records matched' },
  ];
  const evidenceRows = [
    ['intent', 'agent.action.refund.payment', 'captured'],
    ['policy', 'finance.refund.requires_approval', 'matched'],
    ['approval', 'finance.owner / slack approval', 'recorded'],
    ['runner', 'scoped key / temporary grant', 'executed'],
    ['verifier', 'source outcome equals requested state', 'verified'],
  ];
  const leftFragments = fragments.slice(0, 2);
  const rightFragments = fragments.slice(2);

  const ProofFragment = ({ item, index }: { item: (typeof fragments)[number]; index: number }) => {
    const Icon = item.icon;
    return (
      <motion.div
        className="relative min-w-0 border border-[#ded9cf] bg-[#fffefa]/86 p-4"
        initial={reduce ? false : { opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-80px' }}
        transition={{ duration: 0.48, ease, delay: 0.06 + index * 0.05 }}
      >
        <div className="flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center border border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]">
            <Icon size={16} />
          </span>
          <div className="min-w-0">
            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">{item.label}</p>
            <p className="mt-1 truncate text-sm font-semibold text-[#171a15]">{item.value}</p>
            <p className="mt-1 text-[11px] leading-relaxed text-[#777266]">{item.meta}</p>
          </div>
        </div>
      </motion.div>
    );
  };

  return (
    <div className="relative mx-auto w-full max-w-6xl">
      <div className="relative overflow-hidden border border-[#ded9cf] bg-[#fffefa]/74 p-3 shadow-[0_28px_80px_-64px_rgba(23,25,22,0.52)] backdrop-blur sm:p-4 md:p-5">
        <span className="absolute -left-1.5 -top-1.5 h-3 w-3 border-l border-t border-[#cfc9bd]" />
        <span className="absolute -right-1.5 -top-1.5 h-3 w-3 border-r border-t border-[#cfc9bd]" />
        <span className="absolute -bottom-1.5 -left-1.5 h-3 w-3 border-b border-l border-[#cfc9bd]" />
        <span className="absolute -bottom-1.5 -right-1.5 h-3 w-3 border-b border-r border-[#cfc9bd]" />

        <div className="relative z-10 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(320px,390px)_minmax(0,1fr)] lg:items-stretch">
          <div className="grid gap-5 lg:h-full lg:content-center">
            {leftFragments.map((item, index) => (
              <ProofFragment key={item.label} item={item} index={index} />
            ))}
          </div>

          <motion.div
            className="relative overflow-hidden border border-[#d4d0c4] bg-[#fffdf7] shadow-[0_1px_2px_rgba(28,31,26,0.06),0_40px_86px_-58px_rgba(28,31,26,0.58)]"
            initial={reduce ? false : { opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.58, ease, delay: 0.08 }}
          >
            <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(23,26,21,0.024)_1px,transparent_1px),linear-gradient(rgba(23,26,21,0.018)_1px,transparent_1px)] bg-[size:14px_14px]" />
            <motion.div
              className="pointer-events-none absolute left-0 right-0 z-20 h-16 bg-[linear-gradient(180deg,rgba(47,95,102,0),rgba(47,95,102,0.12),rgba(47,95,102,0))]"
              initial={false}
              animate={reduce ? { y: 0, opacity: 0.25 } : { y: [-70, 360], opacity: [0, 1, 0] }}
              transition={{ duration: 5.2, repeat: reduce ? 0 : Infinity, ease: 'linear' }}
            />

            <div className="relative border-b border-[#ded9cf] px-4 py-3 sm:px-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-[#2f5f66]">Zroky evidence pack</p>
                  <h3 className="mt-1 text-[1.05rem] font-semibold leading-tight text-[#171a15]">refund.payment / matched</h3>
                </div>
                <span className="inline-flex items-center gap-2 border border-[#c2e4cf] bg-[#e7f5ec] px-3 py-1.5 font-mono text-[10.5px] font-semibold uppercase tracking-[0.12em] text-[#256b45]">
                  <Check size={13} /> signed
                </span>
              </div>
            </div>

            <div className="relative px-4 py-4 sm:px-5">
              <div className="grid grid-cols-2 gap-3 border-b border-[#ded9cf] pb-3 font-mono text-[10px]">
                <div>
                  <p className="uppercase tracking-[0.14em] text-[#8a867a]">receipt id</p>
                  <p className="mt-1 font-semibold text-[#171a15]">zrk_rc_9f2c41</p>
                </div>
                <div className="text-right">
                  <p className="uppercase tracking-[0.14em] text-[#8a867a]">proof status</p>
                  <p className="mt-1 font-semibold text-[#256b45]">verified</p>
                </div>
              </div>

              <div className="mt-3 divide-y divide-[#e2ded4] border-y border-[#ded9cf]">
                {evidenceRows.map(([label, value, status], index) => (
                  <div key={label} className="grid grid-cols-[4.25rem_1fr_4rem] gap-2 py-2 font-mono">
                    <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8a867a]">{label}</span>
                    <span className="min-w-0 truncate text-[10.5px] font-semibold text-[#171a15]">{value}</span>
                    <motion.span
                      className="text-right text-[10px] font-semibold uppercase tracking-[0.08em] text-[#2f5f66]"
                      animate={reduce ? undefined : { opacity: [0.58, 1, 0.58] }}
                      transition={{ duration: 2.6, repeat: Infinity, delay: index * 0.18 }}
                    >
                      {status}
                    </motion.span>
                  </div>
                ))}
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_3.75rem]">
                <div className="min-w-0">
                  <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#8a867a]">signature hash</p>
                  <p className="mt-1.5 break-all font-mono text-[10.5px] font-semibold leading-relaxed text-[#171a15]">
                    sha256:7f3a9e10c4b7d9c2e01b8e6a5f91b0c2
                  </p>
                  <div className="mt-2.5 h-5 overflow-hidden border border-[#ded9cf] bg-[#f6f5ef]">
                    <motion.div
                      className="h-full w-[44%] bg-[repeating-linear-gradient(90deg,#171a15_0_2px,transparent_2px_5px,#171a15_5px_6px,transparent_6px_10px,#171a15_10px_13px,transparent_13px_17px)] opacity-75"
                      initial={false}
                      animate={reduce ? { x: 0 } : { x: ['-12%', '134%', '-12%'] }}
                      transition={{ duration: 6.4, repeat: reduce ? 0 : Infinity, ease: 'linear' }}
                    />
                  </div>
                </div>
                <div className="grid h-[3.75rem] w-[3.75rem] grid-cols-5 grid-rows-5 gap-1 border border-[#d7d4ca] bg-[#f8f7f2] p-1.5">
                  {Array.from({ length: 25 }).map((_, index) => (
                    <span
                      key={index}
                      className={`block ${[0, 1, 2, 5, 10, 12, 14, 16, 18, 20, 21, 23, 24].includes(index) ? 'bg-[#171a15]' : 'bg-transparent'}`}
                    />
                  ))}
                </div>
              </div>

              <div className="mt-4 border-t border-[#ded9cf] pt-3">
                <div className="grid gap-2 sm:grid-cols-3">
                  {['intent bound', 'source matched', 'tamper-evident'].map((item) => (
                    <span key={item} className="border border-[#d8d4c8] bg-[#fbfaf6] px-2.5 py-1.5 text-center font-mono text-[9px] font-semibold uppercase tracking-[0.1em] text-[#5f625b]">
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>

          <div className="grid gap-5 lg:h-full lg:content-center">
            {rightFragments.map((item, index) => (
              <ProofFragment key={item.label} item={item} index={index + leftFragments.length} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function ProofStandard() {
  return (
    <Section id="receipts" className="bg-[#fbfaf6] py-16 md:py-20">
      <SectionHeader
        eyebrow="Evidence pack"
        title="Every agent action leaves verifiable enterprise proof."
        copy="Zroky records the intent, policy decision, approval path, system-of-record outcome, and signed receipt so security, operations, and auditors can verify what actually happened."
        align="center"
      />

      <Reveal delay={0.08} className="mt-10">
        <PrintedReceiptArtifact />
      </Reveal>
    </Section>
  );
}

const IMPLEMENTATION_SNIPPET = `receipt = zroky.protect(
    action="refund.create",
    params={"customer_id": "acct_1028", "amount": 500},
    policy="finance.refund.v4",
    verify_with=["stripe", "netsuite"],
    wait_for_receipt=True,
)

assert receipt["proof_status"] == "matched"`;

function ImplementationPathSection() {
  const [copied, setCopied] = useState(false);
  const reduce = useReducedMotion();
  const rollout = [
    {
      step: '01',
      title: 'Choose one action',
      detail: 'Start with a refund, access grant, deploy, export, or customer message that carries real business risk.',
      icon: ShieldAlert,
    },
    {
      step: '02',
      title: 'Attach policy',
      detail: 'Set limits, approval owners, allowed systems, and the source record that must agree.',
      icon: LockKeyhole,
    },
    {
      step: '03',
      title: 'Verify record state',
      detail: 'Let Zroky compare the action result against Stripe, NetSuite, Salesforce, Zendesk, or your database.',
      icon: DatabaseZap,
    },
    {
      step: '04',
      title: 'Expand by action class',
      detail: 'Once proof is working, roll coverage across adjacent actions without replacing the agent framework.',
      icon: ReceiptText,
    },
  ];
  const coverage = [
    'Refunds',
    'Access grants',
    'CRM updates',
    'Deploys',
    'Data exports',
  ];
  const copy = () => {
    void navigator.clipboard?.writeText(IMPLEMENTATION_SNIPPET);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <Section id="implementation" className="bg-[#f3f4ee] py-14 md:py-20">
      <SectionHeader
        eyebrow="Implementation path"
        title="Wrap the action that can hurt you first."
        copy="Start with one high-risk agent operation, add policy, source verification, and receipts around it, then expand Zroky coverage across the actions that change money, access, customer state, and production systems."
        align="center"
      />

      <Reveal delay={0.08} className="mx-auto mt-10 max-w-6xl">
        <div className="relative overflow-hidden border border-[#ded9cf] bg-[#fffefa]/88 shadow-[0_28px_80px_-64px_rgba(23,25,22,0.52)] backdrop-blur">
          <span className="absolute -left-1.5 -top-1.5 h-3 w-3 border-l border-t border-[#cfc9bd]" />
          <span className="absolute -right-1.5 -top-1.5 h-3 w-3 border-r border-t border-[#cfc9bd]" />
          <span className="absolute -bottom-1.5 -left-1.5 h-3 w-3 border-b border-l border-[#cfc9bd]" />
          <span className="absolute -bottom-1.5 -right-1.5 h-3 w-3 border-b border-r border-[#cfc9bd]" />

          <div className="grid lg:grid-cols-[1.02fr_0.98fr]">
            <div className="min-w-0 border-b border-[#ded9cf] p-4 sm:p-5 lg:border-b-0 lg:border-r">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#ded9cf] pb-4">
                <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">Protected wrapper</p>
                <span className="border border-[#cfe0dd] bg-[#eaf1ef] px-2.5 py-1 font-mono text-[10.5px] font-semibold text-[#2f5f66]">
                  no framework rewrite
                </span>
              </div>

              <div className="mt-5 min-w-0 overflow-hidden bg-[#22271f]">
                <div className="flex items-center justify-between border-b border-white/10 px-4 py-3 sm:px-5">
                  <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-[#d9ded4]">
                    zroky / python
                  </span>
                  <button
                    type="button"
                    onClick={copy}
                    className="inline-flex items-center gap-1.5 border border-white/15 bg-white/5 px-2.5 py-1.5 font-mono text-[11px] text-[#f4f6f1] transition hover:bg-white/10"
                  >
                    {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? 'copied' : 'copy'}
                  </button>
                </div>
                <pre className="max-w-full overflow-x-auto p-4 font-mono text-[11.5px] leading-relaxed text-[#eef1ec] sm:p-5 sm:text-[12.5px]">{IMPLEMENTATION_SNIPPET}</pre>
              </div>

              <div className="mt-5 grid gap-2 sm:grid-cols-3">
                {[
                  ['Policy', 'limit + approver'],
                  ['Verifier', 'Stripe + NetSuite'],
                  ['Receipt', 'signed on match'],
                ].map(([label, value]) => (
                  <div key={label} className="border border-[#ded9cf] bg-[#fbfaf6] p-3">
                    <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">{label}</p>
                    <p className="mt-1 text-[12.5px] font-semibold text-[#171a15]">{value}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="relative min-w-0 p-4 sm:p-5">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#ded9cf] pb-4">
                <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">Rollout path</p>
                <span className="border border-[#d4d0c4] bg-[#fffefa] px-2.5 py-1 font-mono text-[10.5px] font-semibold text-[#34362f]">
                  expand by risk
                </span>
              </div>

              <div className="relative mt-5">
                <span className="absolute bottom-8 left-[1.14rem] top-8 w-px bg-[#cfe0dd]" aria-hidden="true" />
                {!reduce ? (
                  <motion.span
                    className="absolute left-[0.91rem] top-8 h-11 w-1.5 bg-[linear-gradient(180deg,rgba(47,95,102,0),rgba(47,95,102,0.95),rgba(47,95,102,0))]"
                    aria-hidden="true"
                    animate={{ y: [0, 308, 0] }}
                    transition={{ duration: 5.8, repeat: Infinity, ease: 'linear' }}
                  />
                ) : null}

                <div className="grid gap-3">
                  {rollout.map((item, index) => {
                    const Icon = item.icon;
                    return (
                      <motion.div
                        key={item.title}
                        className="relative grid grid-cols-[2.35rem_1fr] gap-3 border border-[#ded9cf] bg-[#fffefa] p-3.5"
                        initial={reduce ? false : { opacity: 0, y: 12 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: '-80px' }}
                        transition={{ duration: 0.45, ease, delay: index * 0.05 }}
                      >
                        <span className="relative z-10 grid h-9 w-9 place-items-center border border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]">
                          <Icon size={16} />
                        </span>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-baseline gap-2">
                            <span className="font-mono text-[10px] font-semibold tracking-[0.14em] text-[#2f5f66]">{item.step}</span>
                            <h3 className="text-[0.98rem] font-semibold leading-tight text-[#171a15]">{item.title}</h3>
                          </div>
                          <p className="mt-2 text-[13px] leading-relaxed text-[#6b7068]">{item.detail}</p>
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              </div>

            </div>
          </div>

          <div className="border-t border-[#ded9cf] bg-[#fbfaf6] p-4 sm:p-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <p className="shrink-0 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">Coverage expansion</p>
              <div className="min-w-0 overflow-x-auto">
                <div className="flex w-max items-center gap-2 pr-2">
                  {coverage.map((item, index) => (
                    <div key={item} className="flex shrink-0 items-center gap-2">
                      <span className="border border-[#cfe0dd] bg-[#eaf1ef] px-2.5 py-1.5 text-[11.5px] font-semibold text-[#34362f]">
                        {item}
                      </span>
                      {index < coverage.length - 1 ? <ArrowRight size={13} className="shrink-0 text-[#8a867a]" /> : null}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </Reveal>
    </Section>
  );
}

function FinalCTA() {
  return (
    <section className="section-lines w-full bg-[#fbfcfa] px-4 py-20 text-[#171a15] md:py-24">
      <Reveal>
        <div className="relative z-10 mx-auto max-w-6xl rounded-[20px] border border-[#d7d4ca] bg-[#fffdfa] p-5 text-center shadow-[0_34px_78px_-54px_rgba(28,31,26,0.34)] sm:p-8 md:rounded-[24px] md:p-14 md:shadow-[0_40px_90px_-52px_rgba(28,31,26,0.38)]">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">Operationalize autonomy</p>
          <h2 className="mx-auto mt-3 max-w-3xl text-balance text-[1.95rem] font-semibold leading-[1.08] tracking-[-0.025em] text-[#151713] min-[380px]:text-[2.15rem] md:text-[3.4rem] md:leading-[1.05] md:tracking-[-0.03em]">
            Give agents authority only when your business can prove the outcome.
          </h2>
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
      <ControlFlowSection />
      <ConnectorWall />
      <ProofStandard />
      <ProtectedActionsSection />
      <ClaimVsRealitySection />
      <ImplementationPathSection />
      <FinalCTA />
    </div>
  );
}
