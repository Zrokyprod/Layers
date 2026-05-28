# zroky-sdk

Open-source flight recorder SDK for production AI agents � Python capture for LLM calls, tools, retrieval, memory, latency, cost, and failures.

[![PyPI](https://img.shields.io/pypi/v/zroky)](https://pypi.org/project/zroky/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)](https://python.org)
[![License: FSL-1.1-MIT](https://img.shields.io/badge/license-FSL--1.1--MIT-blue)](LICENSE)

Zroky Watch is the open-source data plane for Zroky. It lets developers capture the evidence behind agent behavior without installing a black box. Zroky Pilot/Cloud adds the private control plane: issue grouping, root-cause diagnosis, replay orchestration, judge verification, Goldens, CI gates, and team workflow.

## Why developers use it

- **Capture the full agent run**: prompts, responses, tool calls, retrieval, memory, latency, cost, status, and outcomes.
- **Keep production safe**: capture is non-blocking and failures never break your provider call path.
- **Debug with evidence**: stable prompt fingerprints, trace IDs, workflow labels, and agent metadata make failures reproducible.
- **Prepare for replay**: captured incidents can become replay cases and CI Goldens in Zroky Pilot.
- **Trust the data plane**: the SDK is open source, small, inspectable, and FSL-1.1-MIT licensed.

## Install

```bash
pip install zroky
```

Optional LangChain integration:

```bash
pip install "zroky[langchain]"
```

Local development install:

```bash
pip install -e .
```

## 5-minute quickstart

```python
import os

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
)

print(response)
```

By default the SDK sends capture events to:

```text
https://api.zroky.com/v1/ingest
```

Override the ingest endpoint only when your Zroky team gives you a custom endpoint:

```bash
export ZROKY_INGEST_URL=http://localhost:8000/v1/ingest
```

## Capture retrieval and memory

Agent failures often come from RAG and memory state, not just the model call.

```python
import zroky

call_id = zroky.capture_retrieval(
    query="refund policy",
    index_name="support-kb",
    documents=[{"id": "policy_v11", "score": 0.91, "title": "Refunds"}],
)

zroky.capture_memory(
    operation="write",
    namespace="customer-memory",
    keys=["user_123:preferences"],
    parent_call_id=call_id,
)
```

## What gets captured

Each event follows the Zroky ingest schema and can include:

| Field | Example |
|---|---|
| `call_id` | `8d4f...` |
| `trace_id` | `trace_abc` |
| `agent_name` | `refund-agent` |
| `workflow_name` | `refund_review` |
| `prompt_version` | `refund-v42` |
| `provider` | `openai` |
| `model` | `gpt-4o-mini` |
| `call_type` | `chat`, `retrieval`, `memory`, `trace` |
| `latency_ms` | `342` |
| `prompt_tokens` | `128` |
| `completion_tokens` | `64` |
| `total_tokens` | `192` |
| `status` | `success`, `failed`, `blocked` |
| `prompt_fingerprint` | stable SHA-256 prompt shape |

## What is not open source

This repo is part of the free Zroky Watch OSS data plane. The Zroky backend, dashboard, judge engine, diagnosis logic, billing, and autonomous workflow are proprietary and delivered through Zroky Cloud and enterprise agreements.

## Preflight validation

The SDK supports advisory pre-execution validation before provider calls.

- It never mutates your payload.
- It does not block provider execution unless blocking warning types are configured.
- It prints only when warnings exist.
- It includes warning-spam suppression.

Enable with environment variables:

```bash
export ZROKY_VALIDATE_PREFLIGHT=true
export ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE=1.0
```

Or configure in code:

```python
import zroky

zroky.init(
    validate_preflight=True,
    validate_preflight_sample_rate=1.0,
)
```

Warning types:

- `TOKEN_OVERFLOW`
- `RATE_LIMIT_RISK`
- `AUTH_RISK`

## Production prevention

For wrapped calls through `zroky.call()` / `zroky.acall()`, the SDK can apply retry, fallback, rate-limit, circuit-breaker, cache, budget, timeout, and preflight policies consistently.

```python
zroky.init(
    retry_max_retries=2,
    fallback_models=["gpt-4o-mini", "claude-3-haiku"],
    fallback_adaptive=True,
    rate_limits={
        "openai/gpt-4o": {"rpm": 500, "tpm": 30000},
    },
    preflight_blocking_warning_types=["AUTH_RISK"],
)
```

## Deployment model

There are two launch shapes:

| Mode | What you use | What you get |
|---|---|---|
| Watch OSS | SDK, Gateway, Replay Worker | Open instrumentation, transport, and replay execution against Zroky Cloud or an approved endpoint |
| Zroky Pilot | Zroky Cloud control plane | Issues, diagnosis, replay proof, Goldens, dashboard, and CI gates |

The backend and dashboard source code are not part of this OSS repo.

## Run tests

```bash
pip install -e ".[dev]"
python -m pytest -q tests
python -m py_compile zroky/__init__.py zroky/_call.py zroky/_async.py zroky/_telemetry.py zroky/preflight.py
```

## Release

Tag-driven publish to PyPI:

```bash
# 1. Bump version in pyproject.toml
# 2. Commit and push, then:
git tag v0.1.1
git push origin v0.1.1
```

Required repository secrets:

- `TEST_PYPI_API_TOKEN`
- `PYPI_API_TOKEN`

## License

[FSL-1.1-MIT](LICENSE) � free for any use except building a competing product. Converts to plain MIT on the second anniversary of each release.
