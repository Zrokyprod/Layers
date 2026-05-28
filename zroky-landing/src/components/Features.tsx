import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  Bell,
  Bot,
  CheckCircle2,
  CircleDollarSign,
  GitPullRequest,
  MessageSquareText,
  PlayCircle,
  Shield,
  Star,
} from 'lucide-react';

const modules = [
  {
    label: 'Agents Launchpad',
    body: "See every agent's health, last issue, success rate, and replay coverage in one ranked view.",
    icon: Bot,
  },
  {
    label: 'Issue Command Queue',
    body: 'Repeated failures become one owned Issue with root cause, severity, cost impact, and next action.',
    icon: AlertTriangle,
  },
  {
    label: 'Verified Fix PR',
    body: 'Candidate patches carry diagnosis context, replay evidence, and the Golden that prevents a repeat.',
    icon: GitPullRequest,
  },
  {
    label: 'Replay Proof Path',
    body: 'Compare the original failure with candidate behavior before marking any fix as verified.',
    icon: PlayCircle,
  },
  {
    label: 'Cost of Failure',
    body: 'Failed loops, wasted tool calls, and high-cost retries surfaced by workflow and owner.',
    icon: CircleDollarSign,
  },
  {
    label: 'Ask Zroky',
    body: 'Natural-language Q&A backed by real evidence. Answers link to the issue, replay, and next action.',
    icon: MessageSquareText,
  },
];

const ossItems = [
  { label: 'zroky-sdk', desc: 'Python + JS SDK. Captures every agent run.' },
  { label: 'zroky-gateway', desc: 'OpenAI-compatible proxy. Gateway capture mode.' },
  { label: 'zroky-replay-worker', desc: 'Replay executor. Runs fixes against real incidents.' },
];

export default function Features() {
  return (
    <section id="command-center" className="relative w-full py-24 md:py-28">
      <div className="mx-auto w-full max-w-[92rem] px-4 sm:px-5 lg:px-8">

        {/* Header */}
        <div className="mx-auto max-w-2xl text-center">
          <span className="eyebrow justify-center">
            <Activity className="h-3.5 w-3.5 text-accent" />
            Command center
          </span>
          <h2 className="mt-5 text-balance text-4xl font-black leading-tight text-primary md:text-5xl">
            A command center for verified fixes, not alerts.
          </h2>
          <p className="mt-5 text-lg leading-8 text-secondary">
            Every page in Zroky is part of one operating loop — from the first failure signal to the CI gate that prevents a repeat.
          </p>
        </div>

        {/* 6-module grid */}
        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {modules.map((mod, index) => {
            const Icon = mod.icon;
            const accents = [
              'border-t-accent',
              'border-t-gold',
              'border-t-success',
              'border-t-accent',
              'border-t-gold',
              'border-t-success',
            ];
            return (
              <motion.div
                key={mod.label}
                initial={{ opacity: 0, y: 14 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ duration: 0.3, delay: index * 0.05 }}
                className={`group relative overflow-hidden rounded-[1.5rem] border border-panel-border border-t-[3px] bg-white p-6 shadow-sm transition duration-300 hover:shadow-premium ${accents[index]}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="grid h-11 w-11 place-items-center rounded-2xl border border-panel-border bg-canvas text-accent transition duration-200 group-hover:border-accent/30 group-hover:bg-accent/5">
                    <Icon className="h-5 w-5" />
                  </span>
                  <span className="font-mono text-[11px] font-black text-tertiary">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                </div>
                <h3 className="mt-4 text-base font-black text-primary">{mod.label}</h3>
                <p className="mt-2 text-sm leading-6 text-secondary">{mod.body}</p>
              </motion.div>
            );
          })}
        </div>

        {/* OSS vs Pilot split */}
        <div className="mt-6 grid gap-4 lg:grid-cols-2">

          {/* OSS panel */}
          <div className="overflow-hidden rounded-[1.5rem] border border-panel-border bg-white shadow-sm">
            <div className="border-b border-panel-border bg-canvas px-6 py-5">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Star className="h-4 w-4 text-accent" />
                  <span className="text-sm font-black text-primary">Open source data plane</span>
                </div>
                <span className="rounded-full border border-panel-border bg-white px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-tertiary">
                  FSL-1.1-MIT
                </span>
              </div>
              <p className="mt-1.5 text-xs font-bold text-secondary">
                SDK, Gateway, Replay Worker — free to use on any infrastructure.
              </p>
            </div>
            <div className="divide-y divide-panel-border">
              {ossItems.map((item) => (
                <div key={item.label} className="flex items-center gap-3 px-6 py-4">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-panel-border bg-canvas">
                    <Star className="h-3.5 w-3.5 text-accent" />
                  </span>
                  <div>
                    <div className="font-mono text-xs font-black text-primary">{item.label}</div>
                    <div className="text-xs font-bold text-secondary">{item.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Pilot panel */}
          <div className="overflow-hidden rounded-[1.5rem] border border-primary bg-primary shadow-premium">
            <div className="border-b border-white/10 px-6 py-5">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Shield className="h-4 w-4 text-gold" />
                  <span className="text-sm font-black text-white">Zroky Pilot — control plane</span>
                </div>
                <span className="rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-gold">
                  Paid
                </span>
              </div>
              <p className="mt-1.5 text-xs font-bold text-slate-400">
                Diagnosis, replay proof, CI gates, and team controls on top of the OSS data plane.
              </p>
            </div>
            <div className="divide-y divide-white/10">
              {[
                { label: 'Issue diagnosis', desc: 'Root cause + blast radius + owner', icon: Activity },
                { label: 'Replay proof', desc: 'Verified fix vs stub — labels are honest', icon: CheckCircle2 },
                { label: 'CI Goldens', desc: 'Regression gates from real incidents', icon: Shield },
                { label: 'Slack & Teams alerts', desc: 'Issue cards delivered to your on-call channel', icon: Bell },
                { label: 'Ask Zroky', desc: 'Evidence-backed natural language Q&A', icon: MessageSquareText },
              ].map(({ label, desc, icon: RowIcon }) => (
                <div key={label} className="flex items-center gap-3 px-6 py-4">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-white/10 bg-white/8">
                    <RowIcon className="h-3.5 w-3.5 text-gold" />
                  </span>
                  <div>
                    <div className="text-xs font-black text-white">{label}</div>
                    <div className="text-xs font-bold text-slate-400">{desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>
      </div>
    </section>
  );
}
