# Zroky Phase 6 Build Report

Status: Complete at source-test level
Phase: Incident Lifecycle
Tracker IDs: P6-001 to P6-005

## Scope

Phase 6 turns non-verified outcome snapshots into operator-actionable incidents, then adds manual remediation and operations dashboard surfaces.

## Completed IDs

- P6-001 Incident creation from non-verified snapshots.
- P6-002 Manual remediation and re-verification.
- P6-003 Operations dashboard.
- P6-004 Brand-new dashboard shell and final IA.
- P6-005 Dashboard real API wiring and states.

## Added Code

- `zroky-backend/app/domain/incident/builder.py`
- `zroky-backend/app/api/routes/incidents.py`
- `zroky-dashboard/src/app/(dashboard)/operations/page.tsx`
- `zroky-dashboard/src/app/(dashboard)/operations/page.test.tsx`

## Changed Code

- `zroky-backend/app/domain/incident/__init__.py`
- `zroky-backend/app/api/routes/outcome_graphs.py`
- `zroky-backend/app/domain/outcome_graph/builder.py`
- `zroky-backend/app/api/routes/runs.py`
- `zroky-backend/app/api/routes/policy.py`
- `zroky-backend/app/api/router.py`
- `zroky-backend/tests/test_final_intents_api.py`
- `zroky-dashboard/src/components/dashboard-shell.tsx`
- `zroky-dashboard/src/components/dashboard-shell.test.tsx`
- `zroky-dashboard/src/lib/api.ts`
- `zroky-dashboard/src/lib/dashboard-route-contract.ts`
- `zroky-dashboard/src/lib/dashboard-route-contract.test.ts`

## Tests And Checks

- `python -m pytest tests/test_final_intents_api.py tests/test_final_outcome_graph.py -q` passed in `zroky-backend`.
- `python -m py_compile app/domain/incident/builder.py app/domain/incident/__init__.py app/api/routes/incidents.py app/api/routes/outcome_graphs.py app/api/router.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py tests/test_final_outcome_graph.py -q` passed after manual remediation.
- `python -m py_compile app/api/routes/incidents.py app/domain/outcome_graph/builder.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py tests/test_final_outcome_graph.py -q` passed after final runs/approval list APIs.
- `python -m py_compile app/api/routes/runs.py app/api/routes/policy.py` passed in `zroky-backend`.
- `npm test -- --run "src/app/(dashboard)/operations/page.test.tsx" "src/lib/dashboard-route-contract.test.ts"` passed in `zroky-dashboard`.
- `npx eslint "src/app/(dashboard)/operations/page.tsx" "src/app/(dashboard)/operations/page.test.tsx" "src/lib/api.ts" "src/lib/dashboard-route-contract.ts" "src/lib/dashboard-route-contract.test.ts"` passed in `zroky-dashboard`.
- `npm test -- --run "src/components/dashboard-shell.test.tsx" "src/lib/dashboard-route-contract.test.ts"` passed in `zroky-dashboard`.
- `npx eslint "src/components/dashboard-shell.tsx" "src/components/dashboard-shell.test.tsx" "src/lib/dashboard-route-contract.ts" "src/lib/dashboard-route-contract.test.ts"` passed in `zroky-dashboard`.
- `npm test -- --run "src/app/(dashboard)/operations/page.test.tsx" "src/components/dashboard-shell.test.tsx" "src/lib/dashboard-route-contract.test.ts"` passed in `zroky-dashboard`.
- `npx eslint "src/app/(dashboard)/operations/page.tsx" "src/app/(dashboard)/operations/page.test.tsx" "src/components/dashboard-shell.tsx" "src/components/dashboard-shell.test.tsx" "src/lib/dashboard-route-contract.ts" "src/lib/dashboard-route-contract.test.ts"` passed in `zroky-dashboard`.

## Known Risks

- Manual resolution requires a same-intent verified outcome graph different from the failed graph. Timestamp ordering is not used because SQLite test timestamps are too coarse.
- Operations route is protected, real-API-backed, and promoted into the final primary IA.
- Old focused pages remain protected support routes but are removed from primary navigation. Hard deletion is left to the structured workspace/codebase cleanup tasks.
- Phase 6 is source-test complete. Live browser/API smoke is still covered by later production-readiness phases.

## Decision

Phase 6 complete at source-test level. Next tracker ID: P7-001.
