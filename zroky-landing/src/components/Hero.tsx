import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowRight,
  CheckCircle2,
  GitBranch,
  TerminalSquare,
} from 'lucide-react';

const WORDS = ['guessing', 'logging', 'wondering', 'praying'];

const PARTICLES = [
  { x: '8%',  y: '30%', size: 8,  op: 0.18, dur: 7,   delay: 0   },
  { x: '18%', y: '65%', size: 5,  op: 0.12, dur: 9,   delay: 1.2 },
  { x: '72%', y: '20%', size: 7,  op: 0.15, dur: 8,   delay: 0.5 },
  { x: '85%', y: '55%', size: 5,  op: 0.10, dur: 11,  delay: 2   },
  { x: '92%', y: '80%', size: 6,  op: 0.14, dur: 6.5, delay: 0.8 },
  { x: '55%', y: '88%', size: 4,  op: 0.10, dur: 10,  delay: 1.8 },
];

export default function Hero() {
  const [wordIdx, setWordIdx] = useState(0);
  const [showNew, setShowNew] = useState(false);

  useEffect(() => {
    const id = setInterval(() => setWordIdx((i) => (i + 1) % WORDS.length), 2200);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setShowNew(true), 3400);
    return () => clearTimeout(t);
  }, []);

  return (
    <section className="relative w-full overflow-x-clip px-4 pb-16 pt-40 sm:px-5 md:pb-20 md:pt-44 lg:min-h-[92vh] lg:flex lg:items-center lg:px-8 lg:pb-24">
      {/* Ambient floating particles */}
      {PARTICLES.map((p, i) => (
        <motion.div
          key={i}
          aria-hidden
          className="pointer-events-none absolute rounded-full bg-accent"
          style={{ left: p.x, top: p.y, width: p.size, height: p.size, opacity: p.op }}
          animate={{ y: [0, -(p.size * 12), 0], opacity: [p.op, p.op * 3, p.op] }}
          transition={{ duration: p.dur, delay: p.delay, repeat: Infinity, ease: 'easeInOut' }}
        />
      ))}
      <div className="relative mx-auto grid w-full max-w-[92rem] items-center gap-12 lg:grid-cols-[0.88fr_1.12fr] xl:gap-16">

        {/* ── LEFT: Copy ── */}
        <motion.div
          className="flex flex-col"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        >
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="inline-flex w-fit items-center gap-2 rounded-full border border-panel-border bg-white px-3 py-1.5 text-[11px] font-extrabold uppercase tracking-[0.16em] text-secondary shadow-sm"
          >
            <TerminalSquare className="h-3.5 w-3.5 text-accent" />
            AI Agent Reliability
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.05, ease: [0.16, 1, 0.3, 1] }}
            className="mt-6 max-w-[30rem] text-5xl font-black leading-[1.08] text-primary sm:text-6xl lg:text-[3.4rem] 2xl:text-7xl"
          >
            Stop{' '}
            <span className="relative inline-block" style={{ minWidth: '9rem' }}>
              <AnimatePresence mode="wait">
                <motion.span
                  key={WORDS[wordIdx]}
                  initial={{ opacity: 0, filter: 'blur(10px)', y: 6 }}
                  animate={{ opacity: 1, filter: 'blur(0px)', y: 0 }}
                  exit={{ opacity: 0, filter: 'blur(10px)', y: -6 }}
                  transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
                  className="text-accent"
                >
                  {WORDS[wordIdx]}
                </motion.span>
              </AnimatePresence>
            </span>
            {' '}why your agents fail.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.09, ease: [0.16, 1, 0.3, 1] }}
            className="mt-5 max-w-[30rem] text-balance text-lg leading-8 text-secondary"
          >
            Capture every production run, diagnose root cause, prove fixes with replay,
            and ship CI guards that block regressions.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.13, ease: [0.16, 1, 0.3, 1] }}
            className="mt-8 flex flex-col gap-3 sm:flex-row"
          >
            <a
              href="/auth/register"
              className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-primary px-6 py-3 text-sm font-extrabold text-white shadow-sm transition duration-200 hover:bg-accent focus:outline-none focus:ring-2 focus:ring-accent/35"
            >
              Get Started Free
              <ArrowRight className="h-4 w-4" />
            </a>
            <a
              href="mailto:sales@zroky.ai?subject=Zroky+demo"
              className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full border border-panel-border bg-white px-6 py-3 text-sm font-extrabold text-primary shadow-sm transition duration-200 hover:border-accent/40 hover:bg-accent/5 focus:outline-none focus:ring-2 focus:ring-accent/35"
            >
              Talk to us
            </a>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.17, ease: [0.16, 1, 0.3, 1] }}
            className="mt-8 flex flex-wrap gap-5 text-sm font-bold text-secondary"
          >
            {['Evidence-first diagnosis', 'Replay-verified fixes', 'CI regression gates'].map((item) => (
              <div key={item} className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 shrink-0 text-accent" />
                {item}
              </div>
            ))}
          </motion.div>
        </motion.div>

        {/* ── RIGHT: Product panel ── */}
        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.988 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.6, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          className="relative"
        >
          <div className="overflow-hidden rounded-[1.5rem] border border-panel-border bg-white shadow-premium">

            {/* Window chrome */}
            <div className="flex items-center justify-between gap-4 border-b border-panel-border bg-canvas px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
                <span className="ml-2.5 font-mono text-xs font-bold text-tertiary">
                  Issues
                </span>
              </div>
              <span className="rounded-full border border-danger/25 bg-danger/10 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-danger">
                2 active
              </span>
            </div>

            {/* Stats strip */}
            <div className="grid grid-cols-3 divide-x divide-panel-border border-b border-panel-border bg-canvas/60">
              {[
                ['43', 'affected calls'],
                ['$281', 'projected waste'],
                ['1', 'replay ready'],
              ].map(([value, label]) => (
                <div key={label} className="px-4 py-3 text-center">
                  <div className="text-sm font-black text-primary">{value}</div>
                  <div className="mt-0.5 text-[10px] font-bold uppercase tracking-[0.1em] text-tertiary">{label}</div>
                </div>
              ))}
            </div>

            {/* Live new issue pulse — appears after 3.4s */}
            <AnimatePresence>
              {showNew && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                  className="overflow-hidden border-b border-panel-border"
                >
                  <div className="flex items-center gap-3 bg-accent/5 px-4 py-2.5">
                    <motion.span
                      animate={{ opacity: [1, 0.3, 1] }}
                      transition={{ duration: 1.4, repeat: Infinity }}
                      className="h-2 w-2 shrink-0 rounded-full bg-accent"
                    />
                    <span className="text-xs font-black text-accent">NEW</span>
                    <span className="min-w-0 truncate text-xs font-bold text-secondary">
                      #49 · Customer sync agent — stale embedding on 8 calls
                    </span>
                    <span className="ml-auto shrink-0 font-mono text-[10px] text-tertiary">just now</span>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Issue #47 — expanded */}
            <div className="border-b border-panel-border bg-white p-4">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 shrink-0 rounded-full border border-danger/30 bg-danger/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.1em] text-danger">
                  HIGH
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-black text-primary">
                    #47 · Refund agent loops after tool timeout
                  </div>
                  <div className="mt-2.5 grid grid-cols-2 gap-x-5 gap-y-1.5 text-xs text-secondary">
                    <div>
                      <span className="font-bold text-tertiary">Root cause  </span>
                      <span className="font-mono font-bold text-primary">stale policy chunk</span>
                    </div>
                    <div>
                      <span className="font-bold text-tertiary">Agent  </span>
                      <span className="font-mono font-bold text-primary">refund_agent</span>
                    </div>
                    <div>
                      <span className="font-bold text-tertiary">Calls  </span>
                      <span className="font-bold text-primary">43 affected</span>
                    </div>
                    <div>
                      <span className="font-bold text-tertiary">Waste  </span>
                      <span className="font-bold text-danger">$281 projected</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Issue #48 — collapsed */}
            <div className="flex items-center gap-3 border-b border-panel-border bg-canvas/60 px-4 py-3">
              <span className="shrink-0 rounded-full border border-warning/30 bg-warning/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.1em] text-warning">
                MED
              </span>
              <span className="min-w-0 truncate text-sm font-bold text-secondary">
                #48 · Weak evidence on customer sync workflow
              </span>
              <span className="ml-auto shrink-0 font-mono text-xs text-tertiary">2 calls</span>
            </div>

            {/* Verified replay result */}
            <div className="bg-canvas/60 p-4">
              <div className="overflow-hidden rounded-xl border border-gold/30 bg-white">
                <div className="flex items-center gap-2 border-b border-gold/20 bg-gold/5 px-4 py-2.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-gold" />
                  <span className="text-[10px] font-black uppercase tracking-[0.12em] text-gold">
                    Verified Replay · Issue #47
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 p-3">
                  <div className="rounded-lg border border-danger/20 bg-danger/5 px-3 py-2.5">
                    <div className="text-[10px] font-black uppercase tracking-[0.1em] text-tertiary">Before</div>
                    <div className="mt-1.5 font-mono text-[11px] font-bold text-danger">
                      4× retry loop · failed
                    </div>
                  </div>
                  <div className="rounded-lg border border-success/20 bg-success/5 px-3 py-2.5">
                    <div className="text-[10px] font-black uppercase tracking-[0.1em] text-tertiary">After</div>
                    <div className="mt-1.5 font-mono text-[11px] font-bold text-success">
                      resolved correctly ✓
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-3 border-t border-panel-border px-4 py-2.5">
                  <span className="text-xs font-bold text-secondary">
                    Fix PR ready · CI Golden queued
                  </span>
                  <div className="flex items-center gap-1.5 text-xs font-extrabold text-primary">
                    <GitBranch className="h-3.5 w-3.5" />
                    Open PR
                  </div>
                </div>
              </div>
            </div>

          </div>

          {/* Laptop stand */}
          <div className="mx-auto h-2.5 w-[86%] rounded-b-[2rem] border-x border-b border-panel-border bg-gradient-to-b from-slate-100 to-slate-200 shadow-sm" />
          <div className="mx-auto h-1.5 w-[44%] rounded-b-full bg-slate-300/60" />
        </motion.div>

      </div>
    </section>
  );
}
