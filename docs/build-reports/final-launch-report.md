# Zroky Final Launch Report

Date: 2026-07-22
Status: Release-candidate ready with final production release workflow
Tracker scope: P0-001 through P11-012

## Launch Decision

Zroky is ready for release-candidate packaging from the current local build evidence.

The GitHub production release workflow has been rewritten to run only final product gates. Final production deployment approval still requires that workflow to pass on GitHub against a clean commit, plus deployed smoke URLs when available.

## Final Product Surface

The final product is an autonomous-agent control and assurance platform with these production surfaces:

- Pre-execution intent intake and policy decisioning.
- Approval requirements before risky execution.
- Customer-side execution attempts with evidence references.
- Runs, incidents, recovery, events, observations, and outcome graphs.
- Assurance packs for workflow definitions and proof contracts.
- System-of-record integrations and reconciliation.
- Dashboard IA for Home, Operations, Workflows, Systems, Evidence, and Settings.
- Public SDK entrypoints for guard, pre-execution guard, protected action, verified action, outcome verification, and runner integration.

## Evidence Summary

### Product Workflow Evidence

- Observe-only workflow E2E passed.
- Approval-controlled recovery E2E passed.
- New workflow publication without core backend code change passed.
- Non-verified outcome creates incident instead of false success.
- Recovery dispatch uses approval, separation-of-duties, fresh evidence, and audit log checks.
- Final approval requirements are actionable through digest-bound approve/deny endpoints.
- Stripe-shaped refund test loop proves both verified refund evidence and false-success incident creation.
- Live Stripe test-loop runner is available and fails closed unless a Stripe test secret is explicitly provided.
- Section 7 cleanup removed unused beat jobs, legacy worker task modules, MCP ingress, and standalone dead directories from the production cutover branch.
- Applied Alembic revision `0122_mcp_interception` remains traversable for existing prod databases; MCP table removal is now a forward migration.

### Dashboard Evidence

- Final dashboard browser E2E passed for policy, verification, incident, recovery, and evidence surfaces.
- Old `/actions` and `/agents` dashboard route trees were removed from the production dashboard.
- Production dashboard build passed after old dashboard route removal.
- Final dashboard smoke validates login, proxy health, secure session cookie setup, and production server boot.

### Backend Evidence

- Final deployment smoke validates backend live/ready health and protected final API route guards.
- Old diagnosis, replay, observability, issues, judge, drift, digest, and golden-set route families are not mounted in the final backend router.
- Required auth, billing, projects, policy, action, run, incident, outcome, evidence, assurance-pack, and system-of-record surfaces remain mounted.
- Policy first-read seed race was fixed and covered with regression coverage.
- Final-domain outbox worker is beat-scheduled, claims server-owned verification, recovery-planning, and evidence jobs, releases row locks before handling, logs dead jobs, and fails closed until real handlers exist; recovery execution remains on the customer executor claim/complete path.
- Final `/v1/approvals` endpoints resolve `FinalApprovalRequirement` rows with tenant, role, pending-state, and binding-digest checks.
- Stripe refund contract uses final APIs end to end: Assurance Pack, intent, policy, approval, run, Stripe source-of-record observation, outcome graph, incident, and signed evidence.
- Live runner can execute the same flow against Stripe test API with an existing test refund or explicit test-refund creation.
- Final worker beat schedule no longer includes ClickHouse sync, discovery refresh/scan, judge calibration, or provider drift jobs.
- Migration graph has one head at `0129_drop_mcp_interception_tables`.

### SDK Evidence

- JS public package entrypoint no longer exports old capture/prompt-fingerprint helpers.
- Python public package entrypoint no longer exports old capture/prompt-fingerprint helpers.
- Final SDK entrypoints remain public: guard, pre-execution guard, protect, verified action, await proof, verify outcome, outcome, and runner integration.
- JS SDK tests and build passed.
- Python SDK public-surface and final guard tests passed.

### Tracker Evidence

- `scripts/verify_zroky_build_plan.ps1` passed after P11-003.
- Final production release workflow was rewritten to final gates only.
- Final codebase shape boundaries were added for API v1, worker jobs, infrastructure, and Python SDK.
- FinalDomainOutboxJob worker fail-closed drain was added and covered by focused regression tests.

