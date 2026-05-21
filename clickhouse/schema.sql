-- ClickHouse schema for Zroky aggregations.
-- Applied once on container startup via CLICKHOUSE_INIT_SCRIPTS.
--
-- Source of truth is Postgres; ClickHouse holds derived roll-ups
-- synced by the zroky-backend worker (incremental every 60 s).

CREATE DATABASE IF NOT EXISTS zroky;

USE zroky;

-- ── Raw ingest events (staging table for worker inserts) ─────────────────────

CREATE TABLE IF NOT EXISTS ingest_events (
    event_id       String,
    project_id     String,
    provider       LowCardinality(String),
    model          LowCardinality(String),
    call_type      LowCardinality(String),
    timestamp_utc  DateTime64(3, 'UTC'),
    latency_ms     Float32,
    prompt_tokens  UInt32,
    output_tokens  UInt32,
    total_tokens   UInt32,
    cost_usd       Float32,
    status         LowCardinality(String),
    status_code    UInt16,
    failure_code   LowCardinality(String) DEFAULT '',
    agent_name     String DEFAULT ''
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp_utc)
ORDER BY (project_id, timestamp_utc, event_id)
TTL timestamp_utc + INTERVAL 90 DAY;

-- ── /cost — hourly roll-ups ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cost_hourly (
    project_id    String,
    hour          DateTime('UTC'),
    model         LowCardinality(String),
    call_type     LowCardinality(String),
    calls         UInt64,
    prompt_tokens UInt64,
    output_tokens UInt64,
    total_tokens  UInt64,
    cost_usd      Float64
) ENGINE = SummingMergeTree((calls, prompt_tokens, output_tokens, total_tokens, cost_usd))
ORDER BY (project_id, hour, model, call_type);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_cost_hourly
TO cost_hourly
AS SELECT
    project_id,
    toStartOfHour(timestamp_utc) AS hour,
    model,
    call_type,
    count()                      AS calls,
    sum(prompt_tokens)           AS prompt_tokens,
    sum(output_tokens)           AS output_tokens,
    sum(total_tokens)            AS total_tokens,
    sum(cost_usd)                AS cost_usd
FROM ingest_events
GROUP BY project_id, hour, model, call_type;

-- ── /cost — daily roll-ups ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cost_daily (
    project_id    String,
    day           Date,
    model         LowCardinality(String),
    call_type     LowCardinality(String),
    calls         UInt64,
    prompt_tokens UInt64,
    output_tokens UInt64,
    total_tokens  UInt64,
    cost_usd      Float64
) ENGINE = SummingMergeTree((calls, prompt_tokens, output_tokens, total_tokens, cost_usd))
ORDER BY (project_id, day, model, call_type);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_cost_daily
TO cost_daily
AS SELECT
    project_id,
    toDate(timestamp_utc) AS day,
    model,
    call_type,
    count()               AS calls,
    sum(prompt_tokens)    AS prompt_tokens,
    sum(output_tokens)    AS output_tokens,
    sum(total_tokens)     AS total_tokens,
    sum(cost_usd)         AS cost_usd
FROM ingest_events
GROUP BY project_id, day, model, call_type;

-- ── /issues — top-K by failure_code × fingerprint ───────────────────────────

CREATE TABLE IF NOT EXISTS issues_topk (
    project_id    String,
    failure_code  LowCardinality(String),
    day           Date,
    occurrences   UInt64,
    affected_agents AggregateFunction(uniq, String)
) ENGINE = AggregatingMergeTree()
ORDER BY (project_id, failure_code, day);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_issues_topk
TO issues_topk
AS SELECT
    project_id,
    failure_code,
    toDate(timestamp_utc)          AS day,
    count()                        AS occurrences,
    uniqState(agent_name)          AS affected_agents
FROM ingest_events
WHERE failure_code != ''
GROUP BY project_id, failure_code, day;
