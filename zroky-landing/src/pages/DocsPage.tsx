import { type ReactNode } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import {
  AlertTriangle,
  ArrowRight,
  Check,
  Code2,
  DatabaseZap,
  FileCheck2,
  GitBranch,
  KeyRound,
  LockKeyhole,
  Route,
  Server,
  ShieldCheck,
  Terminal,
  Workflow,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { DEMO_URL, SIGN_UP_URL } from '../lib/links';

const revealEase = [0.16, 1, 0.3, 1] as const;

const pythonSnippet = `import zroky

decision = zroky.verified_action(
    agent_id="ops_agent",
    action_type="access.grant",
    parameters={"role": "admin", "target_user": "user_881"},
    source_of_record="okta",
)

proof = zroky.await_action_proof(decision["action_id"])
assert proof["proof_status"] == "matched"`;

const typescriptSnippet = `import { zroky } from "@zroky-ai/sdk";

const decision = await zroky.verifiedAction({
  agentId: "release-agent",
  actionType: "production.deploy",
  parameters: { service: "billing-api", version: "2026.07.04" },
  sourceOfRecord: "deployments",
});

const receipt = await zroky.receipts.get(decision.actionId);`;

const gatewaySnippet = `docker run -d \\
  -p 8090:8090 \\
  -e ZROKY_API_URL=https://api.zroky.com \\
  -e ZROKY_GATEWAY_API_KEY=$ZROKY_GATEWAY_API_KEY \\
  ghcr.io/zroky-ai/zroky-gateway:latest

export OPENAI_BASE_URL=http://localhost:8090/v1`;

const ciSnippet = `name: Zroky protected action checks
on: [pull_request]

jobs:
  zroky:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: zroky/protected-action-ci@v1
        with:
          api_key: \${{ secrets.ZROKY_API_KEY }}
          project_id: \${{ vars.ZROKY_PROJECT_ID }}
          fail_on_unverified_receipt: true`;

const quickstartSteps = [
  {
    icon: KeyRound,
    title: 'Create a project key',
    body: 'Use a scoped project key for one environment and one first protected action.',
    signal: 'settings',
  },
  {
    icon: ShieldCheck,
    title: 'Define the policy gate',
    body: 'Choose who can approve, what must be held, and what fails closed.',
    signal: 'policy',
  },
  {
    icon: DatabaseZap,
    title: 'Connect source of record',
    body: 'Pick the system that proves reality after the action runs.',
    signal: 'verifier',
  },
  {
    icon: Terminal,
    title: 'Wrap the action',
    body: 'Route only the risky operation through Zroky first, then expand by policy.',
    signal: 'sdk',
  },
];

const loopSteps = [
  ['Propose', 'Agent submits intent, parameters, actor, and environment.'],
  ['Policy', 'Zroky decides allow, hold, or block before mutation.'],
  ['Approve', 'The right owner approves high-risk actions with context.'],
  ['Run', 'A scoped runner executes only the approved operation.'],
  ['Verify', 'The source of record confirms what actually changed.'],
  ['Receipt', 'A signed evidence record is created and retained.'],
];

const codePanels = [
  {
    id: 'sdk',
    icon: Terminal,
    label: 'Python SDK',
    title: 'Protect one high-risk action from Python.',
    body: 'Start with the action that can hurt the business. The SDK returns a decision before execution and a proof state after verification.',
    language: 'python',
    code: pythonSnippet,
  },
  {
    id: 'typescript',
    icon: Code2,
    label: 'TypeScript SDK',
    title: 'Wrap a production service action.',
    body: 'Use the same application flow, but route the risky operation through policy, runner, verification, and receipt state.',
    language: 'ts',
    code: typescriptSnippet,
  },
  {
    id: 'gateway',
    icon: Route,
    label: 'Gateway',
    title: 'Adopt routing-level control when SDK changes are slower.',
    body: 'Run the gateway near your service and move compatible provider traffic through Zroky while you plan direct SDK integration.',
    language: 'bash',
    code: gatewaySnippet,
  },
  {
    id: 'ci-gates',
    icon: GitBranch,
    label: 'CI gate',
    title: 'Block releases that lose proof.',
    body: 'Use CI when protected-action behavior has to remain stable before new code reaches production.',
    language: 'yaml',
    code: ciSnippet,
  },
];

const providerRules = [
  {
    icon: Check,
    title: 'Core control does not depend on model output.',
    body: 'Policy decisions, runner state, source verification, and receipts are control-plane behavior.',
  },
  {
    icon: KeyRound,
    title: 'Use provider keys only for optional AI assistance.',
    body: 'Summaries or policy suggestions can use BYOK so model spend stays visible in your provider account.',
  },
  {
    icon: AlertTriangle,
    title: 'Never mark tool-call success as proof.',
    body: 'A 200 response can be recorded, but the receipt is signed only after source-of-record verification.',
  },
];

const troubleshooting = [
  ['Decision stays held', 'Check the policy owner, approval route, and whether the action class requires a human gate.'],
  ['Proof is not verified', 'Confirm the source connector can read the final state and the action id maps to the system record.'],
  ['Receipt is missing', 'Check that runner execution completed and verification reached matched or not_verified state.'],
  ['CI does not block', 'Confirm the workflow uses the right project id and fail_on_unverified_receipt is enabled.'],
];

function Reveal({
  children,
  className = '',
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.58, ease: revealEase, delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

function Section({
  children,
  id,
  className = '',
}: {
  children: ReactNode;
  id?: string;
  className?: string;
}) {
  return (
    <section id={id} className={`w-full scroll-mt-28 px-4 py-16 text-[#171a15] md:py-20 ${className}`}>
      <div className="mx-auto max-w-[1260px]">{children}</div>
    </section>
  );
}

function Eyebrow({ icon: Icon, children }: { icon: LucideIcon; children: ReactNode }) {
  return (
    <p className="inline-flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#2f5f66]">
      <Icon size={14} />
      {children}
    </p>
  );
}

function SectionHeader({
  icon,
  eyebrow,
  title,
  copy,
}: {
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  copy: string;
}) {
  return (
    <Reveal>
      <div className="max-w-3xl">
        <Eyebrow icon={icon}>{eyebrow}</Eyebrow>
        <h2 className="mt-3 text-[2.1rem] font-semibold leading-[1.05] tracking-[-0.03em] text-[#151713] md:text-[3.05rem]">
          {title}
        </h2>
        <p className="mt-4 text-[1.04rem] leading-[1.65] text-[#5b615a]">{copy}</p>
      </div>
    </Reveal>
  );
}

function PrimaryButton({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-[10px] bg-[linear-gradient(180deg,#376f77,#2f5f66)] px-5 text-sm font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.2),0_14px_28px_-16px_rgba(47,95,102,0.75)] transition duration-150 hover:-translate-y-px active:translate-y-0 sm:w-auto"
    >
      {children}
    </a>
  );
}

function GhostButton({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-[10px] border border-[#d4d0c4] bg-[#fffdfa] px-5 text-sm font-semibold text-[#252821] shadow-[0_1px_2px_rgba(32,35,31,0.05)] transition hover:-translate-y-px hover:border-[#c4bfb2] sm:w-auto"
    >
      {children}
    </a>
  );
}

function DocsConsoleVisual() {
  return (
    <Reveal delay={0.08}>
      <div className="overflow-hidden rounded-[24px] border border-[#d7d4ca] bg-[#fffdfa] shadow-[0_1px_2px_rgba(28,31,26,0.05),0_42px_90px_-54px_rgba(28,31,26,0.5)]">
        <div className="flex items-center gap-2 border-b border-[#dedacf] bg-[#f8f7f2] px-4 py-3">
          <span className="h-3 w-3 rounded-full bg-[#ef6a5b]" />
          <span className="h-3 w-3 rounded-full bg-[#f4bd4f]" />
          <span className="h-3 w-3 rounded-full bg-[#61c454]" />
          <span className="ml-2 truncate rounded-[8px] border border-[#dedacf] bg-[#fffdfa] px-3 py-1 font-mono text-[11px] text-[#777266]">
            docs.zroky.com/protected-action
          </span>
        </div>

        <div className="grid gap-4 p-4 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="rounded-[16px] bg-[#171a15] p-4 text-[#eef1ec]">
            <div className="mb-4 flex items-center justify-between gap-3">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#9fb8b2]">quickstart</span>
              <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] font-semibold text-[#dce7e3]">matched</span>
            </div>
            <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-[12px] leading-6 text-[#e8ece6]">
              {pythonSnippet}
            </pre>
          </div>

          <div className="grid gap-3">
            {[
              ['Policy decision', 'Held until owner approval', 'hold'],
              ['Scoped runner', 'Admin grant executed with limited credential', 'run'],
              ['Source verification', 'Directory role matched target state', 'matched'],
              ['Signed receipt', 'sha256:7f3a9e10... ready for export', 'signed'],
            ].map(([label, body, status]) => (
              <div key={label} className="rounded-[14px] border border-[#dedacf] bg-[#f8f7f2] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-[#171a15]">{label}</p>
                    <p className="mt-1 text-[13px] leading-relaxed text-[#5b615a]">{body}</p>
                  </div>
                  <span className="rounded-full border border-[#cfe0dd] bg-[#eaf1ef] px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-[#2f5f66]">
                    {status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Reveal>
  );
}

function CodePanel({ panel }: { panel: (typeof codePanels)[number] }) {
  const Icon = panel.icon;

  return (
    <Reveal>
      <article id={panel.id} className="scroll-mt-28 overflow-hidden rounded-[18px] border border-[#d7d4ca] bg-[#fffdfa] shadow-[0_1px_2px_rgba(28,31,26,0.04)]">
        <div className="border-b border-[#dedacf] bg-[#f8f7f2] p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <span className="inline-flex items-center gap-2 rounded-full border border-[#dedacf] bg-[#fffdfa] px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-[#2f5f66]">
                <Icon size={14} />
                {panel.label}
              </span>
              <h3 className="mt-4 text-xl font-semibold leading-tight text-[#171a15]">{panel.title}</h3>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-[#5b615a]">{panel.body}</p>
            </div>
            <span className="w-fit shrink-0 rounded-[8px] border border-[#dedacf] bg-[#fffdfa] px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-[#777266]">
              {panel.language}
            </span>
          </div>
        </div>
        <div className="bg-[#171a15] p-5">
          <pre className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-[12px] leading-6 text-[#eef1ec]">
            <code>{panel.code}</code>
          </pre>
        </div>
      </article>
    </Reveal>
  );
}

export default function DocsPage() {
  return (
    <div className="w-full overflow-x-hidden bg-[#fbfcfa] text-[#171a15]">
      <section
        className="relative overflow-hidden px-4 pb-14 pt-28 md:pb-16 md:pt-32"
        style={{
          background: 'linear-gradient(180deg,#fbfaf6 0%,#f3f4ee 58%,#fbfcfa 100%)',
          fontFeatureSettings: "'ss01','cv01'",
        }}
      >
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-[520px]"
          style={{
            background:
              'radial-gradient(60% 38% at 50% 0%, rgba(255,255,255,0.95), transparent 76%), linear-gradient(180deg, rgba(234,231,220,0.72), transparent 64%)',
          }}
        />

        <div className="relative z-10 mx-auto grid max-w-[1260px] gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
          <Reveal>
            <div>
              <Eyebrow icon={Workflow}>Docs</Eyebrow>
              <h1 className="mt-6 max-w-4xl text-[2.65rem] font-semibold leading-[1] tracking-[-0.035em] text-[#12140f] sm:text-[3.4rem] md:text-[4.35rem]">
                Build your first governed agent action.
              </h1>
              <p className="mt-6 max-w-2xl text-[1.06rem] leading-[1.7] text-[#555b53] md:text-[1.16rem]">
                Use Zroky where an agent can change money, access, customer state, or production. Start with one action, prove the loop, then expand by policy.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <PrimaryButton href="#quickstart">
                  Start quickstart <ArrowRight size={15} />
                </PrimaryButton>
                <GhostButton href="#sdk">View SDK setup</GhostButton>
                <GhostButton href={DEMO_URL}>Book a demo</GhostButton>
              </div>
            </div>
          </Reveal>

          <DocsConsoleVisual />
        </div>
      </section>

      <Section id="quickstart" className="bg-[#fbfcfa] py-14 md:py-20">
        <SectionHeader
          icon={Zap}
          eyebrow="Quickstart"
          title="Protect the action before you protect the whole agent."
          copy="The clean rollout is narrow: one risky operation, one policy owner, one source of record, one signed receipt. Once that loop works, add more action classes."
        />

        <div className="mt-10 grid gap-4 lg:grid-cols-4">
          {quickstartSteps.map((step, index) => {
            const Icon = step.icon;
            return (
              <Reveal key={step.title} delay={index * 0.04}>
                <article className="h-full rounded-[16px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.04)]">
                  <div className="flex items-center justify-between gap-4">
                    <span className="grid h-11 w-11 place-items-center rounded-[12px] border border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]">
                      <Icon size={19} />
                    </span>
                    <span className="rounded-full border border-[#dedacf] bg-[#f8f7f2] px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-[#777266]">
                      {step.signal}
                    </span>
                  </div>
                  <h3 className="mt-5 text-base font-semibold text-[#171a15]">{step.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-[#5b615a]">{step.body}</p>
                </article>
              </Reveal>
            );
          })}
        </div>
      </Section>

      <Section id="control-loop" className="bg-[#f3f4ee] py-14 md:py-20">
        <div className="grid gap-10 lg:grid-cols-[0.82fr_1.18fr] lg:items-start">
          <SectionHeader
            icon={ShieldCheck}
            eyebrow="Control loop"
            title="Every protected action moves through the same contract."
            copy="Nothing skips the line: not urgency, not scale, not a confident-looking tool response. Zroky checks authority before execution and checks reality before evidence is signed."
          />

          <Reveal delay={0.08}>
            <div className="rounded-[20px] border border-[#d7d4ca] bg-[#fffdfa] p-4 shadow-[0_1px_2px_rgba(28,31,26,0.04),0_38px_76px_-58px_rgba(28,31,26,0.42)]">
              <div className="grid gap-3 md:grid-cols-3">
                {loopSteps.map(([label, body], index) => (
                  <div key={label} className="relative rounded-[14px] border border-[#dedacf] bg-[#f8f7f2] p-4">
                    <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#2f5f66]">
                      0{index + 1}
                    </span>
                    <h3 className="mt-3 text-base font-semibold text-[#171a15]">{label}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-[#5b615a]">{body}</p>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-[14px] border border-[#cfe0dd] bg-[#eaf1ef] p-4">
                <p className="text-sm font-semibold leading-relaxed text-[#2f5f66]">
                  The receipt is not a log line. It is the signed answer to three questions: who allowed this, did the real system match, and can we prove it later?
                </p>
              </div>
            </div>
          </Reveal>
        </div>
      </Section>

      <Section className="bg-[#fbfcfa] py-14 md:py-20">
        <SectionHeader
          icon={Terminal}
          eyebrow="Code setup"
          title="Use the path that matches your deployment."
          copy="Direct SDK integration is best for owned services. Gateway adoption helps when traffic needs to move first. CI gates keep proof requirements from regressing."
        />
        <div className="mt-9 grid gap-5 xl:grid-cols-2">
          {codePanels.map((panel) => (
            <CodePanel key={panel.id} panel={panel} />
          ))}
        </div>
      </Section>

      <Section id="provider-keys" className="bg-[#f3f4ee] py-14 md:py-20">
        <div className="grid gap-10 lg:grid-cols-[0.82fr_1.18fr] lg:items-start">
          <SectionHeader
            icon={KeyRound}
            eyebrow="Provider keys"
            title="Keep model spend explicit. Keep control deterministic."
            copy="Zroky does not need a provider key to make core control decisions. Use BYOK for optional AI assistance, summaries, or analysis that would otherwise hide model cost inside the product."
          />
          <div className="grid gap-3">
            {providerRules.map((rule, index) => {
              const Icon = rule.icon;
              return (
                <Reveal key={rule.title} delay={index * 0.04}>
                  <article className="rounded-[16px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.04)]">
                    <div className="flex gap-4">
                      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-[11px] border border-[#cfe0dd] bg-[#eaf1ef] text-[#2f5f66]">
                        <Icon size={18} />
                      </span>
                      <div>
                        <h3 className="text-base font-semibold text-[#171a15]">{rule.title}</h3>
                        <p className="mt-2 text-sm leading-relaxed text-[#5b615a]">{rule.body}</p>
                      </div>
                    </div>
                  </article>
                </Reveal>
              );
            })}
          </div>
        </div>
      </Section>

      <Section id="receipts" className="bg-[#fbfcfa] py-14 md:py-20">
        <div className="grid gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <Reveal>
            <div className="rounded-[20px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.04)]">
              <div className="grid gap-3">
                {[
                  ['policy_snapshot', 'approval required for admin role'],
                  ['approval_trail', 'owner approved from dashboard'],
                  ['runner_event', 'scoped credential executed once'],
                  ['source_comparison', 'directory role matched'],
                  ['evidence_hash', 'sha256:7f3a9e10...'],
                ].map(([key, value]) => (
                  <div key={key} className="grid gap-2 rounded-[12px] border border-[#dedacf] bg-[#f8f7f2] px-4 py-3 sm:grid-cols-[11rem_1fr]">
                    <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#777266]">{key}</span>
                    <span className="text-sm font-semibold text-[#171a15]">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          </Reveal>
          <SectionHeader
            icon={FileCheck2}
            eyebrow="Receipts"
            title="Treat proof as an artifact your team can inspect."
            copy="A receipt should carry policy context, approval state, runner execution, source comparison, and evidence hash. That is what makes autonomy reviewable after the moment has passed."
          />
        </div>
      </Section>

      <Section id="troubleshooting" className="bg-[#f3f4ee] py-14 md:py-20">
        <div className="grid gap-10 lg:grid-cols-[0.72fr_1.28fr]">
          <SectionHeader
            icon={Server}
            eyebrow="Troubleshooting"
            title="Debug the loop by state, not guesswork."
            copy="When something looks stuck, locate the state: decision, approval, runner, verifier, or receipt. The fix usually belongs to that boundary."
          />
          <div className="grid gap-3 md:grid-cols-2">
            {troubleshooting.map(([title, body], index) => (
              <Reveal key={title} delay={index * 0.03}>
                <article className="h-full rounded-[16px] border border-[#d7d4ca] bg-[#fffdfa] p-5 shadow-[0_1px_2px_rgba(28,31,26,0.04)]">
                  <h3 className="text-base font-semibold text-[#171a15]">{title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-[#5b615a]">{body}</p>
                </article>
              </Reveal>
            ))}
          </div>
        </div>
      </Section>

      <section className="w-full bg-[#fbfcfa] px-4 py-20 text-[#171a15]">
        <Reveal>
          <div className="mx-auto max-w-6xl rounded-[24px] border border-[#d7d4ca] bg-[#fffdfa] p-8 shadow-[0_40px_90px_-52px_rgba(28,31,26,0.38)] md:p-12">
            <div className="flex flex-col gap-7 lg:flex-row lg:items-end lg:justify-between">
              <div className="max-w-3xl">
                <Eyebrow icon={LockKeyhole}>First protected action</Eyebrow>
                <h2 className="mt-3 text-[2.15rem] font-semibold leading-[1.05] tracking-[-0.03em] text-[#151713] md:text-[3.15rem]">
                  Put one real action behind Zroky.
                </h2>
                <p className="mt-4 text-[1.04rem] leading-[1.65] text-[#5b615a]">
                  Start with the operation your team would never want an agent to run invisibly.
                </p>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                <PrimaryButton href={SIGN_UP_URL}>
                  Start free <ArrowRight size={15} />
                </PrimaryButton>
                <GhostButton href="/pricing">Review plans</GhostButton>
              </div>
            </div>
          </div>
        </Reveal>
      </section>
    </div>
  );
}