## Verified Commands

- `python -m pytest tests/test_final_intents_api.py::test_observe_only_workflow_runs_end_to_end_with_signed_evidence -q`
- `python -m pytest tests/test_final_intents_api.py::test_incident_recovery_execution_queues_customer_executor -q`
- `python -m pytest tests/test_final_intents_api.py::test_new_workflow_shape_publishes_without_backend_code_change -q`
- `npx playwright test e2e/final-flow.spec.ts --project=chromium`
- `npx playwright test e2e/final-product-smoke.spec.ts --project=chromium`
- `python -m pytest tests/test_final_backend_route_allowlist.py tests/test_owner_route_gate.py tests/test_final_product_smoke_contract.py -q`
- `npm test -- tests/public_surface.test.ts tests/intent.test.ts tests/guard.test.ts tests/verified_action.test.ts tests/verify.test.ts`
- `npm run build` in `zroky-sdk-js`
- `python -m pytest tests/test_final_sdk_public_surface.py tests/test_final_pre_execution_guard.py tests/test_runner.py -q`
- `python -m pytest tests/test_final_codebase_shape.py tests/test_final_backend_route_allowlist.py -q`
- `python -m pytest tests/test_final_domain_outbox_worker.py -q`
- `python -m pytest tests/test_final_intents_api.py::test_final_approval_resolution_requires_role_and_binding_digest tests/test_final_intents_api.py::test_final_approval_deny_blocks_bound_intent -q`
- `python -m pytest tests/test_final_intents_api.py::test_stripe_refund_test_loop_verifies_real_sor_and_catches_false_success -q`
- `python -m py_compile scripts/run_stripe_test_loop.py`
- `python -m pytest tests/test_final_backend_route_allowlist.py tests/test_final_codebase_shape.py tests/test_final_domain_outbox_worker.py tests/test_rls_migration_guards.py -q`
- Alembic script compile and one-head migration graph check for `0129_drop_mcp_interception_tables`
- `python -m pytest tests/test_final_sdk_shape.py tests/test_final_sdk_public_surface.py -q`
- `powershell -ExecutionPolicy Bypass -File 'D:\Zroky AI\scripts\verify_zroky_build_plan.ps1'`
- static workflow contract check for `.github/workflows/paid-launch-readiness.yml`

## Rollback Path

If the release candidate fails during deployment or production smoke:

1. Stop deployment before traffic cutover if health, readiness, auth, policy, or dashboard boot fails.
2. Keep the previous production image/site version serving traffic.
3. Re-run the final smoke script against the failed candidate and save logs.
4. If backend route allowlist fails, revert only the release candidate image and keep the old production router untouched.
5. If dashboard boot or session smoke fails, roll back only the dashboard deployment.
6. If SDK package smoke fails, do not publish package artifacts; keep the previous SDK version active.
7. Re-open the failed tracker row as `Blocked` or `Implemented` with exact failing evidence before attempting another release.

## Known Risks

- The GitHub release workflow must still pass in GitHub against a clean commit before production deployment is considered complete.
- Legacy backend route source files and old route-specific tests still exist in the repository, but they are not mounted in the final production router.
- SDK internals for capture/trace compatibility still exist for implementation and tests, but old helpers are removed from public package entrypoints.
- Local validation does not replace a real hosted production smoke against deployed URLs and production secrets.
- Full historical test suites still include old product-era tests; final release gates should run final-product suites only.
- Final outbox server-owned job handlers are intentionally not fake-success handlers; adding real idempotent handlers is the next safe migration step.
- Human separation-of-duties for final approvals is role-gated today; strict approver/originator inequality requires a schema field before enforcement can be made exact.
- Stripe loop evidence is still contract-level; a live Stripe test API run with customer-local secret reference remains the next external proof.
- No Stripe test secret was present in this workspace, so P11-010 verified runner safety but not a real Stripe network run.
- Legacy diagnosis/replay route source still exists where not mounted by the final router; P11-011 removed production scheduling and standalone dead surfaces, not every historical source file.
- ClickHouse service modules still exist where internal analytics imports them; P11-011 removed scheduling and standalone schema directory only.

## Required Next Step

Run the final GitHub production release workflow on a clean commit and provide deployed production smoke URLs when available.
