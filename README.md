# Zroky — AI Fix Engine

> **Capture → Diagnose → Verified-Fix PR. This is the product. Not a dashboard.**

Zroky is the reliability platform for agent builders. It watches every AI call your LangGraph, CrewAI, AutoGen, or custom agent makes, groups failures into issues, generates fix PRs verified by a replay sandbox, and closes the loop automatically.

**ICP:** Teams running 1 K–1 M agent calls/day who ship fixes weekly.

[![CI](https://github.com/zroky/zroky-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/zroky/zroky-ai/actions/workflows/ci.yml)
[![API Contract](https://github.com/zroky/zroky-ai/actions/workflows/api-contract-check.yml/badge.svg)](https://github.com/zroky/zroky-ai/actions/workflows/api-contract-check.yml)
[![Schema Drift](https://github.com/zroky/zroky-ai/actions/workflows/schema-drift-check.yml/badge.svg)](https://github.com/zroky/zroky-ai/actions/workflows/schema-drift-check.yml)

---

## Quickstart — self-host in 2 minutes

```bash
git clone https://github.com/zroky/zroky-ai
cd zroky-ai
make self-host        # copies env example, builds images, starts stack
make self-host-seed   # loads 1 K demo events for instant exploration
```

Open **http://localhost:3000** — dashboard with live demo data.

> **First run:** edit `zroky-backend/.env.self-host` and add your `OPENAI_API_KEY`
> (or Anthropic/Google key) before starting. Everything else defaults to local services.

---

## What the closed loop looks like

1. Agent makes an LLM call → Zroky SDK captures it (< 5 ms p95 overhead)
2. Call appears in `/issues` grouped by `(failure_code, prompt_fingerprint, agent_name)`
3. Diagnosis engine assigns a failure code (`LOOP_DETECTED`, `CONTEXT_OVERFLOW`, …)
4. Fix generator produces a candidate patch
5. Replay worker executes the patch in an isolated sandbox → `PASS` or `FAIL`
6. On `PASS`: GitHub PR opened, linked to the issue
7. PR merged → failure absent on next run → issue auto-resolved

---

## Repository layout

| Path | What it contains |
|---|---|
| `zroky-backend/` | FastAPI backend, Celery workers, Alembic migrations |
| `zroky-dashboard/` | Next.js 16 dashboard (App Router + TypeScript) |
| `zroky-sdk/` | Python SDK (`pip install zroky`) |
| `api-contracts/` | Frozen OpenAPI spec + IngestEvent v2 JSON Schema |
| `scripts/` | CI lint, code generators, seed data |
| `prometheus/` | Prometheus config + SLO burn-rate alert rules |
| `grafana/` | Pre-built dashboards (cost, diagnosis engine, system overview) |
| `docs/` | Architecture and agent-coverage docs |

---

## SDK — 3-line integration

```python
import zroky

zroky.init(api_key="zk-your-key", project_id="your-project")

@zroky.trace
async def call_agent(prompt: str):
    return await openai.chat.completions.create(...)
```

SDK overhead p95 < 5 ms (CI-enforced, Rule 4).

---

## Engineering guardrails

Ten rules, every one CI-enforced. See [ZROKY-Q1-90DAY-PLAN.md](ZROKY-Q1-90DAY-PLAN.md) §2.

| Rule | Enforcement |
|---|---|
| 1 — One schema source of truth (`IngestEvent`) | `schema-drift-check` CI job |
| 2 — Plugin architecture for detectors & fixes | Contract-test gate per plugin |
| 3 — No new file > 30 KB | `file-size-lint` CI job |
| 4 — Every customer-facing number has a CI benchmark | `benchmarks` CI job |
| 5 — Chaos tests weekly | `chaos-weekly` scheduled workflow |
| 6 — Labeled eval sets per detector | Precision/recall gate per PR |
| 7 — Zroky observes Zroky | SLO burn-rate alerts, live dashboard at every Friday demo |
| 8 — Self-hostable on Day 1 | `make self-host` < 2 min on a clean machine |
| 9 — API v1 frozen; breakage goes to v2 | `api-v1-frozen-check` CI job |
| 10 — Docs as code | `check_docs_drift` CI job |

---

## Development

### Local capture verification without Docker

Use this when changing the gateway, backend ingest path, JS SDK capture contract, or dashboard capture health UI.

```powershell
.\make.ps1 capture-e2e-local
```

On macOS/Linux, or any shell with Python available:

```bash
python scripts/run_capture_e2e_local.py
```

This runs the gateway Go tests, backend capture ingest tests, JS SDK tests/build/size gate, and targeted dashboard lint.
It also runs a live no-Docker smoke test that starts the backend, gateway, and a mock OpenAI upstream, then verifies `/capture/health` reports a gateway event.
The same command is enforced in `.github/workflows/capture-e2e-local.yml`.

```bash
# Backend
cd zroky-backend
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -x -q

# Dashboard
cd zroky-dashboard
npm install && npm run dev

# Regenerate IngestEvent v2 artifacts (after schema changes)
python scripts/gen_from_schema.py
```

Full spec: [ZROKY-PRODUCT-DOC-V1.1.md](ZROKY-PRODUCT-DOC-V1.1.md)
Q1 90-day plan: [ZROKY-Q1-90DAY-PLAN.md](ZROKY-Q1-90DAY-PLAN.md)
