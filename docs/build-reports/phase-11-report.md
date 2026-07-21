# Zroky Phase 11 Build Report

Status: In Progress
Phase: Production Surface Cleanup And Launch Packaging
Tracker IDs: P11-001 to P11-012

## Scope

Phase 11 removes old production surfaces that do not belong to the final Zroky product, then packages the final launch evidence.

## Completed IDs

- P11-001 Remove old dashboard from production app.
- P11-002 Remove non-allowlisted backend routes from production.
- P11-003 Remove old SDK exports from production path.
- P11-004 Final launch report.
- P11-005 Final GitHub production release workflow.
- P11-006 Final codebase shape convergence.
- P11-007 FinalDomainOutboxJob worker fail-closed drain.
- P11-008 Final approval resolution API.
- P11-009 Stripe refund test-loop contract.
- P11-010 Live Stripe test-loop runner.
- P11-011 Section 7 production cleanup.
- P11-012 Preserve applied Alembic MCP revision.

## P11-001 Result

The old `/actions` and `/agents` dashboard route trees were removed from the production dashboard app. Their useful product concepts now live under the final dashboard IA:

- Operations: live runs, action intents, approvals, recovery, incidents.
- Workflows: workflow setup and operating model.
- Evidence: signed proof and outcome verification.
- Systems: integrations and system-of-record posture.
- Settings: workspace configuration.

## Changed Code

- Deleted `zroky-dashboard/src/app/(dashboard)/actions/`.
- Deleted `zroky-dashboard/src/app/(dashboard)/agents/`.
- Updated `zroky-dashboard/src/lib/dashboard-route-contract.ts`.
- Updated `zroky-dashboard/src/lib/dashboard-route-contract.test.ts`.
- Updated `zroky-dashboard/src/lib/route-auth-guard.test.ts`.
- Updated `zroky-dashboard/src/components/dashboard-shell.tsx`.
- Repointed old dashboard links to final routes across dashboard pages and libraries.
- Fixed `zroky-backend/app/services/pilot.py` so first-read policy seeding is idempotent when concurrent requests race on the same project.
- Added focused regression coverage in `zroky-backend/tests/test_pilot.py`.
- Updated `zroky-backend/app/api/router.py` so old diagnosis, replay, observability, issues, judge, drift, digest, and golden-set route families are no longer mounted in the production router.
- Removed stale old-route settings from `zroky-backend/app/core/config.py` and `zroky-backend/tests/conftest.py`.
- Added final backend route allowlist regression coverage in `zroky-backend/tests/test_final_backend_route_allowlist.py`.
- Updated `zroky-backend/tests/test_owner_route_gate.py` so stale legacy env flags cannot re-enable old production routes.
- Removed old JS public exports for `promptFingerprint`, `captureHandoff`, `captureMemory`, `capturePolicyDecision`, `captureRetrieval`, and `captureToolCall` from `zroky-sdk-js/src/index.ts`.
- Updated `zroky-sdk-js/package.json` public description/keywords away from generic observability/capture language.
- Removed old Python public exports for `capture_handoff`, `capture_memory`, `capture_policy_decision`, `capture_retrieval`, `capture_tool_call`, and `generate_prompt_fingerprint` from `zroky-sdk/zroky/__init__.py`.
- Added JS and Python public-surface regression tests.
- Added `docs/build-reports/final-launch-report.md`.
- Rewrote `.github/workflows/paid-launch-readiness.yml` as `Final Production Release` with final-only tracker, backend, dashboard, SDK, and optional deployed smoke gates.
- Added final API v1, worker job, infrastructure, and Python SDK boundary modules with shape regression tests.
- Added `zroky-backend/app/services/final_domain_outbox.py` and `zroky-backend/app/worker/_internal/tasks_final_domain_outbox.py` to claim server-owned final-domain outbox jobs without falsely marking unimplemented handlers as successful.
- Added `final-domain-outbox-sweep` to Celery beat and structured dead-job logging; claim commits before job handling so row locks are not held across future external reads.
- Added final `/v1/approvals` list, approve, and deny endpoints for `FinalApprovalRequirement` rows while preserving old `/v1/runtime-policy/approvals` compatibility routes.
- Added a Stripe-shaped refund loop contract that verifies a real source-of-record observation and catches a false agent success claim with an incident.
- Added a live Stripe test-loop runner that refuses to run without `STRIPE_TEST_SECRET_KEY=sk_test_*` and either an existing refund ID or explicit test-refund creation.
- Removed unused beat schedules for ClickHouse sync, discovery refresh/scan, judge calibration, and provider drift.
- Removed legacy worker task modules for diagnosis, replay, regression CI, drift, and discovery from the final worker aggregator.
- Removed standalone dead directories `clickhouse/`, `zroky-replay-worker/`, and the unmounted MCP ingress surface under `zroky-backend/app/mcp/`.
- Restored applied `0122_mcp_interception` as a tombstone/no-op migration and added `0129_drop_mcp_interception_tables` as the forward table-removal migration.
- Repointed final worker facade modules for verification, recovery, and evidence jobs to the final-domain outbox task.

