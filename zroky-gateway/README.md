# zroky-gateway

Open-source multi-provider LLM gateway for AI agent telemetry � a high-performance flight recorder for OpenAI-compatible APIs, Anthropic, and Gemini.

[![License: FSL-1.1-MIT](https://img.shields.io/badge/license-FSL--1.1--MIT-blue)](LICENSE)
[![Go 1.22+](https://img.shields.io/badge/go-1.22+-blue)](https://golang.org)

Zroky Gateway sits between your application and upstream model providers. It forwards requests, strips Zroky-only headers before they reach providers, redacts telemetry copies, and emits structured agent evidence to Zroky Cloud or an approved endpoint.

## Why developers use it

- **One central capture point** for polyglot stacks and third-party agent frameworks.
- **Not OpenAI-only**: supports OpenAI-compatible routes, Anthropic Messages, and Google Gemini paths.
- **Zero provider-path mutation**: request/response bytes pass through; redaction applies only to telemetry copies.
- **Production-safe emit**: telemetry runs asynchronously and never blocks provider responses.
- **Open data plane**: run the gateway with project allowlists and caller auth.

## 5-minute quickstart

```bash
docker run -d \
  -p 8090:8090 \
  -e ZROKY_EMIT_MODE=http \
  -e ZROKY_API_URL=https://api.zroky.com \
  -e ZROKY_INGEST_URL=https://api.zroky.com/api/v1/ingest \
  -e ZROKY_GATEWAY_API_KEY=$ZROKY_GATEWAY_API_KEY \
  ghcr.io/zroky-ai/zroky-gateway:latest
```

Point any OpenAI-compatible client at the gateway:

```bash
export OPENAI_BASE_URL=http://localhost:8090/v1
```

Or in code:

```ts
import OpenAI from "openai";

const openai = new OpenAI({
  baseURL: "http://localhost:8090/v1",
  defaultHeaders: {
    "X-Zroky-Project-Id": process.env.ZROKY_PROJECT_ID!,
    "X-Zroky-Agent-Name": "refund-agent",
    "X-Zroky-Workflow-Name": "refund-review",
    "X-Zroky-Prompt-Version": "refund-v42",
  },
});
```

## Supported providers

| Provider | Gateway path | Upstream |
|---|---|---|
| OpenAI Chat Completions | `/v1/chat/completions` | `https://api.openai.com/v1/chat/completions` |
| OpenAI Responses | `/v1/responses` | `https://api.openai.com/v1/responses` |
| OpenAI Embeddings | `/v1/embeddings` | `https://api.openai.com/v1/embeddings` |
| Anthropic Messages | `/v1/messages` | `https://api.anthropic.com/v1/messages` |
| Google Gemini | `/v1beta/models/...` | `https://generativelanguage.googleapis.com/v1beta/models/...` |

The path suffix is forwarded verbatim to the provider route configured for that provider.

## SDK or Gateway?

| Scenario | Recommended approach |
|---|---|
| Python/Node app and SDK install is easy | `zroky-sdk` or `@zroky/sdk` |
| Multiple languages/services | Gateway |
| You cannot modify app code | Gateway |
| You need a local/prod proxy and centralized PII boundary | Gateway |
| You want in-process spans for retrieval/memory | SDK + optional Gateway |

## Request headers

| Header | Required | Description |
|---|---|---|
| `X-Zroky-Project-Id` | Yes | Zroky project identifier |
| `X-Project-Id` | No | Alias for `X-Zroky-Project-Id` |
| `X-Zroky-Call-Id` | No | Caller-provided call ID |
| `X-Zroky-Agent-Name` | No | Agent label |
| `X-Zroky-Session-Id` | No | User/session grouping |
| `X-Zroky-Workflow-Id` | No | Workflow run grouping |
| `X-Zroky-Workflow-Name` | No | Human-readable workflow name |
| `X-Zroky-Prompt-Version` | No | Prompt deploy version |
| `X-Zroky-Step-Index` | No | Workflow step index |
| `X-Zroky-Trace-Id` | No | Distributed trace ID |
| `X-Zroky-Parent-Call-Id` | No | Parent span/call ID |

These headers are stripped before forwarding to OpenAI, Anthropic, or Google.

## PII redaction

The gateway redacts telemetry copies before emitting to Zroky. The raw provider request/response stream is not modified.

Default redaction patterns:

- Email addresses
- Phone numbers
- Luhn-valid credit card numbers
- Social Security Numbers

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8090` | Gateway listen port |
| `ZROKY_EMIT_MODE` | `redis` | `redis`, `http`, or `dual` |
| `ZROKY_API_URL` | `https://api.zroky.com` | Zroky control plane URL |
| `ZROKY_INGEST_URL` | `${ZROKY_API_URL}/api/v1/ingest` | Direct HTTP ingest endpoint |
| `ZROKY_GATEWAY_API_KEY` | required | Zroky API key |
| `ZROKY_GATEWAY_AUTH_TOKEN` | empty | Optional token required from callers |
| `ZROKY_ALLOWED_PROJECT_IDS` | empty | Optional project allowlist |
| `OPENAI_API_KEY` | empty | Optional upstream key injected by gateway |
| `ANTHROPIC_API_KEY` | empty | Optional upstream key injected by gateway |
| `GOOGLE_API_KEY` | empty | Optional upstream key injected by gateway |
| `MAX_BODY_BYTES` | `4194304` | Maximum captured body bytes |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warn`, `error` |

## Architecture

```text
Your App
  �
  � provider-compatible request + X-Zroky-* context
  ?
zroky-gateway
  +- strip Zroky headers before upstream
  +- forward request to provider
  +- stream response back to caller
  +- redact bounded telemetry copy ? emit IngestEventV2
       +- Redis Stream
       +- HTTP ingest
       +- dual mode
```

## What is not open source

This repo is part of the free Zroky Watch OSS data plane. The Zroky backend, dashboard, judge engine, diagnosis logic, billing, and autonomous workflow are proprietary and delivered through Zroky Cloud and enterprise agreements.

## Build and test

```bash
go build -o zroky-gateway ./cmd/gateway
go test ./...
go vet ./...
```

Benchmark:

```bash
GATEWAY_URL=http://localhost:8090 go run bench/bench_gateway_overhead_go.go
```

## License

[FSL-1.1-MIT](LICENSE) � free for any use except building a competing product. Converts to plain MIT on the second anniversary of each release.
