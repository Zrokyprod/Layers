import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { AlertTriangle, ArrowRight, ArrowUpRight, Check, RefreshCw } from 'lucide-react';

type Tone = 'accent' | 'warning' | 'success' | 'danger' | 'neutral';

const pill: Record<Tone, string> = {
  accent: 'border-[#2f5f66]/25 bg-[rgba(47,95,102,0.08)] text-[#2f5f66]',
  warning: 'border-[#b7791f]/25 bg-[#b7791f]/10 text-[#8a5a12]',
  success: 'border-[#16a34a]/25 bg-[#16a34a]/10 text-[#15803d]',
  danger: 'border-[#d14343]/25 bg-[#d14343]/10 text-[#b23636]',
  neutral: 'border-[#e4e0d6] bg-[#efeee7] text-[#57564e]',
};
const dot: Record<Tone, string> = {
  accent: 'bg-[#2f5f66]',
  warning: 'bg-[#b7791f]',
  success: 'bg-[#16a34a]',
  danger: 'bg-[#d14343]',
  neutral: 'bg-[#8a867a]',
};

function Pill({ tone, children }: { tone: Tone; children: string }) {
  return (
    <span className={`inline-flex h-[22px] items-center gap-1.5 rounded-full border px-2 text-[10px] font-semibold uppercase tracking-[0.04em] ${pill[tone]}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot[tone]}`} />
      {children}
    </span>
  );
}

const MODULES = [
  { id: 'home', label: 'Mission Control', url: 'home' },
  { id: 'approvals', label: 'Approvals', url: 'approvals' },
  { id: 'actions', label: 'Actions', url: 'actions' },
  { id: 'evidence', label: 'Evidence', url: 'evidence' },
  { id: 'connectors', label: 'Connectors', url: 'connectors' },
];

