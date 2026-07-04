import { ArrowRight, CalendarDays, ShieldCheck } from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import type { ReactNode } from 'react';
import { DEMO_URL, SIGN_UP_URL } from '../../lib/links';
import { AnimatedDashboard } from './AnimatedDashboard';

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
  const reduce = useReducedMotion();

  return (
    <section
      className="relative w-full overflow-hidden px-3 pt-28 pb-14 text-[#161814] sm:px-4 md:pt-32 lg:pt-36"
      style={{
        background: 'linear-gradient(180deg,#fbfaf6 0%,#f4f2eb 50%,#fbfcfa 100%)',
        fontFeatureSettings: "'ss01','cv01'",
      }}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[560px]"
        style={{
          background:
            'radial-gradient(62% 38% at 50% 0%, rgba(255,255,255,0.95), transparent 76%), linear-gradient(180deg, rgba(234,231,220,0.78), transparent 64%)',
        }}
      />

      <div className="relative z-10 mx-auto max-w-[1260px]">
        <div className="mx-auto max-w-[980px] text-center">
          <Reveal>
            <span className="inline-flex items-center gap-2 rounded-full border border-[#c9ddda] bg-[#eaf1ef] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66] shadow-[0_1px_2px_rgba(32,35,31,0.04)]">
              <ShieldCheck size={12} /> AI agent action control plane
            </span>
          </Reveal>

          <Reveal delay={0.06}>
            <h1 className="mt-6 text-[2.55rem] font-semibold leading-[0.98] tracking-[-0.03em] text-[#12140f] sm:text-[3.25rem] md:text-[4.1rem] lg:text-[4.8rem] lg:tracking-[-0.035em]">
              <span className="block">Scale enterprise agents </span>
              <span className="block text-[#2f5f66]">with governed execution.</span>
            </h1>
          </Reveal>

          <Reveal delay={0.12}>
            <p className="mx-auto mt-6 max-w-[760px] text-balance text-[1.08rem] leading-[1.65] text-[#555b53] md:text-[1.16rem]">
              <span className="block">Zroky gives every agent a policy gate, controlled runner, and verifiable proof trail.</span>
              <span className="block">Security, operations, and buyers can trust what scaled autonomy is allowed to do.</span>
            </p>
          </Reveal>

          <Reveal delay={0.18}>
            <div className="mt-8 flex flex-col items-stretch justify-center gap-3 sm:flex-row sm:flex-wrap sm:items-center">
              <a
                href={DEMO_URL}
                className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-[12px] bg-[linear-gradient(180deg,#3a747c,#2f5f66)] px-6 text-sm font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.22),0_18px_34px_-18px_rgba(47,95,102,0.72)] transition duration-150 hover:-translate-y-px hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.22),0_22px_40px_-20px_rgba(47,95,102,0.78)] active:translate-y-0 sm:w-auto"
              >
                <CalendarDays size={16} /> Book a demo
              </a>
              <a
                href={SIGN_UP_URL}
                className="inline-flex h-12 w-full items-center justify-center gap-1.5 rounded-[12px] border border-[#c9ddda] bg-[linear-gradient(180deg,#ffffff,#eef5f3)] px-6 text-sm font-semibold text-[#2f5f66] shadow-[inset_0_1px_0_rgba(255,255,255,0.95),0_12px_26px_-18px_rgba(47,95,102,0.28)] transition hover:-translate-y-px hover:border-[#a9c9c4] hover:bg-[#f7fffd] sm:w-auto"
              >
                Start free <ArrowRight size={15} />
              </a>
            </div>
          </Reveal>
        </div>

        <motion.div
          className="relative z-10 mx-auto mt-12"
          initial={reduce ? false : { opacity: 0, y: 34 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease, delay: 0.28 }}
        >
          <AnimatedDashboard />
        </motion.div>
      </div>
    </section>
  );
}
