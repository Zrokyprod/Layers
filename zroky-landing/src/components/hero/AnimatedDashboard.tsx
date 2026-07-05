import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import {
  Activity,
  ArrowRight,
  Bot,
  Check,
  FileCheck2,
  Home,
  LockKeyhole,
  PlugZap,
  ShieldCheck,
  SlidersHorizontal,
} from 'lucide-react';

type ModuleIcon = typeof Home;

export type ModuleTourItem = {
  id: string;
  label: string;
  group: string;
  icon: ModuleIcon;
  headline: string;
  body: string;
  status: string;
  metrics: Array<{ label: string; value: string }>;
  panel: Array<{ label: string; value: string; ok?: boolean }>;
};

export const moduleTour: ModuleTourItem[] = [
  {
    id: 'home',
    label: 'Home',
    group: 'Mission control',
    icon: Home,
    headline: 'Fleet posture, queue pressure, and proof health in one command view.',
    body: 'Home tells operators what needs attention now: held actions, outcome mismatches, bypass signals, and the selected proof state.',
    status: 'Live command',
    metrics: [
      { label: 'Protected', value: '128' },
      { label: 'Queued', value: '3' },
      { label: 'Matched', value: '96%' },
    ],
    panel: [
      { label: 'Decision queue', value: 'Admin access grant held' },
      { label: 'Selected proof', value: 'Receipt pending review' },
      { label: 'Bypass risk', value: '0 unreceipted mutations', ok: true },
    ],
  },
  {
    id: 'approvals',
    label: 'Approvals',
    group: 'Human gate',
    icon: LockKeyhole,
    headline: 'Risky agent actions pause with the exact reason they need review.',
    body: 'Approvals shows intent, policy hit, business impact, expiry, approvers, and the decision trail before money, data, access, or production changes.',
    status: 'Needs decision',
    metrics: [
      { label: 'Held', value: '3' },
      { label: 'SLA', value: '14m' },
      { label: 'Policy', value: 'R4' },
    ],
    panel: [
      { label: 'Action', value: 'access.grant - admin role' },
      { label: 'Reason', value: 'Privilege level and sequence risk' },
      { label: 'Approver', value: 'Security owner assigned', ok: true },
    ],
  },
  {
    id: 'actions',
    label: 'Actions',
    group: 'Lifecycle',
    icon: Activity,
    headline: 'Every protected action has a visible lifecycle from intent to receipt.',
    body: 'Actions shows propose, policy, approval, runner execution, verification, receipt, and evidence state without guessing where the flow stopped.',
    status: 'Lifecycle trace',
    metrics: [
      { label: 'Proposed', value: '42' },
      { label: 'Running', value: '2' },
      { label: 'Receipts', value: '39' },
    ],
    panel: [
      { label: 'Runner', value: 'Customer-hosted production runner', ok: true },
      { label: 'Credential', value: 'Scoped deploy token' },
      { label: 'State', value: 'Verifier waiting on source record' },
    ],
  },
  {
    id: 'agents',
    label: 'Agents',
    group: 'Fleet',
    icon: Bot,
    headline: 'Agent inventory shows who can act and what controls protect them.',
    body: 'Agents tracks runtime, framework, tool coverage, policy assignment, environment, and missing proof coverage for every autonomous worker.',
    status: 'Fleet coverage',
    metrics: [
      { label: 'Active', value: '18' },
      { label: 'Covered', value: '94%' },
      { label: 'High risk', value: '4' },
    ],
    panel: [
      { label: 'Frameworks', value: 'LangGraph, CrewAI, custom' },
      { label: 'Tools', value: '7 protected operations' },
      { label: 'Coverage', value: 'Policy and verifier attached', ok: true },
    ],
  },
  {
    id: 'outcomes',
    label: 'Outcomes',
    group: 'Verification',
    icon: ShieldCheck,
    headline: 'Agent claims are compared with the system of record.',
    body: 'Outcomes proves whether the actual ledger, CRM, ticket, or database state matches what the agent claimed happened.',
    status: 'Outcome proven',
    metrics: [
      { label: 'Checks', value: '312' },
      { label: 'Matched', value: '301' },
      { label: 'Mismatch', value: '2' },
    ],
    panel: [
      { label: 'Role', value: 'admin = admin', ok: true },
      { label: 'Actor', value: 'agent-runner = agent-runner', ok: true },
      { label: 'Status', value: 'approved = approved', ok: true },
    ],
  },
  {
    id: 'evidence',
    label: 'Evidence',
    group: 'Audit proof',
    icon: FileCheck2,
    headline: 'Evidence packs make every approved action exportable.',
    body: 'Evidence collects policy, approval, runner event, verification comparison, receipt hash, and signature context for audit review.',
    status: 'Export ready',
    metrics: [
      { label: 'Receipts', value: '301' },
      { label: 'Hashes', value: '301' },
      { label: 'Exports', value: '18' },
    ],
    panel: [
      { label: 'Receipt', value: 'rec_9f2c...b41', ok: true },
      { label: 'Signature', value: 'HMAC verified', ok: true },
      { label: 'Format', value: 'Audit JSON and PDF' },
    ],
  },
  {
    id: 'policies',
    label: 'Policies',
    group: 'Runtime rules',
    icon: SlidersHorizontal,
    headline: 'Policy gates define when autonomy can run without a human.',
    body: 'Policies score action class, amount, sequence risk, required approvers, kill switches, and escalation behavior.',
    status: 'Gate active',
    metrics: [
      { label: 'Rules', value: '24' },
      { label: 'Kills', value: '0' },
      { label: 'Approval', value: '2x' },
    ],
    panel: [
      { label: 'Money limit', value: 'Hold above $500' },
      { label: 'Sequence risk', value: 'Bulk read to external send' },
      { label: 'Default', value: 'Fail closed', ok: true },
    ],
  },
  {
    id: 'connectors',
    label: 'Connectors',
    group: 'Source systems',
    icon: PlugZap,
    headline: 'Connectors turn business systems into proof sources.',
    body: 'Connectors check Stripe, Salesforce, ledger databases, ticketing, and internal APIs after execution so proof is grounded in reality.',
    status: 'Preflight pass',
    metrics: [
      { label: 'Live', value: '8' },
      { label: 'Health', value: '99.9%' },
      { label: 'Lag', value: '1.2s' },
    ],
    panel: [
      { label: 'Stripe', value: 'Payout read ready', ok: true },
      { label: 'Salesforce', value: 'Record compare ready', ok: true },
      { label: 'GitHub', value: 'Deploy check ready', ok: true },
    ],
  },
];

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[10px] border border-[#e0ddd3] bg-[#fffdfa] px-3 py-2">
      <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-[#878174]">{label}</p>
      <p className="mt-0.5 text-[18px] font-semibold text-[#171a15]">{value}</p>
    </div>
  );
}

