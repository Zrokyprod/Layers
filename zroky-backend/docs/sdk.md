# SDK Guide

The ZROKY Python SDK (`zroky-sdk`) captures LLM agent call events and streams
them to the backend in batches. It supports both **sync** and **async**
applications, transparent PII masking, and an offline buffer for resilient
operation on flaky networks.

## Installation

```bash
pip install zroky
```

Optional extras:

```bash
pip install zroky[langchain]        # LangChain callbacks
pip install zroky[opentelemetry]    # OTel span instrumentation
```

## Quick start

```python
import zroky

zroky.init(
    api_key="zk_live_...",
    project="my-project-id",
)

# If you use the OpenAI / Anthropic wrappers, events are captured automatically.
# Manual emission is also supported:
zroky.emit({
    "call_id": "call_abc_123",
    "provider": "openai",
    "model": "gpt-4o",
    "status": "success",
    "latency_ms": 420,
    "prompt_tokens": 100,
    "completion_tokens": 25,
})
```

## Configuration

All values can be set via environment variables or passed explicitly to
`zroky.init()`.

| Env variable | Description | Default |
|--------------|-------------|---------|
| `ZROKY_API_KEY` | Authentication key for the cloud backend | *(required)* |
| `ZROKY_PROJECT` | Project / tenant identifier | *(required)* |
| `ZROKY_MODE` | `cloud` (send to backend) or `local` (SQLite only) | `cloud` |
| `ZROKY_MASK_PII` | Strip user-facing identifiers from payloads | `true` |
| `ZROKY_INGEST_URL` | Custom backend URL | `http://localhost:8000` |
| `ZROKY_BATCH_SIZE` | Events per HTTP request | `10` |
| `ZROKY_FLUSH_INTERVAL` | Seconds between automatic flushes | `5` |
| `ZROKY_MAX_QUEUE_SIZE` | In-memory queue hard cap before dropping | `10_000` |
| `ZROKY_VALIDATE_PREFLIGHT` | Run pre-flight validation on every event | `false` |
| `ZROKY_ENABLE_OFFLINE_BUFFER` | Persist failed events to disk for retry | `true` |

## Async mode

For async / FastAPI / asyncio apps, use the async API:

```python
import asyncio
import zroky

async def main():
    await zroky.init_async(
        api_key="zk_live_...",
        project="my-project-id",
    )

    # Events are emitted into an async queue and flushed in the background.
    zroky.emit({"call_id": "...", "provider": "openai", ...})

    # Graceful shutdown flushes any remaining buffered events.
    await zroky.shutdown()

asyncio.run(main())
```

The async path uses `httpx.AsyncClient` with the same retry, circuit-breaker,
and offline-buffer semantics as the sync path.

## Resilience features

- **Circuit breaker** — if the backend is down, the SDK stops making requests
  after 5 consecutive failures and silently drops new events so your app is
  never blocked.
- **Exponential backoff** — transient 5xx / timeout retries with jitter.
- **Offline buffer** — when the circuit is open or the network is unavailable,
  events are spooled to a local NDJSON file (`~/.zroky/offline_buffer.ndjson`).
  On the next successful flush the buffer is replayed automatically in
  chronological order.

## CLI debugging tool

Install the SDK package to get the `zroky` CLI:

```bash
zroky config              # show resolved SDK config (API key redacted)
zroky health              # ping the ingest endpoint
zroky buffer status       # inspect offline-buffer size
zroky buffer flush        # replay buffered events to the backend
zroky buffer clear        # delete buffered events (irreversible)
zroky tail --topics=diagnosis,loop_alert   # stream live events via websocket
zroky replay events.ndjson                 # replay a JSON / NDJSON file
```
