import { type ReactNode } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import {
  ArrowRight,
  Check,
  Code2,
  ExternalLink,
  GitBranch,
  Github,
  KeyRound,
  Layers,
  PlayCircle,
  Route,
  ShieldCheck,
  Terminal,
  Workflow,
  Zap,
} from 'lucide-react';
import { docsNav } from './docs/docsContent';
import { SIGN_UP_URL } from '../lib/links';

const pythonSnippet = `import os
import openai
import zroky

zroky.init(
    api_key=os.environ["ZROKY_API_KEY"],
    project=os.environ["ZROKY_PROJECT"],
    agent_framework="custom-python",
    environment="production",
)

response = zroky.call(
    provider="openai",
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Summarize this refund request"}],
    _client=openai.OpenAI(),
)`;

const typescriptSnippet = `import OpenAI from "openai";
import { init, wrap } from "@zroky-ai/sdk";

init({
  projectId: process.env.ZROKY_PROJECT_ID,
  apiKey: process.env.ZROKY_API_KEY,
});

const openai = wrap(new OpenAI(), {
  agentName: "support-agent",
  workflowId: "refund-review",
  environment: "production",
});

const response = await openai.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "Summarize this refund request" }],
});`;

const gatewaySnippet = `docker run -d \\
  -p 8090:8090 \\
  -e ZROKY_EMIT_MODE=http \\
  -e ZROKY_API_URL=https://api.zroky.com \\
  -e ZROKY_INGEST_URL=https://api.zroky.com/api/v1/ingest \\
  -e ZROKY_GATEWAY_API_KEY=$ZROKY_GATEWAY_API_KEY \\
  ghcr.io/zroky-ai/zroky-gateway:latest

export OPENAI_BASE_URL=http://localhost:8090/v1`;

const ciActionSnippet = [
  'name: Zroky Regression CI',
  'on:',
  '  pull_request:',
  '    branches: [main]',
  '',
  'jobs:',
  '  replay-ci:',
  '    runs-on: ubuntu-latest',
  '    permissions:',
  '      pull-requests: write',
  '    steps:',
  '      - uses: actions/checkout@v4',
  '      - uses: zroky/regression-ci@v1',
  '        with:',
  '          api_key: ${{ secrets.ZROKY_API_KEY }}',
  '          project_id: ${{ vars.ZROKY_PROJECT_ID }}',
  '          post_pr_comment: true',
  '          fail_on_regression: true',
  '        env:',
  '          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}',
].join('\n');

const capturePaths = [
  {
    icon: Terminal,
    title: 'Python SDK',
    body: 'Instrument Python agents directly when your team controls the runtime and wants capture close to the provider call.',
    signal: 'zroky.init + zroky.call',
    href: '/docs/python-sdk',
  },
  {
    icon: Code2,
    title: 'TypeScript SDK',
    body: 'Wrap the OpenAI client in Node, Next.js, or agent services so traces and failures stay attached to the workflow.',
    signal: 'init + wrap',
    href: '/docs/typescript-sdk',
  },
  {
    icon: Route,
    title: 'Gateway',
    body: 'Route OpenAI-compatible traffic through Zroky when you need capture without changing every agent implementation.',
    signal: 'proxy capture',
    href: '/docs/gateway',
  },
];

const timeline = [
  {
    icon: Zap,
    label: 'Capture',
    body: 'SDK or Gateway sends production calls, prompt context, tool path, latency, and cost evidence.',
  },
  {
    icon: Workflow,
    label: 'Diagnose',
    body: 'Zroky identifies the failure mode, affected workflow, prompt fingerprint, and evidence trail.',
  },
  {
    icon: Layers,
    label: 'Issue',
    body: 'Repeated failures become one diagnosis queue with ownership, impact, and replay candidates.',
  },
  {
    icon: PlayCircle,
    label: 'Replay',
    body: 'Run stub checks for sanity, then verified replay against the original incident before trusting a fix.',
  },
  {
    icon: ShieldCheck,
    label: 'Golden',
    body: 'Promote passing replay proof into release memory so the fixed incident keeps protecting future changes.',
  },
  {
    icon: GitBranch,
    label: 'CI Gate',
    body: 'Run Goldens in CI and block the same agent failure before it reaches users again.',
  },
];

