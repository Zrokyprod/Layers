# Zroky GitHub CI Cleanup Plan

Status: First pass complete  
Tracker IDs: P0-010, P0-011, P0-012

This plan does not delete workflows. It defines final required checks and the smallest safe CI cleanup order.

## P0-010: Remove Or Disable Legacy CI Jobs

Keep and retarget:

- `.github/workflows/ci.yml`: keep as the small default PR gate, but replace broad old-suite pytest with final focused suites after final routes are introduced.
- `.github/workflows/zroky-backend-ci.yml`: keep as backend quality gate, retarget to final API/domain/security tests.
- `.github/workflows/api-contract-check.yml`: keep, but change from frozen old v1 surface to final API allowlist once final routes exist.
- `.github/workflows/zroky-branch-protection-audit.yml`: keep if GitHub branch protection is actively used.
- `.github/workflows/zroky-staging-rollout-verify.yml`: keep only if it becomes final product deployment smoke.
- `.github/workflows/zroky-sdk-publish.yml`: keep only after Python SDK public exports are cleaned.
- `.github/workflows/zroky-sdk-js-publish.yml`: keep only after JS SDK public exports are cleaned.

Remove or rewrite:

- `.github/workflows/capture-e2e-local.yml`: old capture product surface.
- `.github/workflows/schema-drift-check.yml`: old observability schema drift path.
- `.github/workflows/paid-launch-readiness.yml`: rewrite from scratch; current file includes capture, replay, goldens, replay worker, regression CI action, and old launch criteria.
- `.github/workflows/zroky-design-partner-owner-proof.yml`: rewrite around final outcome assurance evidence, not old pilot/call proof.
- `.github/workflows/pricing-config-weekly-pr.yml`: defer unless pricing config is active launch scope.
- `.github/workflows/chaos-weekly.yml`: defer until final relay/recovery architecture exists.

Also remove old CI scripts when no final workflow calls them:

- `scripts/run_capture_e2e_local.py`
- `scripts/run_capture_smoke_no_docker.py`
- old replay/golden-heavy paid readiness scripts
- old money-path scripts that create replay/golden/diagnosis artifacts, unless rewritten as final outcome assurance fixtures.

## P0-011: Final Required Checks List

Required PR checks for final product:

- build plan verifier;
- backend lint/typecheck;
- backend final API tests;
- backend tenant isolation/security tests;
- policy/idempotency tests;
- outcome verification tests;
- recovery planner/executor protocol tests once recovery exists;
- evidence signing/verifier tests;
- dashboard typecheck;
- dashboard unit tests for final pages;
- dashboard browser E2E for final operator flow once dashboard exists;
- Python SDK tests for final public API;
- JavaScript SDK tests for final public API;
- API allowlist check;
- production config validator;
- deployment smoke check before release.

Do not require checks for deleted surfaces:

- replay worker;
- goldens;
- judge calibration;
- provider drift;
- old capture health;
- regression CI action;
- diagnosis engine;
- feature-interest polling.

## P0-012: Branch Protection And Release Gate Spec

Branch protection should require only stable final-product checks.

Recommended required checks before Phase 1:

- build plan verifier;
- current backend lint/tests that still pass;
- dashboard typecheck/build once existing blocker is fixed;
- API contract check adjusted to current feature flags.

Recommended required checks before live launch:

- build plan verifier;
- backend final API/domain/security tests;
- dashboard final E2E;
- SDK public API tests;
- API allowlist check;
- production config validator;
- deployment smoke;
- evidence verifier test;
- tenant isolation negative tests.

Release workflow rules:

- release workflow must run from a clean commit;
- release workflow must not publish old diagnosis/replay/observability products;
- release workflow must run final product smoke before deployment;
- rollback command/path must be documented in the launch report.

## Stop Conditions

Stop CI deletion and reclassify if:

- current branch protection requires a check before its replacement exists;
- package publishing still needs old export compatibility for an active customer;
- a final dashboard/API smoke check still depends on old capture/replay routes;
- API contract allowlist cannot yet distinguish final and legacy routes.

