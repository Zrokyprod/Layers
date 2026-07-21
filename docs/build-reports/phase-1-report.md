# Zroky Phase 1 Build Report

Status: In progress  
Phase: Final Domain Foundation  
Tracker IDs: P1-001 to P1-005

## Scope

Phase 1 creates the clean product domain foundation before routes, persistence, workers, and dashboard screens are rebuilt around it.

## Completed IDs

- P1-001 Final domain module skeleton.
- P1-002 Final domain database table source implemented.
- P1-003 Final transactional outbox source implemented.
- P1-004 Tenant negative tests for final domain API and worker paths.

## Added Code

- `zroky-backend/app/domain/__init__.py`
- `zroky-backend/app/domain/intent/__init__.py`
- `zroky-backend/app/domain/policy/__init__.py`
- `zroky-backend/app/domain/approval/__init__.py`
- `zroky-backend/app/domain/assurance_pack/__init__.py`
- `zroky-backend/app/domain/connector_manifest/__init__.py`
- `zroky-backend/app/domain/observation/__init__.py`
- `zroky-backend/app/domain/outcome_graph/__init__.py`
- `zroky-backend/app/domain/incident/__init__.py`
- `zroky-backend/app/domain/recovery/__init__.py`
- `zroky-backend/app/domain/evidence/__init__.py`
- `zroky-backend/app/domain/tenancy/__init__.py`
- `zroky-backend/tests/test_final_domain_skeleton.py`
- `zroky-backend/app/db/_internal/model_final_domain.py`
- `zroky-backend/alembic/versions/0123_create_final_domain_tables.py`
- `zroky-backend/tests/test_final_domain_tables.py`
- `zroky-backend/alembic/versions/0124_create_final_domain_outbox_jobs.py`
- `zroky-backend/tests/test_final_intents_api.py`

## Tests And Checks

- `python -m pytest tests/test_final_domain_skeleton.py -q` passed in `zroky-backend`.
- `python -m pytest tests/test_final_domain_tables.py tests/test_final_domain_skeleton.py -q` passed in `zroky-backend`.
- `python -m py_compile app/db/_internal/model_final_domain.py alembic/versions/0123_create_final_domain_tables.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_domain_tables.py -q` passed in `zroky-backend`.
- `python -m py_compile app/db/_internal/model_final_domain.py alembic/versions/0123_create_final_domain_tables.py alembic/versions/0124_create_final_domain_outbox_jobs.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py::test_final_intent_read_rejects_cross_tenant_project_context tests/test_final_intents_api.py::test_recovery_dispatch_claim_rejects_cross_tenant_worker_context -q` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py -q` passed in `zroky-backend`.

## Known Risks

- P1-001 is only the package boundary. No domain schemas, database models, or API routes are implemented yet.
- P1-002 is Implemented, not Verified, because migration apply/rollback has not been run against a real database in this run.
- P1-003 is Implemented, not Verified, because migration apply/rollback has not been run against a real database in this run.
- P1-004 uses SQLite API/worker path tests. Real Postgres RLS enforcement remains covered separately by the static and Postgres-specific RLS guard work.

## Decision

P1-004 is complete. Phase 1 still has P1-002 and P1-003 in Implemented state until real migration apply/rollback verification is run.
