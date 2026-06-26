export type DocsSlug =
  | 'quickstart'
  | 'python-sdk'
  | 'typescript-sdk'
  | 'gateway'
  | 'provider-keys'
  | 'replay'
  | 'goldens'
  | 'ci-gates'
  | 'troubleshooting';

export type CodeBlock = {
  label: string;
  language: string;
  code: string;
};

export type DocsSection = {
  id: string;
  title: string;
  intro?: string;
  steps?: string[];
  bullets?: string[];
  codeBlocks?: CodeBlock[];
  checks?: string[];
  warning?: string;
};

export type DocsArticle = {
  slug: DocsSlug;
  category: string;
  title: string;
  description: string;
  outcome: string;
  primaryCta?: {
    label: string;
    href: string;
  };
  sections: DocsSection[];
};

export const docsOrder: DocsSlug[] = [
  'quickstart',
  'python-sdk',
  'typescript-sdk',
  'gateway',
  'provider-keys',
  'replay',
  'goldens',
  'ci-gates',
  'troubleshooting',
];

export const pythonCaptureCode = `import os
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

export const typescriptCaptureCode = `import OpenAI from "openai";
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

export const gatewayDockerCode = `docker run -d \\
  -p 8090:8090 \\
  -e ZROKY_EMIT_MODE=http \\
  -e ZROKY_API_URL=https://api.zroky.com \\
  -e ZROKY_INGEST_URL=https://api.zroky.com/api/v1/ingest \\
  -e ZROKY_GATEWAY_API_KEY=$ZROKY_GATEWAY_API_KEY \\
  ghcr.io/zroky-ai/zroky-gateway:latest`;

export const gatewayClientCode = `import OpenAI from "openai";

const openai = new OpenAI({
  baseURL: "http://localhost:8090/v1",
  defaultHeaders: {
    "X-Zroky-Project-Id": "proj_xxxx",
    "X-Zroky-Agent-Name": "refund-agent",
    "X-Zroky-Workflow-Name": "refund-review",
    "X-Zroky-Prompt-Version": "refund-v42",
  },
});`;