function MissionControl() {
  const metrics = [
    ['Controlled actions', '128', 'Action intents in the current window', 'neutral'],
    ['Pending approvals', '1', 'Human decisions waiting', 'warning'],
    ['Verified outcomes', '99% matched', '742 matched / 748 checks', 'success'],
    ['Bypass risk', '0', 'Unreceipted source mutations', 'success'],
  ] as const;
  const queue = [
    ['1', 'Refund $4,200.00 held', 'billing-ops', 'Above approval threshold / rule: finance-agent', 'Held', 'warning'],
    ['2', 'Payout $18,900.00 held', 'vendor-pay', 'Exceeds $5,000 / RazorpayX payout', 'Held', 'warning'],
    ['3', 'Account.update matched', 'crm-sync', 'Salesforce record verified', 'Matched', 'success'],
  ] as const;
  return (
    <div>
      {/* verdict hero */}
      <div className="flex items-start justify-between gap-4 rounded-[12px] border border-[#e4d9c2] bg-[linear-gradient(180deg,#fdf6e8,#faf3e4)] p-4">
        <div className="flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[10px] bg-[#b7791f]/12 text-[#b7791f]"><AlertTriangle size={18} /></span>
          <div>
            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8a867a]">Mission control</p>
            <h4 className="mt-0.5 text-[16px] font-semibold text-[#1a1a17]">1 action needs your approval</h4>
            <p className="mt-0.5 text-[12px] text-[#57564e]">Held actions wait for a human decision before they run.</p>
          </div>
        </div>
        <div className="hidden flex-col items-end gap-2 sm:flex">
          <span className="inline-flex items-center gap-1.5 font-mono text-[10px] text-[#8a867a]"><span className="h-1.5 w-1.5 rounded-full bg-[#16a34a]" /> Updated 4s ago</span>
          <div className="flex items-center gap-1.5">
            <span className="inline-flex h-7 items-center gap-1 rounded-[8px] border border-[#e4e0d6] bg-white px-2.5 text-[11px] font-semibold text-[#57564e]"><RefreshCw size={12} /> Refresh</span>
            <span className="inline-flex h-7 items-center rounded-[8px] bg-[#2f5f66] px-2.5 text-[11px] font-semibold text-white">Review approvals</span>
          </div>
        </div>
      </div>
      {/* proof strip */}
      <div className="mt-3 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
        {metrics.map(([label, value, detail, tone]) => (
          <div key={label} className="rounded-[10px] border border-[#e4e0d6] bg-white p-3">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-[0.06em] text-[#8a867a]">{label}</span>
              <ArrowUpRight size={12} className="text-[#c4bfb2]" />
            </div>
            <div className={`mt-1.5 text-[18px] font-semibold tracking-tight text-[#1a1a17] [font-variant-numeric:tabular-nums]`}>{value}</div>
            <p className="mt-0.5 text-[10px] leading-snug text-[#8a867a]">{detail}</p>
            <span className={`mt-2 inline-block h-1 w-8 rounded-full ${dot[tone]} opacity-70`} />
          </div>
        ))}
      </div>
      {/* decision queue */}
      <div className="mt-3 overflow-hidden rounded-[10px] border border-[#e4e0d6]">
        <div className="flex items-center justify-between border-b border-[#e4e0d6] bg-[#f7f6f2] px-3 py-2">
          <span className="text-[11px] font-semibold text-[#57564e]">Decision queue - what needs attention</span>
          <span className="flex gap-1">
            <span className="rounded-full bg-[#2f5f66] px-2 py-0.5 text-[9px] font-semibold text-white">All 3</span>
            <span className="rounded-full border border-[#e4e0d6] px-2 py-0.5 text-[9px] font-semibold text-[#8a867a]">Needs 2</span>
          </span>
        </div>
        <div className="divide-y divide-[#efeee7] bg-white">
          {queue.map(([p, title, agent, reason, status, tone]) => (
            <div key={p} className="flex items-center gap-3 px-3 py-2.5">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md border border-[#e4e0d6] bg-[#f7f6f2] font-mono text-[11px] font-semibold text-[#57564e]">{p}</span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12px] font-semibold text-[#1a1a17]">{title}</p>
                <p className="truncate text-[10px] text-[#8a867a]">Agent: {agent} / {reason}</p>
              </div>
              <Pill tone={tone}>{status}</Pill>
              <ArrowRight size={13} className="text-[#c4bfb2]" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Approvals() {
  return (
    <div>
      <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8a867a]">Approvals</p>
      <h4 className="mt-1 text-[16px] font-semibold text-[#1a1a17]">Review a held action</h4>
      <div className="mt-4 rounded-[12px] border border-[#e4e0d6] bg-white p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[14px] font-semibold text-[#1a1a17]">payout.create - $18,900.00</p>
            <p className="mt-0.5 font-mono text-[11px] text-[#8a867a]">agent: vendor-pay / environment: production</p>
          </div>
          <Pill tone="warning">Held</Pill>
        </div>
        <div className="mt-3 grid gap-2 rounded-[10px] border border-[#efeee7] bg-[#f7f6f2] p-3 sm:grid-cols-2">
          <div><p className="font-mono text-[9px] uppercase tracking-[0.08em] text-[#8a867a]">Rule matched</p><p className="text-[12px] text-[#1a1a17]">amount &gt; $5,000 / finance-agent</p></div>
          <div><p className="font-mono text-[9px] uppercase tracking-[0.08em] text-[#8a867a]">Verifier</p><p className="text-[12px] text-[#1a1a17]">RazorpayX payout ledger</p></div>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <span className="inline-flex h-8 items-center gap-1.5 rounded-[8px] bg-[#16a34a] px-3 text-[12px] font-semibold text-white"><Check size={14} /> Approve</span>
          <span className="inline-flex h-8 items-center rounded-[8px] border border-[#e4e0d6] bg-white px-3 text-[12px] font-semibold text-[#b23636]">Deny</span>
          <span className="ml-auto font-mono text-[10px] text-[#8a867a]">expires in 27:14</span>
        </div>
      </div>
    </div>
  );
}

function Actions() {
  const steps = ['Proposed', 'Held', 'Approved', 'Executed', 'Verified'];
  return (
    <div>
      <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8a867a]">Action detail</p>
      <h4 className="mt-1 text-[16px] font-semibold text-[#1a1a17]">refund.payment - $4,200.00</h4>
      <div className="mt-6 rounded-[12px] border border-[#e4e0d6] bg-[#f7f6f2] p-5">
        <div className="relative flex items-center justify-between">
          <div className="absolute left-4 right-4 top-[10px] h-[2px] bg-[#16a34a]/30" />
          {steps.map((label, i) => (
            <div key={label} className="relative z-10 flex flex-1 flex-col items-center gap-2 text-center">
              <span className="grid h-5 w-5 place-items-center rounded-full bg-[#16a34a] text-white ring-4 ring-[#f7f6f2]"><Check size={11} /></span>
              <span className="text-[10px] font-semibold text-[#1a1a17]">{label}</span>
              <span className="font-mono text-[8px] uppercase tracking-[0.06em] text-[#8a867a]">{i === steps.length - 1 ? 'ledger' : 'ok'}</span>
            </div>
          ))}
        </div>
      </div>
      <p className="mt-3 font-mono text-[11px] text-[#8a867a]">Verified against Razorpay ledger - amount, currency, status matched.</p>
    </div>
  );
}

function Evidence() {
  const rows = [
    ['Action', 'refund.payment - $4,200.00 USD'],
    ['Policy', 'R4 - approval above $500 - passed'],
    ['Approval', 'priya@acme.com - 12:04 IST'],
    ['Verified', 'Razorpay ledger - matched'],
    ['Evidence', 'sha256:9f2c...b41'],
  ];
  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8a867a]">Evidence</p>
          <h4 className="mt-1 text-[16px] font-semibold text-[#1a1a17]">Signed Action Receipt</h4>
        </div>
        <Pill tone="success">Matched</Pill>
      </div>
      <div className="mt-4 overflow-hidden rounded-[12px] border border-[#e4e0d6] bg-white">
        <div className="h-[3px] bg-[linear-gradient(90deg,#2f5f66,#244d53)]" />
        <div className="divide-y divide-[#efeee7] px-4">
          {rows.map(([label, value]) => (
            <div key={label} className="grid grid-cols-[6.5rem_1fr] gap-3 py-2.5">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-[#8a867a]">{label}</span>
              <span className="text-[12px] text-[#1a1a17] [font-variant-numeric:tabular-nums]">{value}</span>
            </div>
          ))}
        </div>
        <div className="m-4 rounded-[10px] border border-[#2f5f66]/15 bg-[rgba(47,95,102,0.06)] p-3">
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-[#2f5f66]">Signature</p>
          <p className="mt-1 break-all font-mono text-[11px] text-[#2f5f66]">HMAC-SHA256 - key zrk_live_1 - 7f3a...d92c</p>
        </div>
      </div>
    </div>
  );
}

function Connectors() {
  const items = [
    ['Stripe', 'refund + payout ledger', 'healthy', 'success'],
    ['Razorpay', 'payout + refund ledger', 'healthy', 'success'],
    ['Salesforce', 'CRM record verify', 'template', 'warning'],
    ['PostgreSQL', 'read-only source of truth', 'healthy', 'success'],
    ['Slack', 'approval routing', 'connected', 'accent'],
  ] as const;
  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8a867a]">Connectors</p>
          <h4 className="mt-1 text-[16px] font-semibold text-[#1a1a17]">Verifiers and routing</h4>
        </div>
        <Pill tone="success">Coverage 92%</Pill>
      </div>
      <div className="mt-4 divide-y divide-[#efeee7] overflow-hidden rounded-[10px] border border-[#e4e0d6] bg-white">
        {items.map(([name, desc, status, tone]) => (
          <div key={name} className="flex items-center justify-between gap-2 px-3 py-2.5">
            <div className="flex min-w-0 items-center gap-2.5">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md border border-[#e4e0d6] bg-[#f7f6f2] font-mono text-[10px] font-semibold text-[#2f5f66]">{name.charAt(0)}</span>
              <div className="min-w-0">
                <p className="truncate text-[12px] font-medium text-[#1a1a17]">{name}</p>
                <p className="truncate font-mono text-[10px] text-[#8a867a]">{desc}</p>
              </div>
            </div>
            <Pill tone={tone}>{status}</Pill>
          </div>
        ))}
      </div>
    </div>
  );
}

function render(id: string) {
  switch (id) {
    case 'approvals': return <Approvals />;
    case 'actions': return <Actions />;
    case 'evidence': return <Evidence />;
    case 'connectors': return <Connectors />;
    default: return <MissionControl />;
  }
}

const LOOP = ['Agents', 'Policies', 'Approvals', 'Outcomes', 'Evidence', 'Connectors'];

export function DashboardMock() {
  const reduced = Boolean(useReducedMotion());
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [index, setIndex] = useState(0);
  const [inView, setInView] = useState(true);

  useEffect(() => {
    const node = rootRef.current;
    if (!node || typeof IntersectionObserver === 'undefined') return undefined;
    const obs = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { threshold: 0.25 });
    obs.observe(node);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (reduced || !inView) return undefined;
    const t = window.setInterval(() => setIndex((i) => (i + 1) % MODULES.length), 3600);
    return () => window.clearInterval(t);
  }, [reduced, inView]);

  const active = MODULES[index];

  return (
    <div ref={rootRef} className="relative">
      <div className="pointer-events-none absolute -inset-x-10 -top-10 bottom-0 -z-10 bg-[radial-gradient(60%_50%_at_50%_0%,rgba(79,90,82,0.10),transparent_70%)]" />
      <div className="overflow-hidden rounded-[16px] border border-[#d8dbd2] bg-[#f7f6f2] shadow-[0_2px_6px_rgba(42,45,40,0.05),0_40px_90px_-40px_rgba(42,45,40,0.35)]">
        {/* window bar */}
        <div className="flex items-center gap-2 border-b border-[#e4e0d6] bg-white px-4 py-2.5">
          <img src="/zroky.png" alt="Zroky" className="h-4 w-4 rounded object-contain" />
          <span className="ml-1 rounded-md bg-[#efeee7] px-2 py-0.5 font-mono text-[10px] text-[#8a867a]">app.zroky.com / {active.url}</span>
          <span className="ml-auto hidden gap-1.5 sm:flex">
            <span className="h-2.5 w-2.5 rounded-full bg-[#e4e0d6]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#e4e0d6]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#e4e0d6]" />
          </span>
        </div>

        {/* module tabs */}
        <div className="flex flex-wrap gap-1.5 border-b border-[#e4e0d6] bg-white px-3 py-2.5">
          {MODULES.map((m, i) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setIndex(i)}
              className={`rounded-full px-3 py-1 text-[11px] font-semibold transition ${
                i === index ? 'bg-[#1a1a17] text-white' : 'text-[#57564e] hover:text-[#1a1a17]'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {/* content */}
        <div className="relative min-h-[330px] overflow-hidden bg-[#f7f6f2] p-4 sm:p-5">
          <AnimatePresence mode="wait">
            <motion.div
              key={active.id}
              initial={reduced ? false : { opacity: 0, x: 32 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reduced ? { opacity: 0 } : { opacity: 0, x: -32 }}
              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            >
              {render(active.id)}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* control-loop strip */}
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-[#e4e0d6] bg-white px-4 py-2.5">
          {LOOP.map((label) => (
            <span key={label} className="text-[11px] font-medium text-[#8a867a]">{label}</span>
          ))}
        </nav>
      </div>
    </div>
  );
}
