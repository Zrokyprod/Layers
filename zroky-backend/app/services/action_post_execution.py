from __future__ import annotations

from app.db.models import McpInterceptionEvent
from app.services._action_post_execution_connectors import *  # noqa: F403
from app.services._action_post_execution_core import *  # noqa: F403
from app.services.connector_credentials import RemoteCredentialResolutionRequired
from app.services.private_runner_verification import enqueue_private_runner_verification
from app.services.verification_execution_controls import (
    ControlledConnector,
    VerificationExecutionControls,
)


def _direct_record_connector_for_context(context: Mapping[str, Any]) -> ApiRecordConnector | None:
    """Use explicit MCP/SOR evidence already captured in the execution plan.

    This preserves the hybrid contract: the inline path captures upstream
    evidence and queues work; the worker performs the actual proof evaluation.
    """
    verification = _as_dict(context.get("verification"))
    if not verification:
        return None
    actual = _direct_record(verification)
    record_found = verification.get("record_found")
    if record_found is None and actual is not None:
        record_found = True
    if actual is None and not isinstance(record_found, bool):
        return None
    connector_type = _connector_alias(verification.get("connector_type")) or "mcp_tool_result"
    return ApiRecordConnector(
        record=actual,
        record_found=record_found if isinstance(record_found, bool) else None,
        connector_type=connector_type,
    )


def _direct_record(value: Mapping[str, Any]) -> dict[str, Any] | None:
    for key in ("actual", "record", "source_record"):
        item = value.get(key)
        if isinstance(item, Mapping):
            return dict(item)
    return None


