# Zroky Phase 3 Build Report

Status: In progress  
Phase: Universal Intake  
Tracker IDs: P3-001 to P3-006

## Scope

Phase 3 adds intake paths for external agent activity without turning Zroky into the executor.

## Completed IDs

- P3-001 REST/webhook run intake.
- P3-002 CloudEvents envelope support.
- P3-003 OTLP/OpenTelemetry intake.
- P3-004 MCP import as untrusted capability draft.
- P3-005 A2A Agent Card import.
- P3-006 PII redaction before evidence export.

## Added Code

- `zroky-backend/app/api/routes/runs.py`
- `zroky-backend/app/api/routes/events.py`
- `zroky-backend/app/api/routes/evidence.py`
- `zroky-backend/alembic/versions/0126_create_final_agent_runs.py`
- `zroky-backend/alembic/versions/0127_create_final_connector_capability_drafts.py`

## Changed Code

- `zroky-backend/app/api/router.py`
- `zroky-backend/app/db/_internal/model_final_domain.py`
- `zroky-backend/tests/test_final_domain_tables.py`
- `zroky-backend/tests/test_final_intents_api.py`

## Tests And Checks

- `python -m pytest tests/test_final_intents_api.py tests/test_final_domain_tables.py -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/runs.py app/api/router.py app/db/_internal/model_final_domain.py alembic/versions/0126_create_final_agent_runs.py` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/events.py app/api/routes/runs.py app/api/router.py` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/events.py` passed in `zroky-backend` after OTLP JSON intake.
- `python -m py_compile app/api/routes/events.py app/db/_internal/model_final_domain.py alembic/versions/0127_create_final_connector_capability_drafts.py` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/events.py` passed in `zroky-backend` after A2A import.
- `python -m py_compile app/api/routes/evidence.py` passed in `zroky-backend`.

## Known Risks

- CloudEvents support currently handles structured JSON `com.zroky.run.declared`. Intent, observation, decision, and recovery event types are not normalized yet.
- OTLP support currently handles JSON trace export shape only; protobuf collector ingestion is not implemented.
- MCP import stores only untrusted drafts; no recovery trust is granted.
- A2A import stores only untrusted drafts; no recovery trust is granted.
- Final evidence bundle create/read stores redacted payload only.
- Migration apply/rollback against a real database is still pending for final-domain migrations.

## Decision

Phase 3 complete at source-test level. Next ID: P4-001.
