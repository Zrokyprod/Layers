# Architecture

## Overview

ZROKY is a **layered** backend consisting of:

1. **Ingest layer** — REST API (`/api/v1/ingest`) accepts batched call events from the SDK.
2. **Queue / worker layer** — Celery tasks enqueue diagnosis jobs and run the analysis pipeline.
3. **Diagnosis engine** — rule-based + LLM-augmented classification of failure modes.
4. **Loop detector** — state-machine on top of Redis sorted-sets that flags repeated error / no-progress patterns.
5. **Dashboard / analytics layer** — read-only analytics endpoints backed by read-replica aware queries, with a Redis caching layer.
6. **Realtime layer** — WebSocket hub that pushes diagnosis results and loop alerts to live dashboards.

## Component diagram

```
 ┌──────────────────┐
 │  ZROKY Python SDK │
 │  (sync + async)  │
 └────────┬─────────┘
          │ HTTP/JSON batch
          ▼
 ┌──────────────────────────────┐
 │  FastAPI ingest API          │
 │  ── rate-limited, validated  │
 └────────┬─────────────────────┘
          │ enqueue
          ▼
 ┌──────────────────────────────┐
 │  Celery (Redis broker)       │
 │  ── diagnosis pipeline       │
 └────────┬─────────────────────┘
          │
    ┌─────┴──────┐
    ▼            ▼
 ┌────────┐  ┌──────────┐
 │Worker  │  │Loop      │
 │(rules  │  │detection │
 │+ LLM)  │  │(Redis)   │
 └───┬────┘  └────┬─────┘
     │            │
     └──────┬─────┘
            ▼
   ┌────────────────┐
   │ Postgres (RLS) │
   │ diagnosis_jobs  │
   │ calls           │
   │ fix_events      │
   └────────────────┘
            │
            ▼
   ┌──────────────────────────┐
   │ Dashboard / Analytics API │
   │  ── read-replica ready  │
   │  ── Redis cache layer   │
   │  ── WebSocket realtime  │
   └──────────────────────────┘
```

## High-volume tables (time-series)

- `calls` — one row per LLM call, partitioned by month.
- `diagnosis_jobs` — one row per diagnosis run, partitioned by month.
- `fix_events` — one row per emitted fix suggestion, partitioned by month.

A scheduled partition-maintenance job creates new monthly partitions two months ahead and drops partitions older than the retention window (default 12 months).

## Request flow

### Ingestion

1. SDK batches events in memory (flush interval configurable, default 5 s).
2. On flush the SDK `POST /api/v1/ingest` with retry + circuit breaker.
3. Backend writes events to `calls` via `DiagnosisJob` creation.
4. Celery worker picks up the diagnosis job and runs the analysis pipeline.
5. If loop conditions are met, the worker publishes a `loop_alert` topic via the realtime hub.

### Analytics

1. Dashboard requests `/api/v1/analytics/summary` with a JWT / API key.
2. Auth layer enforces project membership (tenant context).
3. Read-only endpoints use the read-replica engine if `DATABASE_READ_REPLICA_URL` is configured, otherwise fall back transparently to the primary engine.
4. Expensive results are cached in Redis with a namespace (e.g. `zroky:analytics:summary:{tenant_id}`).

### Realtime

1. Browser opens `wss://host/api/v1/realtime?topics=diagnosis,loop_alert`.
2. WebSocket handler authenticates via `x-api-key` header or Bearer JWT.
3. Messages are broadcast in-process to all connections sharing the same `tenant_id`.
4. Worker tasks call `publish_diagnosis()` / `publish_loop_alert()` which schedules a coroutine on the event loop.

## Scaling notes

- **Database:** Partitioned tables keep individual partition sizes bounded. The read-replica dependency offloads analytics queries from the primary.
- **Redis:** Used for loop-detection state, cache layer, and Celery broker. If Redis is down the cache falls back to in-process dict (tests / degraded mode).
- **Workers:** Celery workers scale horizontally. The diagnosis pipeline is stateless except for the Redis loop-detection cache.
- **Realtime:** The current hub is in-process. For multi-pod deployment wrap `hub.publish()` with a Redis Pub/Sub channel and have each pod subscribe on startup.
