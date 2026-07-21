# Zroky Phase 9 Build Report

Status: In progress
Phase: Live Product Hardening
Tracker IDs: P9-001 to P9-005

## Scope

Phase 9 adds enterprise live-readiness controls around access, auditability, secrets, sandboxing, and fail-closed production configuration.

## Completed IDs

- P9-001 SSO/RBAC/separation of duties.
- P9-002 Audit log for privileged/recovery actions.
- P9-003 Customer-local secrets strategy.
- P9-004 Executor sandbox/enforcement option.
- P9-005 Production config validator.

## Changed Code

- `zroky-backend/app/api/routes/incidents.py`
- `zroky-backend/app/api/routes/_action_intents_schemas.py`
- `zroky-backend/app/core/config.py`
- `zroky-backend/app/core/config_validation.py`
- `zroky-backend/app/services/audit_logs.py`
- `zroky-backend/app/services/_action_runner_core.py`
- `zroky-backend/app/services/_action_runner_attempts.py`
- `zroky-backend/tests/test_action_intents.py`
- `zroky-backend/tests/test_final_intents_api.py`

## Tests And Checks

- `python -m pytest tests/test_final_intents_api.py::test_incident_recovery_execution_queues_customer_executor -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/incidents.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py::test_incident_recovery_execution_queues_customer_executor -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/incidents.py app/services/audit_logs.py` passed in `zroky-backend`.
- `python -m pytest tests/test_action_intents.py::test_customer_local_secrets_mode_requires_vault_refs -q` passed in `zroky-backend`.
- `python -m py_compile app/core/config.py app/services/_action_runner_core.py` passed in `zroky-backend`.
- `python -m pytest tests/test_action_intents.py::test_action_runner_manifest_binds_executor_enforcement_to_plan tests/test_action_intents.py::test_execution_adapter_contracts_are_exposed -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/_action_intents_schemas.py app/services/_action_runner_core.py app/services/_action_runner_attempts.py` passed in `zroky-backend`.
- `python -m pytest tests/test_production_config.py::test_production_config_accepts_hardened_profile tests/test_production_config.py::test_production_config_rejects_missing_final_live_hardening_controls tests/test_production_config.py::test_production_config_rejects_insecure_defaults -q` passed in `zroky-backend`.
- `python -m py_compile app/core/config.py app/core/config_validation.py` passed in `zroky-backend`.

## Known Risks

- JWT/project-membership RBAC already exists. Recovery execution now enforces separation-of-duties and writes an audit log row. Customer-local secrets mode is opt-in and defaults off for existing deployments. Executor enforcement is a signed runner-manifest option, not an in-repo container runtime installation. Production startup now fails closed for missing final live hardening controls.

## Decision

Phase 9 is complete. Next ID: P10-001.