const codePanels = [
  {
    id: 'sdk',
    icon: Terminal,
    label: 'Python SDK',
    title: 'Capture a production call from Python.',
    body: 'Initialize Zroky once, then capture the provider call with the project and workflow context your release process needs.',
    language: 'python',
    code: pythonSnippet,
  },
  {
    id: 'typescript-sdk',
    icon: Code2,
    label: 'TypeScript SDK',
    title: 'Wrap the client used by your agent service.',
    body: 'Use the same provider client, but send Zroky enough context to connect traces, issues, replay proof, and CI gates.',
    language: 'ts',
    code: typescriptSnippet,
  },
  {
    id: 'gateway',
    icon: Route,
    label: 'Gateway Docker',
    title: 'Proxy compatible traffic through Zroky.',
    body: 'Run the Gateway near your service and point compatible provider traffic at it when SDK changes are not the fastest path.',
    language: 'bash',
    code: gatewaySnippet,
  },
  {
    id: 'ci-gate',
    icon: GitBranch,
    label: 'GitHub Action',
    title: 'Run replay proof in pull requests.',
    body: 'Attach promoted Goldens to CI so production incidents can become pass or block decisions before deploy.',
    language: 'yaml',
    code: ciActionSnippet,
  },
];

const providerRules = [
  {
    icon: Check,
    title: 'Capture first',
    body: 'Signup, capture, traces, issues, and basic dashboard review stay usable before a provider key is connected.',
  },
  {
    icon: KeyRound,
    title: 'BYOK for verified replay',
    body: 'Verified replay uses your provider account so model spend remains visible, auditable, and controlled by your team.',
  },
  {
    icon: PlayCircle,
    title: 'Stub replay stays available',
    body: 'Stub replay remains a sanity-only path when you want structure checks without a real model call.',
  },
];

const references = [
  {
    icon: Terminal,
    title: 'Python SDK path',
    body: 'Install, initialize, and capture provider calls in Python agent services.',
    href: 'https://github.com/zroky-ai/zroky-sdk',
  },
  {
    icon: Code2,
    title: 'TypeScript SDK path',
    body: 'Wrap Node and browser-adjacent agent clients with workflow context.',
    href: 'https://github.com/zroky-ai/zroky-sdk-js',
  },
  {
    icon: Route,
    title: 'Gateway path',
    body: 'Deploy a compatible proxy for teams that want routing-level capture.',
    href: 'https://github.com/zroky-ai/zroky-gateway',
  },
  {
    icon: GitBranch,
    title: 'CI gate path',
    body: 'Run promoted Goldens in pull requests with regression blocking.',
    href: 'https://github.com/zroky-ai/zroky-regression-ci-action',
  },
];

const revealEase = [0.16, 1, 0.3, 1] as const;

function SectionReveal({
  className,
  children,
  delay = 0,
}: {
  className?: string;
  children: ReactNode;
  delay?: number;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.section
      initial={reduceMotion ? false : { opacity: 0, y: 22 }}
      whileInView={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.14, margin: '-80px' }}
      transition={{ duration: 0.52, delay, ease: revealEase }}
      className={className}
    >
      {children}
    </motion.section>
  );
}

function SectionHeader({
  label,
  title,
  body,
  align = 'left',
}: {
  label: string;
  title: string;
  body: string;
  align?: 'left' | 'center';
}) {
  return (
    <div className={align === 'center' ? 'mx-auto max-w-3xl text-center' : 'max-w-3xl'}>
      <span className="eyebrow">
        <span className="h-1.5 w-1.5 rounded-full bg-primary" />
        {label}
      </span>
      <h2 className="mt-5 text-balance text-3xl font-semibold leading-tight text-primary sm:text-4xl lg:text-5xl">{title}</h2>
      <p className="mt-4 text-base leading-8 text-secondary sm:text-lg">{body}</p>
    </div>
  );
}

