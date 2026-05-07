# ZROKY Documentation

ZROKY is a production AI diagnosis and observability platform. It captures LLM
agent call events, detects loops and failures, diagnoses root causes, and pushes
real-time alerts to a web dashboard.

## Quick links

- [Architecture](architecture.md) — how the system is built
- [SDK](sdk.md) — sending events from your agents
- [Deployment](deployment.md) — running the platform in production
- [Security](security.md) — auth, encryption, and responsible disclosure

## Repository layout

```
zroky-backend/        FastAPI backend (Postgres, Redis, Celery)
zroky-sdk/            Python SDK (httpx-based, sync + async)
docs/                 This directory
```

## Core concepts

| Term | Meaning |
|------|---------|
| **Call event** | A single LLM agent call (prompt → response) with cost, latency, and metadata |
| **Diagnosis job** | Async pipeline that analyses a group of call events and produces fix suggestions |
| **Loop detection** | Identifies repeated failures / no-progress patterns across recent calls |
| **Loop alert** | A real-time WebSocket event pushed to the dashboard when a loop is detected |
| **Tenant** | A project/organisation boundary enforced by Row-Level Security (RLS) |

## Getting started

### Backend (local)

```bash
cd zroky-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your DATABASE_URL, REDIS_URL, etc.
alembic upgrade head
python -m uvicorn app.main:app --reload
```

### SDK (in your agent code)

```python
import zroky

zroky.init(api_key="zk_...", project="my-project")

# Events are captured automatically if you use the OpenAI/Anthropic wrappers.
# Or emit manually:
zroky.emit({"call_id": "abc", "provider": "openai", "model": "gpt-4o", ...})
```

For more details see the per-topic docs linked above.
