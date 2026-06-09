"use client";

import Link from "next/link";
import { ArrowRight, CheckCircle2, Code2, Copy, Terminal } from "lucide-react";
import { useState } from "react";

const sections = [
  { id: "quickstart", label: "Quickstart" },
  { id: "install", label: "Install SDK" },
  { id: "api-key", label: "Create API key" },
  { id: "capture", label: "Capture first run" },
  { id: "gateway", label: "Gateway option" },
  { id: "replay", label: "Replay failed run" },
  { id: "golden", label: "Promote to Golden" },
  { id: "ci", label: "Run CI gate" },
  { id: "repos", label: "SDK repos" },
];

const snippets = {
  javascript: {
    install: "npm install @zroky/sdk",
    capture: `import { Zroky } from "@zroky/sdk";
import OpenAI from "openai";

const zroky = new Zroky({
  apiKey: process.env.ZROKY_API_KEY,
});

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

const run = await zroky.capture("checkout-agent", async (trace) => {
  const response = await openai.chat.completions.create({
    model: "gpt-4.1-mini",
    messages: [
      { role: "system", content: "You are a checkout assistant." },
      { role: "user", content: "Apply the saved discount and finish checkout." },
    ],
  });

  trace.output(response.choices[0]?.message?.content ?? "");
  return response;
});`,
    replay: `await zroky.replay.create({
  traceId: "trc_failed_8f1",
  candidate: {
    promptVersion: "checkout-agent@fix-schema-guard",
  },
  gate: "must-pass",
});`,
    ci: `npx zroky gate run \\
  --suite checkout-goldens \\
  --fail-on regression \\
  --report json`,
  },
  python: {
    install: "pip install zroky",
    capture: `from zroky import Zroky
from openai import OpenAI
import os

zroky = Zroky(api_key=os.environ["ZROKY_API_KEY"])
openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

with zroky.capture("checkout-agent") as trace:
    response = openai.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "You are a checkout assistant."},
            {"role": "user", "content": "Apply the saved discount and finish checkout."},
        ],
    )
    trace.output(response.choices[0].message.content or "")`,
    replay: `zroky.replay.create(
    trace_id="trc_failed_8f1",
    candidate={"prompt_version": "checkout-agent@fix-schema-guard"},
    gate="must-pass",
)`,
    ci: `zroky gate run \\
  --suite checkout-goldens \\
  --fail-on regression \\
  --report json`,
  },
};

type Language = keyof typeof snippets;

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  const copyCode = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  return (
    <div className="z-code-block">
      <button type="button" onClick={copyCode} aria-label="Copy code">
        <Copy aria-hidden="true" />
        {copied ? "Copied" : "Copy"}
      </button>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}

export function PublicDocsPage() {
  const [language, setLanguage] = useState<Language>("javascript");
  const active = snippets[language];

  return (
    <section className="z-docs-layout">
      <aside className="z-docs-sidebar" aria-label="Docs table of contents">
        <strong>Docs v1</strong>
        {sections.map((section) => (
          <a key={section.id} href={`#${section.id}`}>
            {section.label}
          </a>
        ))}
      </aside>

      <article className="z-docs-main">
        <section id="quickstart" className="z-docs-card">
          <span className="z-kicker">Developer quickstart</span>
          <h1>Capture one failed run, replay the fix, and gate the release.</h1>
          <p>
            This v1 guide shows the shortest path from SDK install to CI gate. Use SDK capture when you control app
            code, or gateway capture when you want traffic routed through Zroky.
          </p>
          <div className="z-docs-tabs" role="tablist" aria-label="Language">
            {(["javascript", "python"] as const).map((item) => (
              <button
                key={item}
                type="button"
                className={item === language ? "is-active" : undefined}
                onClick={() => setLanguage(item)}
              >
                {item === "javascript" ? "JavaScript" : "Python"}
              </button>
            ))}
          </div>
        </section>

        <section id="install" className="z-docs-card">
          <h2>Install SDK</h2>
          <p>Install the SDK in the service that runs your AI agent.</p>
          <CodeBlock code={active.install} />
        </section>

        <section id="api-key" className="z-docs-card">
          <h2>Create API key</h2>
          <p>
            Create a project key from Zroky settings, then expose it as <code>ZROKY_API_KEY</code> in your runtime.
          </p>
          <div className="z-docs-checks">
            {["Project-scoped key", "Rotate from dashboard", "Keep provider keys separate"].map((item) => (
              <span key={item}>
                <CheckCircle2 aria-hidden="true" />
                {item}
              </span>
            ))}
          </div>
        </section>

        <section id="capture" className="z-docs-card">
          <h2>Capture first run</h2>
          <p>Wrap the agent path that can fail in production. Zroky keeps trace evidence attached to the run.</p>
          <CodeBlock code={active.capture} />
        </section>

        <section id="gateway" className="z-docs-card">
          <h2>Gateway option</h2>
          <p>Route provider calls through the Zroky gateway when you want capture without changing every call site.</p>
          <CodeBlock
            code={`OPENAI_BASE_URL=https://gateway.zroky.com/openai
ZROKY_API_KEY=zk_live_project_key
ZROKY_AGENT=checkout-agent`}
          />
        </section>

        <section id="replay" className="z-docs-card">
          <h2>Replay failed run</h2>
          <p>Use the failed trace id to replay the exact scenario against a candidate prompt, tool, or model change.</p>
          <CodeBlock code={active.replay} />
        </section>

        <section id="golden" className="z-docs-card">
          <h2>Promote to Golden</h2>
          <p>After a replay passes, promote the verified trace into a golden behavior contract.</p>
          <CodeBlock
            code={`zroky golden promote trc_failed_8f1 \\
  --suite checkout-goldens \\
  --label discount-tool-contract`}
          />
        </section>

        <section id="ci" className="z-docs-card">
          <h2>Run CI gate</h2>
          <p>Run replay suites during release. Fail the build if a known production failure regresses.</p>
          <CodeBlock code={active.ci} />
        </section>

        <section id="repos" className="z-docs-card z-docs-repos">
          <Terminal aria-hidden="true" />
          <h2>SDK repos</h2>
          <p>SDK repos will be linked here when public packages are released.</p>
          <div>
            <Link href="/signup" className="z-primary-button">
              Start free
              <ArrowRight aria-hidden="true" />
            </Link>
            <Link href="mailto:sales@zroky.com?subject=Zroky%20SDK%20access" className="z-secondary-button">
              Request SDK access
              <Code2 aria-hidden="true" />
            </Link>
          </div>
        </section>
      </article>
    </section>
  );
}
