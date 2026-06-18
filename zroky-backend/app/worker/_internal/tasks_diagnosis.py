from app.worker._internal.tasks_common import *
from app.worker._internal.tasks_utils import *
from app.worker._internal.tasks_loop_detection import *

@celery_app.task(name="app.worker.tasks.run_fast_diagnosis", queue="diagnosis_fast")
def run_fast_diagnosis(payload: dict) -> list[dict]:
    return mask_value(evaluate_fast_rules(mask_payload(payload)))


@celery_app.task(name="app.worker.tasks.run_pattern_diagnosis", queue="diagnosis_pattern")
def run_pattern_diagnosis(payload: dict) -> dict:
    diagnoses, informational = evaluate_pattern_rules(mask_payload(payload))
    return {
        "diagnoses": mask_value(diagnoses),
        "informational": mask_value(informational),
    }


@celery_app.task(name="app.worker.tasks.process_diagnosis", bind=True, max_retries=3)
def process_diagnosis(self, tenant_id: str, diagnosis_id: str, payload: dict | None = None) -> dict:
    task_key = f"{tenant_id}:{diagnosis_id}"
    with idempotency_guard(task_key) as acquired:
        if not acquired:
            record_diagnosis_job("duplicate_ignored")
            return {
                "status": "duplicate_ignored",
                "tenant_id": tenant_id,
                "diagnosis_id": diagnosis_id,
            }

        session = SessionLocal()
        try:
            set_db_tenant_context(session, tenant_id)
            job = session.execute(
                select(DiagnosisJob).where(
                    DiagnosisJob.tenant_id == tenant_id,
                    DiagnosisJob.diagnosis_id == diagnosis_id,
                )
            ).scalar_one_or_none()
            call = None
            if job is not None and job.call_id:
                call = session.get(Call, job.call_id)
            if call is None:
                call = session.execute(
                    select(Call).where(
                        Call.project_id == tenant_id,
                        Call.id == diagnosis_id,
                    )
                ).scalar_one_or_none()

            if job is not None and _normalize_text(job.status) in TERMINAL_DIAGNOSIS_STATUSES:
                record_diagnosis_job("duplicate_ignored")
                existing_result = _safe_json_object(job.result_json)
                if existing_result:
                    existing_result.setdefault("status", "already_done")
                    return existing_result
                return {
                    "status": "already_done",
                    "tenant_id": tenant_id,
                    "diagnosis_id": diagnosis_id,
                }

            diagnosis_payload = _payload_for_call_or_legacy(
                call=call,
                job=job,
                payload=payload,
            )
            try:
                from app.services.failure_intelligence import enrich_payload_with_trace_context

                diagnosis_payload = enrich_payload_with_trace_context(
                    session,
                    tenant_id=tenant_id,
                    call=call,
                    payload=diagnosis_payload,
                )
            except Exception:
                logger.debug("failure_intelligence_payload_enrichment_failed", exc_info=True)

            payload_with_db_context = mask_payload(_enrich_payload_with_db_loop_context(
                session,
                tenant_id=tenant_id,
                payload=diagnosis_payload,
            ))

            if job is not None:
                job.status = "processing"
                job.agent_name = _as_text(payload_with_db_context.get("agent_name"))
                job.prompt_fingerprint = _as_text(payload_with_db_context.get("prompt_fingerprint"))
                session.commit()

            # Keep orchestration inside one task while exposing dedicated fast/pattern
            # tasks so production workers can route them independently by queue.
            fast_diagnoses = evaluate_fast_rules(payload_with_db_context)
            pattern_diagnoses, informational = evaluate_pattern_rules(payload_with_db_context)

            result = mask_value(build_diagnosis_result(
                payload=payload_with_db_context,
                fast_diagnoses=fast_diagnoses,
                pattern_diagnoses=pattern_diagnoses,
                informational=informational,
            ))
            result["status"] = "processed"
            result["tenant_id"] = tenant_id
            result["diagnosis_id"] = diagnosis_id

            diagnosis_categories = [
                str(item.get("category", "UNKNOWN"))
                for item in result.get("diagnoses", [])
                if isinstance(item, dict)
            ]

            if any(category == "LOOP_DETECTED" for category in diagnosis_categories):
                loop_mapping = (
                    payload_with_db_context.get("loop")
                    if isinstance(payload_with_db_context.get("loop"), Mapping)
                    else {}
                )
                loop_agent_name = _as_text(payload_with_db_context.get("agent_name")) or _as_text(
                    loop_mapping.get("agent_name")
                )
                loop_prompt_fingerprint = _as_text(payload_with_db_context.get("prompt_fingerprint")) or _as_text(
                    loop_mapping.get("prompt_fingerprint")
                )

                if loop_agent_name and loop_prompt_fingerprint:
                    mark_loop_detected_fired(
                        tenant_id=tenant_id,
                        agent_name=loop_agent_name,
                        prompt_fingerprint=loop_prompt_fingerprint,
                        fired_at=datetime.now(timezone.utc),
                        cooldown_seconds=LOOP_COOLDOWN_SECONDS,
                    )

            record_diagnosis_job("completed")
            record_diagnosis_rule_hits(diagnosis_categories)

            logger.info(
                "diagnosis_task_completed",
                extra={
                    "event": "diagnosis_task",
                    "tenant_id": tenant_id,
                    "diagnosis_id": diagnosis_id,
                    "categories": diagnosis_categories,
                    "diagnosis_count": len(diagnosis_categories),
                },
            )

            if job is not None:
                job.status = "done" if job.call_id else "completed"
                job.result_json = json.dumps(mask_value(result), separators=(",", ":"))
                job.error_message = None
                sync_alerts_from_jobs(session, tenant_id, [job])
                session.commit()

                # Deliver alert to the tenant's connected Slack channel.
                # Fires only when there are real diagnoses (not healthy traces).
                if diagnosis_categories:
                    from app.services.notification_dispatch import dispatch_alert_to_tenant_channels
                    dispatch_alert_to_tenant_channels(
                        db=session,
                        tenant_id=tenant_id,
                        categories=diagnosis_categories,
                        agent_name=job.agent_name,
                        diagnosis_id=diagnosis_id,
                    )

                # Group each detected failure code into the canonical anomalies
                # table. The public `/v1/issues` API projects these grouped
                # problem rows for customer-facing triage.
                try:
                    from app.db.models import Anomaly
                    from app.services.anomalies import compute_fingerprint, map_failure_code_to_detector
                    from app.services.failure_intelligence import issue_evidence_from_diagnosis
                    from app.services.issues import upsert_issue
                    from app.services.notification_dispatch import dispatch_new_issue_slack_alert
                    _call_cost = float(getattr(call, "cost_total", None) or 0.0) if call else 0.0
                    _occurred_at = getattr(job, "created_at", None) or datetime.now(timezone.utc)
                    _prompt_fp = _as_text(payload_with_db_context.get("prompt_fingerprint"))
                    _agent_name = _as_text(payload_with_db_context.get("agent_name"))
                    _seen_groups: set[str] = set()
                    for _diag_item in result.get("diagnoses", []):
                        if not isinstance(_diag_item, dict):
                            continue
                        _code = str(_diag_item.get("category", "")).strip().upper()
                        if not _code or _code in ("UNKNOWN", ""):
                            continue
                        _evidence = issue_evidence_from_diagnosis(
                            diagnosis_item=_diag_item,
                            payload=payload_with_db_context,
                            call=call,
                            job=job,
                            diagnosis_id=diagnosis_id,
                        )
                        _grouping_signature = _as_text(_evidence.get("grouping_signature"))
                        _seen_key = f"{_code}:{_grouping_signature or ''}"
                        if _seen_key in _seen_groups:
                            continue
                        _seen_groups.add(_seen_key)
                        _detector = map_failure_code_to_detector(_code)
                        _existing_issue_id = None
                        if _detector is not None:
                            _fingerprint = compute_fingerprint(
                                detector=_detector,
                                prompt_fingerprint=_prompt_fp,
                                agent_name=_agent_name,
                                extra=_grouping_signature,
                            )
                            _existing_issue_id = session.execute(
                                select(Anomaly.id).where(
                                    Anomaly.project_id == tenant_id,
                                    Anomaly.fingerprint == _fingerprint,
                                )
                            ).scalar_one_or_none()
                        _issue = upsert_issue(
                            session,
                            project_id=tenant_id,
                            failure_code=_code,
                            prompt_fingerprint=_prompt_fp,
                            agent_name=_agent_name,
                            call_id=str(job.call_id or ""),
                            diagnosis_id=diagnosis_id,
                            occurred_at=_occurred_at,
                            call_cost_usd=_call_cost,
                            evidence=_evidence,
                            fingerprint_extra=_grouping_signature,
                            trace_id=_as_text(_evidence.get("trace_id")),
                            user_id=_as_text(_evidence.get("user_id")),
                        )
                        if _issue is not None and _existing_issue_id is None:
                            dispatch_new_issue_slack_alert(
                                db=session,
                                tenant_id=tenant_id,
                                issue_id=_issue.id,
                                failure_code=_code,
                                severity=_issue.severity,
                                agent_name=_agent_name,
                                diagnosis_id=diagnosis_id,
                                call_id=str(job.call_id or "") or None,
                            )
                except Exception:
                    logger.warning("issue_upsert_failed", exc_info=True)
                # Write shown event so the fix appears in adoption funnel analytics.
                try:
                    _result_payload = _fix_safe_json_object(job.result_json)
                    _fix_id = extract_fix_id_from_result(_result_payload, diagnosis_id=diagnosis_id)
                    _now = datetime.now(timezone.utc)
                    ensure_fix_event_prerequisites(
                        session,
                        project_id=tenant_id,
                        diagnosis_id=diagnosis_id,
                        fix_id=_fix_id,
                        event_type="shown",
                        anchor_time=_now,
                        source="system",
                        inferred_from="diagnosis_completed",
                        metadata={"feed": "diagnosis_task"},
                    )
                    record_fix_event(
                        session,
                        project_id=tenant_id,
                        diagnosis_id=diagnosis_id,
                        fix_id=_fix_id,
                        event_type="shown",
                        metadata={
                            "categories": diagnosis_categories,
                            "source_endpoint": "diagnosis_task",
                        },
                        idempotency_key=f"system:diagnosis-shown:{tenant_id}:{diagnosis_id}",
                        source="system",
                        timestamp=_now,
                    )
                except Exception:
                    logger.debug("fix_shown_event_write_failed", exc_info=True)
                # Best-effort realtime broadcast â€” never blocks the worker.
                try:
                    publish_diagnosis(
                        tenant_id=tenant_id,
                        diagnosis={
                            "diagnosis_id": diagnosis_id,
                            "call_id": job.call_id,
                            "status": job.status,
                            "categories": diagnosis_categories,
                            "agent_name": job.agent_name,
                        },
                    )
                    if "LOOP_DETECTED" in diagnosis_categories:
                        publish_loop_alert(
                            tenant_id=tenant_id,
                            alert={
                                "diagnosis_id": diagnosis_id,
                                "agent_name": job.agent_name,
                                "prompt_fingerprint": job.prompt_fingerprint,
                            },
                        )
                    if "AUTH_FAILURE" in diagnosis_categories:
                        publish_auth_failure_alert(
                            tenant_id=tenant_id,
                            alert={
                                "diagnosis_id": diagnosis_id,
                                "agent_name": job.agent_name,
                            },
                        )
                    if "RATE_LIMIT" in diagnosis_categories:
                        publish_rate_limit_alert(
                            tenant_id=tenant_id,
                            alert={
                                "diagnosis_id": diagnosis_id,
                                "agent_name": job.agent_name,
                            },
                        )
                    if "COST_SPIKE" in diagnosis_categories:
                        publish_cost_spike(
                            tenant_id=tenant_id,
                            spike={
                                "diagnosis_id": diagnosis_id,
                                "agent_name": job.agent_name,
                            },
                        )
                except Exception:  # noqa: BLE001
                    logger.debug("realtime publish failed", exc_info=True)
                try:
                    evaluate_pending_fix_resolutions(session, project_id=tenant_id)
                    evaluate_fix_regressions(session, project_id=tenant_id)
                    calibrate_resolved_fix_confidence(session, project_id=tenant_id)
                except Exception:
                    logger.exception(
                        "fix_resolution_evaluation_failed",
                        extra={
                            "event": "fix_resolution_evaluation",
                            "tenant_id": tenant_id,
                            "diagnosis_id": diagnosis_id,
                        },
                    )

                try:
                    from app.services.judge_shadow import should_run_shadow_judge
                    for _code in diagnosis_categories:
                        if should_run_shadow_judge(db=session, tenant_id=tenant_id, failure_code=_code):
                            _call_prompt = None
                            _call_response = None
                            if job.call is not None:
                                _raw = _safe_json_object(job.call.payload_json)
                                _call_prompt = _as_text(_raw.get("prompt"))
                                _call_response = _as_text(_raw.get("response"))
                            run_shadow_judge_task.apply_async(
                                kwargs={
                                    "tenant_id": tenant_id,
                                    "call_id": str(job.call_id or ""),
                                    "failure_code": _code,
                                    "call_prompt": _call_prompt,
                                    "call_response": _call_response,
                                    "diagnosis_summary": str(diagnosis_id),
                                },
                                queue="diagnosis_pattern",
                                countdown=5,
                            )
                            break
                except Exception:
                    logger.debug("shadow_judge_dispatch_failed", exc_info=True)

            return result
        except Exception as exc:
            session.rollback()

            settings = get_settings()
            max_retries = max(0, settings.DIAGNOSIS_TASK_MAX_RETRIES)
            retry_count = _current_retry_count(self)
            error_message = mask_error_message(exc)

            job = session.execute(
                select(DiagnosisJob).where(
                    DiagnosisJob.tenant_id == tenant_id,
                    DiagnosisJob.diagnosis_id == diagnosis_id,
                )
            ).scalar_one_or_none()

            if retry_count < max_retries:
                countdown = _calculate_retry_countdown(
                    retry_count=retry_count,
                    base_seconds=settings.DIAGNOSIS_TASK_RETRY_BASE_SECONDS,
                    max_seconds=settings.DIAGNOSIS_TASK_RETRY_MAX_SECONDS,
                )

                if job is not None:
                    job.status = "retrying"
                    job.error_message = error_message
                    session.add(job)
                    session.commit()

                record_diagnosis_job("retry_scheduled")
                logger.warning(
                    "diagnosis_task_retry_scheduled",
                    extra={
                        "event": "diagnosis_task",
                        "tenant_id": tenant_id,
                        "diagnosis_id": diagnosis_id,
                        "retry_count": retry_count,
                        "max_retries": max_retries,
                        "countdown_seconds": countdown,
                    },
                )
                raise self.retry(exc=exc, countdown=countdown, max_retries=max_retries)

            dead_letter_payload = {
                "status": "dead_lettered",
                "tenant_id": tenant_id,
                "diagnosis_id": diagnosis_id,
                "error_message": error_message,
                "retry_count": retry_count,
                "max_retries": max_retries,
                "dead_lettered_at": datetime.now(timezone.utc).isoformat(),
            }

            if job is not None:
                job.status = "failed" if job.call_id else "dead_lettered"
                job.error_message = error_message
                job.result_json = json.dumps(dead_letter_payload, separators=(",", ":"))
                session.add(job)
                session.commit()

            record_diagnosis_job("dead_lettered")
            logger.exception(
                "diagnosis_task_dead_lettered",
                extra={
                    "event": "diagnosis_task",
                    "tenant_id": tenant_id,
                    "diagnosis_id": diagnosis_id,
                    "retry_count": retry_count,
                    "max_retries": max_retries,
                },
            )
            return dead_letter_payload
        finally:
            session.close()


__all__ = [name for name in globals() if not name.startswith("__")]
