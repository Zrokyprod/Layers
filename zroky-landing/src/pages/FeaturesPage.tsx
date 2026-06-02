import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  CircleDollarSign,
  GitBranch,
  MessageSquareText,
  PlayCircle,
  Shield,
} from 'lucide-react';

const features = [
  {
    icon: Bot,
    label: 'Agents Launchpad',
    headline: 'Every agent ranked by what matters.',
    body: 'One view across all your agents: health score, last issue, success rate, cost per successful task, replay coverage, and the recommended action. No manual aggregation — Zroky derives it from your real production data.',
    bullets: [
      'Real-time health across all agents',
      'Success rate and cost per workflow',
      'Replay coverage gap detection',
      'One-click issue creation from any agent',
    ],
    log: [
      'agent: refund_agent · health: DEGRADED',
      'last_issue: #47 · severity: HIGH',
      'success_rate: 61% · cost_per_task: $0.34',
      'replay_coverage: 0/1 issues verified',
    ],
  },
  {
    icon: AlertTriangle,
    label: 'Issue Command Queue',
    headline: 'One Issue instead of 43 scattered traces.',
    body: 'When the same failure pattern repeats, Zroky groups it into a plain-English Issue with root cause, blast radius, projected waste, owner, and recommended next action. No manual triage.',
    bullets: [
      'Automatic grouping by failure pattern',
      'Root cause with confidence scoring',
      'Projected waste and cost impact',
      'Owner assignment and resolution tracking',
    ],
    log: [
      'issue: #47 · severity: HIGH',
      'detector: tool_loop',
      'root_cause: stale policy chunk',
      'affected: 43 calls · waste: $281',
    ],
  },
  {
    icon: PlayCircle,
    label: 'Replay Proof Path',
    headline: 'Verified means the behavior actually changed.',
    body: 'A fix is only "verified" when a real_llm replay of the candidate against the original incident passes. Stub replays are clearly labeled "sanity check only" — they never show the verified badge.',
    bullets: [
      'real_llm, stub, mocked-tool, shadow modes',
      'Before/after behavioral comparison',
      'Verified badge only on real evidence',
      'Promote passing replay to CI Golden',
    ],
    log: [
      'mode: real_llm · status: passed',
      'original_behavior: failed (4× loop)',
      'candidate_behavior: resolved correctly',
      'verdict: VERIFIED ✓',
    ],
  },
  {
    icon: GitBranch,
    label: 'CI Golden Gates',
    headline: 'The same regression cannot ship twice.',
    body: 'Passed replays promote into Golden traces that run in CI before every deploy. If a candidate change breaks a Golden, the release is blocked. Production memory becomes a release gate.',
    bullets: [
      'Promote any verified replay to CI Golden',
      'Golden sets run before every deploy',
      'Release blocked on any Golden failure',
      'Flaky and blocking/advisory flags',
    ],
    log: [
      'golden_set: refund_agent_v2',
      'traces: 12 · status: all passing',
      'ci_gate: required · branch: main',
      'last_run: 2 hours ago · pass ✓',
    ],
  },
  {
    icon: CircleDollarSign,
    label: 'Cost of Failure',
    headline: 'Failed loops have a dollar figure attached.',
    body: 'Every Issue shows the projected cost of the failure — failed retries, wasted tokens, and high-cost loops — by workflow, agent, and owner. Teams can prioritize by blast radius, not just severity.',
    bullets: [
      'Projected waste per Issue',
      'Cost breakdown by workflow and agent',
      'Token usage and retry cost tracking',
      'Cost issue detection',
    ],
    log: [
      'issue: #47 · cost_impact: $281',
      'retry_loops: 43 × 4 retries',
      'tokens_wasted: 184k',
      'owner_team: agent-platform',
    ],
  },
  {
    icon: MessageSquareText,
    label: 'Ask Zroky',
    headline: 'Natural language Q&A backed by evidence.',
    body: 'Ask Zroky anything about your agents and get answers backed by real traces, issues, and replay results. If there is not enough data to answer, it says so — it never guesses.',
    bullets: [
      '"Why did this agent fail?" with root cause',
      '"What should we do next?" with replay action',
      'Answers link to issue, replay, and evidence',
      'Returns "not enough data" when honest',
    ],
    log: [
      'query: "why did refund agent fail?"',
      'evidence: issue #47 · 43 traces',
      'answer: stale policy chunk detected',
      'suggested_action: run replay candidate',
    ],
  },
];

