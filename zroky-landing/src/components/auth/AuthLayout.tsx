import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft } from 'lucide-react';
import type { ReactNode } from 'react';

interface AuthLayoutProps {
  children: ReactNode;
  scene: ReactNode;
  tagline: string;
  caption: string;
}

function StarField() {
  const stars = Array.from({ length: 100 }, (_, i) => ({
    x: ((i * 157.3 + 47) % 100).toFixed(2),
    y: ((i * 113.7 + 23) % 100).toFixed(2),
    r: i % 7 === 0 ? 1.5 : i % 4 === 0 ? 1 : 0.4,
    op: (0.12 + (i % 7) * 0.06).toFixed(2),
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
    <div className="flex min-h-screen">
      {/* Left — dark illustration panel */}
      <div className="relative hidden flex-col overflow-hidden bg-[#0b0d10] lg:flex lg:w-[52%] xl:w-[55%]">
        <StarField />

        {/* Top bar */}
        <div className="relative z-10 flex items-center justify-between p-8">
          <Link to="/">
            <img src="/zroky.logo.png" alt="Zroky" className="h-7 brightness-0 invert" />
          </Link>
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[11px] font-extrabold text-slate-400 transition duration-200 hover:bg-white/10 hover:text-white"
          >
            <ArrowLeft className="h-3 w-3" />
            Back to site
          </Link>
        </div>

        {/* Scene */}
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

        {/* Tagline */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.35 }}
          className="relative z-10 p-8 pt-0"
        >
          <p className="text-lg font-black leading-snug text-white">{tagline}</p>
          <p className="mt-1.5 text-sm font-bold text-slate-500">{caption}</p>
        </motion.div>
      </div>

      {/* Right — form panel */}
      <div className="flex flex-1 flex-col items-center justify-center bg-canvas px-4 py-12 sm:px-8">
        <div className="mb-8 lg:hidden">
          <Link to="/">
            <img src="/zroky.logo.png" alt="Zroky" className="h-7" />
          </Link>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 22 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.42, ease: 'easeOut' }}
          className="w-full max-w-[400px]"
        >
          {children}
        </motion.div>
      </div>
    </div>
  );
}
