import { ArrowRight, CalendarDays, ShieldCheck } from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import type { ReactNode } from 'react';
import { DEMO_URL, SIGN_UP_URL } from '../../lib/links';
import { DashboardMock } from '../DashboardMock';

const ease = [0.16, 1, 0.3, 1] as const;

function Reveal({ children, delay = 0, className = '' }: { children: ReactNode; delay?: number; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.65, ease, delay }}
    >
      {children}
    </motion.div>
  );
}

export default function Hero() {
  return (
    <section
      className="relative w-full overflow-hidden bg-[#fbfcfa] px-4 pt-32 pb-16 text-[#20231f] md:pt-40"
      style={{ fontFeatureSettings: "'ss01','cv01'" }}
    >
      <div className="mesh-rocket pointer-events-none absolute inset-x-0 top-0 h-[520px]" />
      <div className="grid-light pointer-events-none absolute inset-x-0 top-0 h-[520px] opacity-80" />

      {/* centered copy */}
      <div className="relative z-10 mx-auto max-w-3xl text-center">
        <Reveal>
          <span className="inline-flex items-center gap-2 rounded-full border border-[#d8dbd2] bg-[#f2f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#4f5a52]">
            <ShieldCheck size={12} /> Agent Reliability Control Plane
          </span>
        </Reveal>
        <Reveal delay={0.06}>
          <h1 className="mx-auto mt-6 max-w-5xl text-[clamp(2.3rem,4.8vw,4.25rem)] font-semibold leading-[1.06] tracking-[-0.03em] text-[#20231f]">
            <span className="block md:whitespace-nowrap">Give your agents authority.</span>
            <span className="block text-[#566158] md:whitespace-nowrap">Keep proof of every action.</span>
          </h1>
        </Reveal>
        <Reveal delay={0.12}>
          <p className="mx-auto mt-6 max-w-xl text-[1.05rem] leading-[1.6] text-[#5b615a]">
            Zroky holds every high-risk action for approval, executes it with isolated credentials, verifies it against
            your system of record, and signs an audit-grade receipt.
          </p>
        </Reveal>
        <Reveal delay={0.18}>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <a
              href={DEMO_URL}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-full bg-[linear-gradient(180deg,#5f675f,#2f342e)] px-6 text-sm font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_10px_24px_-12px_rgba(42,45,40,0.5)] transition duration-150 hover:-translate-y-px hover:brightness-110 focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#4f5a52]/25 active:translate-y-0"
            >
              <CalendarDays size={16} /> Book a demo
            </a>
            <a
              href={SIGN_UP_URL}
              className="inline-flex h-11 items-center justify-center gap-1.5 px-4 text-sm font-semibold text-[#3f4942] transition hover:text-[#20231f]"
            >
              Start free <ArrowRight size={15} />
            </a>
          </div>
        </Reveal>
        <Reveal delay={0.24}>
          <p className="mt-5 font-mono text-[12px] text-[#8b9288]">
            Fail-closed by default. We never call an unverified action "done".
          </p>
        </Reveal>
      </div>

      {/* product visual */}
      <Reveal delay={0.28} className="relative z-10 mx-auto mt-16 max-w-[1340px]">
        <DashboardMock />
      </Reveal>
    </section>
  );
}
