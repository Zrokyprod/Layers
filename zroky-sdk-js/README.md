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
import { captureRetrieval, init, wrap } from "@zroky/sdk";

init({
  projectId: process.env.ZROKY_PROJECT_ID,
  apiKey: process.env.ZROKY_API_KEY,
});

// Before: const openai = new OpenAI();
const openai = wrap(new OpenAI(), { agentName: "support-agent" });

// All subsequent calls are captured automatically — no other changes needed.
const response = await openai.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Hello" }],
});

await captureRetrieval({
  query: "refund policy",
  indexName: "support-kb",
  documents: [{ id: "doc_123", score: 0.92 }],
  parentCallId: response._zroky_call_id,
});
```

That's it. Zroky captures latency, token usage, errors, stable prompt
fingerprints, RAG retrievals, and memory operations. Capture is non-blocking:
retryable ingest failures are retried and then kept in a bounded in-memory
buffer for the next successful emit.

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

### `init(config)`

Sets default SDK configuration for `wrap()`, `trace()`, and `outcome()`.

```ts
import { init } from "@zroky/sdk";

init({
  projectId: process.env.ZROKY_PROJECT_ID,
  apiKey: process.env.ZROKY_API_KEY,
  endpoint: process.env.ZROKY_ENDPOINT,
});
```

#### Config options

| Option | Type | Default | Description |
|---|---|---|---|
| `projectId` | `string` | `ZROKY_PROJECT_ID` env var | Your Zroky project identifier |
| `apiKey` | `string` | `ZROKY_API_KEY` env var | Your Zroky ingest API key |
| `endpoint` | `string` | `https://api.zroky.com/v1/ingest` | Override ingest endpoint |
| `agentName` | `string` | - | Label this call site (e.g. `"summariser-agent"`) |
| `agentFramework` | `string` | - | Agent framework tag (e.g. `"langgraph"`, `"custom-js"`) |
| `sessionId` | `string` | - | Group calls into a user session |
| `workflowId` | `string` | - | Group calls into a multi-step workflow |
| `traceId` | `string` | - | Group related spans into one trace |
| `parentCallId` | `string` | - | Link this call to a parent span/call |
| `environment` | `string` | - | Runtime environment (e.g. `"production"`, `"staging"`) |
| `disabled` | `boolean` | `false` | Set `true` to disable capture (e.g. in test environments) |

### `trace(fn, config?)`

Wraps an async function as a named trace span. Useful for multi-step
workflows where you want the whole run grouped together.

```ts
import { trace } from "@zroky/sdk";

const runWorkflow = trace(async () => {
  const step1 = await openai.chat.completions.create(/* ... */);
  const step2 = await openai.chat.completions.create(/* ... */);
  return { step1, step2 };
}, { projectId: "...", apiKey: "...", agentName: "planner" });

const result = await runWorkflow();
```

### `captureRetrieval(options, config?)`

Captures RAG/search context that happens outside the LLM call. Use it after
vector search, hybrid search, reranking, or knowledge-base lookup.

```ts
import { captureRetrieval } from "@zroky/sdk";

await captureRetrieval({
  query: "refund policy",
  indexName: "support-kb",
  retrieverVersion: "hybrid-v3",
  latencyMs: 17,
  documents: [
    { id: "doc_123", title: "Refunds", score: 0.92, contentPreview: "..." },
  ],
});
```

### `captureMemory(options, config?)`

Captures memory reads/writes/summaries so agent state changes are visible in
the same production trace as LLM calls.

```ts
import { captureMemory } from "@zroky/sdk";

await captureMemory({
  operation: "write",
  namespace: "customer-memory",
  keys: ["user_123:preferences"],
  itemCount: 1,
  bytes: 512,
});
```

### `promptFingerprint(text)`

Returns a stable, deterministic hash of a prompt string. Used internally to
detect repeated prompt shapes across calls (loop detection). You can also call
it directly to build your own deduplication logic.

```ts
import { promptFingerprint } from "@zroky/sdk";

const fp = promptFingerprint("Summarise the following: ...");
// 64-char SHA-256 hex digest, stable across runs and aligned with the Python SDK
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

## Using with a self-hosted Zroky backend

If you run the Zroky backend yourself, point the SDK at that backend's ingest
endpoint:

```ts
const openai = wrap(new OpenAI(), {
  projectId: "proj_xxxx",
  apiKey: "zroky_xxxx",
  endpoint: "http://localhost:8000/api/v1/ingest",
});
```

---

## What gets captured

Each call emits one structured event with:

| Field | Example |
|---|---|
| `call_id` | `"8d4f..."` |
| `event_id` | `"8d4f...:capture"` |
| `schema_version` | `"v2"` |
| `provider` | `"openai"` |
| `model` | `"gpt-4o"` |
| `call_type` | `"chat"`, `"retrieval"`, `"memory"`, or `"trace"` |
| `latency_ms` | `342` |
| `prompt_tokens` | `128` |
| `completion_tokens` | `64` |
| `total_tokens` | `192` |
| `status` | `"success"` or `"error"` |
| `error_message` | `"Rate limit exceeded"` (on error) |
| `prompt_fingerprint` | 64-char SHA-256 hex digest |
| `agent_name` | `"summariser-agent"` (if set) |
| `session_id` | (if set) |
| `workflow_id` | (if set) |

Emit is fire-and-forget for application safety. Retryable failures are retried
with exponential backoff, then buffered in memory and flushed with the next
successful emit. Instrumentation never throws into your application path.

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
