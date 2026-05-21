# @zroky/sdk

TypeScript / JavaScript SDK for [Zroky](https://zroky.com) — captures every
OpenAI (and compatible) call your AI agent makes, streams structured telemetry
to the Zroky control plane, and provides production-grade retry, fallback, and
preflight protection with **zero changes to your existing call sites**.

[![npm version](https://badge.fury.io/js/%40zroky%2Fsdk.svg)](https://www.npmjs.com/package/@zroky/sdk)
[![License: FSL-1.1-MIT](https://img.shields.io/badge/license-FSL--1.1--MIT-blue)](LICENSE)

---

## Install

```bash
npm install @zroky/sdk
# or
yarn add @zroky/sdk
# or
pnpm add @zroky/sdk
```

Peer dependency: `openai >= 4.0.0` (optional — only needed for `wrap()`).

---

## Quickstart — 2-line integration

```ts
import OpenAI from "openai";
import { wrap } from "@zroky/sdk";

// Before: const openai = new OpenAI();
const openai = wrap(new OpenAI(), {
  projectId: process.env.ZROKY_PROJECT_ID,
  apiKey: process.env.ZROKY_API_KEY,
});

// All subsequent calls are captured automatically — no other changes needed.
const response = await openai.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Hello" }],
});
```

That's it. Zroky captures latency, token usage, errors, and a stable prompt
fingerprint for every call, then fires a non-blocking background emit so your
call path is never slowed down.

---

## API

### `wrap(client, config?)`

Patches an existing OpenAI client to capture and emit telemetry.

```ts
import OpenAI from "openai";
import { wrap } from "@zroky/sdk";

const openai = wrap(new OpenAI(), config);
```

Returns the same client object (mutated in-place, same TypeScript type).

#### Config options

| Option | Type | Default | Description |
|---|---|---|---|
| `projectId` | `string` | `ZROKY_PROJECT_ID` env var | Your Zroky project identifier |
| `apiKey` | `string` | `ZROKY_API_KEY` env var | Your Zroky ingest API key |
| `endpoint` | `string` | `https://api.zroky.com/v1/ingest` | Override ingest endpoint (e.g. self-hosted gateway) |
| `agentName` | `string` | — | Label this call site (e.g. `"summariser-agent"`) |
| `sessionId` | `string` | — | Group calls into a user session |
| `workflowId` | `string` | — | Group calls into a multi-step workflow |
| `disabled` | `boolean` | `false` | Set `true` to disable capture (e.g. in test environments) |

### `trace(name, fn, config?)`

Wraps an async function as a named trace span. Useful for multi-step
workflows where you want the whole run grouped together.

```ts
import { trace } from "@zroky/sdk";

const result = await trace("my-workflow", async () => {
  const step1 = await openai.chat.completions.create(/* ... */);
  const step2 = await openai.chat.completions.create(/* ... */);
  return { step1, step2 };
}, { projectId: "...", apiKey: "..." });
```

### `promptFingerprint(text)`

Returns a stable, deterministic hash of a prompt string. Used internally to
detect repeated prompt shapes across calls (loop detection). You can also call
it directly to build your own deduplication logic.

```ts
import { promptFingerprint } from "@zroky/sdk";

const fp = promptFingerprint("Summarise the following: ...");
// "a3f8c12d" — stable across runs, not sensitive to whitespace
```

---

## Environment variables

```bash
ZROKY_PROJECT_ID=proj_xxxx      # required
ZROKY_API_KEY=zroky_xxxx        # required
ZROKY_ENDPOINT=https://...      # optional override
ZROKY_DISABLED=true             # optional: disable all capture
```

All options can also be passed directly to `wrap()` or `trace()` — env vars
are the fallback.

---

## Using with the Zroky Gateway (self-hosted ingest)

If you want requests to flow through your own infrastructure before reaching
Zroky, run [`zroky-gateway`](https://github.com/zroky-ai/zroky-gateway) and
point the SDK at it:

```ts
const openai = wrap(new OpenAI(), {
  projectId: "proj_xxxx",
  apiKey: "zroky_xxxx",
  endpoint: "http://your-gateway:8090/v1/ingest",
});
```

The gateway handles PII redaction, buffering, and forwards to the Zroky
control plane on your behalf.

---

## What gets captured

Each call emits one structured event with:

| Field | Example |
|---|---|
| `provider` | `"openai"` |
| `model` | `"gpt-4o"` |
| `call_type` | `"chat"` |
| `latency_ms` | `342` |
| `prompt_tokens` | `128` |
| `output_tokens` | `64` |
| `total_tokens` | `192` |
| `status` | `"success"` or `"error"` |
| `status_code` | `200` |
| `error_message` | `"Rate limit exceeded"` (on error) |
| `prompt_fingerprint` | `"a3f8c12d"` |
| `agent_name` | `"summariser-agent"` (if set) |
| `session_id` | (if set) |
| `workflow_id` | (if set) |

Emit is fire-and-forget — failures are silently swallowed so instrumentation
never crashes your application.

---

## Bundle size

The SDK ships as CJS + ESM, fully tree-shakeable, with **zero runtime
dependencies**. The `openai` peer dependency is optional. `prepublishOnly`
runs a bundle-size check to keep the footprint small.

---

## License

[FSL-1.1-MIT](LICENSE) — free for any use except building a competing product.
Converts to plain MIT on the second anniversary of each release.
See [fsl.software](https://fsl.software/) for the full terms.
