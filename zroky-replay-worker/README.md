# zroky-replay-worker

Zero-trust replay worker for proving AI agent fixes � an open-source execution data plane for Zroky replay jobs.

[![License: FSL-1.1-MIT](https://img.shields.io/badge/license-FSL--1.1--MIT-blue)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)](https://python.org)

The Replay Worker pulls pending replay jobs from the Zroky control plane, verifies signed artifacts, executes patched call context against a real LLM provider, computes output deltas, and reports the result back.

## Why developers use it

- **No inbound ports**: the worker pulls jobs; it never accepts pushed payloads.
- **Artifact verification**: HMAC verification happens before any artifact is downloaded or executed.
- **Isolated execution path**: replay execution has a timeout and returns structured pass/fail/error results.
- **Real proof path**: replay compares original production evidence against candidate behavior.
- **Open execution plane**: keep replay execution explicit, signed, and auditable.

## What is a replay job?

A replay job is a signed instruction from the Zroky control plane:

```text
original incident evidence
+ candidate fix diff
+ signed artifact URL
+ timeout and trace metadata
= replay execution result
```

The worker handles execution only. Zroky Cloud/Pilot handles issue grouping, replay orchestration, judge policy, dashboard, Goldens, and CI gates.

## Quickstart

```bash
docker run -d \
  --name zroky-replay-worker \
  -e CONTROL_PLANE_URL=https://api.zroky.com \
  -e WORKER_TOKEN=$ZROKY_WORKER_TOKEN \
  -e ARTIFACT_SIGNING_KEY=$ZROKY_ARTIFACT_SIGNING_KEY \
  -e OPENROUTER_API_KEY=$OPENROUTER_API_KEY \
  ghcr.io/zroky-ai/zroky-replay-worker:latest
```

The worker starts polling immediately. No ports need to be opened.

## Docker Compose

```yaml
services:
  replay-worker:
    image: ghcr.io/zroky-ai/zroky-replay-worker:latest
    environment:
      CONTROL_PLANE_URL: https://api.zroky.com
      WORKER_TOKEN: ${ZROKY_WORKER_TOKEN}
      ARTIFACT_SIGNING_KEY: ${ZROKY_ARTIFACT_SIGNING_KEY}
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
      MAX_CONCURRENT_JOBS: 4
    restart: unless-stopped
```

## Protocol

The worker protocol is pull-based:

```text
1. POST /v1/replay/poll
   body: { worker_token, capacity }
   response: { jobs: [...] }

2. For each job:
   - verify HMAC signature
   - download signed artifact
   - apply candidate diff
   - execute patched context
   - compute diff metric
   - optionally request judge verdict

3. POST /v1/replay/result
   body: { worker_token, result }
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `CONTROL_PLANE_URL` | `https://api.zroky.com` | Zroky control plane to poll |
| `WORKER_TOKEN` | required | Authentication token for this worker |
| `ARTIFACT_SIGNING_KEY` | required | HMAC key used to verify artifact URLs |
| `OPENROUTER_API_KEY` | empty | Provider key used for real LLM replay execution |
| `POLL_INTERVAL_SECONDS` | `10` | Poll cadence |
| `MAX_CONCURRENT_JOBS` | `4` | Maximum parallel replay jobs |
| `JOB_TIMEOUT_SECONDS` | `300` | Per-job hard timeout |
| `LOG_LEVEL` | `INFO` | Log verbosity |

## Security model

- **Pull only**: no inbound replay payloads and no open replay ports required.
- **Verify before execute**: invalid artifact signatures return an error result; no artifact code runs.
- **No provider keys in artifacts**: artifacts contain call context, not API keys.
- **Timeout enforced**: long-running jobs return controlled timeout errors.
- **Structured result**: every job reports `pass`, `fail`, or `error` with metadata.

## Deployment model

| Mode | What you use | What you get |
|---|---|---|
| Watch OSS | Replay Worker + SDK/Gateway | Open execution worker that talks to Zroky Cloud or an approved endpoint |
| Zroky Pilot | Zroky Cloud control plane | Full replay orchestration, dashboard, Goldens, and CI gates |

The backend and dashboard source code are not part of this OSS repo.

## Build from source

```bash
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Health endpoints:

| Endpoint | Description |
|---|---|
| `GET /health` | Basic liveness |
| `GET /ready` | Ready only when `WORKER_TOKEN` is configured |

## Run tests

```bash
pip install pytest httpx pytest-asyncio
python -m pytest -q
python -m py_compile app/main.py app/poller.py app/runner.py app/artifacts.py app/config.py app/models.py
```

## License

[FSL-1.1-MIT](LICENSE) � free for any use except building a competing product. Converts to plain MIT on the second anniversary of each release.
