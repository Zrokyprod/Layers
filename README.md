# Zroky

> AI Agent Regression Firewall.

Hero promise: **Stop shipping the same agent failure twice.**

Zroky captures production AI-agent failures, groups repeats into owned issues, verifies candidate changes with replay, promotes trusted cases into Goldens, and blocks repeated regressions in CI.

This is not positioned as an automatic fix engine. Zroky can draft reviewer-ready remediation evidence, but the core product promise is regression prevention: the same production failure should not ship twice.

**ICP:** teams running production AI agents at 10k-1M calls/month that need release protection for support, refund, sales, ops, or workflow agents.

---

## Product Loop

```text
Capture -> Diagnose -> Issue -> Replay -> Golden -> CI Gate
```

1. Capture the real production call through the SDK or gateway.
2. Diagnose the failure with high-confidence detectors.
3. Group repeated failures into one owned issue.
4. Replay the failed case against a candidate prompt, model, policy, or tool change.
5. Promote verified replay evidence into a Golden.
6. Run Goldens in CI and block pull requests that reintroduce protected failures.

The default money path is:

```text
capture failure -> diagnose -> issue -> replay -> promote Golden -> CI gate
```

---

## Quickstart

```bash
pip install zroky
```

```python
import os
import zroky

zroky.init(
    api_key=os.environ["ZROKY_API_KEY"],
    project_id=os.environ["ZROKY_PROJECT_ID"],
)

@zroky.trace(agent="refund_agent", workflow="status_lookup")
async def call_agent(prompt: str):
    return await agent.run(prompt)
```

Captured events are sent to Zroky Cloud by default. Self-hosted deployments can point the SDK at a private ingest URL.

---

## Core Surfaces

| Surface | Purpose |
|---|---|
| `Failure Inbox` | Ranked production failure queue and next actions |
| `Issues` | Clustered failure patterns with owner, impact, and proof status |
| `Replay Lab` | Original-vs-candidate replay verification |
| `Goldens` | Promoted regression guards for critical workflows |
| `CI Gates` | Pull-request release decisions backed by replay evidence |
| `Cost` | Wasted spend, blast radius, and prevented-repeat value |
| `Settings` | API keys, provider keys, billing, team, and integrations |

Secondary diagnostic surfaces such as traces, calls, drift, recommendations, and admin tools exist to support the core loop, but they are not the primary product wedge.

---

## Repository Layout

| Path | What it contains |
|---|---|
| `zroky-backend/` | FastAPI backend, Celery workers, Alembic migrations |
| `zroky-dashboard/` | Next.js dashboard and authenticated product UI |
| `zroky-landing/` | Public marketing site |
| `zroky-sdk/` | Python SDK |
| `zroky-sdk-js/` | JavaScript SDK |
| `zroky-regression-ci-action/` | GitHub Action for Golden replay gates |
| `zroky-replay-worker/` | Customer-hostable replay worker |
| `zroky-gateway/` | Optional OpenAI-compatible capture gateway |
| `api-contracts/` | Frozen OpenAPI and ingest schemas |
| `docs/` | Product, architecture, and deployment docs |

---

## Verification Commands

```powershell
python scripts/run_capture_e2e_local.py

cd zroky-dashboard
npm test
npm run build

cd ..\zroky-landing
npm run build

cd ..\zroky-sdk
..\.venv\Scripts\python.exe -m pytest -q

cd ..\zroky-sdk-js
npm test
npm run build
npm run size

cd ..\zroky-regression-ci-action
npm test -- --runInBand
```

---

## Guardrails

- SDK overhead must remain low enough for production capture.
- PII masking and provider-key handling must fail closed.
- Goldens only become blocking when replay evidence is trusted.
- Auto-fix and PR generation remain gated, reviewable, and optional.
- Product copy must not claim automatic code repair unless the feature is explicitly enabled and verified.
