import { ArrowRight } from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import { useEffect, useState, type ReactNode } from 'react';
import { SIGN_UP_URL } from '../../lib/links';

const ease = [0.16, 1, 0.3, 1] as const;
const loopSeconds = 6.2;

const statusFrames = ['INTENT CAPTURED', 'APPROVAL REQUIRED', 'SOURCE MATCHED', 'RECEIPT SIGNED'] as const;

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

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function useHeroLoop() {
  const reduce = Boolean(useReducedMotion());
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (reduce) return undefined;
    const startedAt = performance.now();
    const id = window.setInterval(() => setElapsed((performance.now() - startedAt) / 1000), 80);
    return () => window.clearInterval(id);
  }, [reduce]);

  const progress = reduce ? loopSeconds - 0.1 : ((elapsed % loopSeconds) + loopSeconds) % loopSeconds;
  const frame = reduce ? statusFrames.length - 1 : Math.floor((progress / loopSeconds) * statusFrames.length) % statusFrames.length;

  return { reduce, progress, frame };
}

function BifrostRingScene({ progress }: { progress: number }) {
  const reduce = Boolean(useReducedMotion());
  const ringRows = [-142, -114, -88, -62, -38, -17, 0, 17, 38, 62, 88, 114, 142];
  const leftRingX = 236;
  const rightRingX = 1024;
  const token = reduce ? 1 : clamp((progress % loopSeconds) / loopSeconds, 0, 1);
  const leftTokenX = 42 + (leftRingX - 48 - 42) * token;
  const rightTokenX = 1218 - (1218 - (rightRingX + 48)) * token;

  const ringRibs = Array.from({ length: 38 }, (_, index) => {
    const t = -1.28 + (index / 37) * 2.56;
    return {
      y: 305 + Math.sin(t) * 182,
      depth: Math.cos(t),
    };
  });
  const particles = [-118, -84, -52, -22, 18, 48, 82, 118].map((offset, index) => ({
    offset,
    delay: index * 0.28,
    width: index % 3 === 0 ? 22 : 15,
  }));

  return (
    <div aria-hidden className="pointer-events-none absolute left-1/2 top-[6.6rem] z-0 hidden h-[610px] w-full max-w-[1260px] -translate-x-1/2 overflow-visible lg:block">
      <svg className="h-full w-full" viewBox="0 0 1260 610" fill="none" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="zroky-bifrost-line" x1="60" y1="305" x2="1200" y2="305" gradientUnits="userSpaceOnUse">
            <stop stopColor="#20241e" stopOpacity="0.02" />
            <stop offset="0.22" stopColor="#20241e" stopOpacity="0.24" />
            <stop offset="0.5" stopColor="#20241e" stopOpacity="0.045" />
            <stop offset="0.78" stopColor="#20241e" stopOpacity="0.24" />
            <stop offset="1" stopColor="#20241e" stopOpacity="0.02" />
          </linearGradient>
          <linearGradient id="zroky-bifrost-signal" x1="60" y1="305" x2="1200" y2="305" gradientUnits="userSpaceOnUse">
            <stop stopColor="#3a747c" stopOpacity="0" />
            <stop offset="0.26" stopColor="#3a747c" stopOpacity="0.9" />
            <stop offset="0.5" stopColor="#3a747c" stopOpacity="0.12" />
            <stop offset="0.74" stopColor="#3a747c" stopOpacity="0.9" />
            <stop offset="1" stopColor="#3a747c" stopOpacity="0" />
          </linearGradient>
        </defs>

        {ringRows.map((offset, index) => (
          <motion.path
            key={`left-lane-${offset}`}
            d={`M 28 ${305 + offset} C 96 ${305 + offset} 138 ${305 + offset * 0.74} 174 ${305 + offset * 0.38} C 202 ${305 + offset * 0.16} 216 305 ${leftRingX - 50} 305`}
            stroke="url(#zroky-bifrost-line)"
            strokeWidth="1"
            strokeDasharray={index % 3 === 0 ? '24 28' : index % 3 === 1 ? '3 38' : '1 46'}
            initial={false}
            animate={reduce ? { opacity: 0.75 } : { opacity: [0.4, 0.82, 0.4], pathLength: [0.9, 1, 0.9], strokeDashoffset: [0, -74] }}
            transition={{ duration: 4.9, repeat: reduce ? 0 : Infinity, ease: 'linear', delay: index * 0.045 }}
          />
        ))}
        {ringRows.map((offset, index) => (
          <motion.path
            key={`right-lane-${offset}`}
            d={`M 1232 ${305 + offset} C 1164 ${305 + offset} 1122 ${305 + offset * 0.74} 1086 ${305 + offset * 0.38} C 1058 ${305 + offset * 0.16} 1044 305 ${rightRingX + 50} 305`}
            stroke="url(#zroky-bifrost-line)"
            strokeWidth="1"
            strokeDasharray={index % 3 === 0 ? '24 28' : index % 3 === 1 ? '3 38' : '1 46'}
            initial={false}
            animate={reduce ? { opacity: 0.75 } : { opacity: [0.4, 0.82, 0.4], pathLength: [0.9, 1, 0.9], strokeDashoffset: [0, 74] }}
            transition={{ duration: 4.9, repeat: reduce ? 0 : Infinity, ease: 'linear', delay: index * 0.045 }}
          />
        ))}

        <motion.path
          d={`M 28 305 C 96 305 138 305 174 305 C 202 305 216 305 ${leftRingX - 50} 305`}
          stroke="url(#zroky-bifrost-signal)"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeDasharray="22 34"
          initial={false}
          animate={reduce ? { strokeDashoffset: 0 } : { strokeDashoffset: [0, -220] }}
          transition={{ duration: 4.4, repeat: reduce ? 0 : Infinity, ease: 'linear' }}
        />
        <motion.path
          d={`M 1232 305 C 1164 305 1122 305 1086 305 C 1058 305 1044 305 ${rightRingX + 50} 305`}
          stroke="url(#zroky-bifrost-signal)"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeDasharray="22 34"
          initial={false}
          animate={reduce ? { strokeDashoffset: 0 } : { strokeDashoffset: [0, 220] }}
          transition={{ duration: 4.4, repeat: reduce ? 0 : Infinity, ease: 'linear' }}
        />

        {particles.map((particle) => (
          <motion.line
            key={`left-particle-${particle.offset}`}
            x1="48"
            x2={48 + particle.width}
            y1={305 + particle.offset}
            y2={305 + particle.offset}
            stroke="#3a747c"
            strokeOpacity="0.52"
            strokeWidth="1.35"
            strokeLinecap="round"
            initial={false}
            animate={
              reduce
                ? { opacity: 0.32 }
                : {
                    x: [0, 132],
                    y: [0, -particle.offset * 0.62],
                    opacity: [0, 0.75, 0],
                  }
            }
            transition={{ duration: 2.9, repeat: reduce ? 0 : Infinity, ease: 'linear', delay: particle.delay }}
          />
        ))}
        {particles.map((particle) => (
          <motion.line
            key={`right-particle-${particle.offset}`}
            x1="1212"
            x2={1212 - particle.width}
            y1={305 + particle.offset}
            y2={305 + particle.offset}
            stroke="#3a747c"
            strokeOpacity="0.52"
            strokeWidth="1.35"
            strokeLinecap="round"
            initial={false}
            animate={
              reduce
                ? { opacity: 0.32 }
                : {
                    x: [0, -132],
                    y: [0, -particle.offset * 0.62],
                    opacity: [0, 0.75, 0],
                  }
            }
            transition={{ duration: 2.9, repeat: reduce ? 0 : Infinity, ease: 'linear', delay: particle.delay }}
          />
        ))}

        <motion.circle
          cx={leftTokenX}
          cy="305"
          r="4.5"
          fill="#3a747c"
          stroke="#fbfaf6"
          strokeWidth="4"
          initial={false}
          animate={reduce ? { opacity: 0.9 } : { opacity: [0.55, 1, 0.55] }}
          transition={{ duration: 1.25, repeat: reduce ? 0 : Infinity, ease: 'easeInOut' }}
        />
        <motion.circle
          cx={rightTokenX}
          cy="305"
          r="4.5"
          fill="#3a747c"
          stroke="#fbfaf6"
          strokeWidth="4"
          initial={false}
          animate={reduce ? { opacity: 0.9 } : { opacity: [0.55, 1, 0.55] }}
          transition={{ duration: 1.25, repeat: reduce ? 0 : Infinity, ease: 'easeInOut' }}
        />

        <g opacity="0.78">
          <motion.ellipse
            cx={leftRingX}
            cy="305"
            rx="54"
            ry="188"
            stroke="#20241e"
            strokeOpacity="0.22"
            strokeWidth="1.1"
            initial={false}
            animate={reduce ? { opacity: 0.78, rx: 54 } : { opacity: [0.62, 0.86, 0.62], rx: [54, 58, 54] }}
            transition={{ duration: 5.2, repeat: reduce ? 0 : Infinity, ease: 'easeInOut' }}
          />
          <motion.ellipse
            cx={leftRingX + 18}
            cy="305"
            rx="38"
            ry="164"
            stroke="#20241e"
            strokeOpacity="0.14"
            strokeWidth="1"
            initial={false}
            animate={reduce ? { opacity: 0.76, rx: 38 } : { opacity: [0.5, 0.82, 0.5], rx: [38, 41, 38] }}
            transition={{ duration: 4.7, repeat: reduce ? 0 : Infinity, ease: 'easeInOut', delay: 0.2 }}
          />
          <motion.ellipse
            cx={leftRingX + 43}
            cy="305"
            rx="24"
            ry="190"
            stroke="#20241e"
            strokeOpacity="0.22"
            strokeWidth="1.05"
            initial={false}
            animate={reduce ? { opacity: 0.82, rx: 24 } : { opacity: [0.58, 0.88, 0.58], rx: [24, 27, 24] }}
            transition={{ duration: 5.6, repeat: reduce ? 0 : Infinity, ease: 'easeInOut', delay: 0.35 }}
          />

          <motion.ellipse
            cx={rightRingX}
            cy="305"
            rx="54"
            ry="188"
            stroke="#20241e"
            strokeOpacity="0.22"
            strokeWidth="1.1"
            initial={false}
            animate={reduce ? { opacity: 0.78, rx: 54 } : { opacity: [0.62, 0.86, 0.62], rx: [54, 58, 54] }}
            transition={{ duration: 5.2, repeat: reduce ? 0 : Infinity, ease: 'easeInOut' }}
          />
          <motion.ellipse
            cx={rightRingX - 18}
            cy="305"
            rx="38"
            ry="164"
            stroke="#20241e"
            strokeOpacity="0.14"
            strokeWidth="1"
            initial={false}
            animate={reduce ? { opacity: 0.76, rx: 38 } : { opacity: [0.5, 0.82, 0.5], rx: [38, 41, 38] }}
            transition={{ duration: 4.7, repeat: reduce ? 0 : Infinity, ease: 'easeInOut', delay: 0.2 }}
          />
          <motion.ellipse
            cx={rightRingX - 43}
            cy="305"
            rx="24"
            ry="190"
            stroke="#20241e"
            strokeOpacity="0.22"
            strokeWidth="1.05"
            initial={false}
            animate={reduce ? { opacity: 0.82, rx: 24 } : { opacity: [0.58, 0.88, 0.58], rx: [24, 27, 24] }}
            transition={{ duration: 5.6, repeat: reduce ? 0 : Infinity, ease: 'easeInOut', delay: 0.35 }}
          />

          <motion.ellipse
            cx={leftRingX + 42}
            cy="305"
            rx="35"
            ry="208"
            stroke="#3a747c"
            strokeOpacity="0.11"
            strokeWidth="1"
            strokeDasharray="7 12 26 18"
            initial={false}
            animate={reduce ? { strokeDashoffset: 0, rx: 35 } : { strokeDashoffset: [0, -90], rx: [35, 39, 35] }}
            transition={{ duration: 9, repeat: reduce ? 0 : Infinity, ease: 'linear' }}
          />
          <motion.ellipse
            cx={rightRingX - 42}
            cy="305"
            rx="35"
            ry="208"
            stroke="#3a747c"
            strokeOpacity="0.11"
            strokeWidth="1"
            strokeDasharray="7 12 26 18"
            initial={false}
            animate={reduce ? { strokeDashoffset: 0, rx: 35 } : { strokeDashoffset: [0, 90], rx: [35, 39, 35] }}
            transition={{ duration: 9, repeat: reduce ? 0 : Infinity, ease: 'linear' }}
          />

          {ringRibs.map((rib, index) => (
            <motion.line
              key={`left-rib-${index}`}
              x1={leftRingX + 26 + Math.max(0, rib.depth) * 7}
              y1={rib.y}
              x2={leftRingX + 70 - Math.max(0, rib.depth) * 8}
              y2={rib.y + (index % 2 ? 1 : -1)}
              stroke={index % 5 === 0 ? '#3a747c' : '#20241e'}
              strokeOpacity={index % 5 === 0 ? '0.17' : '0.1'}
              strokeWidth="1"
              initial={false}
              animate={reduce ? { opacity: index % 5 === 0 ? 0.9 : 0.7 } : { opacity: index % 5 === 0 ? [0.52, 1, 0.52] : [0.35, 0.78, 0.35] }}
              transition={{ duration: 3.8, repeat: reduce ? 0 : Infinity, ease: 'easeInOut', delay: index * 0.035 }}
            />
          ))}
          {ringRibs.map((rib, index) => (
            <motion.line
              key={`right-rib-${index}`}
              x1={rightRingX - 26 - Math.max(0, rib.depth) * 7}
              y1={rib.y}
              x2={rightRingX - 70 + Math.max(0, rib.depth) * 8}
              y2={rib.y + (index % 2 ? 1 : -1)}
              stroke={index % 5 === 0 ? '#3a747c' : '#20241e'}
              strokeOpacity={index % 5 === 0 ? '0.17' : '0.1'}
              strokeWidth="1"
              initial={false}
              animate={reduce ? { opacity: index % 5 === 0 ? 0.9 : 0.7 } : { opacity: index % 5 === 0 ? [0.52, 1, 0.52] : [0.35, 0.78, 0.35] }}
              transition={{ duration: 3.8, repeat: reduce ? 0 : Infinity, ease: 'easeInOut', delay: index * 0.035 }}
            />
          ))}

          <motion.path
            d={`M ${leftRingX + 34} 178 L ${leftRingX + 52} 207 L ${leftRingX + 39} 238 L ${leftRingX + 60} 266 L ${leftRingX + 47} 302 L ${leftRingX + 63} 338 L ${leftRingX + 45} 386`}
            stroke="#20241e"
            strokeOpacity="0.12"
            strokeWidth="1"
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={false}
            animate={reduce ? { strokeDashoffset: 0 } : { strokeDashoffset: [0, -36] }}
            transition={{ duration: 6.5, repeat: reduce ? 0 : Infinity, ease: 'linear' }}
            strokeDasharray="18 18"
          />
          <motion.path
            d={`M ${rightRingX - 34} 178 L ${rightRingX - 52} 207 L ${rightRingX - 39} 238 L ${rightRingX - 60} 266 L ${rightRingX - 47} 302 L ${rightRingX - 63} 338 L ${rightRingX - 45} 386`}
            stroke="#20241e"
            strokeOpacity="0.12"
            strokeWidth="1"
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={false}
            animate={reduce ? { strokeDashoffset: 0 } : { strokeDashoffset: [0, 36] }}
            transition={{ duration: 6.5, repeat: reduce ? 0 : Infinity, ease: 'linear' }}
            strokeDasharray="18 18"
          />
        </g>
      </svg>
    </div>
  );
}