export const ciActionCode = [
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

export const docsArticles: Record<DocsSlug, DocsArticle> = {
  quickstart: {
    slug: 'quickstart',
    category: 'Start here',
    title: 'Quickstart: capture a failure and turn it into release protection.',
    description:
      'Use this path when you want the shortest real adoption flow: create access, capture production evidence, diagnose it into an issue, run replay, promote a Golden, and wire a CI gate.',
    outcome: 'By the end, your first agent flow follows Capture -> Diagnose -> Issue -> Replay -> Golden -> CI Gate.',
    primaryCta: { label: 'Create account', href: 'https://zroky.com/signup' },
    sections: [
      {
        id: 'before-you-start',
        title: 'Before you start',
        intro: 'You only need Zroky project access to capture calls. A model provider key is not required until verified replay.',
        bullets: [
          'Create or join a Zroky account.',
          'Open dashboard settings and create a project API key.',
          'Copy the project id and API key into your service environment.',
          'Choose SDK capture when you can edit agent code, or Gateway capture when routing is faster.',
        ],
        codeBlocks: [
          {
            label: 'Environment',
            language: 'bash',
            code: `export ZROKY_PROJECT_ID="proj_xxxx"
export ZROKY_PROJECT="proj_xxxx"
export ZROKY_API_KEY="zk_live_xxxx"`,
          },
        ],
      },
      {
        id: 'capture',
        title: '1. Capture the first production call',
        intro: 'Start with one important agent workflow. Capture enough context for diagnosis, replay, and cost analysis.',
        steps: [
          'Install the Python or TypeScript SDK, or run the Gateway.',
          'Set project id and API key as environment variables.',
          'Wrap the provider call used by the agent.',
          'Run the agent normally against a real workflow.',
        ],
        codeBlocks: [
          { label: 'Python capture', language: 'python', code: pythonCaptureCode },
          { label: 'TypeScript capture', language: 'ts', code: typescriptCaptureCode },
        ],
        checks: [
          'A trace appears in the dashboard trace list.',
          'The trace has provider, model, prompt, response, status, latency, and cost context where available.',
          'If the call failed, it can be grouped into an issue.',
        ],
      },
      {
        id: 'failure-loop',
        title: '2. Move from failure to release signal',
        intro: 'The product loop is intentionally narrow. Do not create Goldens from raw traces. Use replay proof first.',
        steps: [
          'Open the Failure Inbox and review the diagnosed issue.',
          'Confirm the issue owner, impact, evidence, and replay readiness.',
          'Run stub replay for a cheap sanity check if you only need structure validation.',
          'Connect a provider key only when verified replay needs a real model call.',
          'Run verified replay against the original incident and candidate fix.',
          'Promote passing replay evidence to a Golden.',
          'Run the Golden set in CI and decide whether it should block release.',
        ],
        checks: [
          'Stub replay is labeled sanity-only.',
          'Verified replay prompts for a provider key if no active key exists.',
          'A Golden only comes from trusted replay proof.',
          'CI shows pass, advisory, or block behavior based on Golden results.',
        ],
      },
      {
        id: 'next',
        title: '3. Pick the detailed guide you need next',
        bullets: [
          'Use Python SDK if your agent service is Python.',
          'Use TypeScript SDK if your service runs in Node or Next.js.',
          'Use Gateway if you want routing-level capture with minimal code edits.',
          'Use Provider keys before verified replay.',
          'Use CI gates when Goldens are ready to protect releases.',
        ],
      },
    ],
  },
  'python-sdk': {
    slug: 'python-sdk',
    category: 'Capture',
    title: 'Python SDK: capture provider calls from a Python agent.',
    description:
      'Install the SDK, initialize the project, wrap the model call, and verify that Zroky receives production evidence.',
    outcome: 'A Python agent call appears in Zroky with enough context for trace inspection, issue grouping, replay, and cost analysis.',
    sections: [
      {
        id: 'install',
        title: 'Install',
        intro: 'Install Zroky beside the provider client your agent already uses.',
        codeBlocks: [{ label: 'Install packages', language: 'bash', code: 'pip install zroky openai' }],
      },
      {
        id: 'configure',
        title: 'Configure project access',
        intro: 'Use a project API key for capture. Keep provider keys separate; they are only needed for verified replay.',
        codeBlocks: [
          {
            label: 'Environment',
            language: 'bash',
            code: `export ZROKY_PROJECT="proj_xxxx"
export ZROKY_API_KEY="zk_live_xxxx"
export OPENAI_API_KEY="sk_provider_xxxx"`,
          },
        ],
      },
      {
        id: 'capture-call',
        title: 'Capture a call',
        intro: 'Initialize Zroky once at service startup, then call your provider through the captured wrapper.',
        codeBlocks: [{ label: 'Python', language: 'python', code: pythonCaptureCode }],
        checks: [
          'The trace is visible after the agent run finishes.',
          'The trace includes provider and model labels.',
          'The workflow can be filtered by environment and agent framework.',
        ],
      },
      {
        id: 'production-notes',
        title: 'Production notes',
        bullets: [
          'Initialize once during process startup, not before every request.',
          'Use environment="production" only for real production traffic.',
          'Do not print Zroky API keys or provider keys in logs.',
          'Capture one critical workflow first, then expand after traces are useful.',
        ],
      },
      {
        id: 'when-it-fails',
        title: 'When capture does not appear',
        checks: [
          'Confirm ZROKY_PROJECT and ZROKY_API_KEY are set in the same runtime as the agent.',
          'Confirm outbound HTTP to the Zroky API is allowed.',
          'Confirm the service ran the wrapped call path, not an uncaptured fallback path.',
          'Check whether the call failed before the provider request was made.',
        ],
      },
    ],
  },
  'typescript-sdk': {
    slug: 'typescript-sdk',
    category: 'Capture',
    title: 'TypeScript SDK: wrap the client used by your Node agent.',
    description:
      'Use the TypeScript SDK when your agent service owns the provider client and you want capture attached directly to workflow context.',
    outcome: 'Node or Next.js agent calls arrive in Zroky with trace, workflow, provider, and replay-ready evidence.',
    sections: [
      {
        id: 'install',
        title: 'Install',
        codeBlocks: [{ label: 'Install packages', language: 'bash', code: 'npm install @zroky-ai/sdk openai' }],
      },
      {
        id: 'configure',
        title: 'Configure project access',
        intro: 'Use Zroky project access for capture and keep the model provider key in your normal provider environment.',
        codeBlocks: [
          {
            label: 'Environment',
            language: 'bash',
            code: `export ZROKY_PROJECT_ID="proj_xxxx"
export ZROKY_API_KEY="zk_live_xxxx"
export OPENAI_API_KEY="sk_provider_xxxx"`,
          },
        ],
      },
      {
        id: 'wrap-client',
        title: 'Wrap the provider client',
        intro: 'Wrap once, then use the client normally. Zroky keeps the workflow and environment attached to the captured call.',
        codeBlocks: [{ label: 'TypeScript', language: 'ts', code: typescriptCaptureCode }],
        checks: [
          'The captured call appears in traces.',
          'The trace has agentName and workflowId context.',
          'Failures can be grouped into issues and sent to replay.',
        ],
      },
      {
        id: 'runtime-guidance',
        title: 'Runtime guidance',
        bullets: [
          'Initialize before the first captured provider call.',
          'Reuse the wrapped client instead of wrapping a new client for every request.',
          'Keep capture on the server side when prompts or user data are sensitive.',
          'Use clear workflow ids so Goldens later map to release-critical flows.',
        ],
      },
      {
        id: 'when-to-use-gateway',
        title: 'When Gateway is better',
        bullets: [
          'Use Gateway when several services call compatible provider endpoints and code changes would be slow.',
          'Use SDK capture when you need richer application-level workflow labels.',
          'Use both only when each service has a clear owner and duplicate capture is avoided.',
        ],
      },
    ],
  },
  gateway: {
    slug: 'gateway',
    category: 'Capture',
    title: 'Gateway: capture compatible provider traffic through a local proxy.',
    description:
      'Use the Gateway when routing provider traffic is faster than editing every agent service. It keeps capture separate from application code.',
    outcome: 'OpenAI-compatible traffic is captured with project, agent, workflow, and prompt-version headers.',
    sections: [
      {
        id: 'run-gateway',
        title: 'Run the Gateway',
        intro: 'Run the Gateway near your agent service. Start locally first, then move to your deployment runtime.',
        codeBlocks: [{ label: 'Docker', language: 'bash', code: gatewayDockerCode }],
      },
      {
        id: 'route-traffic',
        title: 'Route provider calls',
        intro: 'Point compatible clients at the Gateway and send Zroky context through headers.',
        codeBlocks: [
          { label: 'Set base URL', language: 'bash', code: 'export OPENAI_BASE_URL=http://localhost:8090/v1' },
          { label: 'Client headers', language: 'ts', code: gatewayClientCode },
        ],
        checks: [
          'The Gateway receives provider traffic.',
          'The dashboard shows traces under the configured project id.',
          'Agent name, workflow name, and prompt version are visible in captured context.',
        ],
      },
      {
        id: 'deployment',
        title: 'Deployment guidance',
        bullets: [
          'Run Gateway in the same network boundary as the agent service when possible.',
          'Store ZROKY_GATEWAY_API_KEY as a secret, not in source code.',
          'Set one project id per environment or tenant model that your team can reason about.',
          'Keep provider credentials in the existing service environment unless your deployment intentionally centralizes them.',
        ],
      },
      {
        id: 'choose-gateway',
        title: 'When Gateway is the right path',
        bullets: [
          'You need coverage before touching multiple codebases.',
          'Your client already supports an OpenAI-compatible base URL.',
          'You want consistent capture headers across services.',
          'You can control routing and secrets in the deployment environment.',
        ],
      },
    ],
  },
  'provider-keys': {
    slug: 'provider-keys',
    category: 'Replay',
    title: 'Provider keys: connect only when verified replay needs a real model call.',
    description:
      'Zroky does not ask for provider keys during signup or capture. A key is required when real replay, Golden replay, or CI replay needs provider execution.',
    outcome: 'Verified replay can run through your provider account while capture remains lightweight and adoption-friendly.',
    sections: [
      {
        id: 'rule',
        title: 'The rule',
        bullets: [
          'Signup does not need a provider key.',
          'SDK capture and Gateway capture do not need a provider key.',
          'Trace inspection and issue review do not need a provider key.',
          'Verified replay, Golden replay, and CI replay require an active provider key unless Zroky-managed replay is enabled for your account.',
        ],
      },
      {
        id: 'connect',
        title: 'Connect a provider key',
        intro: 'Use the dashboard provider settings or the inline replay prompt when a verified replay is started.',
        steps: [
          'Open Settings > Provider keys in the dashboard.',
          'Choose the provider used by the captured incident.',
          'Add a label that makes ownership clear, such as production-openai or staging-anthropic.',
          'Paste the provider API key and save.',
          'Return to Replay Lab and run verified replay.',
        ],
        checks: [
          'The key is shown as active after save.',
          'The plaintext key is not shown again after submission.',
          'The replay action continues after a valid key exists.',
        ],
      },
      {
        id: 'modes',
        title: 'Which actions require a key',
        bullets: [
          'real_llm replay requires a provider key.',
          'mocked-tool replay requires a provider key when the model call is real.',
          'live-sandbox and shadow replay require a provider key.',
          'Golden replay and CI replay require a provider key when they execute real model calls.',
          'stub replay does not require a provider key and remains sanity-only.',
        ],
      },
      {
        id: 'cost-control',
        title: 'Cost control',
        bullets: [
          'BYOK keeps model spend visible in your provider account.',
          'Use replay credits and CI execution caps to prevent surprise usage.',
          'Start with stub replay for structure checks, then spend real provider tokens only on release-relevant incidents.',
          'Use pricing limits to decide when a team should move from Starter to Pro.',
        ],
      },
    ],
  },
  replay: {
    slug: 'replay',
    category: 'Replay',
    title: 'Replay: prove a fix against the incident that actually happened.',
    description:
      'Replay turns a captured production failure into fix evidence. It should answer whether the original failure is reproduced and whether the candidate change passes.',
    outcome: 'A replay run produces a trusted pass, fail, or inconclusive result that can become a Golden only when it proves the fix.',
    sections: [
      {
        id: 'start',
        title: 'Start from evidence',
        steps: [
          'Open a failed trace, issue, or Replay Lab.',
          'Select the original captured call or highest-priority issue.',
          'Choose replay mode.',
          'Add candidate changes only when you are testing a fix.',
          'Run replay and inspect the verdict before promoting anything.',
        ],
      },
      {
        id: 'modes',
        title: 'Replay modes',
        bullets: [
          'stub: cheap sanity check, no provider key, not trusted fix proof.',
          'real_llm: real provider execution using your connected provider key.',
          'mocked-tool: keeps model verification while controlling tool behavior.',
          'live-sandbox: runs against sandboxed live dependencies when available.',
          'shadow: compares behavior without making it the production path.',
        ],
        warning: 'Do not treat stub replay as verified proof. Stub can catch shape problems, but it cannot prove model behavior.',
      },
      {
        id: 'verdict',
        title: 'Read the verdict',
        checks: [
          'Reproduced original failure: the replay recreated the incident conditions.',
          'Candidate passed: the proposed fix changed behavior enough to satisfy the expected result.',
          'Candidate failed: the fix did not resolve the incident or introduced a new failure.',
          'Inconclusive: required context, tools, or provider execution were unavailable.',
        ],
      },
      {
        id: 'after-replay',
        title: 'After a passing replay',
        steps: [
          'Save the replay run summary.',
          'Promote the verified fix to a Golden when the behavior should never regress.',
          'Attach the Golden to the correct release workflow.',
          'Run it in CI before enabling blocking behavior.',
        ],
      },
    ],
  },
  goldens: {
    slug: 'goldens',
    category: 'Release memory',
    title: 'Goldens: turn verified fixes into release memory.',
    description:
      'A Golden is not a static test written from a guess. In Zroky, the strongest Golden starts from a real incident and verified replay proof.',
    outcome: 'A fixed production failure becomes a reusable guard that can run before release.',
    sections: [
      {
        id: 'create',
        title: 'Create a Golden',
        steps: [
          'Run verified replay from a failed trace or issue.',
          'Confirm the candidate fix passes with trusted replay proof.',
          'Choose Promote to Golden.',
          'Name the Golden set after the protected workflow, not the bug ticket.',
          'Decide whether the Golden is advisory or eligible for CI blocking.',
        ],
        checks: [
          'The source replay is non-stub and trusted.',
          'The Golden has a clear workflow owner.',
          'The expected behavior is specific enough to fail on repeat regression.',
        ],
      },
      {
        id: 'organize',
        title: 'Organize Golden sets',
        bullets: [
          'Group by release-critical workflow, such as refund-review or claim-triage.',
          'Keep noisy or unstable cases advisory until they are reliable.',
          'Remove duplicate cases that test the same failure pattern.',
          'Review Goldens after model, policy, or tool changes.',
        ],
      },
      {
        id: 'run',
        title: 'Run Goldens',
        steps: [
          'Open Goldens in the dashboard.',
          'Select the set tied to the release workflow.',
          'Run the set manually before wiring CI, or trigger from Replay Lab.',
          'Inspect failures and decide whether they represent real release risk.',
        ],
      },
      {
        id: 'promote-to-ci',
        title: 'Promote to CI',
        bullets: [
          'Start as advisory while the team builds trust in the set.',
          'Enable blocking only for stable, release-critical Goldens.',
          'Keep failed CI runs linked to replay evidence so reviewers can understand the block.',
        ],
      },
    ],
  },
  'ci-gates': {
    slug: 'ci-gates',
    category: 'Release protection',
    title: 'CI gates: block repeated agent failures before deploy.',
    description:
      'CI gates run promoted Goldens against pull requests so production incidents become enforceable release checks.',
    outcome: 'A pull request can pass, warn, or block based on replay evidence from real production failures.',
    sections: [
      {
        id: 'setup',
        title: 'Add the GitHub Action',
        intro: 'Add Zroky to pull request CI after at least one Golden set exists.',
        codeBlocks: [{ label: 'GitHub Action', language: 'yaml', code: ciActionCode }],
      },
      {
        id: 'secrets',
        title: 'Configure secrets and variables',
        bullets: [
          'Store ZROKY_API_KEY as a GitHub secret.',
          'Store ZROKY_PROJECT_ID as a repository or organization variable.',
          'Keep provider keys in Zroky provider settings, not in the workflow file.',
          'Grant pull-requests: write only if you want Zroky to post PR comments.',
        ],
      },
      {
        id: 'blocking',
        title: 'Choose advisory or blocking behavior',
        bullets: [
          'Use advisory CI while the team validates Golden quality.',
          'Use fail_on_regression: true when failures should block merge.',
          'Keep high-noise Goldens out of blocking sets.',
          'Review every block with the replay summary before changing the test.',
        ],
      },
      {
        id: 'read-results',
        title: 'Read CI results',
        checks: [
          'Pass: protected Goldens replayed successfully.',
          'Warn: a non-blocking set found risk or missing proof.',
          'Block: a blocking Golden failed and the release should not proceed until reviewed.',
          'Provider key error: connect or refresh the provider key before running real replay CI.',
        ],
      },
    ],
  },
  troubleshooting: {
    slug: 'troubleshooting',
    category: 'Support',
    title: 'Troubleshooting: fix the common capture, replay, and CI failures.',
    description:
      'Use this page when Zroky is not receiving calls, replay is blocked, Goldens are noisy, or CI is not producing the expected result.',
    outcome: 'You can identify whether the problem is project access, capture path, provider key, replay mode, Golden quality, or CI configuration.',
    sections: [
      {
        id: 'capture-missing',
        title: 'Trace does not appear',
        checks: [
          'Confirm the service has ZROKY_API_KEY and ZROKY_PROJECT_ID or ZROKY_PROJECT at runtime.',
          'Confirm the wrapped SDK client or Gateway route is the path actually used by the agent.',
          'Confirm outbound network access to the Zroky ingest API.',
          'For Gateway, confirm OPENAI_BASE_URL points to the Gateway and headers include project id.',
        ],
      },
      {
        id: 'provider-key',
        title: 'Replay asks for a provider key',
        checks: [
          'This is expected for real_llm, mocked-tool with model execution, live-sandbox, shadow, Golden replay, and CI replay.',
          'Connect a provider key in Settings > Provider keys or from the inline replay prompt.',
          'Use stub replay only when you need sanity checks without provider spend.',
          'If a key exists, confirm it is active and belongs to the provider used by the captured incident.',
        ],
      },
      {
        id: 'replay-fails',
        title: 'Replay fails or is inconclusive',
        checks: [
          'Check whether the original trace has root call evidence.',
          'Check whether required tool context was captured.',
          'Check whether the candidate fix changed the prompt, policy, model, or tool behavior you intended.',
          'Check provider rate limits and account access if the replay reached the provider.',
        ],
      },
      {
        id: 'golden-noise',
        title: 'Golden is too noisy',
        checks: [
          'Move the Golden to advisory until it is stable.',
          'Use clearer expected behavior from the verified replay run.',
          'Remove duplicate cases that represent the same failure.',
          'Split mixed workflows into separate Golden sets.',
        ],
      },
      {
        id: 'ci-does-not-block',
        title: 'CI does not block',
        checks: [
          'Confirm fail_on_regression is true in the workflow.',
          'Confirm the Golden set is marked as blocking in Zroky.',
          'Confirm the GitHub Action has the expected project id and API key.',
          'Confirm the failed case belongs to the set that CI is running.',
        ],
      },
    ],
  },
};

export const docsNav = docsOrder.map((slug) => ({
  slug,
  title: docsArticles[slug].title,
  category: docsArticles[slug].category,
}));
