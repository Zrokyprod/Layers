import { ArrowRight } from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import { useEffect, useState, type ReactNode } from 'react';
import { SIGN_UP_URL } from '../../lib/links';

const ease = [0.16, 1, 0.3, 1] as const;
const loopSeconds = 6.2;

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

  return { progress };
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
            <stop stopColor="#20241e" stopOpacity="0.01" />
            <stop offset="0.22" stopColor="#20241e" stopOpacity="0.095" />
            <stop offset="0.5" stopColor="#20241e" stopOpacity="0.025" />
            <stop offset="0.78" stopColor="#20241e" stopOpacity="0.095" />
            <stop offset="1" stopColor="#20241e" stopOpacity="0.01" />
          </linearGradient>
          <linearGradient id="zroky-bifrost-signal" x1="60" y1="305" x2="1200" y2="305" gradientUnits="userSpaceOnUse">
            <stop stopColor="#3a747c" stopOpacity="0" />
            <stop offset="0.26" stopColor="#3a747c" stopOpacity="0.28" />
            <stop offset="0.5" stopColor="#3a747c" stopOpacity="0.045" />
            <stop offset="0.74" stopColor="#3a747c" stopOpacity="0.28" />
            <stop offset="1" stopColor="#3a747c" stopOpacity="0" />
          </linearGradient>
        </defs>

        <g stroke="#20241e" strokeLinecap="round" strokeLinejoin="round" opacity="0.14">
          <path d="M 346 220 L 398 190 L 452 220 L 400 250 Z" />
          <path d="M 346 220 V 370 L 400 402 V 250 Z" />
          <path d="M 452 220 V 370 L 400 402 V 250 Z" />
          <path d="M 372 238 L 400 222 L 428 238" />
          <path d="M 808 220 L 862 190 L 914 220 L 862 250 Z" />
          <path d="M 808 220 V 370 L 862 402 V 250 Z" />
          <path d="M 914 220 V 370 L 862 402 V 250 Z" />
          <path d="M 836 238 L 862 222 L 890 238" />
          <path d="M 806 414 C 846 406 880 423 880 462 C 880 492 850 507 820 488 C 802 476 810 452 838 462" />
          <path d="M 810 444 H 868 M 814 461 H 858 M 818 478 H 846" />
          <circle cx="398" cy="308" r="20" />
          <path d="M 386 308 L 396 318 L 412 296" />
          <path d="M 850 292 C 850 265 872 252 892 252 C 914 252 932 268 932 292" />
          <path d="M 836 292 H 946 V 352 H 836 Z" />
          <path d="M 886 318 H 896 V 338 H 886 Z" />
        </g>

        {ringRows.map((offset, index) => (
          <motion.path
            key={`left-lane-${offset}`}
            d={`M 28 ${305 + offset} C 96 ${305 + offset} 138 ${305 + offset * 0.74} 174 ${305 + offset * 0.38} C 202 ${305 + offset * 0.16} 216 305 ${leftRingX - 50} 305`}
            stroke="url(#zroky-bifrost-line)"
            strokeWidth="1"
            strokeDasharray={index % 3 === 0 ? '24 28' : index % 3 === 1 ? '3 38' : '1 46'}
            initial={false}
            animate={reduce ? { opacity: 0.34 } : { opacity: [0.14, 0.34, 0.14], pathLength: [0.9, 1, 0.9], strokeDashoffset: [0, -74] }}
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
            animate={reduce ? { opacity: 0.34 } : { opacity: [0.14, 0.34, 0.14], pathLength: [0.9, 1, 0.9], strokeDashoffset: [0, 74] }}
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
            strokeOpacity="0.28"
            strokeWidth="1.35"
            strokeLinecap="round"
            initial={false}
            animate={
              reduce
                ? { opacity: 0.32 }
                : {
                    x: [0, 132],
                    y: [0, -particle.offset * 0.62],
                    opacity: [0, 0.38, 0],
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
            strokeOpacity="0.28"
            strokeWidth="1.35"
            strokeLinecap="round"
            initial={false}
            animate={
              reduce
                ? { opacity: 0.32 }
                : {
                    x: [0, -132],
                    y: [0, -particle.offset * 0.62],
                    opacity: [0, 0.38, 0],
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
          animate={reduce ? { opacity: 0.48 } : { opacity: [0.22, 0.48, 0.22] }}
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
          animate={reduce ? { opacity: 0.48 } : { opacity: [0.22, 0.48, 0.22] }}
          transition={{ duration: 1.25, repeat: reduce ? 0 : Infinity, ease: 'easeInOut' }}
        />

        <g opacity="0.44">
          <motion.ellipse
            cx={leftRingX}
            cy="305"
            rx="54"
            ry="188"
            stroke="#20241e"
            strokeOpacity="0.15"
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
            strokeOpacity="0.085"
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
            strokeOpacity="0.14"
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
            strokeOpacity="0.15"
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
            strokeOpacity="0.085"
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
            strokeOpacity="0.14"
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

export default function Hero() {
  const { progress } = useHeroLoop();

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
        <div className="mx-auto min-w-0 max-w-[860px] text-center">
          <Reveal>
            <div className="inline-flex max-w-full items-center justify-center border border-[#ded9cf] bg-[#fbfaf6]/86 px-3 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.11em] text-[#3f433d] shadow-[0_1px_2px_rgba(17,20,15,0.04)] backdrop-blur sm:text-[11px] sm:tracking-[0.14em]">
              All your agents, one control layer
            </div>
          </Reveal>

          <Reveal delay={0.04}>
            <p className="mt-7 font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-[#3a747c]">[ Policy. Approval. Proof. ]</p>
          </Reveal>

          <Reveal delay={0.07}>
            <h1 className="mx-auto mt-3 max-w-[670px] text-[1.92rem] font-semibold leading-[1.03] tracking-[-0.02em] text-[#090b08] min-[380px]:text-[2.22rem] sm:text-[2.68rem] md:text-[3.12rem] lg:text-[3.5rem] lg:tracking-[-0.03em]">
              <span className="block">Deploy AI agents at scale</span>
              {' '}
              <span className="block">without losing control</span>
            </h1>
          </Reveal>

          <Reveal delay={0.13}>
            <p className="mx-auto mt-4 max-w-[610px] text-balance text-[0.84rem] leading-[1.58] text-[#5f635b] sm:text-[0.9rem] md:text-[0.94rem]">
              Zroky sits between agents and business systems to enforce approvals, scoped permissions, policy checks, and signed audit trails for every action.
            </p>
          </Reveal>

          <Reveal delay={0.19}>
            <div className="mx-auto mt-6 flex max-w-[24rem] justify-center">
              <a
                href={SIGN_UP_URL}
                className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-[10px] bg-[linear-gradient(180deg,#3a747c,#2f5f66)] px-7 font-mono text-[12px] font-semibold uppercase tracking-[0.08em] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_14px_30px_-18px_rgba(47,95,102,0.66)] transition hover:-translate-y-px active:scale-[0.98] sm:w-auto"
              >
                Get started <ArrowRight size={14} />
              </a>
            </div>
          </Reveal>

        </div>
      </div>
    </section>
  );
}
