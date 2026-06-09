import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

interface AuthLayoutProps {
  children: ReactNode;
  scene: ReactNode;
  tagline: string;
  caption: string;
}

function StarField() {
  const stars = Array.from({ length: 96 }, (_, i) => ({
    x: ((i * 157.3 + 47) % 100).toFixed(2),
    y: ((i * 113.7 + 23) % 100).toFixed(2),
    r: i % 7 === 0 ? 1.4 : i % 4 === 0 ? 1 : 0.4,
    op: (0.1 + (i % 7) * 0.05).toFixed(2),
    dur: (1.8 + (i % 5) * 0.7).toFixed(1),
  }));

  return (
    <svg className="absolute inset-0 h-full w-full" aria-hidden>
      {stars.map((s, i) => (
        <circle key={i} cx={`${s.x}%`} cy={`${s.y}%`} r={s.r} fill="white" opacity={s.op}>
          <animate
            attributeName="opacity"
            values={`${s.op};${(Number(s.op) * 0.25).toFixed(2)};${s.op}`}
            dur={`${s.dur}s`}
            repeatCount="indefinite"
          />
        </circle>
      ))}
    </svg>
  );
}

export default function AuthLayout({ children, scene, tagline, caption }: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen bg-black text-white">
      <div className="relative hidden flex-col overflow-hidden border-r border-white/[0.08] bg-black lg:flex lg:w-[52%] xl:w-[55%]">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_48%_22%,rgba(255,255,255,0.16),transparent_30%),linear-gradient(180deg,#000000_0%,#000000_100%)]" />
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-45" />
        <StarField />

        <div className="relative z-10 flex items-center p-8">
          <Link to="/">
            <img src="/logo.png" alt="Zroky" className="h-7" />
          </Link>
        </div>

        <div className="relative z-10 flex flex-1 items-center justify-center px-8">
          <motion.div
            initial={{ opacity: 0, scale: 0.92, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.7, ease: 'easeOut' }}
            className="w-full max-w-[460px]"
          >
            {scene}
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.35 }}
          className="relative z-10 p-8 pt-0"
        >
          <p className="text-lg font-semibold leading-snug text-white">{tagline}</p>
          <p className="mt-1.5 text-sm font-semibold leading-6 text-white/55">{caption}</p>
        </motion.div>
      </div>

      <div className="relative flex flex-1 flex-col items-center justify-center overflow-hidden bg-black px-4 py-10 sm:px-8">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(255,255,255,0.12),transparent_30%),linear-gradient(180deg,#000000_0%,#000000_100%)] lg:hidden" />
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-35 lg:hidden" />

        <div className="relative z-10 mb-8 lg:hidden">
          <Link to="/">
            <img src="/logo.png" alt="Zroky" className="h-8" />
          </Link>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 22 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.42, ease: 'easeOut' }}
          className="relative z-10 w-full max-w-[430px] rounded-lg border border-white/[0.12] bg-white/[0.035] p-5 shadow-[0_32px_120px_-82px_rgba(255,255,255,0.48)] backdrop-blur-xl sm:p-6"
        >
          {children}
        </motion.div>
      </div>
    </div>
  );
}
