# Zroky Phase 2 Build Report

Status: In progress  
Phase: Pre-Execution Governance  
Tracker IDs: P2-001 to P2-005

## Scope

Phase 2 adds the pre-execution governance surface: trusted intent intake, policy decisioning, exact approvals, and SDK guards.

## Completed IDs

- P2-001 Trusted intent API.
- P2-002 Policy check API.
- P2-003 Idempotency conflict protection.
- P2-004 Exact approval requirements.
- P2-005 SDK pre-execution guard.

## Added Code

- `zroky-backend/app/api/routes/intents.py`
- `zroky-backend/app/api/routes/policy.py`
- `zroky-backend/tests/test_final_intents_api.py`
- `zroky-backend/alembic/versions/0125_create_final_approval_requirements.py`
- `zroky-sdk/zroky/intent.py`
- `zroky-sdk/tests/test_final_pre_execution_guard.py`
- `zroky-sdk-js/src/intent.ts`
- `zroky-sdk-js/tests/intent.test.ts`

## Changed Code

- `zroky-backend/app/api/router.py`
- `zroky-backend/app/db/_internal/model_final_domain.py`
- `zroky-backend/alembic/versions/0123_create_final_domain_tables.py`
- `zroky-sdk/zroky/__init__.py`
- `zroky-sdk-js/src/index.ts`

## Tests And Checks

- `python -m pytest tests/test_final_intents_api.py -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/intents.py app/api/router.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py tests/test_final_domain_tables.py -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/intents.py app/api/routes/policy.py app/api/router.py app/db/_internal/model_final_domain.py alembic/versions/0123_create_final_domain_tables.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py -q` passed in `zroky-backend` after adding changed-payload conflict protection.
- `python -m pytest tests/test_final_intents_api.py tests/test_final_domain_tables.py -q` passed in `zroky-backend` after adding digest-bound approval requirements.
- `python -m py_compile app/api/routes/policy.py app/db/_internal/model_final_domain.py alembic/versions/0125_create_final_approval_requirements.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_pre_execution_guard.py -q` passed in `zroky-sdk`.
- `python -m py_compile zroky/intent.py zroky/__init__.py` passed in `zroky-sdk`.
- `npm test -- --run tests/intent.test.ts` passed in `zroky-sdk-js` and ran the JS SDK suite with the new test included.

## Known Risks

- Policy rule evaluation is not implemented yet. Current safe default is `observe_only`; only admin/owner can force a decision.
- Approval approve/deny endpoints are not implemented yet; P2-004 only creates exact approval requirements.
- SDK final guard is additive. Existing legacy `guard/protect` behavior is unchanged.

## Decision

Phase 2 complete at source-test level. Next ID: P3-001.
