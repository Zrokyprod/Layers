# Zroky Legacy Route Deletion Plan

Status: First pass complete  
Tracker ID: P0-007

This plan does not delete routes. It defines the smallest safe deletion order.

## Current State

The backend router already gates several old surfaces with `FEATURE_LEGACY_*` flags, but the production code still imports and can mount many legacy routes. The final product should remove old route imports and route files after replacement surfaces exist.

Relevant files:

- `zroky-backend/app/api/router.py`
- `zroky-backend/app/core/config.py`

## Delete Batch 1: Already Legacy-Gated Routes

These are safest to remove first because the router already treats them as legacy:

- `ablation.py`
- `analytics.py`
- `ask.py`
- `detectors.py`
- `digest.py`
- `fix_events.py`
- `intel.py`
- `judge_calibration_routes.py`
- `judge_health.py`
- `live.py`
- `provider_drift.py`
- `recommendations.py`
- `reliability.py`
- `diagnoses.py`
- `issues.py`
- `contracts.py`
- `goldens.py`
- `replay.py`
- `replay_dispatch.py`
- `replay_runs.py`
- `regression_ci.py`
- `diagnosis.py`

Also remove related feature flags after route deletion:

- `FEATURE_LEGACY_OBSERVABILITY_API`
- `FEATURE_LEGACY_REPLAY_API`
- `FEATURE_LEGACY_DIAGNOSIS_API`
- `FEATURE_LEGACY_ISSUES_API`
- `FEATURE_LEGACY_DIAGNOSIS_ALIAS`

Keep `FEATURE_LEGACY_OWNER` and `FEATURE_LEGACY_INVITATIONS` until account/admin flows are separately classified.

## Delete Batch 2: Always-On Old Product Routes

These are currently always mounted and need replacement decisions before deletion:

- `capture.py`
- `calls.py`
- `traces.py`
- `alerts.py`
- `pilot.py`
- `feature_interest.py`
- `feature_flags.py`, unless retained as final internal config support.
- `mcp` routes, unless converted from interception gateway to untrusted import capability.

Replacement mapping:

- `capture`, `calls`, `traces` -> final run journal and observation intake.
- `alerts` -> final incidents and notifications.
- `pilot` -> delete after final design-partner validation flow exists.
- `feature_interest` -> delete; not part of final product.
- `mcp interception` -> delete as gateway; keep only MCP import if rebuilt under final connector/tool capability registry.

## Migrate Batch: Final Product Core

These should not be deleted without replacement:

- `action_intents.py` -> trusted intent API and policy decision API.
- `runtime_policy.py` -> final `/v1/policy/check`.
- `actions.py` -> final operations/runs surfaces.
- `outcomes.py` and `outcome_saved_reconciliation.py` -> outcome graph verification.
- `evidence.py` -> signed evidence bundles.
- `integrations.py`, `system_of_record_integrations.py`, `_sor_*` -> connector manifests and authoritative source bindings.
- `agents.py` -> agent registry/A2A capability mapping only.
- `tool_registry.py` -> connector/tool capability registry only.
- `notifications.py` -> incident/approval notifications.
- `export.py` -> evidence export only.

## Tests To Remove With Legacy Routes

Delete or archive tests that only protect deleted product surfaces:

- diagnosis tests;
- replay tests;
- goldens tests;
- judge tests;
- provider drift tests;
- old feature-interest tests;
- old capture/calls/traces tests after final run journal tests replace them.

Do not delete tests that cover reusable final invariants such as tenant isolation, idempotency, signing, approval binding, or outcome reconciliation semantics.

## Required Verification After Each Batch

Run at minimum:

```powershell
powershell -ExecutionPolicy Bypass -File "D:\Zroky AI\scripts\verify_zroky_build_plan.ps1"
```

Then run focused backend tests for the still-mounted final surfaces:

```text
health
auth
runtime policy
action intents
outcomes
evidence
integrations
tenant isolation
```

## Stop Conditions

Stop deletion and reclassify if:

- a final dashboard page still calls a deleted endpoint;
- an SDK final public method still depends on a deleted route;
- billing/account/admin flows depend on removed route data;
- API contract check still expects deleted routes;
- production config validator depends on old replay/capture settings.

