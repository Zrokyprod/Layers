import { Bot, Brain, Code2, GitBranch, PlayCircle, Gauge, Shield, Users, Zap } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { motion } from 'framer-motion';

const integrations: { label: string; icon: LucideIcon }[] = [
  { label: 'LangGraph', icon: GitBranch },
  { label: 'CrewAI', icon: Users },
  { label: 'AutoGen', icon: Bot },
  { label: 'OpenAI SDK', icon: Brain },
  { label: 'Anthropic SDK', icon: Zap },
  { label: 'Custom agents', icon: Code2 },
  { label: 'Gateway capture', icon: Gauge },
];

const stats = [
  {
    value: '<5ms',
    label: 'Capture overhead',
    icon: Zap,
    body: 'SDK observes production runs without sitting in the critical path.',
    accent: 'text-accent',
    soft: 'bg-accent/8 border-accent/15',
  },
  {
    value: 'Verified',
    label: 'Replay standard',
    icon: PlayCircle,
    body: 'Stub replays are never counted as verified fixes. Labels are honest.',
    accent: 'text-gold',
    soft: 'bg-gold/8 border-gold/15',
  },
  {
    value: 'CI Goldens',
    label: 'Release safety',
    icon: GitBranch,
    body: 'Passed incidents become regression checks before risky changes ship.',
    accent: 'text-success',
    soft: 'bg-success/8 border-success/15',
  },
  {
    value: 'Scoped',
    label: 'Data control',
    icon: Shield,
    body: 'Incidents, replay proof, and release gates organized by project.',
    accent: 'text-accent',
    soft: 'bg-accent/8 border-accent/15',
  },
];

export default function Proof() {
  return (
    <section id="proof" className="relative w-full border-y border-panel-border bg-white py-14 md:py-16">
      <div className="mx-auto w-full max-w-[92rem] px-4 sm:px-5 lg:px-8">

        {/* Integrations strip */}
        <div className="flex flex-col items-center gap-5 text-center">
          <span className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-tertiary">
            Works with the agents your team already ships
          </span>
          <div className="flex flex-wrap justify-center gap-2">
            {integrations.map(({ label, icon: Icon }, i) => (
              <motion.span
                key={label}
                initial={{ opacity: 0, y: 8 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.28, delay: i * 0.06 }}
                whileHover={{ scale: 1.06 }}
                className="inline-flex items-center gap-2 rounded-full border border-panel-border bg-canvas px-4 py-2.5 text-xs font-extrabold text-secondary transition duration-200 hover:border-accent/30 hover:bg-accent/5 hover:text-primary cursor-default"
              >
                <Icon className="h-3.5 w-3.5 text-accent" />
                {label}
              </motion.span>
            ))}
          </div>
        </div>

        {/* Proof stat cards */}
        <div className="mt-12 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {stats.map((item, i) => {
            const Icon = item.icon;
            return (
              <motion.div
                key={item.label}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.35, delay: i * 0.08 }}
                whileHover={{ y: -4 }}
                className="group rounded-[1.25rem] border border-panel-border bg-white p-6 shadow-sm transition-shadow duration-200 hover:shadow-premium cursor-default"
              >
                <motion.div
                  whileHover={{ scale: 1.12 }}
                  transition={{ type: 'spring', stiffness: 300 }}
                  className={`inline-grid h-11 w-11 place-items-center rounded-2xl border ${item.soft} ${item.accent}`}
                >
                  <Icon className="h-5 w-5" />
                </motion.div>
                <div className={`mt-4 text-2xl font-black ${item.accent}`}>{item.value}</div>
                <div className="mt-1 text-[10px] font-black uppercase tracking-[0.14em] text-tertiary">
                  {item.label}
                </div>
                <p className="mt-3 text-sm leading-6 text-secondary">{item.body}</p>
              </motion.div>
            );
          })}
        </div>

      </div>
    </section>
  );
}
