import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { AlertTriangle, Check, Plug, ShieldCheck, Zap } from 'lucide-react';

/* step 0 = approval pending, 1 = approved + verifying, 2 = verified + signed */
const FLOW = ['Held', 'Approved', 'Verified', 'Signed'];

function flowActive(step: number) {
  if (step === 0) return 1; // Held
  if (step === 1) return 2; // Approved
  return 4; // Verified + Signed
}

function SlackCard({ step, reduced }: { step: number; reduced: boolean }) {
  const approved = step >= 1;
  const signed = step >= 2;
  return (
    <div className="overflow-hidden rounded-[14px] border border-[#d8dbd2] bg-white shadow-[0_2px_6px_rgba(42,45,40,0.05),0_30px_60px_-38px_rgba(42,45,40,0.32)]">
      <div className="flex items-center gap-2 border-b border-[#e6e8e2] bg-[#f7f8f4] px-4 py-2.5">
        <span className="h-2 w-2 rounded-full bg-[#2f7d50]" />
        <span className="text-[12px] font-semibold text-[#20231f]"># agent-approvals</span>
        <span className="ml-auto font-mono text-[10px] text-[#8b9288]">Slack</span>
      </div>
      <div className="p-4">
        <div className="flex items-start gap-3">
          <img src="/zroky.png" alt="" className="h-8 w-8 shrink-0 rounded-[8px] border border-[#e6e8e2] object-contain" />
          <div className="min-w-0 flex-1">
            <p className="text-[12px] font-semibold text-[#20231f]">Zroky <span className="ml-1 rounded bg-[#eef0eb] px-1 py-0.5 font-mono text-[9px] font-medium text-[#8b9288]">APP</span></p>
            <div className="mt-2 rounded-[10px] border border-[#b87922]/25 bg-[#b87922]/[0.07] p-3">
              <p className="flex items-center gap-1.5 text-[12px] font-semibold text-[#8a5a16]">
                <AlertTriangle size={13} /> Approval needed
              </p>
              <p className="mt-1 text-[13px] font-semibold text-[#20231f]">refund.payment - $4,200.00</p>
              <p className="mt-0.5 font-mono text-[11px] text-[#8b9288]">agent: billing-ops - rule: amount &gt; $500</p>

              <div className="mt-3 min-h-[32px]">
                <AnimatePresence mode="wait">
                  {!approved ? (
                    <motion.div
                      key="buttons"
                      initial={reduced ? false : { opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.25 }}
                      className="flex items-center gap-2"
                    >
                      <span className="inline-flex h-8 items-center gap-1.5 rounded-[8px] bg-[#2f7d50] px-3 text-[12px] font-semibold text-white">
                        <Check size={13} /> Approve
                      </span>
                      <span className="inline-flex h-8 items-center rounded-[8px] border border-[#d8dbd2] bg-white px-3 text-[12px] font-semibold text-[#9f3f36]">Deny</span>
                    </motion.div>
                  ) : (
                    <motion.p
                      key="approved"
                      initial={reduced ? false : { opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.3 }}
                      className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-[#276844]"
                    >
                      <Check size={14} /> Approved by priya - 12:04 IST
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>
            </div>

            {signed ? (
              <motion.div
                initial={reduced ? false : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className="mt-2 flex items-start gap-2 rounded-[10px] border border-[#2f7d50]/20 bg-[#2f7d50]/[0.07] p-2.5"
              >
                <ShieldCheck size={14} className="mt-0.5 shrink-0 text-[#2f7d50]" />
                <p className="text-[11px] leading-snug text-[#276844]">
                  Executed with isolated credential, verified against Razorpay ledger, signed into receipt <span className="font-mono">zrk_rc_9f2c</span>.
                </p>
              </motion.div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function FlowStrip({ step }: { step: number }) {
  const active = flowActive(step);
  return (
    <div className="mt-4 flex items-center">
      {FLOW.map((label, i) => {
        const done = i < active;
        const tone = i < 1 ? '#b87922' : '#2f7d50';
        return (
          <div key={label} className="flex flex-1 items-center last:flex-none">
            <div className="flex flex-col items-center gap-1.5">
              <motion.span
                className="grid h-5 w-5 place-items-center rounded-full text-white"
                animate={{ backgroundColor: done ? tone : '#d8dbd2' }}
                transition={{ duration: 0.3 }}
              >
                <Check size={11} />
              </motion.span>
              <span className={`text-[10px] font-semibold ${done ? 'text-[#20231f]' : 'text-[#a2a69c]'}`}>{label}</span>
            </div>
            {i < FLOW.length - 1 && (
              <div className="relative mx-1 h-[2px] flex-1 self-start" style={{ marginTop: 9 }}>
                <div className="absolute inset-0 rounded-full bg-[#e0e2db]" />
                <motion.div
                  className="absolute inset-y-0 left-0 rounded-full bg-[#4f5a52]"
                  animate={{ width: i < active - 1 ? '100%' : '0%' }}
                  transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

const POINTS = [
  { icon: Plug, text: 'Connect systems of record once - Stripe, Razorpay, Salesforce, Postgres.' },
  { icon: Zap, text: 'Held actions ping Slack (or dashboard) for a human decision in seconds.' },
  { icon: ShieldCheck, text: 'Every approval is verified and signed into an audit-grade receipt.' },
];

const LOGOS = ['OpenAI', 'LangGraph', 'CrewAI', 'MCP', 'Stripe', 'Razorpay', 'Salesforce', 'Zendesk', 'Postgres', 'Slack'];

export function RealtimeControl() {
  const reduced = Boolean(useReducedMotion());
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [step, setStep] = useState(reduced ? 2 : 0);
  const [inView, setInView] = useState(true);

  useEffect(() => {
    const node = rootRef.current;
    if (!node || typeof IntersectionObserver === 'undefined') return undefined;
    const obs = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { threshold: 0.2 });
    obs.observe(node);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (reduced || !inView) return undefined;
    const durations = [2600, 1600, 2000];
    const t = window.setTimeout(() => setStep((s) => (s + 1) % 3), durations[step]);
    return () => window.clearTimeout(t);
  }, [step, inView, reduced]);

  return (
    <section id="realtime" ref={rootRef} className="w-full scroll-mt-28 bg-[#fbfcfa] px-4 py-16 text-[#20231f] md:py-20">
      <div className="mx-auto grid max-w-[1340px] items-center gap-12 lg:grid-cols-[0.92fr_1.08fr]">
        <div>
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#4f5a52]">Real-time control</p>
          <h2 className="mt-3 text-balance text-[2rem] font-semibold leading-[1.08] tracking-[-0.025em] text-[#20231f] md:text-[2.75rem]">
            Connect once. Approve where you already work.
          </h2>
          <p className="mt-4 max-w-md text-[1.02rem] leading-[1.6] text-[#5b615a]">
            Zroky sits between your agents and your real systems. Every high-risk action is routed for a human decision in real time, then verified against the system of record.
          </p>
          <ul className="mt-6 space-y-3">
            {POINTS.map((p) => (
              <li key={p.text} className="flex items-start gap-3">
                <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-[10px] border border-[#d8dbd2] bg-[#e8ebe4] text-[#4f5a52]">
                  <p.icon size={16} />
                </span>
                <span className="text-[14px] leading-relaxed text-[#3f4942]">{p.text}</span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <SlackCard step={step} reduced={reduced} />
          <FlowStrip step={step} />
        </div>
      </div>

      {/* merged systems strip */}
      <div className="mx-auto mt-14 max-w-[1340px]">
        <p className="mb-5 text-center font-mono text-[11px] uppercase tracking-[0.18em] text-[#8b9288]">
          Works across your agent frameworks and systems of record
        </p>
        <div className="marquee-mask relative w-full overflow-hidden">
          <div className="marquee-track gap-12">
            {[...LOGOS, ...LOGOS].map((name, i) => (
              <span key={`${name}-${i}`} className="whitespace-nowrap text-lg font-semibold text-[#5b615a]/60">{name}</span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
