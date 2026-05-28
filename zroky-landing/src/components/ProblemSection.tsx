import { motion } from 'framer-motion';
import { AlertTriangle, ArrowRight, Clock, Frown, HelpCircle, Repeat2 } from 'lucide-react';

const before = [
  { icon: AlertTriangle, label: 'Slack alert fires', detail: '"agent failed: timeout × 43"' },
  { icon: HelpCircle, label: 'Open 3 monitoring tools', detail: 'Datadog, CloudWatch, custom logs' },
  { icon: Clock, label: '3 hours of log diving', detail: '847 lines, no clear signal' },
  { icon: Frown, label: 'Ship a guess', detail: '"We think it\'s the retrieval..."' },
  { icon: Repeat2, label: 'Fails again next sprint', detail: 'Same root cause, different trace' },
];

const after = [
  { label: 'Issue #47', detail: 'Refund agent loops after tool timeout', status: 'HIGH' },
  { label: 'Root cause', detail: 'stale policy chunk in retrieval path', status: null },
  { label: 'Evidence', detail: '43 calls · $281 projected waste', status: null },
  { label: 'Replay', detail: 'candidate_fix_v2 → VERIFIED ✓', status: 'pass' },
  { label: 'Fix PR', detail: 'Opened with proof attached', status: 'done' },
];

export default function ProblemSection() {
  return (
    <section className="relative w-full border-t border-panel-border bg-white py-24 md:py-28">
      <div className="mx-auto w-full max-w-[92rem] px-4 sm:px-5 lg:px-8">

        <div className="mx-auto max-w-2xl text-center">
          <span className="eyebrow justify-center">The problem</span>
          <h2 className="mt-5 text-balance text-4xl font-black leading-tight text-primary md:text-5xl">
            Most teams debug agent failures the same broken way.
          </h2>
          <p className="mt-5 text-lg leading-8 text-secondary">
            Scattered alerts, hours of guesswork, fixes that fail again. Zroky turns that into one Issue, one replay, one PR.
          </p>
        </div>

        <div className="mt-16 grid gap-6 lg:grid-cols-2">

          {/* BEFORE */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.4 }}
            className="overflow-hidden rounded-[1.5rem] border border-danger/25 bg-danger/5"
          >
            <div className="border-b border-danger/15 bg-danger/10 px-5 py-4">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-danger" />
                <span className="text-sm font-black text-danger">Without Zroky</span>
              </div>
              <p className="mt-1 text-xs font-bold text-secondary">The usual agent debugging experience</p>
            </div>
            <div className="divide-y divide-danger/10 p-2">
              {before.map(({ icon: Icon, label, detail }, i) => (
                <motion.div
                  key={label}
                  initial={{ opacity: 0, x: -12 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.32, delay: i * 0.07 }}
                  className="flex items-start gap-3 rounded-xl px-4 py-3.5"
                >
                  <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-danger/10 text-danger">
                    <Icon className="h-4 w-4" />
                  </span>
                  <div>
                    <div className="text-sm font-black text-primary">{label}</div>
                    <div className="mt-0.5 text-xs font-bold text-secondary">{detail}</div>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>

          {/* AFTER */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.4, delay: 0.08 }}
            className="overflow-hidden rounded-[1.5rem] border border-success/25 bg-success/5"
          >
            <div className="border-b border-success/15 bg-success/10 px-5 py-4">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-success" />
                <span className="text-sm font-black text-success">With Zroky</span>
              </div>
              <p className="mt-1 text-xs font-bold text-secondary">Same failure. 15 minutes to a verified fix PR.</p>
            </div>
            <div className="divide-y divide-success/10 p-2">
              {after.map(({ label, detail, status }, i) => (
                <motion.div
                  key={label}
                  initial={{ opacity: 0, x: 12 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.32, delay: 0.12 + i * 0.07 }}
                  className="flex items-center justify-between gap-3 rounded-xl px-4 py-3.5"
                >
                  <div>
                    <div className="text-xs font-black uppercase tracking-[0.12em] text-tertiary">{label}</div>
                    <div className="mt-0.5 text-sm font-bold text-primary">{detail}</div>
                  </div>
                  {status === 'HIGH' && (
                    <span className="shrink-0 rounded-full border border-danger/25 bg-danger/10 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-danger">
                      HIGH
                    </span>
                  )}
                  {status === 'pass' && (
                    <span className="shrink-0 rounded-full border border-success/25 bg-success/10 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-success">
                      VERIFIED
                    </span>
                  )}
                  {status === 'done' && (
                    <span className="shrink-0 rounded-full border border-accent/25 bg-accent/10 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-accent">
                      READY
                    </span>
                  )}
                </motion.div>
              ))}
            </div>
          </motion.div>

        </div>

        {/* Stats row */}
        <div className="mt-8 grid grid-cols-3 overflow-hidden rounded-[1.5rem] border border-panel-border bg-white shadow-sm">
          {[
            ['3 hours → 15 min', 'Time to root cause'],
            ['Guessed → Proven', 'Fix confidence'],
            ['Recurs → Gated', 'Regression protection'],
          ].map(([value, label], i) => (
            <motion.div
              key={label}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.3, delay: i * 0.08 }}
              className="border-r border-panel-border px-6 py-5 last:border-r-0"
            >
              <div className="text-lg font-black text-primary md:text-xl">{value}</div>
              <div className="mt-1 text-xs font-bold text-secondary">{label}</div>
            </motion.div>
          ))}
        </div>

        {/* CTA */}
        <div className="mt-8 flex justify-center">
          <motion.a
            href="/auth/register"
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.97 }}
            className="inline-flex min-h-12 items-center gap-2 rounded-full bg-primary px-8 py-3 text-sm font-extrabold text-white shadow-sm transition duration-200 hover:bg-accent"
          >
            See it on your agents
            <ArrowRight className="h-4 w-4" />
          </motion.a>
        </div>

      </div>
    </section>
  );
}
