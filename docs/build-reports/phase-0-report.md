# Zroky Phase 0 Build Report

Status: In progress  
Phase: Stabilize Current Repo  
Tracker IDs: P0-001 to P0-012

## Scope

Phase 0 prepares the repo for the final Zroky product build. It does not add new product features.

## Required Outcomes

- Route inventory and final API allowlist.
- Dashboard page inventory.
- Old dashboard removal plan.
- SDK module inventory.
- GitHub workflow and release-surface inventory.
- Legacy CI removal/disable plan.
- Final required checks and branch/release gate spec.
- Local/generated artifacts removed.
- Current test/build blockers fixed.
- Tenant isolation/RLS gaps fixed.
- Legacy route deletion plan completed.

## Completed IDs

- P0-001 Route inventory and final API allowlist.
- P0-002 Dashboard page inventory.
- P0-003 SDK module inventory.
- P0-004 Local/generated artifacts removed.
- P0-005 Current test/build blockers verified with focused passing checks.
- P0-006 Tenant isolation/RLS gaps implemented with focused passing checks.
- P0-007 Legacy route deletion plan.
- P0-008 Old dashboard removal plan.
- P0-009 GitHub workflow inventory.
- P0-010 Remove or disable legacy CI jobs.
- P0-011 Final required checks list.
- P0-012 Branch protection and release gate spec.

## Deleted Code

- `.deploy`
- `home-current-production-full.png`
- `home-current-production.png`
- `home-selected.patch`
- `zroky-landing/.codex-hero-current.png`
- `zroky-dashboard-home-pr`
- `zroky-landing-mobile-fix`
- `zroky-railway-prod`

## Migrated Code

- `zroky-backend/alembic/versions/0023_add_fix_embeddings.py` now uses `app.current_tenant_id`, forces RLS, and applies write-scoped `WITH CHECK`.
- `zroky-backend/alembic/versions/0122_mcp_interception.py` now applies forced project RLS to MCP tool bindings and interception events.

## Route Deletion Plan

See `docs/build-reports/legacy-route-deletion-plan.md`.

## GitHub CI Cleanup Plan

See `docs/build-reports/github-ci-cleanup-plan.md`.

## Tests And Checks

- `scripts/verify_zroky_build_plan.ps1` passed after inventory tracker updates.
- `python scripts/check_file_sizes.py` passed.
- `python scripts/check_api_v1_frozen.py` passed after regenerating the frozen spec to match the currently mounted API.
- `npm test -- --run 'src/app/(dashboard)/home/page.test.tsx'` passed in `zroky-dashboard`.
- `npm test -- --run src/components/status-pill.test.tsx` passed in `zroky-admin`.
- `python scripts/check_file_sizes.py` passed again after final product cleanup.
- `python scripts/check_api_v1_frozen.py` passed again after final product cleanup.
- `npm test -- --run "src/app/(dashboard)/home/page.test.tsx"` passed again in `zroky-dashboard`.
- `npm test -- --run src/components/status-pill.test.tsx` passed again in `zroky-admin`.
- `python -m pytest tests/test_rls_migration_guards.py -q` passed in `zroky-backend`.
- `python -m pytest tests/test_tenant_project_route_scoping.py tests/test_tenant_session_project_selection.py -q` passed in `zroky-backend`.
- `python -m pytest tests/test_postgres_rls.py -q` skipped locally because real Postgres RLS integration is not available in this run.
- `rg -n "current_setting\('app\.current_tenant'\)" zroky-backend/alembic/versions zroky-backend/app` returned no matches.

## Known Risks

- Current worktree already contains unrelated modified and untracked files.
- Legacy diagnosis/replay/observability surfaces are still present.
- P0-006 is Implemented, not Verified, because the real Postgres RLS integration test was skipped locally.

## Decision

P0-005 is verified. P0-006 remains Implemented until real Postgres RLS verification is available.
