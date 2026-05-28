import { motion } from 'framer-motion';

const quotes = [
  {
    text: "We were spending 2-3 hours per incident reverse-engineering why our refund agent looped. Zroky turned that into 15 minutes with a verified fix PR attached.",
    name: 'Senior Platform Engineer',
    role: 'Series B AI-native fintech',
    initials: 'SP',
  },
  {
    text: "The replay proof was the thing that convinced our team to actually ship the fix. We stopped debating whether the candidate worked and started trusting the evidence.",
    name: 'AI Infrastructure Lead',
    role: 'Enterprise workflow automation',
    initials: 'AI',
  },
  {
    text: "Our on-call rotation used to dread agent incidents. Now the first thing we see is a diagnosis card with root cause, affected calls, and a suggested replay. It changed how we operate.",
    name: 'Staff Engineer, Agent Platform',
    role: 'Pre-IPO vertical SaaS company',
    initials: 'SE',
  },
];

const LOGOS = [
  'LangGraph', 'CrewAI', 'AutoGen', 'OpenAI', 'Anthropic', 'Mistral', 'LlamaIndex', 'Haystack', 'Slack', 'Teams',
];

export default function SocialProof() {
  return (
    <section className="relative w-full border-t border-panel-border bg-white py-24 md:py-28">
      <div className="mx-auto w-full max-w-[92rem] px-4 sm:px-5 lg:px-8">

        {/* Infinite marquee logo strip */}
        <div className="mb-16 flex flex-col items-center gap-5 text-center">
          <p className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-tertiary">
            Works with the tools and channels your team already uses
          </p>
          <div className="relative w-full overflow-hidden">
            {/* Fade edges */}
            <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-white to-transparent" />
            <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-white to-transparent" />
            <motion.div
              className="flex gap-3 w-max"
              animate={{ x: ['0%', '-50%'] }}
              transition={{ duration: 22, ease: 'linear', repeat: Infinity }}
            >
              {[...LOGOS, ...LOGOS].map((logo, i) => (
                <span
                  key={i}
                  className="inline-flex items-center rounded-full border border-panel-border bg-canvas px-4 py-2 text-xs font-extrabold text-secondary whitespace-nowrap"
                >
                  {logo}
                </span>
              ))}
            </motion.div>
          </div>
        </div>

        {/* Section header */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4 }}
          className="mx-auto max-w-xl text-center"
        >
          <span className="eyebrow justify-center">Early access</span>
          <h2 className="mt-4 text-balance text-3xl font-black leading-tight text-primary md:text-4xl">
            From developers who shipped agents in production and needed this.
          </h2>
        </motion.div>

        {/* Quote cards */}
        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {quotes.map((q, i) => (
            <motion.div
              key={q.name}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.12 }}
              whileHover={{ y: -4, boxShadow: '0 12px 40px -8px rgba(0,0,0,0.12)' }}
              className="flex flex-col justify-between rounded-[1.5rem] border border-panel-border bg-canvas p-6 shadow-sm cursor-default"
            >
              <p className="text-base font-bold leading-7 text-primary">
                "{q.text}"
              </p>
              <div className="mt-6 flex items-center gap-3">
                <motion.span
                  whileHover={{ scale: 1.1 }}
                  className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary text-xs font-black text-white"
                >
                  {q.initials}
                </motion.span>
                <div>
                  <div className="text-sm font-black text-primary">{q.name}</div>
                  <div className="text-xs font-bold text-tertiary">{q.role}</div>
                </div>
              </div>
            </motion.div>
          ))}
        </div>

      </div>
    </section>
  );
}