def _run_verify_job(db: Session, job: ActionPostExecutionJob) -> dict[str, Any]:
    intent = db.execute(
        select(ActionIntent).where(ActionIntent.project_id == job.project_id, ActionIntent.id == job.action_intent_id)
    ).scalar_one()
    attempt = db.execute(
        select(ActionExecutionAttempt).where(
            ActionExecutionAttempt.project_id == job.project_id,
            ActionExecutionAttempt.id == job.execution_attempt_id,
        )
    ).scalar_one()
    context = _verification_context(intent, attempt)
    connector_type = _connector_alias(context.get("connector_type")) or GENERIC_REST_CONNECTOR_TYPE
    job_payload = _as_dict(_json_loads(job.payload_json, {}))

    if attempt.status != "succeeded":
        outcome = _reconcile_not_verified(
            db,
            intent=intent,
            attempt=attempt,
            job=job,
            context=context,
            connector_type="action_execution_terminal",
            reason=f"execution_{attempt.status}",
        )
    else:
        direct_connector = _direct_record_connector_for_context(context)
        if direct_connector is not None:
            claimed = _as_dict(context.get("claimed"))
            trace = _as_dict(context.get("trace"))
            verification = _as_dict(context.get("verification"))
            connector_type = direct_connector.connector_type
            metadata = {
                **_base_metadata(intent=intent, attempt=attempt, job=job, connector_type=connector_type),
                "source": "mcp_proxy",
                "proof_mode": "mcp_direct_hint",
                "mcp_event_id": _text(job_payload.get("mcp_event_id")),
            }
            outcome = reconcile_outcome(
                db,
                project_id=intent.project_id,
                claimed=claimed,
                connector=direct_connector,
                call_id=_text(trace.get("call_id")),
                trace_id=_text(trace.get("trace_id")),
                runtime_policy_decision_id=intent.runtime_policy_decision_id,
                action_type=intent.action_type,
                system_ref=_text(verification.get("system_ref")) or f"mcp:{intent.id}:{attempt.id}",
                amount_usd=_float(claimed.get("amount_usd")),
                currency=_text(claimed.get("currency")),
                match_fields=_as_list(context.get("match_fields")),
                idempotency_key=f"action-post-exec:{intent.id}:{attempt.id}:verify",
                metadata=metadata,
            )
        else:
            try:
                connector, connector_type, missing_reason = _saved_connector_for_context(
                    db=db,
                    intent=intent,
                    context=context,
                )
            except RemoteCredentialResolutionRequired:
                runner_job = enqueue_private_runner_verification(
                    db,
                    intent=intent,
                    attempt=attempt,
                    context=context,
                    connector_type=connector_type,
                )
                if runner_job is not None:
                    return {
                        "status": "pending_private_runner",
                        "verification_job_id": runner_job.id,
                        "runner_id": runner_job.runner_id,
                        "connector_type": runner_job.connector_type,
                    }
                connector = None
                missing_reason = "private_runner_unavailable"
            except Exception as exc:  # noqa: BLE001
                connector = None
                missing_reason = exc.__class__.__name__
            if connector is None:
                outcome = _reconcile_not_verified(
                    db,
                    intent=intent,
                    attempt=attempt,
                    job=job,
                    context=context,
                    connector_type=connector_type,
                    reason=missing_reason or "connector_unavailable",
                )
            else:
                trace = _as_dict(context.get("trace"))
                claimed = _as_dict(context.get("claimed"))
                metadata = _base_metadata(intent=intent, attempt=attempt, job=job, connector_type=connector_type)
                connector = ControlledConnector(
                    connector=connector,
                    controls=VerificationExecutionControls(
                        project_id=intent.project_id,
                        connector_type=connector_type,
                        token=job.id,
                    ),
                )
                try:
                    outcome = reconcile_outcome(
                        db,
                        project_id=intent.project_id,
                        claimed=claimed,
                        connector=connector,
                        call_id=_text(trace.get("call_id")),
                        trace_id=_text(trace.get("trace_id")),
                        runtime_policy_decision_id=intent.runtime_policy_decision_id,
                        action_type=intent.action_type,
                        system_ref=_text(context.get("system_ref"), _as_dict(context.get("verification")).get("system_ref"))
                        or f"{connector_type}:{intent.id}",
                        amount_usd=_float(claimed.get("amount_usd")),
                        currency=_text(claimed.get("currency")),
                        match_fields=_as_list(context.get("match_fields")),
                        proof_manifest=_as_dict(context.get("proof_manifest")) or None,
                        idempotency_key=f"action-post-exec:{intent.id}:{attempt.id}:verify",
                        metadata=metadata,
                    )
                except Exception as exc:  # noqa: BLE001
                    db.rollback()
                    intent = db.execute(
                        select(ActionIntent).where(
                            ActionIntent.project_id == job.project_id,
                            ActionIntent.id == job.action_intent_id,
                        )
                    ).scalar_one()
                    attempt = db.execute(
                        select(ActionExecutionAttempt).where(
                            ActionExecutionAttempt.project_id == job.project_id,
                            ActionExecutionAttempt.id == job.execution_attempt_id,
                        )
                    ).scalar_one()
                    context = _verification_context(intent, attempt)
                    outcome = _reconcile_not_verified(
                        db,
                        intent=intent,
                        attempt=attempt,
                        job=job,
                        context=context,
                        connector_type=connector_type,
                        reason=f"connector_exception:{exc.__class__.__name__}",
                    )

    intent = db.execute(
        select(ActionIntent).where(ActionIntent.project_id == job.project_id, ActionIntent.id == job.action_intent_id)
    ).scalar_one()
    intent.proof_status = intent_proof_status_for_check(outcome)
    intent.receipt_status = RECEIPT_PENDING
    db.add(intent)
    receipt_job = enqueue_action_post_execution_job(
        db,
        project_id=job.project_id,
        action_id=job.action_intent_id,
        attempt_id=job.execution_attempt_id,
        job_type=JOB_GENERATE_RECEIPT,
        payload={
            "trigger": "verification_completed",
            "outcome_reconciliation_id": outcome.id,
            "verdict": outcome.verdict,
            "mcp_event_id": _text(job_payload.get("mcp_event_id")),
        },
    )
    record_action_timeline_event(
        db,
        project_id=job.project_id,
        action_id=job.action_intent_id,
        event_type="verification_completed",
        payload={
            "job_id": job.id,
            "outcome_reconciliation_id": outcome.id,
            "verdict": outcome.verdict,
            "receipt_job_id": receipt_job.id,
        },
        actor=job.claimed_by,
    )
    return {
        "status": "verified",
        "outcome_reconciliation_id": outcome.id,
        "verdict": outcome.verdict,
        "receipt_job_id": receipt_job.id,
    }