export default function FeaturesPage() {
  return (
    <div className="w-full px-4 pb-24 pt-44 sm:px-5 lg:px-8">
      <div className="mx-auto max-w-[92rem]">

        {/* Header */}
        <div className="mx-auto max-w-2xl text-center">
          <span className="eyebrow justify-center">
            <Activity className="h-3.5 w-3.5 text-accent" />
            Platform features
          </span>
          <h1 className="mt-5 text-balance text-4xl font-black leading-tight text-primary md:text-6xl">
            Everything your team needs to own agent reliability.
          </h1>
          <p className="mt-5 text-lg leading-8 text-secondary">
            Six surfaces, one loop. From the first failure signal to the CI gate that prevents a repeat.
          </p>
          <div className="mt-8 flex justify-center gap-3">
            <a
              href="/auth/register"
              className="inline-flex min-h-12 items-center gap-2 rounded-full bg-primary px-6 py-3 text-sm font-extrabold text-white shadow-sm transition hover:bg-accent"
            >
              Get Started Free
              <ArrowRight className="h-4 w-4" />
            </a>
            <a
              href="/pricing"
              className="inline-flex min-h-12 items-center gap-2 rounded-full border border-panel-border bg-white px-6 py-3 text-sm font-extrabold text-primary shadow-sm transition hover:border-accent/40 hover:bg-accent/5"
            >
              See Pricing
            </a>
          </div>
        </div>

        {/* Feature sections */}
        <div className="mt-24 flex flex-col gap-24">
          {features.map((feat, i) => {
            const Icon = feat.icon;
            const flip = i % 2 !== 0;
            return (
              <motion.div
                key={feat.label}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-60px' }}
                transition={{ duration: 0.4 }}
                className={`grid items-center gap-12 lg:grid-cols-2 ${flip ? 'lg:grid-flow-dense' : ''}`}
              >
                {/* Copy */}
                <div className={flip ? 'lg:col-start-2' : ''}>
                  <div className="inline-flex items-center gap-2 rounded-full border border-panel-border bg-white px-3 py-1.5 text-[11px] font-extrabold uppercase tracking-[0.14em] text-secondary shadow-sm">
                    <Icon className="h-3.5 w-3.5 text-accent" />
                    {feat.label}
                  </div>
                  <h2 className="mt-5 text-balance text-3xl font-black leading-tight text-primary md:text-4xl">
                    {feat.headline}
                  </h2>
                  <p className="mt-4 text-lg leading-8 text-secondary">{feat.body}</p>
                  <div className="mt-6 grid gap-2.5">
                    {feat.bullets.map((b) => (
                      <div key={b} className="flex items-center gap-2.5 text-sm font-bold text-secondary">
                        <CheckCircle2 className="h-4 w-4 shrink-0 text-accent" />
                        {b}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Visual */}
                <div className={flip ? 'lg:col-start-1 lg:row-start-1' : ''}>
                  <div className="overflow-hidden rounded-[1.5rem] border border-panel-border bg-white shadow-premium">
                    <div className="flex items-center gap-2 border-b border-panel-border bg-canvas px-4 py-3">
                      <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
                      <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
                      <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
                      <span className="ml-2 font-mono text-xs font-bold text-tertiary">
                        {feat.label} · zroky.ai
                      </span>
                    </div>
                    <div className="divide-y divide-panel-border">
                      {feat.log.map((line) => (
                        <div key={line} className="px-5 py-3 font-mono text-[12px] font-bold text-secondary">
                          <span className="text-accent">{line.split(':')[0]}:</span>
                          {line.substring(line.indexOf(':') + 1)}
                        </div>
                      ))}
                    </div>
                    <div className="flex items-center gap-2 border-t border-panel-border bg-canvas px-5 py-3">
                      <Shield className="h-3.5 w-3.5 text-accent" />
                      <span className="text-xs font-bold text-secondary">Evidence-backed · Real data only</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Bottom CTA */}
        <div className="mt-24 overflow-hidden rounded-[1.5rem] border border-panel-border bg-primary p-10 text-center text-white shadow-premium">
          <h2 className="text-3xl font-black md:text-4xl">Ready to own your agent reliability?</h2>
          <p className="mt-4 text-lg font-bold text-slate-400">
            Start free. Connect your first agent in under 10 minutes.
          </p>
          <div className="mt-8 flex justify-center gap-3">
            <a
              href="/auth/register"
              className="inline-flex min-h-12 items-center gap-2 rounded-full bg-white px-8 py-3 text-sm font-extrabold text-primary transition hover:bg-gold/20 hover:text-white"
            >
              Get Started Free
              <ArrowRight className="h-4 w-4" />
            </a>
            <a
              href="/pricing"
              className="inline-flex min-h-12 items-center gap-2 rounded-full border border-white/20 bg-white/10 px-8 py-3 text-sm font-extrabold text-white transition hover:bg-white/20"
            >
              View Pricing
            </a>
          </div>
        </div>

      </div>
    </div>
  );
}
