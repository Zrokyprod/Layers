import { motion, useReducedMotion } from 'framer-motion';
import { Bot, ShieldCheck, UserCheck, KeyRound, DatabaseZap, ReceiptText } from 'lucide-react';

type Tone = 'neutral' | 'warning' | 'accent' | 'success';

const NODES: { icon: typeof Bot; label: string; sub: string; tone: Tone }[] = [
  { icon: Bot, label: 'Intent', sub: 'Agent proposes', tone: 'neutral' },
  { icon: ShieldCheck, label: 'Policy', sub: 'Held', tone: 'warning' },
  { icon: UserCheck, label: 'Approval', sub: 'Human', tone: 'accent' },
  { icon: KeyRound, label: 'Execute', sub: 'Isolated cred', tone: 'accent' },
  { icon: DatabaseZap, label: 'Verify', sub: 'Matched', tone: 'success' },
  { icon: ReceiptText, label: 'Receipt', sub: 'Signed', tone: 'success' },
];

const ring: Record<Tone, string> = {
  neutral: 'border-[#d8dbd2] text-[#5b615a]',
  warning: 'border-[#b87922]/30 text-[#8a5a16]',
  accent: 'border-[#4f5a52]/30 text-[#3f4942]',
  success: 'border-[#2f7d50]/30 text-[#276844]',
};
const fill: Record<Tone, string> = {
  neutral: 'bg-[#e8ebe4]',
  warning: 'bg-[#f8f0e3]',
  accent: 'bg-[#edf0ea]',
  success: 'bg-[#e9f3ed]',
};

function Connector({ index, reduced }: { index: number; reduced: boolean }) {
  return (
    <div className="relative mx-1 hidden h-[2px] flex-1 self-center overflow-visible md:block" aria-hidden="true">
      <div className="absolute inset-0 rounded-full bg-[#d8dbd2]" />
      <motion.div
        className="absolute inset-y-0 left-0 rounded-full bg-[linear-gradient(90deg,#4f5a52,#343a34)]"
        initial={reduced ? { width: '100%' } : { width: '0%' }}
        whileInView={{ width: '100%' }}
        viewport={{ once: true }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: 0.25 + index * 0.18 }}
      />
      {!reduced && (
        <motion.span
          className="absolute top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-[#4f5a52] shadow-[0_0_0_4px_rgba(79,90,82,0.18)]"
          initial={{ left: '0%', opacity: 0 }}
          animate={{ left: ['0%', '100%'], opacity: [0, 1, 1, 0] }}
          transition={{ duration: 1.4, ease: 'easeInOut', repeat: Infinity, repeatDelay: 1.6, delay: index * 0.25 }}
        />
      )}
    </div>
  );
}

export function FlowDiagram() {
  const reduced = Boolean(useReducedMotion());

  return (
    <div className="relative">
      <div className="flex flex-col gap-3 md:flex-row md:items-stretch md:gap-0">
        {NODES.map((node, index) => {
          const Icon = node.icon;
          return (
            <div key={node.label} className="flex items-center md:contents">
              <motion.div
                className="flex w-full items-center gap-3 rounded-[14px] border border-[#d8dbd2] bg-[#fbfcf8] px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_1px_2px_rgba(42,45,40,0.05),0_18px_36px_-26px_rgba(42,45,40,0.2)] md:w-[150px] md:flex-col md:items-center md:px-3 md:py-4 md:text-center"
                initial={reduced ? false : { opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-60px' }}
                transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1], delay: index * 0.18 }}
              >
                <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-[12px] border ${ring[node.tone]} ${fill[node.tone]}`}>
                  <Icon size={18} />
                </span>
                <span className="md:mt-2">
                  <span className="block text-[14px] font-semibold text-[#20231f]">{node.label}</span>
                  <span className="block font-mono text-[11px] uppercase tracking-[0.06em] text-[#8b9288]">{node.sub}</span>
                </span>
              </motion.div>
              {index < NODES.length - 1 && <Connector index={index} reduced={reduced} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