def _resolve_verify_job_as_not_verified(
    db: Session,
    *,
    job: ActionPostExecutionJob,
    reason: str,
) -> dict[str, Any]:
    job_payload = _as_dict(_json_loads(job.payload_json, {}))
    intent = db.execute(
        select(ActionIntent).where(ActionIntent.project_id == job.project_id, ActionIntent.id == job.action_intent_id)
    ).scalar_one()
    attempt = db.execute(
        select(ActionExecutionAttempt).where(
            ActionExecutionAttempt.project_id == job.project_id,
            ActionExecutionAttempt.id == job.execution_attempt_id,
        )
    ).scalar_one()
    context = _verification_context(intent, attempt)
    connector_type = _connector_alias(context.get("connector_type")) or GENERIC_REST_CONNECTOR_TYPE
    outcome = _reconcile_not_verified(
        db,
        intent=intent,
        attempt=attempt,
        job=job,
        context=context,
        connector_type=connector_type,
        reason=reason,
    )
    intent = db.execute(
        select(ActionIntent).where(ActionIntent.project_id == job.project_id, ActionIntent.id == job.action_intent_id)
    ).scalar_one()
    intent.proof_status = PROOF_NOT_VERIFIED
    intent.receipt_status = RECEIPT_PENDING
    db.add(intent)
    receipt_job = enqueue_action_post_execution_job(
        db,
        project_id=job.project_id,
        action_id=job.action_intent_id,
        attempt_id=job.execution_attempt_id,
        job_type=JOB_GENERATE_RECEIPT,
        payload={
            "trigger": "verification_dead_resolved_not_verified",
            "outcome_reconciliation_id": outcome.id,
            "verdict": outcome.verdict,
            "reason": reason,
            "mcp_event_id": _text(job_payload.get("mcp_event_id")),
        },
    )
    record_action_timeline_event(
        db,
        project_id=job.project_id,
        action_id=job.action_intent_id,
        event_type="verification_completed",
        payload={
            "job_id": job.id,
            "outcome_reconciliation_id": outcome.id,
            "verdict": outcome.verdict,
            "receipt_job_id": receipt_job.id,
            "reason": reason,
        },
        actor=job.claimed_by,
    )
    return {
        "status": "dead_resolved_not_verified",
        "outcome_reconciliation_id": outcome.id,
        "verdict": outcome.verdict,
        "receipt_job_id": receipt_job.id,
    }


def _run_receipt_job(db: Session, job: ActionPostExecutionJob) -> dict[str, Any]:
    job_payload = _as_dict(_json_loads(job.payload_json, {}))
    generated = generate_action_receipt(
        db,
        project_id=job.project_id,
        action_id=job.action_intent_id,
        actor=job.claimed_by,
    )
    intent = db.execute(
        select(ActionIntent).where(ActionIntent.project_id == job.project_id, ActionIntent.id == job.action_intent_id)
    ).scalar_one()
    intent.receipt_status = RECEIPT_GENERATED
    db.add(intent)
    _link_mcp_interception_event(
        db,
        project_id=job.project_id,
        mcp_event_id=_text(job_payload.get("mcp_event_id")),
        receipt_id=generated.row.id,
        receipt_digest=generated.row.receipt_digest,
        proof_status=intent.proof_status,
    )
    return {
        "status": "receipt_generated",
        "receipt_id": generated.row.id,
        "receipt_digest": generated.row.receipt_digest,
        "created": generated.created,
    }


