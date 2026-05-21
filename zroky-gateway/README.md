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
  -e ZROKY_API_URL=https://api.zroky.com \
  -e ZROKY_GATEWAY_API_KEY=your-gateway-api-key \
  ghcr.io/zroky-ai/zroky-gateway:latest
```

### Point your OpenAI client at the gateway

```python
# Python
import openai
openai.base_url = "http://localhost:8090/openai"
```

```ts
// TypeScript
import OpenAI from "openai";
const openai = new OpenAI({ baseURL: "http://localhost:8090/openai" });
```

```bash
# Any tool that respects OPENAI_BASE_URL
export OPENAI_BASE_URL=http://localhost:8090/openai
```

Add the Zroky project header to every request:

```python
import openai
client = openai.OpenAI(
    base_url="http://localhost:8090/openai",
    default_headers={"X-Zroky-Project-Id": "proj_xxxx"},
)
```

---

## Supported providers

| Provider | Gateway path | Upstream |
|---|---|---|
| OpenAI | `/openai/...` | `https://api.openai.com` |
| Anthropic | `/anthropic/...` | `https://api.anthropic.com` |
| Google Gemini | `/google/...` | `https://generativelanguage.googleapis.com` |

The path suffix is forwarded verbatim to the upstream, so
`POST /openai/v1/chat/completions` proxies to
`https://api.openai.com/v1/chat/completions`.

---

## Request headers

| Header | Required | Description |
|---|---|---|
| `X-Zroky-Project-Id` | Yes | Identifies the Zroky project this call belongs to |
| `X-Zroky-Agent-Name` | No | Label the call site (e.g. `summariser-agent`) |
| `X-Zroky-Session-Id` | No | Group calls into a user session |

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

The raw bytes sent to and received from the upstream are **never modified** —
redaction applies only to the copy sent to Zroky telemetry.

---

## Configuration

All configuration is via environment variables.

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8090` | Port the gateway listens on |
| `ZROKY_API_URL` | `https://api.zroky.com` | Zroky control plane URL |
| `ZROKY_GATEWAY_API_KEY` | *(required)* | API key for authenticating with Zroky |
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
   │  POST /openai/v1/chat/completions
   │  X-Zroky-Project-Id: proj_xxxx
   ▼
zroky-gateway
   ├─ Strip Zroky headers
   ├─ Forward to api.openai.com (bytes-passthrough, zero copy)
   ├─ Stream response back to caller
   └─ (async goroutine) Redact → Emit IngestEventV2 → Redis Stream
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