function CommandModule({ progress, frame }: { progress: number; frame: number }) {
  const reduce = Boolean(useReducedMotion());
  const command = 'zroky protect refund.create --policy finance.refund.v4';
  const receipt = 'receipt: zrk_rc_7f3a9e10';
  const commandChars = reduce ? command.length : Math.round(command.length * clamp((progress - 0.5) / 1.35, 0, 1));
  const receiptChars = reduce ? receipt.length : Math.round(receipt.length * clamp((progress - 3.45) / 1.2, 0, 1));
  const status = statusFrames[frame];

  return (
    <Reveal delay={0.27} className="mx-auto mt-6 w-full max-w-[430px]">
      <div className="relative border border-[#e2ded3] bg-[#fffefa]/92 px-4 py-4 text-left shadow-[0_22px_70px_-50px_rgba(23,25,22,0.62)] backdrop-blur">
        <span className="absolute -left-1.5 -top-1.5 h-3 w-3 border-l border-t border-[#cfc9bd]" />
        <span className="absolute -right-1.5 -top-1.5 h-3 w-3 border-r border-t border-[#cfc9bd]" />
        <span className="absolute -bottom-1.5 -left-1.5 h-3 w-3 border-b border-l border-[#cfc9bd]" />
        <span className="absolute -bottom-1.5 -right-1.5 h-3 w-3 border-b border-r border-[#cfc9bd]" />

        <p className="font-mono text-[12px] font-semibold text-[#3a747c]">/* Protected action. Verified outcome. */</p>
        <div className="mt-3 space-y-2 font-mono text-[13px] leading-relaxed text-[#20231f]">
          <p>
            <span className="text-[#3a747c]">$ </span>
            {command.slice(0, commandChars)}
            {!reduce && commandChars < command.length ? <span className="text-[#3a747c]">_</span> : null}
          </p>
          <p className="text-[#6d7068]">
            status: <span className="text-[#2f5f66]">{status}</span>
          </p>
          <p className="text-[#6d7068]">
            {receipt.slice(0, receiptChars)}
            {!reduce && receiptChars > 0 && receiptChars < receipt.length ? <span className="text-[#3a747c]">_</span> : null}
          </p>
        </div>
      </div>
    </Reveal>
  );
}

