from app.worker._internal.tasks_common import *
from app.worker._internal.tasks_loop_detection import *
from app.worker._internal.tasks_utils import *


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
            return {"status": "duplicate_ignored", "tenant_id": tenant_id, "diagnosis_id": diagnosis_id}

        session = SessionLocal()
        try:
            set_db_tenant_context(session, tenant_id)
            job = session.execute(
                select(DiagnosisJob).where(
                    DiagnosisJob.tenant_id == tenant_id,
                    DiagnosisJob.diagnosis_id == diagnosis_id,
                )
            ).scalar_one_or_none()
            call = session.get(Call, job.call_id) if job is not None and job.call_id else None
            if call is None:
                call = session.execute(
                    select(Call).where(Call.project_id == tenant_id, Call.id == diagnosis_id)
                ).scalar_one_or_none()

            if job is not None and _normalize_text(job.status) in TERMINAL_DIAGNOSIS_STATUSES:
                record_diagnosis_job("duplicate_ignored")
                existing = _safe_json_object(job.result_json)
                if existing:
                    return existing
                return {"status": "already_done", "tenant_id": tenant_id, "diagnosis_id": diagnosis_id}

            diagnosis_payload = _payload_for_call_or_legacy(call=call, job=job, payload=payload)
            payload_with_db_context = mask_payload(
                _enrich_payload_with_db_loop_context(session, tenant_id=tenant_id, payload=diagnosis_payload)
            )

            if job is not None:
                job.status = "processing"
                job.agent_name = _as_text(payload_with_db_context.get("agent_name"))
                job.prompt_fingerprint = _as_text(payload_with_db_context.get("prompt_fingerprint"))
                session.add(job)
                session.commit()

            fast_diagnoses = evaluate_fast_rules(payload_with_db_context)
            pattern_diagnoses, informational = evaluate_pattern_rules(payload_with_db_context)
            result = mask_value(
                build_diagnosis_result(
                    payload=payload_with_db_context,
                    fast_diagnoses=fast_diagnoses,
                    pattern_diagnoses=pattern_diagnoses,
                    informational=informational,
                )
            )
            result["status"] = "processed"
            result["tenant_id"] = tenant_id
            result["diagnosis_id"] = diagnosis_id

            categories = [
                str(item.get("category", "UNKNOWN"))
                for item in result.get("diagnoses", [])
                if isinstance(item, dict)
            ]
            if "LOOP_DETECTED" in categories:
                loop_mapping = payload_with_db_context.get("loop") if isinstance(payload_with_db_context.get("loop"), Mapping) else {}
                agent_name = _as_text(payload_with_db_context.get("agent_name")) or _as_text(loop_mapping.get("agent_name"))
                prompt_fingerprint = _as_text(payload_with_db_context.get("prompt_fingerprint")) or _as_text(
                    loop_mapping.get("prompt_fingerprint")
                )
                if agent_name and prompt_fingerprint:
                    mark_loop_detected_fired(
                        tenant_id=tenant_id,
                        agent_name=agent_name,
                        prompt_fingerprint=prompt_fingerprint,
                        fired_at=datetime.now(timezone.utc),
                        cooldown_seconds=LOOP_COOLDOWN_SECONDS,
                    )

            record_diagnosis_job("completed")
            record_diagnosis_rule_hits(categories)

            if job is not None:
                job.status = "done" if job.call_id else "completed"
                job.result_json = json.dumps(mask_value(result), separators=(",", ":"))
                job.error_message = None
                sync_alerts_from_jobs(session, tenant_id, [job])
                session.add(job)
                session.commit()

                try:
                    from app.db.models import Anomaly
                    from app.services.anomalies import (
                        compute_fingerprint,
                        map_failure_code_to_detector,
                    )
                    from app.services.failure_intelligence import issue_evidence_from_diagnosis
                    from app.services.issues import upsert_issue
                    from app.services.notification_dispatch import dispatch_new_issue_slack_alert

                    call_cost = float(getattr(call, "cost_total", None) or 0.0) if call else 0.0
                    occurred_at = getattr(job, "created_at", None) or datetime.now(timezone.utc)
                    prompt_fp = _as_text(payload_with_db_context.get("prompt_fingerprint"))
                    agent_name = _as_text(payload_with_db_context.get("agent_name"))
                    seen_groups: set[str] = set()
                    for diagnosis_item in result.get("diagnoses", []):
                        if not isinstance(diagnosis_item, dict):
                            continue
                        code = str(diagnosis_item.get("category", "")).strip().upper()
                        if not code or code == "UNKNOWN":
                            continue
                        evidence = issue_evidence_from_diagnosis(
                            diagnosis_item=diagnosis_item,
                            payload=payload_with_db_context,
                            call=call,
                            job=job,
                            diagnosis_id=diagnosis_id,
                        )
                        grouping_signature = _as_text(evidence.get("grouping_signature"))
                        seen_key = f"{code}:{grouping_signature or ''}"
                        if seen_key in seen_groups:
                            continue
                        seen_groups.add(seen_key)
                        detector = map_failure_code_to_detector(code)
                        existing_issue_id = None
                        if detector is not None:
                            fingerprint = compute_fingerprint(
                                detector=detector,
                                prompt_fingerprint=prompt_fp,
                                agent_name=agent_name,
                                extra=grouping_signature,
                            )
                            existing_issue_id = session.execute(
                                select(Anomaly.id).where(
                                    Anomaly.project_id == tenant_id,
                                    Anomaly.fingerprint == fingerprint,
                                )
                            ).scalar_one_or_none()
                        issue = upsert_issue(
                            session,
                            project_id=tenant_id,
                            failure_code=code,
                            prompt_fingerprint=prompt_fp,
                            agent_name=agent_name,
                            call_id=str(job.call_id or ""),
                            diagnosis_id=diagnosis_id,
                            occurred_at=occurred_at,
                            call_cost_usd=call_cost,
                            evidence=evidence,
                            fingerprint_extra=grouping_signature,
                            trace_id=_as_text(evidence.get("trace_id")),
                            user_id=_as_text(evidence.get("user_id")),
                        )
                        if issue is not None and existing_issue_id is None:
                            dispatch_new_issue_slack_alert(
                                db=session,
                                tenant_id=tenant_id,
                                issue_id=issue.id,
                                failure_code=code,
                                severity=issue.severity,
                                agent_name=agent_name,
                                diagnosis_id=diagnosis_id,
                                call_id=str(job.call_id or "") or None,
                            )
                except Exception:
                    logger.warning("issue_upsert_failed", exc_info=True)

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
                raise self.retry(exc=exc, countdown=countdown, max_retries=max_retries)

            dead_letter = {
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
                job.result_json = json.dumps(dead_letter, separators=(",", ":"))
                session.add(job)
                session.commit()
            record_diagnosis_job("dead_lettered")
            return dead_letter
        finally:
            session.close()


__all__ = [name for name in globals() if not name.startswith("__")]
