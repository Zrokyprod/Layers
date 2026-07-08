from app.worker._internal.tasks_common import *
from app.worker._internal.tasks_utils import *

@celery_app.task(name="app.worker.tasks.sync_clickhouse", queue="diagnosis_fast", ignore_result=True)
def sync_clickhouse() -> dict:
    """Beat task: pull new Call rows from Postgres â†’ insert into ClickHouse."""
    from app.services.clickhouse_sync import sync_calls_to_clickhouse
    session = SessionLocal()
    try:
        return sync_calls_to_clickhouse(session)
    finally:
        session.close()


@celery_app.task(name="app.worker.tasks.consume_gateway_ingest_stream", queue="diagnosis_fast")
def consume_gateway_ingest_stream() -> dict:
    """Beat task: drain gateway Redis stream into the canonical ingest pipeline."""
    settings = get_settings()
    if not settings.GATEWAY_INGEST_STREAM_ENABLED:
        return {"enabled": False}

    from app.services.gateway_stream_consumer import consume_gateway_stream_once

    result = consume_gateway_stream_once()
    return {"enabled": True, **result.__dict__}


@celery_app.task(name="app.worker.tasks.poll_source_mutations", queue="diagnosis_fast")
def poll_source_mutations() -> dict:
    """Beat task: poll connected systems of record for unreceipted mutations."""
    settings = get_settings()
    if not settings.SOURCE_MUTATION_POLLER_ENABLED:
        return {"enabled": False}

    from app.services.source_mutation_polling import poll_source_mutations_once

    session = SessionLocal()
    try:
        result = poll_source_mutations_once(
            session,
            project_limit=settings.SOURCE_MUTATION_POLLER_PROJECT_LIMIT,
            per_connector_limit=settings.SOURCE_MUTATION_POLLER_PER_CONNECTOR_LIMIT,
            timeout_seconds=settings.SOURCE_MUTATION_POLLER_TIMEOUT_SECONDS,
        )
        return {"enabled": True, **result.__dict__}
    finally:
        session.close()


@celery_app.task(
    name="app.worker.tasks.run_shadow_judge_task",
    queue="diagnosis_pattern",
    max_retries=0,
    ignore_result=True,
)
def run_shadow_judge_task(
    *,
    tenant_id: str,
    call_id: str,
    failure_code: str,
    call_prompt: str | None = None,
    call_response: str | None = None,
    diagnosis_summary: str | None = None,
) -> dict:
    """Background shadow judge â€” fire-and-forget, never retried, never blocks production."""
    from app.services.judge_shadow import run_shadow_judge
    verdict = run_shadow_judge(
        tenant_id=tenant_id,
        call_id=call_id,
        failure_code=failure_code,
        call_prompt=call_prompt,
        call_response=call_response,
        diagnosis_summary=diagnosis_summary,
    )
    logger.info(
        "shadow_judge_completed tenant=%s call=%s code=%s verdict=%s conf=%.2f",
        tenant_id,
        call_id,
        failure_code,
        verdict.get("verdict"),
        verdict.get("confidence", 0.0),
    )
    return verdict


__all__ = [name for name in globals() if not name.startswith("__")]
