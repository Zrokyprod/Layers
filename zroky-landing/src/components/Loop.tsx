import { motion } from 'framer-motion';
import { BadgeCheck, Database, GitBranch, PlayCircle, Radar } from 'lucide-react';

const steps = [
  {
    number: '01',
    label: 'Capture',
    title: 'Every production run, captured.',
    body: 'Wrap your agent with one SDK call. Prompts, tool calls, retrieval chunks, latency, cost, and outcome stay together in one trace.',
    tag: 'One SDK call. Complete context.',
    icon: Database,
    log: ['agent: refund_agent', 'workflow: refund_review', 'spans: 18', 'outcome: failed'],
  },
  {
    number: '02',
    label: 'Diagnose',
    title: 'Failures grouped into owned issues.',
    body: 'Repeated failures become one Issue with severity, root cause, blast radius, and a clear owner. No more chasing scattered traces.',
    tag: 'One issue instead of 43 traces.',
    icon: Radar,
    log: ['detector: tool_loop', 'severity: HIGH', 'affected: 43 calls', 'owner: agent-platform'],
  },
  {
    number: '03',
    label: 'Replay',
    title: 'Fix proven against the real incident.',
    body: 'Candidate fixes replay against the original failure. A passed replay means actual behavior improved — not just a passing unit test.',
    tag: 'Verified evidence. Not guesswork.',
    icon: PlayCircle,
    log: ['original: failed', 'candidate: passed', 'judge: verified', 'delta: behavior fixed'],
  },
  {
    number: '04',
    label: 'Gate',
    title: 'CI Golden blocks the regression.',
    body: 'Passed replays promote into Goldens that run in CI before every deploy. The same regression cannot slip through again.',
    tag: 'Production memory becomes a release gate.',
    icon: GitBranch,
    log: ['golden: promoted', 'ci_gate: required', 'fix_pr: opened', 'replay: attached'],
  },
];

export default function Loop() {
  return (
    <section id="product" className="relative w-full border-y border-panel-border bg-canvas py-24 md:py-28">
      <div className="mx-auto w-full max-w-[92rem] px-4 sm:px-5 lg:px-8">

        {/* Header */}
        <div className="mx-auto max-w-2xl">
          <span className="eyebrow">
            <BadgeCheck className="h-3.5 w-3.5 text-accent" />
            Product flow
          </span>
          <h2 className="mt-5 text-balance text-4xl font-black leading-tight text-primary md:text-5xl">
            Capture the failure. Prove the fix. Ship the PR.
          </h2>
          <p className="mt-5 text-lg leading-8 text-secondary">
            Four steps from production failure to verified fix and CI gate. Every step leaves evidence.
          </p>
        </div>

        {/* Steps grid */}
        <div className="mt-16 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {steps.map((step, index) => {
            const Icon = step.icon;
            return (
              <motion.div
                key={step.label}
                initial={{ opacity: 0, y: 18 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-60px' }}
                transition={{ duration: 0.36, delay: index * 0.06 }}
                className="flex flex-col overflow-hidden rounded-[1.5rem] border border-panel-border bg-white shadow-sm transition duration-300 hover:shadow-premium"
              >
                {/* Card header */}
                <div className="border-b border-panel-border bg-canvas px-5 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-xs font-black text-tertiary">{step.number}</span>
                    <span className="grid h-9 w-9 place-items-center rounded-xl border border-panel-border bg-white text-accent">
                      <Icon className="h-4 w-4" />
                    </span>
                  </div>
                  <div className="mt-3 text-[11px] font-black uppercase tracking-[0.14em] text-accent">
                    {step.label}
                  </div>
                  <h3 className="mt-1 text-lg font-black leading-tight text-primary">{step.title}</h3>
                </div>

                {/* Card body */}
                <div className="flex flex-1 flex-col px-5 py-4">
                  <p className="text-sm leading-6 text-secondary">{step.body}</p>
                  <div className="mt-4 rounded-xl border border-panel-border bg-canvas px-3 py-2 text-xs font-bold text-primary">
                    {step.tag}
                  </div>
                </div>

                {/* Evidence log — dark terminal, always at bottom */}
                <div className="border-t border-panel-border bg-[#101216] px-5 py-4">
                  <div className="mb-2 text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">
                    Evidence payload
                  </div>
                  {step.log.map((line) => (
                    <div key={line} className="mt-1 font-mono text-[11px] leading-5 text-slate-300">
                      {line}
                    </div>
                  ))}
                </div>
              </motion.div>
            );
          })}
        </div>

      </div>
    </section>
  );
}
