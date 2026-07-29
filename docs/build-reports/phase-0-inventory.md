# Zroky Phase 0 Inventory

Status: First pass complete  
Tracker IDs covered: P0-001, P0-002, P0-003, P0-008, P0-009

This inventory does not delete code. It classifies the current repo surface so deletion and migration can happen in small verified batches.

## P0-001: Backend Route Inventory

Current router: `zroky-backend/app/api/router.py`

Final product keep or migrate:

- `health.py`: keep.
- `auth.py`: keep.
- `security.py`: keep.
- `internal.py`: keep only required production/admin health pieces.
- `projects.py`: keep or migrate to tenancy/workspaces.
- `settings.py`: keep or migrate.
- `billing.py`: keep if paid launch remains in scope.
- `action_intents.py`: migrate to trusted intents and policy decisions.
- `runtime_policy.py`: migrate to final `/v1/policy/check`.
- `actions.py`: migrate to Operations/Runs view or delete after final run model exists.
- `evidence.py`: migrate to signed evidence bundles.
- `outcomes.py`: migrate to outcome graph verification.
- `outcome_saved_reconciliation.py`: migrate useful connector verification logic; split or delete old route surface.
- `outcome_reconciliation_helpers.py`: migrate reusable comparison helpers.
- `integrations.py`: migrate only connector/system setup needed by final product.
- `system_of_record_integrations.py` and `_sor_*`: migrate to connector manifests and authoritative source bindings.
- `tool_registry.py`: migrate only if it supports connector/tool capability registry.
- `agents.py`: migrate only agent registry/A2A-compatible parts.
- `realtime_ws.py`: keep only if final dashboard needs live updates.
- `export.py`: migrate to evidence export.
- `providers.py`: migrate only if still needed for final connector credentials/secrets path.
- `notifications.py`: keep only final incident/approval notifications.
- `github_webhooks.py`: keep only if final GitHub workflow/release integration is needed.

Delete or archive from production API:

- `ablation.py`
- `analytics.py`
- `ask.py`
- `contracts.py`
- `detectors.py`
- `diagnoses.py`
- `diagnosis.py`
- `digest.py`
- `feature_interest.py`
- `fix_events.py`
- `goldens.py`
- `intel.py`
- `issues.py`
- `judge_calibration_routes.py`
- `judge_health.py`
- `live.py`
- `pilot.py`
- `provider_drift.py`
- `recommendations.py`
- `regression_ci.py`
- `reliability.py`
- `replay.py`
- `replay_dispatch.py`
- `replay_runs.py`
- `owner.py`
- `invitations.py`, unless still required by final account/team flows.

Router note:

- Legacy route flags exist, but final launch should remove old route imports and mounts instead of keeping a permanent feature-flag graveyard.
- Current always-on routes still include `capture`, `calls`, `traces`, `alerts`, `feature_interest`, `feature_flags`, `pilot`, and `mcp`; these need migration or removal decisions before live cutover.

## P0-002: Dashboard Page Inventory

Current dashboard roots:

- `account`
- `actions`
- `agents`
- `approvals`
- `evidence`
- `home`
- `integrations`
- `outcomes`
- `policies`
- `projects`
- `settings`

Final dashboard target:

- `home`
- `operations/runs`
- `operations/incidents`
- `operations/approvals`
- `workflows`
- `systems`
- `evidence`
- `settings`

Migrate:

- `home`: rebuild as final operations home.
- `actions`: migrate useful action policy views into `operations/runs`.
- `approvals`: migrate to `operations/approvals`.
- `evidence`: rebuild around signed evidence bundles.
- `integrations`: migrate to `systems` or `workflows` connector setup.
- `outcomes`: migrate into run detail/outcome graph views.
- `policies`: migrate into workflow policy/approval configuration.
- `settings`: keep and simplify.
- `account`: keep only if billing/account remains in final launch.
- `projects`: migrate to workspace/environment settings if needed.
- `agents`: migrate only registry/A2A capability setup; remove fleet/health framing if it drifts into control-tower positioning.

Delete from production dashboard:

- old navigation shell;
- old diagnosis/replay/issue language;
- demo-only proof panels that are not wired to final APIs;
- primary dashboard mocks and fixtures;
- old page compatibility tests after replacement E2E exists.

## P0-003: SDK Module Inventory

Python SDK current modules:

- Keep or migrate: `_protect.py`, `_runtime_policy.py`, `_verified_action.py`, `_verify.py`, `_runner.py`, `_outcome.py`, `_errors.py`, `preflight.py`, `cli.py`.
- Migrate carefully: `_capture.py`, `_telemetry.py`, `_call.py`, `_async.py`, `_streaming.py`, `_async_streaming.py`.
- Remove or isolate from final public API: prompt fingerprinting, model fallback, response cache, loop guard, budget/cost helpers, generic diagnosis-era capture exports.

Python public export issue:

- `zroky/__init__.py` still says "Production AI diagnosis engine - capture, diagnose, fix." This must be replaced before launch.

JavaScript SDK current modules:

- Keep or migrate: `protect.ts`, `guard.ts`, `verify.ts`, `verified-action.ts`, `outcome.ts`, `api.ts`, `config.ts`, `types.ts`.
- Migrate carefully: `trace.ts`, `spans.ts`, `emitter.ts`, `pii.ts`.
- Remove or isolate from final public API: `fingerprint.ts`, generic capture span exports, old trace-first product exports that are not needed for final intake.

JavaScript public export issue:

- `src/index.ts` still exports `promptFingerprint`, `captureHandoff`, `captureMemory`, `captureRetrieval`, and `captureToolCall`. These are old observability/capture-era exports unless explicitly mapped to final universal intake.

## P0-008: Old Dashboard Removal Plan

Minimal removal sequence:

1. Build new final dashboard shell and navigation under the final IA.
2. Wire `home`, `operations/runs`, `operations/incidents`, `operations/approvals`, `workflows`, `systems`, `evidence`, and `settings` to final APIs or explicit disabled states.
3. Add browser E2E tests for the complete operator flow.
4. Remove old top-level routes that do not map to final IA.
5. Remove old shared types, fixtures, and tests only after their final replacements pass.

Do not delete dashboard utilities blindly. Reuse only clean low-level helpers that do not carry old product language.

## P0-009: GitHub Workflow Inventory

Current GitHub workflows:

- `api-contract-check.yml`: keep or migrate to final API allowlist check.
- `ci.yml`: keep as top-level smoke only after removing old product gates.
- `zroky-backend-ci.yml`: keep and retarget to final backend tests.
- `zroky-branch-protection-audit.yml`: keep if branch protection remains used.
- `zroky-sdk-js-publish.yml`: keep only after final JS SDK public API is cleaned.
- `zroky-sdk-publish.yml`: keep only after final Python SDK public API is cleaned.
- `zroky-staging-rollout-verify.yml`: keep if retargeted to final product smoke.

Remove or rewrite:

- `capture-e2e-local.yml`: old capture product surface.
- `chaos-weekly.yml`: defer until final recovery/relay architecture exists.
- `paid-launch-readiness.yml`: currently includes replay, goldens, capture, replay worker, and old launch gates; rewrite instead of preserving.
- `pricing-config-weekly-pr.yml`: defer unless pricing config is in active launch scope.
- `schema-drift-check.yml`: old observability schema drift path.
- `zroky-design-partner-owner-proof.yml`: rewrite for final outcome assurance evidence, not old pilot proof.

GitHub gate rule:

- Required checks should be final-product checks only: backend, dashboard, SDKs, API allowlist, tracker verifier, tenant/security, production config, and deployment smoke.