export default function Hero() {
  const { progress, frame } = useHeroLoop();

  return (
    <section
      className="relative w-full overflow-hidden px-3 pb-0 pt-24 text-[#11140f] sm:px-4 md:pt-32 lg:pt-36"
      style={{
        background: 'linear-gradient(180deg,#fbfaf6 0%,#f6f4ee 54%,#fbfaf6 100%)',
        fontFeatureSettings: "'ss01','cv01'",
      }}
    >
      <BifrostRingScene progress={progress} />

      <div className="relative z-10 mx-auto min-w-0 max-w-[1260px]">
        <div className="mx-auto min-w-0 max-w-[1040px] text-center">
          <Reveal>
            <div className="inline-flex max-w-full items-center justify-center border border-[#ded9cf] bg-[#fbfaf6]/86 px-3 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.11em] text-[#3f433d] shadow-[0_1px_2px_rgba(17,20,15,0.04)] backdrop-blur sm:text-[11px] sm:tracking-[0.14em]">
              Enterprise AI agent action control plane
            </div>
          </Reveal>

          <Reveal delay={0.04}>
            <p className="mt-7 font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-[#3a747c]">[ Intercept. Authorize. Verify. ]</p>
          </Reveal>

          <Reveal delay={0.07}>
            <h1 className="mx-auto mt-3 max-w-[980px] text-[1.92rem] font-semibold leading-[1.03] tracking-[-0.02em] text-[#090b08] min-[380px]:text-[2.22rem] sm:text-[2.68rem] md:text-[3.12rem] lg:text-[3.5rem] lg:tracking-[-0.03em]">
              <span className="block">Scale AI agents across your enterprise.</span>
              {' '}
              <span className="block">Control every action they take.</span>
            </h1>
          </Reveal>

          <Reveal delay={0.13}>
            <p className="mx-auto mt-4 max-w-[850px] text-balance text-[0.84rem] leading-[1.58] text-[#5f635b] sm:text-[0.9rem] md:text-[0.94rem]">
              Zroky intercepts agent tool calls before they reach business systems, enforces policy and approvals, verifies outcomes in systems of record, and issues a signed receipt for every protected action.
            </p>
          </Reveal>

          <Reveal delay={0.19}>
            <div className="mx-auto mt-6 flex max-w-[24rem] justify-center">
              <a
                href={SIGN_UP_URL}
                className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-[10px] bg-[linear-gradient(180deg,#3a747c,#2f5f66)] px-7 font-mono text-[12px] font-semibold uppercase tracking-[0.08em] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_14px_30px_-18px_rgba(47,95,102,0.66)] transition hover:-translate-y-px active:scale-[0.98] sm:w-auto"
              >
                Protect your first agent <ArrowRight size={14} />
              </a>
            </div>
          </Reveal>

          <CommandModule progress={progress} frame={frame} />
        </div>
      </div>
    </section>
  );
}
