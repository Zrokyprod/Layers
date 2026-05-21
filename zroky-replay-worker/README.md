# zroky-replay-worker

A stateless, self-hostable **replay execution worker** for the
[Zroky](https://zroky.com) AI reliability platform. The worker polls the
Zroky control plane for pending replay jobs, executes each job against the
real LLM in an isolated subprocess, and reports a structured result including
a `diff_metric` measuring how much the output changed.

[![License: FSL-1.1-MIT](https://img.shields.io/badge/license-FSL--1.1--MIT-blue)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)](https://python.org)

---

## What is a replay job?

When Zroky detects an anomaly (e.g. an accuracy regression or a cost spike),
it generates a candidate fix (a diff against your prompt or call parameters).
A **replay job** takes that candidate fix, applies it to the original call
context, re-runs the call against the real LLM, and computes whether the
output improved.

The worker handles the execution layer — it never needs direct access to your
application code or database.

---

## Quickstart

### Docker (recommended)

```bash
docker run -d \
  --name zroky-replay-worker \
  -e CONTROL_PLANE_URL=https://api.zroky.com \
  -e WORKER_TOKEN=your-worker-token \
  -e ARTIFACT_SIGNING_KEY=your-signing-key \
  ghcr.io/zroky-ai/zroky-replay-worker:latest
```

Get `WORKER_TOKEN` and `ARTIFACT_SIGNING_KEY` from the Zroky dashboard under
**Settings → Replay Workers**.

The worker starts polling immediately. No ports need to be opened — it is
purely outbound.

### Docker Compose

```yaml
services:
  replay-worker:
    image: ghcr.io/zroky-ai/zroky-replay-worker:latest
    environment:
      CONTROL_PLANE_URL: https://api.zroky.com
      WORKER_TOKEN: ${ZROKY_WORKER_TOKEN}
      ARTIFACT_SIGNING_KEY: ${ZROKY_ARTIFACT_SIGNING_KEY}
      MAX_CONCURRENT_JOBS: 4
    restart: unless-stopped
```

---

## Configuration

All configuration is via environment variables (or a `.env` file).

| Variable | Default | Description |
|---|---|---|
| `CONTROL_PLANE_URL` | `https://api.zroky.com` | Zroky control plane to poll |
| `WORKER_TOKEN` | *(required)* | Authentication token for this worker instance |
| `ARTIFACT_SIGNING_KEY` | *(required)* | HMAC key used to verify artifact integrity before execution |
| `POLL_INTERVAL_SECONDS` | `10` | How often to check for new jobs |
| `MAX_CONCURRENT_JOBS` | `4` | Maximum jobs to run in parallel |
| `JOB_TIMEOUT_SECONDS` | `300` | Per-job execution timeout (hard kill at this limit) |
| `LOG_LEVEL` | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

Copy `.env.example` to `.env` for local development.

---

## Security model

The replay worker is designed with a **zero-trust execution model**:

- **Always pulls, never accepts inbound connections.** No ports are opened.
  The worker only makes outbound HTTPS calls to `CONTROL_PLANE_URL`.
- **Artifact signature verified before any execution.** Every job carries a
  signed artifact URL. The worker verifies the HMAC signature against
  `ARTIFACT_SIGNING_KEY` before downloading or executing anything. A job with
  an invalid signature is rejected and reported as an error — no code runs.
- **Execution in an isolated subprocess.** The LLM call is run inside a
  `subprocess` with `JOB_TIMEOUT_SECONDS` enforced as a hard kill. The main
  worker process cannot be affected by a misbehaving job.
- **No credentials stored in artifacts.** Artifacts contain call context
  (prompt, model, parameters) but not API keys. Your provider keys are
  configured separately in the Zroky control plane and injected at the point
  of execution — they never travel in artifact payloads.

---

## How a job is executed

```
Control Plane
  │  Poll: GET /v1/replay/jobs/pending
  │  ← [{replay_id, artifact_url, artifact_signature, candidate_fix_diff, ...}]
  ▼
Worker
  1. Verify HMAC signature on artifact_url
  2. Download artifact (gzip JSON bundle)
  3. Apply candidate_fix_diff to the prompt field
  4. Execute patched context in an isolated subprocess (timeout enforced)
  5. Compute diff_metric:
       0.0 = output identical to expected
       1.0 = output completely different
     status = "pass" if returncode == 0 AND diff_metric <= 0.3
            = "fail" otherwise
  6. POST result to /v1/replay/jobs/{replay_id}/result
```

Results are visible in the Zroky dashboard under **Replay Runs**.

---

## Build from source

Requires Python 3.11+.

```bash
git clone https://github.com/zroky-ai/zroky-replay-worker
cd zroky-replay-worker
pip install -e .
cp .env.example .env
# edit .env with your tokens
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### Run tests

```bash
pip install pytest httpx pytest-asyncio
pytest
```

---

## Health endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Returns `{"status": "ok"}` — suitable for Docker healthcheck |
| `GET /ready` | Returns `{"status": "ready"}` only if `WORKER_TOKEN` is configured |

---

## Running multiple workers

Each worker instance is stateless — you can run as many as you need in
parallel. The control plane distributes jobs across all active workers.
Scale by increasing `MAX_CONCURRENT_JOBS` on a single instance or by
adding more instances.

---

## License

[FSL-1.1-MIT](LICENSE) — free for any use except building a competing product.
Converts to plain MIT on the second anniversary of each release.
See [fsl.software](https://fsl.software/) for the full terms.
