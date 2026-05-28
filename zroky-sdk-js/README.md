# @zroky/sdk

Open-source flight recorder SDK for production AI agents � TypeScript/JavaScript capture for LLM calls, tool paths, retrieval, memory, latency, cost, and failures.

[![npm version](https://badge.fury.io/js/%40zroky%2Fsdk.svg)](https://www.npmjs.com/package/@zroky/sdk)
[![License: FSL-1.1-MIT](https://img.shields.io/badge/license-FSL--1.1--MIT-blue)](LICENSE)

Zroky Watch is the open-source data plane for Zroky. It captures the evidence behind agent behavior from your runtime while keeping the capture path inspectable. Zroky Pilot/Cloud adds the private control plane: issue grouping, root-cause diagnosis, replay orchestration, judge verification, Goldens, CI gates, and team workflow.

## Why developers use it

- **Zero call-site rewrite for OpenAI clients**: wrap an existing client and keep the same API.
- **Capture more than LLM calls**: retrieval spans, memory operations, traces, outcomes, latency, cost, status, and prompt fingerprints.
- **Non-blocking by design**: ingest failures are retried and buffered; instrumentation never throws into your hot path.
- **Tiny package**: CJS + ESM, tree-shakeable, zero runtime dependencies, optional `openai` peer dependency.
- **Ready for replay**: captured incidents can become replay cases and CI Goldens in Zroky Pilot.

## Install

```bash
npm install @zroky/sdk
# or
pnpm add @zroky/sdk
# or
yarn add @zroky/sdk
```

## 5-minute quickstart

```ts
import OpenAI from "openai";
import { captureRetrieval, init, wrap } from "@zroky/sdk";

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
});

await captureRetrieval({
  query: "refund policy",
  indexName: "support-kb",
  documents: [{ id: "policy_v11", score: 0.91, title: "Refunds" }],
  parentCallId: response._zroky_call_id,
});
```

By default the SDK sends capture events to:

```text
https://api.zroky.com/v1/ingest
```

Override only when your Zroky team gives you a custom endpoint:

```bash
ZROKY_ENDPOINT=http://localhost:8000/v1/ingest
```

## SDK or Gateway?

| Need | Use |
|---|---|
| Node/TypeScript app and you can edit code | `@zroky/sdk` |
| Python app | `zroky-sdk` |
| Polyglot services or third-party frameworks | `zroky-gateway` |
| Strict network boundary before provider calls | `zroky-gateway` |

The Gateway supports OpenAI-compatible paths plus Anthropic and Gemini routes. This SDK focuses on JS/TS runtime capture and OpenAI-compatible wrapping.

## API surface

### `wrap(client, config?)`

Patches an existing OpenAI client to capture and emit telemetry while preserving the same client object and TypeScript type.

### `trace(fn, config?)`

Wraps an async function as a named trace span for multi-step agent workflows.

### `captureRetrieval(options, config?)`

Captures RAG/search context after vector search, hybrid search, reranking, or knowledge-base lookup.

### `captureMemory(options, config?)`

Captures memory reads, writes, summaries, namespaces, keys, item counts, and byte estimates.

### `outcome(options, config?)`

Links business outcomes back to captured calls for cost-of-failure analysis.

### `promptFingerprint(text)`

Returns a stable SHA-256 prompt-shape fingerprint aligned with the Python SDK.

## Configuration

| Option | Env var | Default | Description |
|---|---|---|---|
| `projectId` | `ZROKY_PROJECT_ID` | required | Zroky project identifier |
| `apiKey` | `ZROKY_API_KEY` | required | Zroky ingest API key |
| `endpoint` | `ZROKY_ENDPOINT` | `https://api.zroky.com/v1/ingest` | Ingest endpoint |
| `agentName` | - | - | Agent label |
| `agentFramework` | - | - | Framework tag such as `langgraph`, `custom-js` |
| `traceId` | - | generated/propagated | Trace grouping |
| `workflowId` | - | - | Workflow grouping |
| `disabled` | `ZROKY_DISABLED` | `false` | Disable capture |

## What gets captured

Each call emits a structured event with fields such as:

| Field | Example |
|---|---|
| `call_id` | `8d4f...` |
| `event_id` | `8d4f...:capture` |
| `schema_version` | `v2` |
| `provider` | `openai` |
| `model` | `gpt-4o-mini` |
| `call_type` | `chat`, `retrieval`, `memory`, `trace` |
| `latency_ms` | `342` |
| `prompt_tokens` | `128` |
| `completion_tokens` | `64` |
| `total_tokens` | `192` |
| `status` | `success` or `error` |
| `prompt_fingerprint` | stable SHA-256 prompt shape |
| `agent_name` | `support-agent` |

## What is not open source

This repo is part of the free Zroky Watch OSS data plane. The Zroky backend, dashboard, judge engine, diagnosis logic, billing, and autonomous workflow are proprietary and delivered through Zroky Cloud and enterprise agreements.

## Deployment model

| Mode | What you use | What you get |
|---|---|---|
| Watch OSS | SDK, Gateway, Replay Worker | Open instrumentation and replay execution against Zroky Cloud or an approved endpoint |
| Zroky Pilot | Zroky Cloud control plane | Issues, diagnosis, replay proof, Goldens, dashboard, and CI gates |

## Run tests

```bash
npm test
npm run build
npm run size
```

## Bundle size

`prepublishOnly` runs build and size checks. Current bundle target is under 30 KB raw.

## License

[FSL-1.1-MIT](LICENSE) � free for any use except building a competing product. Converts to plain MIT on the second anniversary of each release.
