# Zroky Phase 7 Build Report

Status: In progress
Phase: Safe Recovery
Tracker IDs: P7-001 to P7-006

## Scope

Phase 7 turns verified incidents into safe recovery execution flows without blind retry or raw-secret exposure.

## Completed IDs

- P7-001 Customer recovery executor.
- P7-002 Executor capability manifests.
- P7-003 Recovery playbook registry.
- P7-004 Smallest recovery plan compiler.
- P7-005 Signed dispatch with lease, nonce, fencing.
- P7-006 Result-unknown reconstruction.

## Changed Code

- `zroky-backend/app/api/routes/incidents.py`
- `zroky-backend/app/api/router.py`
- `zroky-backend/app/db/_internal/model_verified_actions.py`
- `zroky-backend/app/services/_action_runner_core.py`
- `zroky-backend/app/services/_action_runner_attempts.py`
- `zroky-backend/app/api/routes/action_intents.py`
- `zroky-backend/app/api/routes/_action_intents_schemas.py`
- `zroky-backend/app/api/routes/_action_intents_helpers.py`
- `zroky-backend/tests/test_final_intents_api.py`
- `zroky-backend/tests/test_action_intents.py`

## Added Code

- `zroky-backend/alembic/versions/0128_add_action_runner_capability_manifest.py`
- `zroky-backend/app/api/routes/recovery.py`

## Tests And Checks

- `python -m pytest tests/test_final_intents_api.py tests/test_final_domain_tables.py -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/incidents.py` passed in `zroky-backend`.
- `python -m pytest tests/test_action_intents.py::test_action_runner_registers_and_records_heartbeat tests/test_action_intents.py::test_action_runner_capability_manifest_is_signed_and_allowlisted tests/test_action_intents.py::test_execution_attempt_is_plan_bound_idempotent_and_secret_safe -q` passed in `zroky-backend`.
- `python -m py_compile app/services/_action_runner_core.py app/services/_action_runner_attempts.py app/api/routes/action_intents.py app/api/routes/_action_intents_helpers.py app/api/routes/_action_intents_schemas.py app/db/_internal/model_verified_actions.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py::test_workflow_assurance_pack_schema_and_immutable_version -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/recovery.py app/api/router.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py::test_recovery_plan_compiler_excludes_already_satisfied_effects tests/test_final_intents_api.py::test_workflow_assurance_pack_schema_and_immutable_version -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/recovery.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py::test_incident_recovery_execution_queues_customer_executor -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/recovery.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py::test_incident_recovery_execution_queues_customer_executor -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/recovery.py` passed in `zroky-backend`.

## Known Risks

- Recovery execution currently queues a `final_domain_outbox_jobs.execute_recovery` job and records the customer executor reference.
- Capability manifests are digest-signed and allowlisted at runner registration/heartbeat.
- Recovery playbook registry reads active Workflow Assurance Packs as source of truth. Dedicated playbook storage is intentionally skipped unless playbooks need independent lifecycle later.
- Recovery plan compiler excludes already matched effect steps.
- Recovery dispatch claim signs the executor command with a nonce, lease expiry, and fencing token.
- Result-unknown reconstruction only runs after a claimed/running dispatch lease expires. It creates a fresh outcome graph from latest observations, then resolves or marks recovery ambiguous based on verified state.

## Decision

Phase 7 is complete at source-test level. Next phase: P8 Evidence and Customer-Facing Assurance.
