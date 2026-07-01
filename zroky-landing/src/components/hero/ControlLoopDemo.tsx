import { useEffect, useMemo, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { DatabaseZap, FileCheck2, KeyRound, LockKeyhole, ReceiptText, ShieldCheck } from 'lucide-react';
import { HERO_STAGES, getHeroTimelineState, isHeroStageComplete, type HeroStageId, type HeroTone } from '../../lib/heroTimeline';
import { StatusPill } from './StatusPill';

type GraphNode = {
  id: HeroStageId;
  title: string;
  detail: string;
  x: number;
  y: number;
  tone: HeroTone;
  icon: typeof ShieldCheck;
};

const graphNodes: GraphNode[] = [
  { id: 'proposed', title: 'Agent intent', detail: 'refund.payment', x: 24, y: 35, tone: 'neutral', icon: ShieldCheck },
  { id: 'held', title: 'Policy gate', detail: 'approval > $500', x: 52, y: 22, tone: 'warning', icon: LockKeyhole },
  { id: 'approved', title: 'Approval', detail: 'priya@acme', x: 74, y: 38, tone: 'accent', icon: FileCheck2 },
  { id: 'executed', title: 'Runner', detail: 'isolated credential', x: 33, y: 70, tone: 'accent', icon: KeyRound },
  { id: 'verified', title: 'System record', detail: 'Razorpay matched', x: 70, y: 70, tone: 'success', icon: DatabaseZap },
  { id: 'receipt', title: 'Signed receipt', detail: 'HMAC + evidence hash', x: 54, y: 51, tone: 'success', icon: ReceiptText },
];

const toneStyles: Record<HeroTone, { dot: string; ring: string; text: string; fill: string }> = {
  neutral: {
    dot: 'bg-[#7c837b]',
    ring: 'ring-[#7c837b]/15',
    text: 'text-[#646b63]',
    fill: 'bg-[#eef0eb]',
  },
  warning: {
    dot: 'bg-[#b87922]',
    ring: 'ring-[#b87922]/18',
    text: 'text-[#8a5a16]',
    fill: 'bg-[#f8f0e3]',
  },
  accent: {
    dot: 'bg-[#4f5a52]',
    ring: 'ring-[#4f5a52]/16',
    text: 'text-[#3f4942]',
    fill: 'bg-[#edf0ea]',
  },
  success: {
    dot: 'bg-[#2f7d50]',
    ring: 'ring-[#2f7d50]/16',
    text: 'text-[#276844]',
    fill: 'bg-[#e9f3ed]',
  },
};

function GraphNodeCard({
  node,
  active,
  complete,
}: {
  node: GraphNode;
  active: boolean;
  complete: boolean;
}) {
  const Icon = node.icon;
  const tone = toneStyles[complete ? node.tone : 'neutral'];
  return (
    <motion.div
      className="absolute z-20 w-[8.75rem] -translate-x-1/2 -translate-y-1/2 sm:w-[9.75rem]"
      style={{ left: `${node.x}%`, top: `${node.y}%` }}
      animate={active ? { y: -5, scale: 1.02 } : { y: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 390, damping: 32 }}
    >
      <div
        className={`relative rounded-[15px] border border-[#d8dbd2] bg-[#fbfcf8]/92 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_12px_30px_-24px_rgba(42,45,40,0.32)] backdrop-blur-md ${
          active ? 'ring-4' : 'ring-0'
        } ${active ? tone.ring : ''}`}
      >
        <div className="flex items-start gap-2.5">
          <div className={`grid h-8 w-8 shrink-0 place-items-center rounded-[10px] border border-[#d8dbd2] ${tone.fill} ${tone.text}`}>
            <Icon size={15} />
          </div>
          <div className="min-w-0">
            <p className="truncate text-[12px] font-semibold tracking-[-0.01em] text-[#20231f]">{node.title}</p>
            <p className="mt-0.5 truncate font-mono text-[10px] text-[#737a71]">{node.detail}</p>
          </div>
        </div>
        <span className={`absolute -right-1.5 -top-1.5 h-3 w-3 rounded-full border-2 border-[#fbfcf8] ${complete ? tone.dot : 'bg-[#c5c9c0]'}`} />
      </div>
    </motion.div>
  );
}

function EventRow({ label, value, tone }: { label: string; value: string; tone: HeroTone }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-[12px] border border-[#d8dbd2] bg-[#fbfcf8]/80 px-3 py-2.5">
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-[#8b9288]">{label}</p>
        <p className="mt-0.5 text-[13px] font-semibold text-[#20231f]">{value}</p>
      </div>
      <StatusPill tone={tone}>{tone === 'warning' ? 'Held' : tone === 'success' ? 'Proof' : tone === 'neutral' ? 'Ready' : 'Live'}</StatusPill>
    </div>
  );
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
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: 0.2 });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (reduced || !inView) return undefined;
    const startedAt = performance.now() - elapsedRef.current * 1000;
    const interval = window.setInterval(() => {
      const next = (performance.now() - startedAt) / 1000;
      elapsedRef.current = next;
      setElapsed(next);
    }, 120);
    return () => window.clearInterval(interval);
  }, [inView, reduced]);

  const state = useMemo(() => getHeroTimelineState(elapsed, reduced), [elapsed, reduced]);
  const activeNode = graphNodes.find((node) => node.id === state.activeStage) ?? graphNodes[0];
  const activeStage = HERO_STAGES.find((stage) => stage.id === state.activeStage) ?? HERO_STAGES[0];

  return (
    <motion.div
      ref={rootRef}
      className="relative"
      initial={reduced ? false : { opacity: 0, y: 24, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
    >
      <div className="absolute -inset-10 rounded-[36px] bg-[radial-gradient(circle_at_50%_10%,rgba(79,90,82,0.18),transparent_70%)]" />
      <div className="relative overflow-hidden rounded-[28px] border border-[#d8dbd2] bg-[#eef0eb]/80 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.85),0_2px_8px_rgba(42,45,40,0.05),0_38px_80px_-46px_rgba(42,45,40,0.42)] backdrop-blur-xl">
        <div className="hero-grain pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative z-10">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#737a71]">Authority graph</p>
              <p className="mt-1 text-sm font-semibold text-[#20231f]">refund - cus_8842 - $4,200.00</p>
            </div>
            <StatusPill tone={activeStage.tone} active>
              {state.activeStage === 'receipt' ? 'Receipt signed' : state.activeStage === 'held' ? 'Approval pending' : 'Control active'}
            </StatusPill>
          </div>

          <div className="relative h-[25rem] overflow-hidden rounded-[22px] border border-[#d8dbd2] bg-[#f7f8f4] shadow-[inset_0_1px_0_rgba(255,255,255,0.95)]">
            <div className="absolute inset-0 bg-[linear-gradient(rgba(42,45,40,0.035)_1px,transparent_1px),linear-gradient(90deg,rgba(42,45,40,0.035)_1px,transparent_1px)] bg-[size:34px_34px]" />
            <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" aria-hidden="true">
              <path
                d="M24 35 C34 18 43 18 52 22 C63 24 69 30 74 38 C69 45 61 49 54 51 C45 54 38 61 33 70 C45 78 59 78 70 70 C64 62 59 55 54 51"
                fill="none"
                stroke="#cfd3ca"
                strokeWidth="0.7"
                strokeLinecap="round"
              />
              <motion.path
                d="M24 35 C34 18 43 18 52 22 C63 24 69 30 74 38 C69 45 61 49 54 51 C45 54 38 61 33 70 C45 78 59 78 70 70 C64 62 59 55 54 51"
                fill="none"
                stroke="#4f5a52"
                strokeWidth="0.9"
                strokeLinecap="round"
                pathLength={state.lineFill}
                transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
              />
            </svg>
            <motion.div
              aria-hidden="true"
              className="absolute z-30 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-[#fbfcf8] bg-[#4f5a52] shadow-[0_0_0_9px_rgba(79,90,82,0.16),0_12px_24px_-14px_rgba(42,45,40,0.6)]"
              animate={{ left: `${activeNode.x}%`, top: `${activeNode.y}%` }}
              transition={{ type: 'spring', stiffness: 380, damping: 30 }}
            />
            {graphNodes.map((node) => (
              <GraphNodeCard
                key={node.id}
                node={node}
                active={node.id === state.activeStage}
                complete={isHeroStageComplete(state, node.id)}
              />
            ))}
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            <EventRow label="Decision" value={state.activeStage === 'held' ? 'approval required' : 'policy in control'} tone={state.activeStage === 'held' ? 'warning' : 'accent'} />
            <EventRow label="Verifier" value={state.activeStage === 'receipt' ? 'ledger matched' : 'ready to compare'} tone={state.activeStage === 'receipt' ? 'success' : 'accent'} />
            <EventRow label="Evidence" value={state.receiptVisible ? 'signed receipt' : 'hash prepared'} tone={state.receiptVisible ? 'success' : 'neutral'} />
          </div>
        </div>
      </div>
    </motion.div>
  );
}