def _link_mcp_interception_event(
    db: Session,
    *,
    project_id: str,
    mcp_event_id: str | None,
    receipt_id: str,
    receipt_digest: str,
    proof_status: str,
) -> None:
    if not mcp_event_id:
        return
    row = db.execute(
        select(McpInterceptionEvent).where(
            McpInterceptionEvent.project_id == project_id,
            McpInterceptionEvent.id == mcp_event_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return
    row.action_receipt_id = receipt_id
    row.receipt_digest = receipt_digest
    row.proof_status = proof_status
    db.add(row)


def _mark_job_succeeded(db: Session, job: ActionPostExecutionJob, result: Mapping[str, Any]) -> ActionPostExecutionJob:
    current = _now()
    job.status = JOB_SUCCEEDED
    job.result_json = _json_dumps(result)
    job.error_message = None
    job.completed_at = current
    job.lease_expires_at = None
    job.updated_at = current
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _mark_job_failed(db: Session, job: ActionPostExecutionJob, exc: Exception) -> ActionPostExecutionJob:
    job_id = job.id
    db.rollback()
    job = db.execute(select(ActionPostExecutionJob).where(ActionPostExecutionJob.id == job_id)).scalar_one()
    current = _now()
    terminal = int(job.attempt_count or 0) >= int(job.max_attempts or DEFAULT_JOB_MAX_ATTEMPTS)
    job.status = JOB_DEAD if terminal else JOB_RETRYING
    job.error_message = str(exc)[:2000]
    job.available_at = current + timedelta(seconds=min(300, 2 ** max(0, int(job.attempt_count or 1))))
    job.lease_expires_at = None
    job.updated_at = current
    if terminal and job.job_type == JOB_GENERATE_RECEIPT:
        intent = db.execute(
            select(ActionIntent).where(ActionIntent.project_id == job.project_id, ActionIntent.id == job.action_intent_id)
        ).scalar_one_or_none()
        if intent is not None:
            intent.receipt_status = RECEIPT_FAILED
            db.add(intent)
    if terminal and job.job_type == JOB_VERIFY_OUTCOME:
        try:
            result = _resolve_verify_job_as_not_verified(
                db,
                job=job,
                reason=f"verify_job_dead:{exc.__class__.__name__}",
            )
            job = db.execute(select(ActionPostExecutionJob).where(ActionPostExecutionJob.id == job_id)).scalar_one()
            job.result_json = _json_dumps(result)
        except Exception as fallback_exc:  # noqa: BLE001
            job = db.execute(select(ActionPostExecutionJob).where(ActionPostExecutionJob.id == job_id)).scalar_one()
            job.error_message = f"{str(exc)[:1000]}; fail_closed_resolution_error={fallback_exc.__class__.__name__}:{str(fallback_exc)[:500]}"
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def process_action_post_execution_job(
    db: Session,
    *,
    job_id: str,
) -> ProcessedPostExecutionJob:
    job = db.execute(select(ActionPostExecutionJob).where(ActionPostExecutionJob.id == job_id)).scalar_one()
    try:
        if job.job_type == JOB_VERIFY_OUTCOME:
            result = _run_verify_job(db, job)
        elif job.job_type == JOB_GENERATE_RECEIPT:
            result = _run_receipt_job(db, job)
        else:
            raise ActionPostExecutionError(f"Unsupported post-execution job type: {job.job_type}.")
    except Exception as exc:  # noqa: BLE001
        failed = _mark_job_failed(db, job, exc)
        return ProcessedPostExecutionJob(failed, {"status": failed.status, "error": str(exc)})
    succeeded = _mark_job_succeeded(db, job, result)
    return ProcessedPostExecutionJob(succeeded, result)


def process_next_action_post_execution_job(
    db: Session,
    *,
    worker_id: str = "action-post-execution-worker",
    lease_seconds: int = DEFAULT_JOB_LEASE_SECONDS,
) -> ProcessedPostExecutionJob | None:
    job = _claim_next_job(db, worker_id=worker_id, lease_seconds=lease_seconds)
    if job is None:
        return None
    started = start_claimed_action_post_execution_job(
        db,
        job_id=job.id,
        worker_id=worker_id,
    )
    if started is None:
        return None
    return process_action_post_execution_job(db, job_id=job.id)


def process_action_post_execution_jobs(
    db: Session,
    *,
    worker_id: str = "action-post-execution-worker",
    limit: int = 25,
) -> dict[str, Any]:
    processed: list[dict[str, Any]] = []
    for _ in range(max(1, int(limit))):
        item = process_next_action_post_execution_job(db, worker_id=worker_id)
        if item is None:
            break
        processed.append(
            {
                "job_id": item.job.id,
                "job_type": item.job.job_type,
                "status": item.job.status,
                "result": item.result,
            }
        )
    return {
        "processed": len(processed),
        "jobs": processed,
    }


def sweep_stale_execution_attempts(
    db: Session,
    *,
    stale_after_seconds: int = 600,
    limit: int = 50,
    actor: str = "action-stale-attempt-sweeper",
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or _now()
    cutoff = current - timedelta(seconds=max(1, int(stale_after_seconds)))
    rows = list(
        db.execute(
            select(ActionExecutionAttempt)
            .where(
                ActionExecutionAttempt.status.in_(("planned", "dispatched", "running")),
                ActionExecutionAttempt.updated_at <= cutoff,
            )
            .order_by(ActionExecutionAttempt.updated_at.asc(), ActionExecutionAttempt.created_at.asc())
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    resolved: list[dict[str, Any]] = []
    if not rows:
        return {"resolved": 0, "attempts": resolved}

    from app.services.action_runner import finish_execution_attempt

    for attempt in rows:
        previous_status = attempt.status
        previous_updated_at = attempt.updated_at
        finish_execution_attempt(
            db,
            project_id=attempt.project_id,
            action_id=attempt.action_intent_id,
            attempt_id=attempt.id,
            final_status="ambiguous",
            result_summary={
                "stale_execution": {
                    "resolved_by": actor,
                    "previous_status": previous_status,
                    "stale_after_seconds": max(1, int(stale_after_seconds)),
                    "stale_cutoff": cutoff.isoformat(),
                    "last_updated_at": previous_updated_at.isoformat() if previous_updated_at is not None else None,
                }
            },
            error_message="Execution attempt timed out before runner reported a terminal status.",
            actor=actor,
        )
        resolved.append(
            {
                "execution_attempt_id": attempt.id,
                "action_intent_id": attempt.action_intent_id,
                "previous_status": previous_status,
            }
        )

    db.commit()
    return {
        "resolved": len(resolved),
        "attempts": resolved,
    }
