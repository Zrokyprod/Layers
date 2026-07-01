import { useEffect, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Check, Headphones, Landmark, Server, ShieldCheck, Ticket } from 'lucide-react';

const AGENTS = [
  { icon: Headphones, label: 'Support', sub: 'refunds, tickets' },
  { icon: Server, label: 'Internal Ops', sub: 'records, workflows' },
  { icon: Ticket, label: 'ITSM / Access', sub: 'grants, permissions' },
  { icon: Landmark, label: 'Finance', sub: 'payouts, invoices' },
];

const STATS = [
  ['1 -> N', 'agents on one control plane'],
  ['Reused', 'policies, runners, verifiers'],
  ['Every action', 'signed into a receipt'],
];

function AgentRow({ agent, index, active }: { agent: typeof AGENTS[number]; index: number; active: boolean }) {
  const Icon = agent.icon;
  return (
    <motion.div
      className="flex items-center gap-3"
      initial={false}
      animate={{ opacity: active ? 1 : 0.35, x: active ? 0 : -6 }}
      transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1], delay: index * 0.05 }}
    >
      {/* connector from spine */}
      <div className="relative h-[2px] w-8 self-center sm:w-12">
        <div className="absolute inset-0 rounded-full bg-[#e0e2db]" />
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full bg-[#4f5a52]"
          initial={false}
          animate={{ width: active ? '100%' : '0%' }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>
      <div className="flex flex-1 items-center gap-3 rounded-[12px] border border-[#d8dbd2] bg-white px-3 py-2.5 shadow-[0_1px_2px_rgba(42,45,40,0.04)]">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[9px] border border-[#e6e8e2] bg-[#f7f8f4] text-[#4f5a52]">
          <Icon size={15} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-semibold text-[#20231f]">{agent.label} agent</p>
          <p className="truncate font-mono text-[10px] text-[#8b9288]">{agent.sub}</p>
        </div>
        <motion.span
          className="inline-flex h-[22px] items-center gap-1.5 rounded-full border border-[#2f7d50]/25 bg-[#2f7d50]/10 px-2 text-[10px] font-semibold uppercase tracking-[0.04em] text-[#276844]"
          initial={false}
          animate={{ opacity: active ? 1 : 0, scale: active ? 1 : 0.9 }}
          transition={{ duration: 0.3, delay: 0.15 }}
        >
          <Check size={11} /> receipt
        </motion.span>
      </div>
    </motion.div>
  );
}

export function ScaleFleet() {
  const reduced = Boolean(useReducedMotion());
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [count, setCount] = useState(reduced ? AGENTS.length : 1);
  const [inView, setInView] = useState(true);

  useEffect(() => {
    const node = rootRef.current;
    if (!node || typeof IntersectionObserver === 'undefined') return undefined;
    const obs = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { threshold: 0.3 });
    obs.observe(node);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (reduced || !inView) return undefined;
    const t = window.setTimeout(() => setCount((c) => (c >= AGENTS.length ? 1 : c + 1)), count >= AGENTS.length ? 2400 : 900);
    return () => window.clearTimeout(t);
  }, [count, inView, reduced]);

  return (
    <section id="scale" ref={rootRef} className="w-full scroll-mt-28 bg-[#f4f6f1] px-4 py-16 text-[#20231f] md:py-20">
      <div className="mx-auto grid max-w-[1340px] items-center gap-12 lg:grid-cols-[0.9fr_1.1fr]">
        <div>
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#4f5a52]">Scale with confidence</p>
          <h2 className="mt-3 text-balance text-[2rem] font-semibold leading-[1.08] tracking-[-0.025em] text-[#20231f] md:text-[2.75rem]">
            One agent today. Your whole fleet tomorrow.
          </h2>
          <p className="mt-4 max-w-md text-[1.02rem] leading-[1.6] text-[#5b615a]">
            Start with the one agent where the risk is obvious. Add the rest of the fleet without rebuilding control - the same policy, runners, and verifiers apply, and every action still ends as a receipt.
          </p>
          <dl className="mt-6 grid gap-4 sm:grid-cols-3">
            {STATS.map(([value, label]) => (
              <div key={label}>
                <dt className="text-[1.4rem] font-semibold tracking-[-0.02em] text-[#20231f]">{value}</dt>
                <dd className="mt-1 text-[12px] leading-snug text-[#8b9288]">{label}</dd>
              </div>
            ))}
          </dl>
        </div>

        {/* diagram */}
        <div className="relative rounded-[20px] border border-[#d8dbd2] bg-[linear-gradient(180deg,#fbfcf8,#f1f3ee)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_30px_70px_-40px_rgba(42,45,40,0.28)] md:p-8">
          <div className="flex items-center gap-4">
            {/* control plane hub */}
            <div className="flex shrink-0 flex-col items-center gap-2">
              <span className="grid h-14 w-14 place-items-center rounded-[16px] border border-[#4f5a52]/25 bg-white shadow-[0_2px_6px_rgba(42,45,40,0.06)]">
                <img src="/zroky.png" alt="Zroky" className="h-8 w-8 object-contain" />
              </span>
              <span className="text-center text-[10px] font-semibold leading-tight text-[#4f5a52]">Control<br />plane</span>
            </div>
            {/* fanned agents */}
            <div className="flex flex-1 flex-col gap-2.5">
              {AGENTS.map((agent, i) => (
                <AgentRow key={agent.label} agent={agent} index={i} active={i < count} />
              ))}
            </div>
          </div>
          <p className="mt-5 flex items-center justify-center gap-1.5 border-t border-[#e6e8e2] pt-4 text-center font-mono text-[11px] text-[#8b9288]">
            <ShieldCheck size={12} className="text-[#4f5a52]" />
            Same policy, same proof - across {count} of {AGENTS.length} agent {count === 1 ? 'type' : 'types'}.
          </p>
        </div>
      </div>
    </section>
  );
}