function CodePanel({ panel }: { panel: (typeof codePanels)[number] }) {
  const Icon = panel.icon;

  return (
    <article id={panel.id} className="card scroll-mt-28 overflow-hidden p-0">
      <div className="border-b border-line bg-white/[0.03] p-4 sm:p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <span className="inline-flex items-center gap-2 rounded-full border border-line bg-white/[0.04] px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-secondary">
              <Icon className="h-3.5 w-3.5" />
              {panel.label}
            </span>
            <h3 className="mt-4 text-xl font-semibold leading-tight text-primary sm:text-2xl">{panel.title}</h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-secondary">{panel.body}</p>
          </div>
          <span className="w-fit shrink-0 rounded-md border border-line bg-ink px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-tertiary">
            {panel.language}
          </span>
        </div>
      </div>
      <div className="max-w-full bg-ink p-4 sm:p-5">
        <pre className="max-w-full overflow-x-auto whitespace-pre-wrap break-words font-mono text-[12px] leading-6 text-secondary">
          <code className="block max-w-full">{panel.code}</code>
        </pre>
      </div>
    </article>
  );
}

export default function DocsPage() {
  const reduceMotion = useReducedMotion();

  return (
    <div className="w-full overflow-x-hidden">
      <section className="relative isolate border-b border-line px-4 pb-14 pt-40 sm:px-6 sm:pb-20 sm:pt-44 lg:px-8">
        <div className="pointer-events-none absolute inset-0 -z-10">
          <div className="grid-bg absolute inset-x-0 top-0 h-[34rem] opacity-70" />
          <motion.div
            aria-hidden="true"
            animate={reduceMotion ? undefined : { rotate: 360 }}
            transition={{ duration: 38, repeat: Infinity, ease: 'linear' }}
            className="absolute left-1/2 top-24 h-72 w-72 -ml-36 rounded-full border border-line bg-[conic-gradient(from_120deg,transparent,rgba(255,255,255,0.18),transparent,rgba(255,255,255,0.1),transparent)] blur-2xl"
          />
        </div>

        <div className="mx-auto grid max-w-[92rem] items-center gap-10 lg:grid-cols-[1.02fr_0.98fr]">
          <div>
            <span className="eyebrow">
              <Workflow className="h-3.5 w-3.5" />
              AI Agent Regression Firewall docs
            </span>
            <h1 className="mt-6 max-w-5xl text-balance text-4xl font-semibold leading-[1.04] text-primary sm:text-6xl lg:text-7xl">
              Stop shipping the same agent failure twice.
            </h1>
            <p className="mt-6 max-w-3xl text-base leading-8 text-secondary sm:text-lg">
              Follow the same product loop everywhere: capture, diagnose, issue, replay, Golden, and CI gate. Provider keys appear only when verified replay needs to run.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <a href="/docs/quickstart" className="btn-primary">
                Start with SDK
                <ArrowRight className="h-4 w-4" />
              </a>
              <a href="/docs/gateway" className="btn-ghost">
                Use Gateway
                <Route className="h-4 w-4" />
              </a>
              <a href="/docs/ci-gates" className="btn-ghost">
                Add CI gate
                <GitBranch className="h-4 w-4" />
              </a>
            </div>
          </div>

          <motion.div
            initial={reduceMotion ? false : { opacity: 0, y: 18 }}
            animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
            transition={{ duration: 0.58, ease: revealEase }}
            className="browser-frame"
          >
            <div className="browser-bar">
              <span className="browser-dot" />
              <span className="browser-dot" />
              <span className="browser-dot" />
              <span className="ml-2 truncate rounded-md border border-line bg-ink px-3 py-1 font-mono text-[11px] text-tertiary">
                docs.zroky.com/quickstart
              </span>
            </div>
            <div className="bg-ink-2 p-4 sm:p-5">
              <div className="rounded-xl border border-line bg-ink p-4">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-tertiary">failure-to-release</span>
                  <span className="badge badge-verified">verified</span>
                </div>
                <div className="grid gap-2">
                  {['capture incident', 'diagnose failure', 'create issue', 'run replay', 'promote golden', 'run CI gate'].map(
                    (item, index) => (
                      <div key={item} className="flex items-center gap-3 rounded-lg border border-line bg-white/[0.03] px-3 py-2.5">
                        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md border border-line bg-white/[0.04] font-mono text-[10px] text-secondary">
                          {index + 1}
                        </span>
                        <span className="font-mono text-xs text-secondary">{item}</span>
                      </div>
                    ),
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      <SectionReveal className="px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <SectionHeader
            label="Capture paths"
            title="Choose the path that matches how your agent already runs."
            body="Start with the smallest integration that gets production evidence into Zroky. The replay and CI workflow can follow after capture is working."
          />
          <div className="mt-8 grid gap-4 lg:grid-cols-3">
            {capturePaths.map((path) => {
              const Icon = path.icon;
              return (
                <a key={path.title} href={path.href} className="card group p-5">
                  <div className="flex items-start justify-between gap-4">
                    <span className="grid h-11 w-11 place-items-center rounded-xl border border-line bg-white/[0.04]">
                      <Icon className="h-5 w-5 text-primary" />
                    </span>
                    <span className="rounded-full border border-line bg-white/[0.04] px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-secondary">
                      {path.signal}
                    </span>
                  </div>
                  <h3 className="mt-5 text-xl font-semibold text-primary">{path.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-secondary">{path.body}</p>
                  <span className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-primary">
                    View setup
                    <ArrowRight className="h-4 w-4 transition duration-200 group-hover:translate-x-0.5" />
                  </span>
                </a>
              );
            })}
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="border-y border-line px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <SectionHeader
            label="Complete docs path"
            title="Follow the product in the same order teams adopt it."
            body="Each guide is built around one job in the contract: capture evidence, diagnose it, group the issue, replay the candidate, promote the Golden, then let CI protect the release."
          />
          <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {docsNav.map((item, index) => (
              <a key={item.slug} href={`/docs/${item.slug}`} className="card group p-4">
                <div className="flex items-center justify-between gap-4">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-tertiary">0{index + 1}</span>
                  <span className="rounded-md border border-line bg-ink px-2 py-1 text-[10px] font-semibold text-tertiary">
                    {item.category}
                  </span>
                </div>
                <h3 className="mt-4 text-base font-semibold leading-6 text-primary">{item.title}</h3>
                <span className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-primary">
                  Open guide
                  <ArrowRight className="h-4 w-4 transition duration-200 group-hover:translate-x-0.5" />
                </span>
              </a>
            ))}
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <SectionHeader
            label="Quickstart"
            title="The adoption path is capture first, then release protection."
            body="Zroky does not need to interrupt signup or basic inspection with provider credentials. Keys appear only when real replay proof is required."
          />
          <div className="mt-10 grid gap-3 lg:grid-cols-6">
            {timeline.map((item, index) => {
              const Icon = item.icon;
              return (
                <div key={item.label} className="card relative p-4">
                  {index < timeline.length - 1 && (
                    <div className="pointer-events-none absolute -right-3 top-8 hidden h-px w-3 bg-line-strong lg:block" />
                  )}
                  <div className="flex items-center justify-between gap-3">
                    <span className="grid h-10 w-10 place-items-center rounded-xl border border-line bg-white/[0.04]">
                      <Icon className="h-5 w-5 text-primary" />
                    </span>
                    <span className="font-mono text-[10px] uppercase tracking-wider text-tertiary">0{index + 1}</span>
                  </div>
                  <h3 className="mt-4 text-base font-semibold text-primary">{item.label}</h3>
                  <p className="mt-2 text-xs leading-5 text-tertiary">{item.body}</p>
                </div>
              );
            })}
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <SectionHeader
            label="Code-first setup"
            title="Four setup panels cover the full failure loop."
            body="Use SDK capture for application code, Gateway capture for routing-level adoption, and CI replay when verified incidents become release gates."
          />
          <div className="mt-9 grid gap-5 xl:grid-cols-2">
            {codePanels.map((panel) => (
              <CodePanel key={panel.id} panel={panel} />
            ))}
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="border-y border-line px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <div className="mx-auto grid max-w-[92rem] gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-start">
          <SectionHeader
            label="Provider key rule"
            title="Provider keys are for verified replay, not for getting started."
            body="Capture works without a model provider key. When your team chooses verified replay, Zroky asks for the key at the replay moment so model spend stays visible in your provider account."
          />
          <div className="grid gap-4">
            {providerRules.map((rule) => {
              const Icon = rule.icon;
              return (
                <div key={rule.title} className="card p-5">
                  <div className="flex gap-4">
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-line bg-white/[0.04]">
                      <Icon className="h-5 w-5 text-primary" />
                    </span>
                    <div>
                      <h3 className="text-lg font-semibold text-primary">{rule.title}</h3>
                      <p className="mt-2 text-sm leading-6 text-secondary">{rule.body}</p>
                    </div>
                  </div>
                </div>
              );
            })}
            <div className="rounded-2xl border border-line bg-ink p-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="max-w-2xl text-sm font-semibold leading-6 text-primary">
                  Real replay modes, Golden replay, and CI replay require an active provider key. Stub replay remains sanity-only.
                </p>
                <a href="/pricing" className="btn-ghost shrink-0">
                  See replay pricing
                  <ArrowRight className="h-4 w-4" />
                </a>
              </div>
            </div>
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <div className="mx-auto max-w-[92rem]">
          <SectionHeader
            label="Reference paths"
            title="Use the integration resource that maps to your rollout."
            body="These links are the implementation paths for capture, routing, and CI gates. Choose the one that gets your first production failure into Zroky fastest."
          />
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {references.map((reference) => {
              const Icon = reference.icon;
              return (
                <a key={reference.title} href={reference.href} target="_blank" rel="noreferrer" className="card group p-5">
                  <div className="flex items-center justify-between gap-4">
                    <span className="grid h-10 w-10 place-items-center rounded-xl border border-line bg-white/[0.04]">
                      <Icon className="h-5 w-5 text-primary" />
                    </span>
                    <Github className="h-4 w-4 text-tertiary" />
                  </div>
                  <h3 className="mt-5 text-base font-semibold text-primary">{reference.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-secondary">{reference.body}</p>
                  <span className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-primary">
                    View integration
                    <ExternalLink className="h-4 w-4 transition duration-200 group-hover:translate-x-0.5" />
                  </span>
                </a>
              );
            })}
          </div>
        </div>
      </SectionReveal>

      <SectionReveal className="px-4 pb-24 pt-6 sm:px-6 lg:px-8">
        <div className="card mx-auto max-w-[92rem] overflow-hidden p-6 sm:p-8 lg:p-10">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <span className="eyebrow">
                <ShieldCheck className="h-3.5 w-3.5" />
                first protected flow
              </span>
              <h2 className="mt-5 text-balance text-3xl font-semibold leading-tight text-primary sm:text-5xl">
                Protect your first agent flow.
              </h2>
              <p className="mt-4 text-base leading-8 text-secondary">
                Capture the failure, replay the fix, promote the proof, and let CI remember what production already taught you.
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <a href={SIGN_UP_URL} className="btn-primary">
                Protect your first agent flow
                <ArrowRight className="h-4 w-4" />
              </a>
              <a href="/pricing" className="btn-ghost">
                Review plans
              </a>
            </div>
          </div>
        </div>
      </SectionReveal>
    </div>
  );
}
