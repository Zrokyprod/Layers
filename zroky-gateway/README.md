# zroky-gateway

A lightweight, high-performance **reverse-proxy gateway** for LLM calls. It
sits between your application and the upstream AI providers (OpenAI, Anthropic,
Google), transparently forwards every request, and streams structured telemetry
to [Zroky](https://zroky.com) — all in a single-binary Docker image with
**p95 overhead < 8 ms** at 100 RPS.

[![License: FSL-1.1-MIT](https://img.shields.io/badge/license-FSL--1.1--MIT-blue)](LICENSE)
[![Go 1.22+](https://img.shields.io/badge/go-1.22+-blue)](https://golang.org)

---

## Why use the gateway instead of the SDK?

| Scenario | Recommended approach |
|---|---|
| Node.js / Python app, SDK is easy to add | [zroky-sdk](https://github.com/zroky-ai/zroky-sdk) / [zroky-sdk-js](https://github.com/zroky-ai/zroky-sdk-js) |
| Polyglot stack — multiple services, multiple languages | **Gateway** — one central point, no per-service SDK |
| Strict PII boundary — requests must not leave your network unredacted | **Gateway** — redacts before forwarding |
| You don't control the application code (third-party agent framework) | **Gateway** — just change the `OPENAI_BASE_URL` env var |
| Need a local proxy for development / debugging | **Gateway** — runs as `docker run` one-liner |

Both approaches produce the same structured telemetry on the Zroky dashboard.

---

## Quickstart

### Docker (recommended)

```bash
docker run -d \
  -p 8090:8090 \
  -e ZROKY_EMIT_MODE=http \
  -e ZROKY_API_URL=https://api.zroky.com \
  -e ZROKY_INGEST_URL=https://api.zroky.com/api/v1/ingest \
  -e ZROKY_GATEWAY_API_KEY=your-gateway-api-key \
  ghcr.io/zroky-ai/zroky-gateway:latest
```

### No-Docker local capture mode

Use direct HTTP emit mode when running the backend locally without Redis:

```powershell
$env:ZROKY_EMIT_MODE="http"
$env:ZROKY_INGEST_URL="http://localhost:8000/api/v1/ingest"
$env:ZROKY_GATEWAY_API_KEY="your-zroky-api-key"
$env:ZROKY_GATEWAY_AUTH_TOKEN="local-shared-token"
$env:ZROKY_WORKFLOW_NAME="support-resolution"
$env:ZROKY_PROMPT_VERSION="support-v42"
go run ./cmd/gateway
```

For a local backend configured with `ALLOW_PROJECT_HEADER_CONTEXT=true`, the
gateway also sends `x-project-id` from `X-Zroky-Project-Id`, so an API key is
not required for development-only smoke tests.

### Point your OpenAI client at the gateway

```python
# Python
import openai
openai.base_url = "http://localhost:8090/v1"
```

```ts
// TypeScript
import OpenAI from "openai";
const openai = new OpenAI({ baseURL: "http://localhost:8090/v1" });
```

```bash
# Any tool that respects OPENAI_BASE_URL
export OPENAI_BASE_URL=http://localhost:8090/v1
```

Add the Zroky project header to every request:

```python
import openai
client = openai.OpenAI(
    base_url="http://localhost:8090/v1",
    default_headers={"X-Zroky-Project-Id": "proj_xxxx"},
)
```

---

## Supported providers

| Provider | Gateway path | Upstream |
|---|---|---|
| OpenAI Chat Completions | `/v1/chat/completions` | `https://api.openai.com/v1/chat/completions` |
| OpenAI Responses | `/v1/responses` | `https://api.openai.com/v1/responses` |
| OpenAI Embeddings | `/v1/embeddings` | `https://api.openai.com/v1/embeddings` |
| Anthropic Messages | `/v1/messages` | `https://api.anthropic.com/v1/messages` |
| Google Gemini | `/v1beta/models/...` | `https://generativelanguage.googleapis.com/v1beta/models/...` |

The path suffix is forwarded verbatim to the upstream, so
`POST /v1/chat/completions` proxies to
`https://api.openai.com/v1/chat/completions`.

---

## Request headers

| Header | Required | Description |
|---|---|---|
| `X-Zroky-Project-Id` | Yes | Identifies the Zroky project this call belongs to |
| `X-Project-Id` | No | Alias for `X-Zroky-Project-Id` |
| `X-Zroky-Call-Id` | No | Caller-provided call id; generated when omitted |
| `X-Zroky-Agent-Name` | No | Label the call site (e.g. `summariser-agent`) |
| `X-Zroky-Session-Id` | No | Group calls into a user session |
| `X-Zroky-Workflow-Id` | No | Group calls into a workflow run |
| `X-Zroky-Workflow-Name` | No | Human-readable workflow or graph name |
| `X-Zroky-Prompt-Version` | No | Prompt deploy version; critical for regression diagnosis |
| `X-Zroky-Step-Index` | No | Zero-based workflow step |
| `X-Zroky-Trace-Id` | No | Distributed trace id |
| `X-Zroky-Parent-Call-Id` | No | Parent call/span id |

These headers are **stripped before forwarding** to the upstream provider —
they never reach OpenAI/Anthropic/Google.

---

## PII redaction

The gateway runs every request and response body through an automatic PII
redactor before including them in the emitted telemetry event. By default the
following patterns are redacted (replaced with `[REDACTED]`):

- Email addresses
- Phone numbers (E.164 and common formats)
- Credit card numbers (Luhn-valid patterns)
- Social Security Numbers

The raw bytes sent to and received from the upstream are **never modified**.
Redaction applies only to the bounded copy sent to Zroky telemetry. Streaming
responses are flushed to the caller while the gateway captures a bounded copy
for telemetry and extracts text/usage from OpenAI and Anthropic SSE chunks when
the provider includes them.

---

## Configuration

All configuration is via environment variables.

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8090` | Port the gateway listens on |
| `ZROKY_EMIT_MODE` | `redis` | Emit sink: `redis`, `http`, or `dual` |
| `ZROKY_API_URL` | `https://api.zroky.com` | Zroky control plane URL |
| `ZROKY_INGEST_URL` | `${ZROKY_API_URL}/api/v1/ingest` | Direct HTTP ingest endpoint used by `http` and `dual` modes |
| `ZROKY_GATEWAY_API_KEY` | *(required)* | API key for authenticating with Zroky |
| `ZROKY_GATEWAY_AUTH_TOKEN` | *(empty)* | Optional shared token required from callers via `X-Zroky-Gateway-Token`, `X-Zroky-Gateway-Key`, or bearer auth |
| `ZROKY_ALLOWED_PROJECT_IDS` | *(empty)* | Optional comma-separated project allowlist; requests for other project IDs are rejected |
| `ZROKY_WORKFLOW_NAME` | *(empty)* | Optional default `workflow_name` when callers do not send `X-Zroky-Workflow-Name` |
| `ZROKY_PROMPT_VERSION` | *(empty)* | Optional default `prompt_version` when callers do not send `X-Zroky-Prompt-Version` |
| `OPENAI_API_KEY` | *(empty)* | Optional upstream OpenAI key injected by the gateway; avoids caller-side provider keys |
| `ANTHROPIC_API_KEY` | *(empty)* | Optional upstream Anthropic key injected by the gateway |
| `GOOGLE_API_KEY` | *(empty)* | Optional upstream Google key injected by the gateway |
| `OPENAI_UPSTREAM_BASE_URL` | `https://api.openai.com` | Override OpenAI upstream for local smoke tests |
| `ANTHROPIC_UPSTREAM_BASE_URL` | `https://api.anthropic.com` | Override Anthropic upstream for local smoke tests |
| `GOOGLE_UPSTREAM_BASE_URL` | `https://generativelanguage.googleapis.com` | Override Google upstream for local smoke tests |
| `REDIS_URL` | `redis://localhost:6379` | Redis for async event buffering |
| `REDIS_STREAM` | `zroky:ingest:v2` | Redis Stream name |
| `MAX_BODY_BYTES` | `4194304` (4 MB) | Maximum request/response body captured |
| `LOG_LEVEL` | `info` | Log verbosity: `debug`, `info`, `warn`, `error` |
| `PRETTY_LOGS` | `false` | Human-readable logs (set `true` in development) |
| `READ_TIMEOUT` | `30s` | Inbound read deadline |
| `WRITE_TIMEOUT` | `60s` | Outbound write deadline |
| `IDLE_TIMEOUT` | `120s` | Keep-alive idle timeout |

Copy `.env.example` to `.env` to get started locally.

---

## Build from source

Requires Go 1.22+.

```bash
git clone https://github.com/zroky-ai/zroky-gateway
cd zroky-gateway
go build -o zroky-gateway ./cmd/gateway
./zroky-gateway
```

### Run tests

```bash
go test ./...
```

### Benchmark (p95 overhead)

```bash
GATEWAY_URL=http://localhost:8090 go run bench/bench_gateway_overhead_go.go
```

Asserts p95 overhead < 8 ms at 100 RPS against a mock upstream.

---

## Architecture

```
Your App
   │
   │  POST /v1/chat/completions
   │  X-Zroky-Project-Id: proj_xxxx
   ▼
zroky-gateway
   ├─ Strip Zroky headers
   ├─ Forward to api.openai.com (bytes-passthrough, zero copy)
   ├─ Stream response back to caller
   └─ (async goroutine) Redact → Emit IngestEventV2
          ├─ redis mode: Redis Stream
          ├─ http mode : POST /api/v1/ingest
          └─ dual mode : Redis Stream + HTTP ingest
                              │
                              ▼
                      Zroky Control Plane
                      (anomaly detection,
                       replay runs,
                       dashboard)
```

The emit step runs in a background goroutine and never blocks the response
path. A 2-second timeout on the emit ensures a slow/down control plane
cannot affect your application.

---

## License

[FSL-1.1-MIT](LICENSE) — free for any use except building a competing product.
Converts to plain MIT on the second anniversary of each release.
See [fsl.software](https://fsl.software/) for the full terms.
