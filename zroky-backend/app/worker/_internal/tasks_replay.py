from app.worker._internal.tasks_common import *
from app.worker._internal.tasks_utils import *

@celery_app.task(
    name="app.worker.tasks.process_replay_run",
    queue="diagnosis_pattern",
    bind=True,
    max_retries=2,
)
def process_replay_run(
    self,
    tenant_id: str,
    run_id: str,
    *,
    record_calibration: bool = False,
) -> dict:
    """Execute a pending ReplayRun (Module 8; plan Â§6.4).

    Grades every GoldenTrace in the parent set against the configured
    judge_engine evaluator and writes one ReplayRunTrace row per trace.

    Idempotent on the (tenant_id, run_id) pair via the standard
    idempotency_guard; once a run is non-pending the executor itself
    short-circuits, so retries are safe.

    Resolves the right evaluator based on the org's plan + entitlements
    so Pro gets single-judge (Haiku-4) and Team+ gets ensemble per locked
    decision #4.
    """
    task_key = f"replay:{tenant_id}:{run_id}"
    with idempotency_guard(task_key) as acquired:
        if not acquired:
            return {
                "status": "duplicate_ignored",
                "tenant_id": tenant_id,
                "run_id": run_id,
            }

        session = SessionLocal()
        try:
            set_db_tenant_context(session, tenant_id)

            # Resolve the right evaluator for this org. Resolver lookups
            # are cached (60s TTL) so this is a cheap call. Failure to
            # resolve (e.g. cache layer down) falls through to the
            # plan-code default path in get_evaluator.
            from app.services import judge_engine
            from app.services.entitlements_resolver import (
                get_plan_code,
                resolve_all,
            )
            from app.services.replay_executor import (
                ReplayBudgetTracker,
                default_resolver,
                execute_replay_run,
                _finalize_error,
                make_live_llm_resolver,
            )
            from app.services.replay_runs import (
                REAL_COMPARISON_REPLAY_MODES,
                REPLAY_MODE_REAL_LLM,
                parse_summary,
            )

            try:
                ents = resolve_all(session, tenant_id)
                plan = get_plan_code(session, tenant_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "process_replay_run.entitlements_lookup_failed tenant=%s",
                    tenant_id,
                    exc_info=True,
                )
                ents = None
                plan = None
            evaluator = judge_engine.get_evaluator(
                plan_code=plan, entitlements_dict=ents
            )

            # â”€â”€ Option B: resolve replay mode + overrides from summary â”€â”€â”€â”€
            run = session.execute(
                select(ReplayRun).where(
                    ReplayRun.project_id == tenant_id,
                    ReplayRun.id == run_id,
                )
            ).scalar_one_or_none()
            if run is None:
                logger.warning(
                    "process_replay_run.run_not_found tenant=%s run=%s",
                    tenant_id, run_id,
                )
                return {
                    "status": "not_found",
                    "tenant_id": tenant_id,
                    "run_id": run_id,
                }

            summary = parse_summary(run.summary_json)
            replay_mode = str(summary.get("replay_mode") or "stub")
            requested_replay_mode = str(
                summary.get("requested_replay_mode") or replay_mode
            )
            candidate_prompt_override = summary.get("candidate_prompt_override")
            candidate_model_override = summary.get("candidate_model_override")

            # Plan gate: real-LLM replay requires Team+ or Enterprise.
            # Fail closed instead of silently running a stub replay.
            use_live_resolver = False
            if (
                replay_mode == REPLAY_MODE_REAL_LLM
                or requested_replay_mode in REAL_COMPARISON_REPLAY_MODES
            ):
                from app.services.entitlements_resolver import has

                real_llm_entitled = has(
                    session, tenant_id, "pilot.real_llm_replay_enabled"
                )
                if not real_llm_entitled:
                    logger.warning(
                        "process_replay_run.plan_gate_blocked tenant=%s run=%s "
                        "plan=%s â€” falling back to stub resolver",
                        tenant_id, run_id, plan,
                    )
                    run = _finalize_error(
                        session, run, reason="real_llm_entitlement_missing"
                    )
                    return {
                        "status": run.status,
                        "tenant_id": tenant_id,
                        "run_id": run_id,
                        "summary": json.loads(run.summary_json) if run.summary_json else {},
                    }
                else:
                    use_live_resolver = True

            # Budget tracker only matters when we're doing live calls.
            budget_tracker = None
            if use_live_resolver:
                from app.core.config import get_settings

                budget_usd = float(
                    get_settings().REPLAY_REAL_LLM_BUDGET_USD
                )
                budget_tracker = ReplayBudgetTracker(budget_usd=budget_usd)

            actual_output_resolver = (
                make_live_llm_resolver(
                    replay_mode=requested_replay_mode,
                    candidate_prompt_override=candidate_prompt_override,
                    candidate_model_override=candidate_model_override,
                    budget_tracker=budget_tracker,
                )
                if use_live_resolver
                else default_resolver
            )

            run = execute_replay_run(
                session,
                project_id=tenant_id,
                run_id=run_id,
                evaluator=evaluator,
                record_calibration=record_calibration,
                actual_output_resolver=actual_output_resolver,
                budget_tracker=budget_tracker,
            )
            if run is None:
                logger.warning(
                    "process_replay_run.run_not_found tenant=%s run=%s",
                    tenant_id, run_id,
                )
                return {
                    "status": "not_found",
                    "tenant_id": tenant_id,
                    "run_id": run_id,
                }

            # â”€â”€ Auto-fix PR generation (most advanced â€” Enterprise) â”€â”€
            # Trigger only when a real-LLM replay with overrides fails.
            if requested_replay_mode in REAL_COMPARISON_REPLAY_MODES and run.status in ("fail", "error"):
                from app.services.replay_pr_dispatch import (
                    dispatch_replay_fix_pr,
                )

                try:
                    outcome = dispatch_replay_fix_pr(
                        session, replay_run=run
                    )
                    logger.info(
                        "process_replay_run.autofix_outcome tenant=%s run=%s "
                        "decision=%s pr_url=%s",
                        tenant_id,
                        run_id,
                        outcome.decision,
                        (outcome.action.pr_url or "")
                        if outcome.action
                        else None,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "process_replay_run.autofix_failed tenant=%s run=%s",
                        tenant_id, run_id,
                    )

            return {
                "status": run.status,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "summary": json.loads(run.summary_json) if run.summary_json else {},
            }
        except Exception as exc:
            session.rollback()
            retry_count = _current_retry_count(self)
            if retry_count < 2:
                logger.warning(
                    "process_replay_run.retry tenant=%s run=%s attempt=%d",
                    tenant_id, run_id, retry_count + 1,
                )
                raise self.retry(exc=exc, countdown=30)
            logger.exception(
                "process_replay_run.failed tenant=%s run=%s",
                tenant_id, run_id,
            )
            # Best-effort: mark the run as error so the dashboard stops
            # polling a pending row indefinitely.
            try:
                from app.services.replay_executor import _finalize_error  # type: ignore[attr-defined]

                run = session.execute(
                    select(ReplayRun).where(
                        ReplayRun.project_id == tenant_id,
                        ReplayRun.id == run_id,
                    )
                ).scalar_one_or_none()
                if run is not None and run.status in ("pending", "running"):
                    _finalize_error(
                        session, run, reason=f"worker_error:{type(exc).__name__}"
                    )
            except Exception:  # noqa: BLE001
                logger.debug("process_replay_run.finalize_error_failed", exc_info=True)
            return {
                "status": "error",
                "tenant_id": tenant_id,
                "run_id": run_id,
                "error_message": mask_error_message(exc),
            }
        finally:
            session.close()


__all__ = [name for name in globals() if not name.startswith("__")]