function DenseActivity() {
  return (
    <div className="grid gap-2">
      {[
        ['P0', 'access.grant held', 'approval required'],
        ['P1', 'crm.customer.update', 'matched'],
        ['P1', 'production.deploy', 'runner pending'],
      ].map(([priority, title, status]) => (
        <div key={title} className="flex items-center gap-2.5 rounded-[10px] border border-[#e3e0d6] bg-[#fbfaf5] px-3 py-2">
          <span className="rounded-[7px] bg-[#ece9df] px-2 py-1 text-[9px] font-semibold text-[#5f5a50]">{priority}</span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[11px] font-semibold text-[#20231f]">{title}</p>
            <p className="truncate text-[10px] text-[#777266]">{status}</p>
          </div>
          <ArrowRight size={13} className="text-[#9b9689]" />
        </div>
      ))}
    </div>
  );
}

function DashboardSlice({ module }: { module: ModuleTourItem }) {
  const Icon = module.icon;
  return (
    <div className="grid h-full min-w-0 gap-3 lg:grid-cols-[1fr_290px]">
      <div className="min-w-0 rounded-[12px] border border-[#dfdbd0] bg-[#fffdfa] p-3 sm:rounded-[14px] sm:p-4">
        <div className="flex items-start gap-3">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[10px] border border-[#c9ddda] bg-[#eaf1ef] text-[#2f5f66] sm:h-9 sm:w-9 sm:rounded-[11px]">
            <Icon size={16} />
          </span>
          <div className="min-w-0">
            <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#8b8578]">{module.group}</p>
            <h3 className="mt-1 max-w-[660px] text-[14.5px] font-semibold leading-tight text-[#151713] sm:text-[17px]">
              {module.headline}
            </h3>
            <p className="mt-1.5 max-w-[660px] text-[10.5px] leading-relaxed text-[#5c6158] sm:text-[11.5px]">{module.body}</p>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          {module.metrics.map((metric) => (
            <MetricTile key={metric.label} {...metric} />
          ))}
        </div>

        <div className="mt-3 grid gap-3 sm:mt-4 xl:grid-cols-[1fr_0.8fr]">
          <div className="rounded-[12px] border border-[#e0ddd3] bg-[#f5f3ec] p-3">
            <div className="flex items-center gap-2 text-[9.5px] font-semibold uppercase tracking-[0.1em] text-[#7c7669]">
              <Activity size={13} /> Decision queue
            </div>
            <div className="mt-3">
              <DenseActivity />
            </div>
          </div>
          <div className="rounded-[12px] border border-[#e0ddd3] bg-[#f5f3ec] p-3">
            <div className="flex flex-wrap items-center gap-2">
              {['Intent', 'Policy', 'Run', 'Verify', 'Receipt'].map((step, index) => (
                <div key={step} className="flex items-center gap-1.5">
                  <span className="rounded-full border border-[#dcd8ce] bg-[#fffdfa] px-2 py-1 text-[9.5px] font-semibold text-[#4e534b]">
                    {step}
                  </span>
                  {index < 4 ? <ArrowRight size={12} className="text-[#a29c8f]" /> : null}
                </div>
              ))}
            </div>
            <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-[#ddd9ce]">
              <motion.div
                key={module.id}
                className="h-full rounded-full bg-[#2f5f66]"
                initial={{ width: '18%' }}
                animate={{ width: '100%' }}
                transition={{ duration: 3, ease: [0.16, 1, 0.3, 1] }}
              />
            </div>
            <p className="mt-3 text-[10.5px] leading-relaxed text-[#6e695f]">
              Policy and proof states stay visible even when the agent workflow is running in the background.
            </p>
          </div>
        </div>
      </div>

      <div className="hidden rounded-[14px] border border-[#dfdbd0] bg-[#f7f5ee] p-4 sm:block">
        <div className="flex items-center justify-between gap-3">
          <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#8b8578]">Selected proof</p>
          <span className="rounded-full border border-[#d8d4c8] bg-[#fffdfa] px-2.5 py-1 text-[9px] font-semibold text-[#34362f]">
            {module.status}
          </span>
        </div>
        <div className="mt-3 space-y-2.5">
          {module.panel.map((row) => (
            <div key={row.label} className="rounded-[10px] border border-[#e1ddd3] bg-[#fffdfa] px-3 py-2.5">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-[#8b8578]">{row.label}</p>
                  <p className="mt-1 text-[11px] font-semibold leading-snug text-[#20231f]">{row.value}</p>
                </div>
                {row.ok ? (
                  <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full border border-[#c9ddda] bg-[#eaf1ef] text-[#2f5f66]">
                    <Check size={13} />
                  </span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 rounded-[10px] border border-[#d9d6ca] bg-[#eeeae1] px-3 py-2">
          <p className="text-[10.5px] font-semibold text-[#34362f]">Receipt state is visible before teams trust automation at scale.</p>
        </div>
      </div>
    </div>
  );
}

export function AnimatedDashboard() {
  const reduce = useReducedMotion();
  const [activeId, setActiveId] = useState(moduleTour[0].id);
  const active = useMemo(() => moduleTour.find((item) => item.id === activeId) ?? moduleTour[0], [activeId]);
  const activeIndex = moduleTour.findIndex((item) => item.id === active.id);
  const ActiveIcon = active.icon;

  useEffect(() => {
    if (reduce) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      setActiveId((current) => {
        const index = moduleTour.findIndex((item) => item.id === current);
        return moduleTour[(index + 1) % moduleTour.length].id;
      });
    }, 3800);
    return () => window.clearInterval(timer);
  }, [reduce]);

  return (
    <div className="mx-auto w-full min-w-0 max-w-[1180px]">
      <div className="overflow-hidden rounded-[18px] border border-[#d2ccbd] bg-[#ede9df] shadow-[0_34px_76px_-50px_rgba(28,31,26,0.48),0_1px_0_rgba(255,255,255,0.8)_inset] sm:rounded-[24px] sm:shadow-[0_46px_100px_-58px_rgba(28,31,26,0.55),0_1px_0_rgba(255,255,255,0.8)_inset]">
        <div className="flex h-9 items-center justify-between border-b border-[#d8d3c6] bg-[linear-gradient(180deg,#f9f7f1,#eae6dc)] px-3 sm:h-11 sm:px-4">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57] shadow-[0_0_0_1px_rgba(0,0,0,0.08)] sm:h-3 sm:w-3" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e] shadow-[0_0_0_1px_rgba(0,0,0,0.08)] sm:h-3 sm:w-3" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#28c840] shadow-[0_0_0_1px_rgba(0,0,0,0.08)] sm:h-3 sm:w-3" />
          </div>
          <div className="hidden rounded-full border border-[#d8d3c6] bg-[#fffdfa] px-4 py-1.5 font-mono text-[11px] font-semibold text-[#6b655b] sm:block">
            zroky.dashboard / protected-actions
          </div>
          <div className="w-[58px]" />
        </div>

        <div className="grid min-h-[420px] bg-[#f8f7f2] sm:min-h-[500px] md:grid-cols-[184px_1fr]">
          <aside className="hidden border-r border-[#dfdbd0] bg-[#f2efe7] p-4 md:flex md:flex-col">
            <img src="/zroky-brand.png" alt="Zroky" className="h-7 w-[116px] object-contain object-left" />
            <p className="mt-5 text-[9px] font-semibold uppercase tracking-[0.14em] text-[#8b8578]">Control</p>
            <div className="mt-2 flex flex-1 flex-col gap-1.5">
              {moduleTour.map((module) => {
                const Icon = module.icon;
                const selected = module.id === active.id;
                return (
                  <button
                    key={module.id}
                    type="button"
                    onClick={() => setActiveId(module.id)}
                    className={`flex min-w-0 items-center gap-2.5 rounded-[9px] px-2.5 py-1.5 text-left text-[11px] font-semibold transition ${
                      selected
                        ? 'border border-[#c9ddda] bg-[#eaf1ef] text-[#2f5f66] shadow-[0_1px_2px_rgba(28,31,26,0.04)]'
                        : 'text-[#5a5e55] hover:bg-[#e8e4da]'
                    }`}
                  >
                    <Icon size={15} className="shrink-0" />
                    <span className="truncate">{module.label}</span>
                  </button>
                );
              })}
            </div>
            <div className="rounded-[12px] border border-[#dedacf] bg-[#fffdfa] p-3">
              <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#2f5f66]" />
                <span className="text-[10.5px] font-semibold text-[#2f5f66]">Enterprise workspace</span>
              </div>
              <p className="mt-1.5 text-[10px] leading-snug text-[#777266]">Policies, proof, and approval state stay connected.</p>
            </div>
          </aside>

          <main className="min-w-0 p-2.5 sm:p-4 lg:p-5">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-[12px] border border-[#dfdbd0] bg-[#fffdfa] px-2.5 py-2 shadow-[0_1px_2px_rgba(30,33,29,0.04)] sm:rounded-[13px] sm:px-3 sm:py-2.5">
              <div className="flex min-w-0 items-center gap-2">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[9px] bg-[#2f5f66] text-white">
                  <ActiveIcon size={16} />
                </span>
                <div className="min-w-0">
                  <p className="truncate text-[12px] font-semibold text-[#11130f]">Dashboard / {active.label}</p>
                  <p className="truncate text-[10px] text-[#777266]">{active.group}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="hidden rounded-[9px] border border-[#dfdbd0] bg-[#f6f5ef] px-2.5 py-1.5 text-[10px] font-semibold text-[#54584f] sm:inline-flex">
                  Last 7 days
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-[9px] border border-[#dfdbd0] bg-[#f6f5ef] px-2.5 py-1.5 text-[10px] font-semibold text-[#34362f]">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#2f5f66]" />
                  Production
                </span>
              </div>
            </div>

            <div className="mt-3 flex gap-1.5 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] md:hidden [&::-webkit-scrollbar]:hidden" aria-label="Dashboard module tour">
              {moduleTour.map((module) => (
                <button
                  key={module.id}
                  type="button"
                  onClick={() => setActiveId(module.id)}
                  className={`shrink-0 rounded-full border px-3 py-1.5 text-[11px] font-semibold ${
                    module.id === active.id ? 'border-[#c9ddda] bg-[#eaf1ef] text-[#2f5f66]' : 'border-[#dfdbd0] bg-[#f7f5ee] text-[#5c6158]'
                  }`}
                >
                  {module.label}
                </button>
              ))}
            </div>

            <div className="mt-3">
              <AnimatePresence mode="wait">
                <motion.div
                  key={active.id}
                  initial={reduce ? false : { opacity: 0, y: 14, scale: 0.99 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={reduce ? undefined : { opacity: 0, y: -10, scale: 0.992 }}
                  transition={{ duration: 0.44, ease: [0.16, 1, 0.3, 1] }}
                >
                  <DashboardSlice module={active} />
                </motion.div>
              </AnimatePresence>
            </div>
          </main>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-center gap-1.5">
        {moduleTour.map((module, index) => (
          <button
            key={module.id}
            type="button"
            aria-label={`Show ${module.label}`}
            onClick={() => setActiveId(module.id)}
            className={`h-2 rounded-full transition-all ${index === activeIndex ? 'w-7 bg-[#2f5f66]' : 'w-2 bg-[#cdc7ba] hover:bg-[#948d80]'}`}
          />
        ))}
      </div>
    </div>
  );
}
