import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, Copy, Terminal } from 'lucide-react';

const tabs = ['Python', 'TypeScript', 'Gateway'] as const;
type Tab = typeof tabs[number];

const code: Record<Tab, string> = {
  Python: `import zroky

# One decorator. That's it.
@zroky.trace(
    agent="refund_agent",
    workflow="refund_review",
)
async def handle_refund(request: RefundRequest):
    # Your existing agent code — unchanged
    chunks = await retriever.search(request.policy_id)
    result  = await llm.complete(chunks, request.query)
    return result

# Zroky captures: prompts, tool calls, retrieval
# chunks, latency, cost, and outcome automatically.`,

  TypeScript: `import { trace } from '@zroky/sdk';

// Wrap once, observe everything
export const handleRefund = trace(
  { agent: 'refund_agent', workflow: 'refund_review' },
  async (request: RefundRequest) => {
    // Your existing agent code — unchanged
    const chunks = await retriever.search(request.policyId);
    const result  = await llm.complete(chunks, request.query);
    return result;
  },
);

// Works with: LangGraph, CrewAI, AutoGen,
// Vercel AI SDK, OpenAI SDK, Anthropic SDK`,

  Gateway: `# Drop-in OpenAI-compatible proxy
# No SDK changes needed

export OPENAI_BASE_URL="https://gw.zroky.ai/v1"
export OPENAI_API_KEY="your-openai-key"
export ZROKY_PROJECT_ID="proj_xxxx"

# Your agents now route through Zroky Gateway.
# Every call is captured, grouped, and diagnosed
# automatically — no code changes required.

# Supports: OpenAI, Anthropic, Gemini, Mistral,
# Groq, OpenRouter, and any OpenAI-compatible API.`,
};

const installCmd: Record<Tab, string> = {
  Python: 'pip install zroky',
  TypeScript: 'npm install @zroky/sdk',
  Gateway: 'docker run -p 8080:8080 ghcr.io/zroky-ai/gateway',
};

export default function CodeSection() {
  const [activeTab, setActiveTab] = useState<Tab>('Python');
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(code[activeTab]);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <section className="relative w-full border-t border-panel-border bg-canvas py-24 md:py-28">
      <div className="mx-auto w-full max-w-[92rem] px-4 sm:px-5 lg:px-8">

        <div className="grid gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">

          {/* Left: copy */}
          <div>
            <span className="eyebrow">
              <Terminal className="h-3.5 w-3.5 text-accent" />
              Developer integration
            </span>
            <h2 className="mt-5 text-balance text-4xl font-black leading-tight text-primary md:text-5xl">
              One decorator. Zero changes to your agent.
            </h2>
            <p className="mt-5 text-lg leading-8 text-secondary">
              Zroky wraps your existing agent with a single decorator or a gateway swap.
              No refactoring, no vendor lock-in, no privacy risk.
            </p>

            <div className="mt-8 grid gap-3">
              {[
                'Works with any LLM provider — OpenAI, Anthropic, Mistral, and more',
                'Privacy-preserving by default — no raw prompts stored',
                'Open-source SDK and Gateway (FSL-1.1-MIT)',
                'No code changes to your existing agent logic',
              ].map((item) => (
                <div key={item} className="flex items-center gap-3 text-sm font-bold text-secondary">
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-accent" />
                  {item}
                </div>
              ))}
            </div>
          </div>

          {/* Right: code panel */}
          <div className="overflow-hidden rounded-[1.5rem] border border-panel-border bg-white shadow-premium">

            {/* Install strip */}
            <div className="flex items-center justify-between gap-4 border-b border-panel-border bg-canvas px-4 py-3">
              <span className="font-mono text-xs font-bold text-secondary">
                $ {installCmd[activeTab]}
              </span>
              <span className="rounded-full border border-success/25 bg-success/10 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-success">
                Latest
              </span>
            </div>

            {/* Tab bar */}
            <div className="flex items-center border-b border-panel-border bg-white px-3 py-2">
              <div className="flex gap-1">
                {tabs.map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(tab)}
                    className={`inline-flex min-h-9 items-center rounded-full px-4 text-xs font-extrabold transition duration-200 focus:outline-none focus:ring-2 focus:ring-accent/35 ${
                      activeTab === tab
                        ? 'bg-primary text-white'
                        : 'text-secondary hover:bg-canvas hover:text-primary'
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={copy}
                className="ml-auto flex items-center gap-1.5 rounded-full border border-panel-border bg-canvas px-3 py-1.5 text-xs font-bold text-secondary transition duration-200 hover:border-accent/35 hover:text-primary"
              >
                {copied ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>

            {/* Code block */}
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.18 }}
                className="bg-[#101216] px-5 py-5"
              >
                <pre className="overflow-x-auto font-mono text-[12.5px] leading-6 text-slate-200">
                  <code>{code[activeTab]}</code>
                </pre>
              </motion.div>
            </AnimatePresence>

            {/* Output preview */}
            <div className="border-t border-panel-border p-4">
              <div className="text-[10px] font-black uppercase tracking-[0.12em] text-tertiary">
                What you get in Zroky
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2">
                {['Complete trace', 'Issue diagnosis', 'Replay proof'].map((item) => (
                  <div
                    key={item}
                    className="rounded-lg border border-panel-border bg-canvas py-2 text-center text-[11px] font-bold text-secondary"
                  >
                    {item}
                  </div>
                ))}
              </div>
            </div>

          </div>

        </div>
      </div>
    </section>
  );
}
