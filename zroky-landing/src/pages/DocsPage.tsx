import { motion } from 'framer-motion';
import { ArrowRight, BookOpen, ExternalLink, Github, Terminal, Zap } from 'lucide-react';

const quickstart = [
  {
    step: '01',
    title: 'Install the SDK',
    code: 'pip install zroky\n# or\nnpm install @zroky/sdk',
    lang: 'bash',
  },
  {
    step: '02',
    title: 'Set your project key',
    code: 'export ZROKY_PROJECT_ID="proj_xxxx"\nexport ZROKY_API_KEY="zk_live_xxxx"',
    lang: 'bash',
  },
  {
    step: '03',
    title: 'Wrap your agent',
    code: '@zroky.trace(agent="my_agent", workflow="main")\nasync def run_agent(input):\n    return await agent.execute(input)',
    lang: 'python',
  },
  {
    step: '04',
    title: 'See your first trace',
    code: '# Run your agent normally.\n# Open zroky.ai/dashboard — your trace appears\n# automatically within seconds.',
    lang: 'bash',
  },
];

const sections = [
  {
    icon: Terminal,
    title: 'Python SDK',
    desc: 'Reference docs for zroky-sdk: trace decorator, manual spans, context, capture config.',
    href: 'https://github.com/zroky-ai/zroky-sdk',
    tag: 'GitHub',
  },
  {
    icon: Terminal,
    title: 'TypeScript / JS SDK',
    desc: 'Reference docs for @zroky/sdk: trace wrapper, async queue, browser and Node.js support.',
    href: 'https://github.com/zroky-ai/zroky-sdk-js',
    tag: 'GitHub',
  },
  {
    icon: Zap,
    title: 'Zroky Gateway',
    desc: 'OpenAI-compatible proxy. Drop-in capture with zero SDK changes. Multi-provider support.',
    href: 'https://github.com/zroky-ai/zroky-gateway',
    tag: 'GitHub',
  },
  {
    icon: Zap,
    title: 'Replay Worker',
    desc: 'Self-hostable replay executor. Run real_llm, stub, or mocked-tool replays against incidents.',
    href: 'https://github.com/zroky-ai/zroky-replay-worker',
    tag: 'GitHub',
  },
  {
    icon: BookOpen,
    title: 'Issues & Diagnosis',
    desc: 'How Zroky groups failures into Issues, scores root cause confidence, and suggests next actions.',
    href: '#',
    tag: 'Guide',
  },
  {
    icon: BookOpen,
    title: 'CI Goldens',
    desc: 'Promoting verified replays to CI Goldens. Running Golden sets in CI. Blocking release on failure.',
    href: '#',
    tag: 'Guide',
  },
];

export default function DocsPage() {
  return (
    <div className="w-full px-4 pb-24 pt-44 sm:px-5 lg:px-8">
      <div className="mx-auto max-w-[92rem]">

        {/* Header */}
        <div className="mx-auto max-w-2xl">
          <span className="eyebrow">Documentation</span>
          <h1 className="mt-4 text-balance text-4xl font-black leading-tight text-primary md:text-5xl">
            Get started with Zroky in under 10 minutes.
          </h1>
          <p className="mt-4 text-lg leading-8 text-secondary">
            One decorator wraps your agent. Traces appear instantly. The rest — diagnosis, replay, CI gates — follows from your real production data.
          </p>
          <div className="mt-6 flex gap-3">
            <a
              href="https://github.com/zroky-ai"
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-11 items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-extrabold text-white shadow-sm transition hover:bg-accent"
            >
              <Github className="h-4 w-4" />
              View on GitHub
            </a>
            <a
              href="/auth/register"
              className="inline-flex min-h-11 items-center gap-2 rounded-full border border-panel-border bg-white px-5 py-2 text-sm font-extrabold text-primary shadow-sm transition hover:border-accent/40 hover:bg-accent/5"
            >
              Get API Key
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>
        </div>

        {/* Quickstart steps */}
        <div className="mt-16">
          <h2 className="mb-6 text-2xl font-black text-primary">Quickstart</h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {quickstart.map((s, i) => (
              <motion.div
                key={s.step}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.3, delay: i * 0.05 }}
                className="overflow-hidden rounded-[1.5rem] border border-panel-border bg-white shadow-sm"
              >
                <div className="border-b border-panel-border bg-canvas px-5 py-4">
                  <span className="font-mono text-xs font-black text-tertiary">{s.step}</span>
                  <h3 className="mt-1 text-sm font-black text-primary">{s.title}</h3>
                </div>
                <div className="bg-[#101216] px-5 py-4">
                  <pre className="overflow-x-auto font-mono text-[11.5px] leading-6 text-slate-300">
                    <code>{s.code}</code>
                  </pre>
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        {/* Doc sections */}
        <div className="mt-16">
          <h2 className="mb-6 text-2xl font-black text-primary">Reference</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sections.map((sec, i) => {
              const Icon = sec.icon;
              return (
                <motion.a
                  key={sec.title}
                  href={sec.href}
                  target={sec.href.startsWith('http') ? '_blank' : undefined}
                  rel={sec.href.startsWith('http') ? 'noreferrer' : undefined}
                  initial={{ opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.3, delay: i * 0.04 }}
                  className="group flex flex-col gap-3 rounded-[1.5rem] border border-panel-border bg-white p-5 shadow-sm transition duration-200 hover:shadow-premium"
                >
                  <div className="flex items-center justify-between">
                    <span className="grid h-10 w-10 place-items-center rounded-xl border border-panel-border bg-canvas text-accent transition group-hover:border-accent/30 group-hover:bg-accent/5">
                      <Icon className="h-4 w-4" />
                    </span>
                    <span className="flex items-center gap-1.5 rounded-full border border-panel-border bg-canvas px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-tertiary">
                      {sec.tag === 'GitHub' && <Github className="h-3 w-3" />}
                      {sec.tag === 'Guide' && <BookOpen className="h-3 w-3" />}
                      {sec.tag}
                      <ExternalLink className="h-3 w-3" />
                    </span>
                  </div>
                  <div>
                    <h3 className="text-base font-black text-primary">{sec.title}</h3>
                    <p className="mt-1.5 text-sm leading-6 text-secondary">{sec.desc}</p>
                  </div>
                </motion.a>
              );
            })}
          </div>
        </div>

        {/* Help strip */}
        <div className="mt-10 overflow-hidden rounded-[1.5rem] border border-panel-border bg-primary p-6 text-white">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h3 className="text-lg font-black">Need help with your integration?</h3>
              <p className="mt-1 text-sm font-bold text-slate-400">
                We offer guided rollout support on the Team plan, or just email us.
              </p>
            </div>
            <div className="flex gap-3">
              <a
                href="mailto:hello@zroky.ai"
                className="inline-flex min-h-11 items-center gap-2 rounded-full border border-white/20 bg-white/10 px-5 py-2 text-sm font-extrabold text-white transition hover:border-white/40 hover:bg-white/20"
              >
                Email us
              </a>
              <a
                href="/pricing"
                className="inline-flex min-h-11 items-center gap-2 rounded-full bg-white px-5 py-2 text-sm font-extrabold text-primary transition hover:bg-gold/20 hover:text-white"
              >
                View Team plan
                <ArrowRight className="h-4 w-4" />
              </a>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