## Tests And Checks

- Dashboard route inventory confirmed no production dashboard `actions` or `agents` directories remain.
- `npm test -- --run src/lib/dashboard-route-contract.test.ts src/lib/route-auth-guard.test.ts src/components/dashboard-shell.test.tsx src/components/command-palette.test.tsx 'src/app/(dashboard)/home/page.test.tsx' 'src/app/(dashboard)/outcomes/page.test.tsx' 'src/app/(dashboard)/evidence/page.test.tsx'` passed in `zroky-dashboard`.
- `npm run build` passed in `zroky-dashboard`; production build output no longer includes `/actions` or `/agents`.
- `python -m pytest tests/test_pilot.py::TestPolicyServices::test_get_or_create_returns_policy_after_unique_race -q` passed in `zroky-backend`.
- `CI=1 ZROKY_E2E_DATABASE_URL=sqlite:///./.data/e2e_dashboard_p11_001_fresh.db ZROKY_E2E_API_PORT=8012 ZROKY_E2E_DASHBOARD_PORT=3012 npx playwright test e2e/final-flow.spec.ts --project=chromium` passed in `zroky-dashboard`.
- `python -m pytest tests/test_final_backend_route_allowlist.py tests/test_owner_route_gate.py tests/test_final_product_smoke_contract.py -q` passed in `zroky-backend`.
- `npm test -- tests/public_surface.test.ts tests/intent.test.ts tests/guard.test.ts tests/verified_action.test.ts tests/verify.test.ts` passed in `zroky-sdk-js`.
- `npm run build` passed in `zroky-sdk-js`.
- `python -m pytest tests/test_final_sdk_public_surface.py tests/test_final_pre_execution_guard.py tests/test_runner.py -q` passed in `zroky-sdk`.
- `powershell -ExecutionPolicy Bypass -File 'D:\Zroky AI\scripts\verify_zroky_build_plan.ps1'` passed after P11-003.
- Static workflow contract check passed: required final release commands are present and old replay/golden/capture/regression launch jobs are absent.
- `python -m pytest tests/test_final_codebase_shape.py tests/test_final_backend_route_allowlist.py -q` passed in `zroky-backend`.
- `python -m pytest tests/test_final_domain_outbox_worker.py -q` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py::test_final_approval_resolution_requires_role_and_binding_digest tests/test_final_intents_api.py::test_final_approval_deny_blocks_bound_intent -q` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py::test_stripe_refund_test_loop_verifies_real_sor_and_catches_false_success -q` passed in `zroky-backend`.
- `python -m py_compile scripts/run_stripe_test_loop.py` passed; missing-key refusal passed.
- `python -m pytest tests/test_final_backend_route_allowlist.py tests/test_final_codebase_shape.py tests/test_final_domain_outbox_worker.py tests/test_rls_migration_guards.py -q` passed in `zroky-backend`.
- Alembic migration script compile passed and the graph has one head: `0129_drop_mcp_interception_tables`.
- `python -m pytest tests/test_final_sdk_shape.py tests/test_final_sdk_public_surface.py -q` passed in `zroky-sdk`.

## Known Risks

- Backend `/v1/agents` and `/v1/actions/lifecycle-summary` are intentionally not removed under P11-001. Backend production route cleanup is tracked separately under P11-002.
- SDK export cleanup is tracked separately under P11-003.
- Legacy route source files and old route-specific tests still exist in the repository for now, but they are not mounted in the final production router. Deleting the remaining source/test files is safe only after any reusable service code is separately classified.
- SDK internals for capture/trace compatibility still exist for tests and lower-level implementation modules, but they are no longer exported from the production package entrypoints.
- The final release workflow includes an optional deployed smoke job that runs only when production API and dashboard URLs are provided through manual workflow inputs.
- Final outbox worker currently fails closed for server-owned job types until each gets a real idempotent handler; `execute_recovery` is intentionally not server-drained because it belongs to the customer executor claim/complete path.
- Final approval resolution enforces tenant, role, pending-state, and binding digest checks. True human separation-of-duties needs an approver/originator identity column in the final approval schema before it can be enforced beyond role level.
- P11-009 is a Stripe-shaped contract with authoritative observation payloads. It does not call the live Stripe API or store a Stripe key.
- P11-010 has not been run against real Stripe credentials in this workspace because no Stripe test secret was provided.
- Legacy diagnosis/replay route source still exists where not mounted by the final router; full source deletion is separate from Section 7 worker/attack-surface cleanup.
- ClickHouse was unscheduled and its standalone schema directory was removed, but ClickHouse service modules remain where still imported by internal analytics.

## Decision

P11-001 through P11-012 are complete.
