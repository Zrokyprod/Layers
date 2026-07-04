import { useEffect, useMemo, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { DatabaseZap, KeyRound, LockKeyhole, ReceiptText, ShieldCheck, Workflow } from 'lucide-react';
import {
  HERO_SIGNATURE_HEX,
  getHeroTimelineState,
  isHeroStageComplete,
  type HeroStageId,
  type HeroTone,
} from '../../lib/heroTimeline';

type RailStep = {
  id: HeroStageId;
  label: string;
  detail: string;
  event: string;
  icon: typeof Workflow;
  tone: HeroTone;
};

const railSteps: RailStep[] = [
  { id: 'proposed', label: 'Propose', detail: 'agent intent', event: 'access.grant', icon: Workflow, tone: 'neutral' },
  { id: 'held', label: 'Policy', detail: 'risk scored', event: 'approval required', icon: LockKeyhole, tone: 'warning' },
  { id: 'approved', label: 'Approve', detail: 'human gate', event: 'approved by owner', icon: ShieldCheck, tone: 'accent' },
  { id: 'executed', label: 'Run', detail: 'scoped runner', event: 'isolated credential', icon: KeyRound, tone: 'accent' },
  { id: 'verified', label: 'Verify', detail: 'system matched', event: 'directory matched', icon: DatabaseZap, tone: 'success' },
  { id: 'receipt', label: 'Receipt', detail: 'evidence sealed', event: 'hash signed', icon: ReceiptText, tone: 'success' },
];

const toneStyles: Record<HeroTone, { bg: string; border: string; text: string; dot: string; ring: string }> = {
  neutral: {
    bg: 'bg-[#f7f6f1]',
    border: 'border-[#dedacf]',
    text: 'text-[#5f655d]',
    dot: 'bg-[#8a867a]',
    ring: 'ring-[#8a867a]/14',
  },
  warning: {
    bg: 'bg-[#fff8ea]',
    border: 'border-[#dfc899]',
    text: 'text-[#8a5a16]',
    dot: 'bg-[#b87922]',
    ring: 'ring-[#b87922]/18',
  },
  accent: {
    bg: 'bg-[#eaf1ef]',
    border: 'border-[#cfe0dd]',
    text: 'text-[#2f5f66]',
    dot: 'bg-[#2f5f66]',
    ring: 'ring-[#2f5f66]/14',
  },
  success: {
    bg: 'bg-[#e7f5ec]',
    border: 'border-[#c2e4cf]',
    text: 'text-[#256b45]',
    dot: 'bg-[#2f7d50]',
    ring: 'ring-[#2f7d50]/16',
  },
};

function waitFrame(callback: () => void) {
  const id = window.setInterval(callback, 120);
  return () => window.clearInterval(id);
}

export function ControlLoopDemo() {
  const reduced = Boolean(useReducedMotion());
  const rootRef = useRef<HTMLDivElement | null>(null);
  const elapsedRef = useRef(0);
  const [elapsed, setElapsed] = useState(0);
  const [inView, setInView] = useState(true);

  useEffect(() => {
    const node = rootRef.current;
    if (!node || typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: 0.25 });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (reduced || !inView) return undefined;
    const startedAt = performance.now() - elapsedRef.current * 1000;
    return waitFrame(() => {
      const next = (performance.now() - startedAt) / 1000;
      elapsedRef.current = next;
      setElapsed(next);
    });
  }, [inView, reduced]);

  const state = useMemo(() => getHeroTimelineState(elapsed, reduced), [elapsed, reduced]);
  const activeStep = railSteps.find((step) => step.id === state.activeStage) ?? railSteps[0];
  const activeTone = toneStyles[activeStep.tone];
  const tokenLeft = state.receiptVisible ? 100 : state.tokenX * 80;
  const lineFill = state.receiptVisible ? 100 : state.lineFill * 80;
  const signature = HERO_SIGNATURE_HEX.slice(0, state.signatureChars);

  return (
    <motion.div
      ref={rootRef}
      className="relative"
      initial={reduced ? false : { opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.62, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="overflow-hidden rounded-[20px] border border-[#d5d2c7] bg-[#fffdfa] shadow-[0_1px_2px_rgba(28,31,26,0.05),0_36px_90px_-56px_rgba(28,31,26,0.5)]">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#dedacf] bg-[#f8f7f2] px-5 py-4">
          <div>
            <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">Protected action rail</p>
            <h3 className="mt-1 text-xl font-semibold text-[#151713]">access.grant / admin role</h3>
          </div>
          <span className={`rounded-[8px] border px-3 py-1.5 text-xs font-semibold ${activeTone.bg} ${activeTone.border} ${activeTone.text}`}>
            {activeStep.event}
          </span>
        </div>

        <div className="px-5 py-7">
          <div className="relative mx-auto max-w-5xl px-2">
            <div className="absolute left-[4.5rem] right-[4.5rem] top-[2.18rem] hidden h-px bg-[#dedacf] md:block" />
            <motion.div
              className="absolute left-[4.5rem] top-[2.18rem] hidden h-px bg-[#2f5f66] md:block"
              initial={false}
              animate={{ width: `calc((100% - 9rem) * ${lineFill / 100})` }}
              transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
            />
            <motion.div
              className="absolute top-[1.78rem] z-20 hidden h-3.5 w-3.5 -translate-x-1/2 rounded-full border-[3px] border-[#fffdfa] bg-[#2f5f66] shadow-[0_0_0_9px_rgba(47,95,102,0.12),0_12px_24px_-14px_rgba(28,31,26,0.65)] md:block"
              initial={false}
              animate={{ left: `calc(4.5rem + (100% - 9rem) * ${tokenLeft / 100})` }}
              transition={{ type: 'spring', stiffness: 380, damping: 32 }}
            />

            <div className="grid gap-3 md:grid-cols-6">
              {railSteps.map((step) => {
                const Icon = step.icon;
                const complete = isHeroStageComplete(state, step.id);
                const active = state.activeStage === step.id;
                const tone = toneStyles[complete ? step.tone : 'neutral'];
                return (
                  <motion.div
                    key={step.id}
                    animate={active ? { y: -4 } : { y: 0 }}
                    transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                    className={`relative rounded-[10px] border bg-[#fffdfa] p-3 shadow-[0_12px_30px_-28px_rgba(31,35,29,0.45)] ${active ? `ring-4 ${tone.ring}` : ''} ${
                      complete ? tone.border : 'border-[#e1ddd3]'
                    }`}
                  >
                    <div className={`grid h-9 w-9 place-items-center rounded-[8px] border ${tone.bg} ${tone.border} ${tone.text}`}>
                      <Icon size={16} />
                    </div>
                    <p className="mt-4 text-[13px] font-semibold text-[#171a15]">{step.label}</p>
                    <p className="mt-1 font-mono text-[10.5px] leading-relaxed text-[#777266]">{step.detail}</p>
                    <span className={`absolute right-2.5 top-2.5 h-2 w-2 rounded-full ${complete ? tone.dot : 'bg-[#cbc7bc]'}`} />
                  </motion.div>
                );
              })}
            </div>
          </div>

          <div className="mt-5 grid gap-3 lg:grid-cols-[1fr_1fr_1fr]">
            <div className="rounded-[10px] border border-[#dfc899] bg-[#fff8ea] p-4">
              <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.12em] text-[#8a5a16]">Policy hold</p>
              <p className="mt-1 text-sm font-semibold text-[#171a15]">Privileged access + sequence risk requires approval.</p>
            </div>
            <div className="rounded-[10px] border border-[#cfe0dd] bg-[#eaf1ef] p-4">
              <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.12em] text-[#2f5f66]">Verifier</p>
              <p className="mt-1 text-sm font-semibold text-[#171a15]">{isHeroStageComplete(state, 'verified') ? 'Matched against identity source.' : 'Waiting for source-of-record match.'}</p>
            </div>
            <div className="rounded-[10px] border border-[#dcd8ce] bg-[#f8f7f2] p-4">
              <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.12em] text-[#777266]">Receipt hash</p>
              <p className="mt-1 truncate font-mono text-sm font-semibold text-[#171a15]">
                {signature || 'pending'}{signature && signature.length < HERO_SIGNATURE_HEX.length ? '_' : ''}
              </p>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
