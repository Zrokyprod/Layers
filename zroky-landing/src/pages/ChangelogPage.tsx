import { motion } from 'framer-motion';
import { ArrowRight, CheckCircle2, GitBranch, PlayCircle, Zap } from 'lucide-react';

const entries = [
  {
    version: 'v2.1.0',
    date: 'May 2025',
    badge: 'Release',
    badgeColor: 'bg-accent/10 text-accent border-accent/25',
    icon: PlayCircle,
    title: 'CI Golden gates in open beta — real LLM replay on production incidents',
    summary:
      'Replay Worker now supports real_llm mode. Candidate fixes run against actual LLM providers, not stubs, before the verified badge appears. CI Golden promotion from a passed real_llm replay is now production-ready.',
    items: [
      'real_llm replay mode available for all Pro+ workspaces',
      'Stub replays clearly labeled "sanity check only" — never counted as verified',
      'Promote any passing real_llm replay directly to CI Golden in one click',
      'Replay Worker OSS v2.1 published to GitHub and Docker Hub',
    ],
  },
  {
    version: 'v2.0.0',
    date: 'April 2025',
    badge: 'Major',
    badgeColor: 'bg-gold/10 text-gold border-gold/25',
    icon: Zap,
    title: 'Issue Command Queue — from scattered traces to one owned diagnosis',
    summary:
      'The Issues page is now the primary operating surface. Repeated failures are automatically grouped into Issues with severity, root cause, blast radius, cost impact, and recommended next action.',
    items: [
      'Automatic issue grouping across tool loops, schema failures, cost spikes, and provider drift',
      'Root cause attribution with confidence scoring (ablation engine)',
      'Ask Zroky — natural language Q&A backed by real evidence',
      'Issue ownership, resolution tracking, and accepted risk workflow',
      'Issues Command Queue replaces the old Anomalies list',
    ],
  },
  {
    version: 'v1.5.0',
    date: 'March 2025',
    badge: 'Release',
    badgeColor: 'bg-accent/10 text-accent border-accent/25',
    icon: GitBranch,
    title: 'Verified Fix PR workflow — replay proof attached to every fix',
    summary:
      'Candidate fixes now go through a structured replay workflow before the fix PR is opened. The PR carries the replay run ID, before/after comparison, and the Golden that will guard the regression.',
    items: [
      'Replay selector: stub, real_llm, mocked-tool, live-sandbox, shadow modes',
      'Verified fix badge only shows for real_llm and live-sandbox modes',
      'Fix PR opens with replay evidence attached automatically',
      'Golden promotion panel on every replay detail page',
    ],
  },
  {
    version: 'v1.2.0',
    date: 'February 2025',
    badge: 'Release',
    badgeColor: 'bg-accent/10 text-accent border-accent/25',
    icon: CheckCircle2,
    title: 'Agents Launchpad and CI Goldens page',
    summary:
      'Two new primary pages added. Agents Launchpad surfaces every agent with health, last issue, success rate, and replay coverage in one view. CI Goldens is now a real memory page, not a tab inside Calibration.',
    items: [
      'Agents Launchpad with per-agent health, cost, and recommended action',
      'Goldens page with set management, replay history, and pass/fail summary',
      'Run a full Golden set from the dashboard with real_llm executor',
      'Flaky and blocking/advisory flags per Golden trace',
    ],
  },
  {
    version: 'v1.0.0',
    date: 'January 2025',
    badge: 'Launch',
    badgeColor: 'bg-success/10 text-success border-success/25',
    icon: Zap,
    title: 'Zroky Pilot — public launch of the agent reliability platform',
    summary:
      'Zroky launches publicly. Capture, diagnose, replay, and gate — the full reliability loop for production AI agents. OSS SDK, Gateway, and Replay Worker available on GitHub.',
    items: [
      'Python SDK and JS SDK published to PyPI and npm',
      'Zroky Gateway — OpenAI-compatible proxy capture mode',
      'Replay Worker — open-source, self-hostable fix executor',
      'Zroky Dashboard — diagnosis, replay, and CI Golden control plane',
      'FSL-1.1-MIT license on all four OSS repos',
    ],
  },
];

export default function ChangelogPage() {
  return (
    <div className="w-full px-4 pb-24 pt-44 sm:px-5 lg:px-8">
      <div className="mx-auto max-w-[92rem]">

        {/* Header */}
        <div className="mx-auto max-w-2xl">
          <span className="eyebrow">What's new</span>
          <h1 className="mt-4 text-balance text-4xl font-black leading-tight text-primary md:text-5xl">
            Changelog
          </h1>
          <p className="mt-4 text-lg leading-8 text-secondary">
            Every release, fix, and feature shipped — with the evidence behind the decision.
          </p>
          <div className="mt-6 flex gap-3">
            <a
              href="https://github.com/zroky-ai"
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-11 items-center gap-2 rounded-full border border-panel-border bg-white px-5 py-2 text-sm font-extrabold text-primary shadow-sm transition hover:border-accent/40 hover:bg-accent/5"
            >
              Follow on GitHub
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>
        </div>

        {/* Timeline */}
        <div className="relative mt-16 ml-4 border-l border-panel-border pl-8 md:ml-8">
          {entries.map((entry, i) => {
            const Icon = entry.icon;
            return (
              <motion.div
                key={entry.version}
                initial={{ opacity: 0, x: -16 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: '-60px' }}
                transition={{ duration: 0.35, delay: i * 0.04 }}
                className="relative mb-14 last:mb-0"
              >
                {/* Timeline dot */}
                <span className="absolute -left-[2.85rem] grid h-9 w-9 place-items-center rounded-full border border-panel-border bg-white shadow-sm">
                  <Icon className="h-4 w-4 text-accent" />
                </span>

                <div className="overflow-hidden rounded-[1.5rem] border border-panel-border bg-white shadow-sm">
                  {/* Header */}
                  <div className="flex flex-col gap-3 border-b border-panel-border bg-canvas px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-3">
                      <span className={`rounded-full border px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.1em] ${entry.badgeColor}`}>
                        {entry.badge}
                      </span>
                      <span className="font-mono text-sm font-black text-primary">{entry.version}</span>
                    </div>
                    <span className="text-xs font-bold text-tertiary">{entry.date}</span>
                  </div>

                  {/* Body */}
                  <div className="px-6 py-6">
                    <h2 className="text-xl font-black text-primary md:text-2xl">{entry.title}</h2>
                    <p className="mt-3 text-sm leading-7 text-secondary">{entry.summary}</p>
                    <ul className="mt-5 grid gap-2">
                      {entry.items.map((item) => (
                        <li key={item} className="flex items-start gap-2.5 text-sm font-bold text-secondary">
                          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>

      </div>
    </div>
  );
}
