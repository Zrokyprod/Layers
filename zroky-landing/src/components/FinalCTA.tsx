import { ArrowRight, Github } from 'lucide-react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';

const DOTS = [
  { x: '5%',  y: '20%', s: 6,  dur: 8,  delay: 0   },
  { x: '15%', y: '70%', s: 4,  dur: 11, delay: 1.5 },
  { x: '88%', y: '15%', s: 5,  dur: 9,  delay: 0.7 },
  { x: '93%', y: '65%', s: 7,  dur: 7,  delay: 2   },
  { x: '50%', y: '85%', s: 4,  dur: 10, delay: 1   },
  { x: '75%', y: '8%',  s: 5,  dur: 8,  delay: 2.5 },
];

export default function FinalCTA() {
  return (
    <section className="relative w-full overflow-hidden border-t border-panel-border bg-primary py-24 md:py-28">

      {/* Ambient floating dots */}
      {DOTS.map((d, i) => (
        <motion.div
          key={i}
          aria-hidden
          className="pointer-events-none absolute rounded-full bg-white/10"
          style={{ left: d.x, top: d.y, width: d.s, height: d.s }}
          animate={{ y: [0, -(d.s * 14), 0], opacity: [0.15, 0.5, 0.15] }}
          transition={{ duration: d.dur, delay: d.delay, repeat: Infinity, ease: 'easeInOut' }}
        />
      ))}

      <div className="relative mx-auto w-full max-w-[92rem] px-4 sm:px-5 lg:px-8">

        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="mx-auto max-w-3xl text-center"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.4 }}
            className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-[11px] font-extrabold uppercase tracking-[0.16em] text-gold"
          >
            Start free today
          </motion.div>

          <h2 className="mt-6 text-balance text-4xl font-black leading-tight text-white md:text-6xl">
            Start capturing production failures today.
          </h2>

          <p className="mt-6 text-lg leading-8 text-slate-300">
            Connect in minutes. First 10 issues free, forever.
            No credit card. OSS data plane you can self-host.
          </p>

          <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
            {/* Glow-pulse primary CTA */}
            <motion.a
              href="/auth/register"
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              animate={{
                boxShadow: [
                  '0 0 0px 0px rgba(255,255,255,0)',
                  '0 0 28px 10px rgba(255,255,255,0.10)',
                  '0 0 0px 0px rgba(255,255,255,0)',
                ],
              }}
              transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
              className="inline-flex min-h-14 items-center gap-2 rounded-full bg-white px-8 py-3 text-base font-extrabold text-primary shadow-sm focus:outline-none focus:ring-2 focus:ring-gold/40"
            >
              Get Started Free
              <ArrowRight className="h-5 w-5" />
            </motion.a>
            <motion.a
              href="https://github.com/zroky-ai"
              target="_blank"
              rel="noreferrer"
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              className="inline-flex min-h-14 items-center gap-2 rounded-full border border-white/20 bg-white/8 px-8 py-3 text-base font-extrabold text-white transition duration-200 hover:border-white/40 hover:bg-white/15 focus:outline-none focus:ring-2 focus:ring-white/20"
            >
              <Github className="h-5 w-5" />
              View on GitHub
            </motion.a>
          </div>

          <p className="mt-6 text-sm font-bold text-slate-500">
            Free tier forever · OSS SDK + Gateway · No vendor lock-in
          </p>
        </motion.div>

        {/* Stat strip — stagger */}
        <div className="mt-16 grid grid-cols-2 gap-px overflow-hidden rounded-[1.5rem] bg-white/10 md:grid-cols-4">
          {[
            ['<5ms', 'Capture overhead'],
            ['1 decorator', 'Integration effort'],
            ['Verified', 'Replay standard'],
            ['CI Goldens', 'Regression protection'],
          ].map(([value, label], i) => (
            <motion.div
              key={label}
              initial={{ opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.35, delay: i * 0.08 }}
              className="bg-primary px-6 py-6 text-center"
            >
              <div className="text-2xl font-black text-white">{value}</div>
              <div className="mt-1 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{label}</div>
            </motion.div>
          ))}
        </div>

        {/* Talk to us */}
        <div className="mt-8 flex flex-col items-center gap-3 text-center sm:flex-row sm:justify-center">
          <p className="text-sm font-bold text-slate-400">
            Building something larger? Need a guided rollout?
          </p>
          <Link
            to="/pricing"
            className="inline-flex items-center gap-1.5 text-sm font-extrabold text-gold hover:underline"
          >
            See Team plan
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

      </div>
    </section>
  );
}
