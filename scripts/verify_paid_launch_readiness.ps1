$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$TmpDir = Join-Path $RootDir ".tmp\paid-launch-pytest"
New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null
$env:TMP = (Resolve-Path $TmpDir).Path
$env:TEMP = $env:TMP

function Invoke-ReadinessStep {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$WorkingDirectory,
    [Parameter(Mandatory = $true)][string]$Command,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
  )

  Write-Host ""
  Write-Host "==> $Name" -ForegroundColor Cyan
  Push-Location $WorkingDirectory
  try {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
      throw "$Name failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

function Clear-NextBuildArtifacts {
  param(
    [Parameter(Mandatory = $true)][string]$ProjectDirectory
  )

  $ResolvedProjectDirectory = (Resolve-Path -LiteralPath $ProjectDirectory).Path
  $NextDirectory = Join-Path $ResolvedProjectDirectory ".next"
  if (-not (Test-Path -LiteralPath $NextDirectory)) {
    return
  }

  $ResolvedNextDirectory = (Resolve-Path -LiteralPath $NextDirectory).Path
  $ProjectPrefix = $ResolvedProjectDirectory.TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
  ) + [System.IO.Path]::DirectorySeparatorChar

  if (-not $ResolvedNextDirectory.StartsWith($ProjectPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove Next build artifacts outside project directory: $ResolvedNextDirectory"
  }

  Remove-Item -LiteralPath $ResolvedNextDirectory -Recurse -Force
}

function Invoke-BackendPytestStep {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string[]]$TestPaths
  )

  Invoke-ReadinessStep `
    -Name "Backend $Name" `
    -WorkingDirectory (Join-Path $RootDir "zroky-backend") `
    -Command "python" `
    -Arguments (@("-m", "pytest", "-q", "--tb=short") + $TestPaths)
}

Invoke-BackendPytestStep -Name "tenant session selection" -TestPaths @("tests/test_tenant_session_project_selection.py")
Invoke-BackendPytestStep -Name "tenant path scoping" -TestPaths @("tests/test_tenant_project_route_scoping.py")
Invoke-BackendPytestStep -Name "durable ingest and trace graph" -TestPaths @(
  "tests/test_ingest.py::test_rich_ingest_event_creates_masked_trace_graph",
  "tests/test_ingest.py::test_duplicate_event_id_does_not_duplicate_trace_span_or_cost",
  "tests/test_ingest.py::test_ingest_idempotency_event_id_prevents_duplicate_cost_and_call"
)
Invoke-BackendPytestStep -Name "capture health" -TestPaths @(
  "tests/test_capture_health.py::test_capture_health_summarizes_sdk_gateway_and_span_sources",
  "tests/test_capture_health.py::test_gateway_heartbeat_uses_api_key_and_creates_capture_alerts",
  "tests/test_capture_health.py::test_gateway_stream_to_db_to_capture_health_e2e"
)
Invoke-BackendPytestStep -Name "failure intelligence" -TestPaths @("tests/test_failure_intelligence.py")
Invoke-BackendPytestStep -Name "replay run API contract" -TestPaths @(
  "tests/test_replay_runs.py::TestDispatchReplayRun::test_dispatch_creates_pending_run",
  "tests/test_replay_runs.py::TestDispatchReplayRun::test_cross_tenant_golden_set_returns_none",
  "tests/test_replay_runs.py::TestDispatchReplayRun::test_stamps_requested_mode_with_executor_compatibility",
  "tests/test_replay_runs.py::TestDispatchReplayRun::test_create_replay_from_call_creates_one_click_run",
  "tests/test_replay_runs.py::TestMarkCallAsGolden::test_active_without_expected_behavior_rejected",
  "tests/test_replay_runs.py::TestReplayModeInResponse::test_backfills_warning_for_legacy_stub_rows",
  "tests/test_replay_runs.py::TestCreateReplayFromIssueRoute::test_creates_one_click_replay_from_issue",
  "tests/test_replay_runs.py::TestInvariants::test_valid_run_statuses_match_db_check"
)
Invoke-BackendPytestStep -Name "replay executor trust" -TestPaths @(
  "tests/test_replay_executor.py::TestExecuteReplayRun::test_real_replay_from_issue_marks_verified_fix",
  "tests/test_replay_executor.py::TestExecuteReplayRun::test_only_inconclusive_finalizes_not_verified",
  "tests/test_replay_executor.py::TestLiveLlmResolver::test_mocked_tool_requires_captured_tool_snapshot",
  "tests/test_replay_executor.py::TestLiveLlmResolver::test_live_sandbox_fails_closed_without_runtime",
  "tests/test_replay_executor.py::TestLiveLlmResolver::test_budget_exceeded_returns_error",
  "tests/test_replay_executor.py::TestLiveLlmResolver::test_provider_error_returns_error"
)
Invoke-BackendPytestStep -Name "replay worker claiming" -TestPaths @("tests/test_replay_worker_claiming.py")
Invoke-BackendPytestStep -Name "behavioral Goldens" -TestPaths @(
  "tests/test_goldens.py::TestAddTrace::test_add_trace_active_without_expected_behavior_rejected",
  "tests/test_goldens.py::TestAddTrace::test_add_trace_with_source_evidence_defaults_to_draft",
  "tests/test_goldens.py::TestPatchRoute::test_patch_flaky_and_blocking_flags_persist",
  "tests/test_goldens.py::TestTraceRoutes::test_add_trace_201",
  "tests/test_goldens.py::TestTraceRoutes::test_add_trace_active_without_expected_behavior_422",
  "tests/test_goldens.py::TestInvariants::test_valid_golden_trace_statuses_match_db_check",
  "tests/test_goldens.py::TestInvariants::test_legacy_rows_without_expected_behavior_are_draft"
)
Invoke-BackendPytestStep -Name "regression CI routes" -TestPaths @("tests/test_regression_ci_routes.py")
Invoke-BackendPytestStep -Name "regression CI orchestrator" -TestPaths @("tests/test_regression_ci_orchestrator.py")
Invoke-BackendPytestStep -Name "runtime policy gate" -TestPaths @("tests/test_runtime_policy_gate.py")
Invoke-BackendPytestStep -Name "billing and quota" -TestPaths @(
  "tests/test_billing_v2.py::TestBillingPlans::test_all_plans_have_same_keys",
  "tests/test_billing_v2.py::TestRazorpayCheckoutRoute::test_create_order_computes_plan_amount_and_tracks_pending_request",
  "tests/test_billing_v2.py::TestRazorpayCheckoutRoute::test_verify_payment_activates_plan_after_valid_signature",
  "tests/test_billing_v2.py::TestBillingQuota::test_strict_quota_check_failure_denies_and_alerts",
  "tests/test_billing_v2.py::TestBillingQuota::test_event_counter_increment_is_portable_and_accumulates_once",
  "tests/test_billing_v2.py::TestBillingQuota::test_hosted_usage_endpoint_returns_calls_replay_goldens_and_metering",
  "tests/test_billing_v2.py::TestWebhookRoute::test_happy_path_payment_succeeded",
  "tests/test_billing_v2.py::TestWebhookRoute::test_idempotent_replay",
  "tests/test_billing_v2.py::TestPortalRoute::test_happy_path_without_customer",
  "tests/test_billing_v2.py::TestInvariants::test_plan_codes_match_tier_matrix"
)
Invoke-BackendPytestStep -Name "owner launch health" -TestPaths @("tests/test_owner_money_path_health.py")
Invoke-BackendPytestStep -Name "production config" -TestPaths @(
  "tests/test_production_config.py",
  "tests/test_launch_env_validator.py"
)

Invoke-ReadinessStep `
  -Name "Release-candidate money-path evidence" `
  -WorkingDirectory $RootDir `
  -Command "python" `
  -Arguments @("scripts/run_money_path_demo.py", "--json")

Invoke-ReadinessStep `
  -Name "Dashboard reliability surfaces" `
  -WorkingDirectory (Join-Path $RootDir "zroky-dashboard") `
  -Command "npm" `
  -Arguments @(
    "test", "--",
    "src/components/dashboard-shell.test.tsx",
    "src/components/command-palette.test.tsx",
    "src/lib/route-auth-guard.test.ts",
    "src/lib/replay-mode.test.ts",
    "src/app/(dashboard)/settings/billing/page.test.tsx",
    "src/app/(dashboard)/goldens/page.test.tsx",
    "src/app/(dashboard)/ci-gates/page.test.tsx",
    "src/app/(dashboard)/ci-gates/[runId]/page.test.tsx"
  )

$PreviousDashboardApiUrl = $env:NEXT_PUBLIC_API_URL
try {
  $env:NEXT_PUBLIC_API_URL = "https://api.zroky.ai"
  Clear-NextBuildArtifacts -ProjectDirectory (Join-Path $RootDir "zroky-dashboard")
  Invoke-ReadinessStep `
    -Name "Dashboard production build" `
    -WorkingDirectory (Join-Path $RootDir "zroky-dashboard") `
    -Command "npm" `
    -Arguments @("run", "build")
} finally {
  if ($null -eq $PreviousDashboardApiUrl) {
    Remove-Item Env:\NEXT_PUBLIC_API_URL -ErrorAction SilentlyContinue
  } else {
    $env:NEXT_PUBLIC_API_URL = $PreviousDashboardApiUrl
  }
}

Invoke-ReadinessStep `
  -Name "Owner/admin launch and money path surfaces" `
  -WorkingDirectory (Join-Path $RootDir "zroky-admin") `
  -Command "npm" `
  -Arguments @(
    "test", "--",
    "src/app/owner/layout.test.tsx",
    "src/app/owner/launch-readiness/page.test.tsx",
    "src/app/owner/page.test.tsx",
    "src/app/owner/money-path/page.test.tsx",
    "src/app/owner/pricing/page.test.tsx",
    "src/app/owner/infrastructure/page.test.tsx",
    "src/app/owner/support/page.test.tsx"
  )

$PreviousOwnerApiUrl = $env:NEXT_PUBLIC_OWNER_API_URL
try {
  $env:NEXT_PUBLIC_OWNER_API_URL = "https://api.zroky.ai"
  Clear-NextBuildArtifacts -ProjectDirectory (Join-Path $RootDir "zroky-admin")
  Invoke-ReadinessStep `
    -Name "Owner/admin production build" `
    -WorkingDirectory (Join-Path $RootDir "zroky-admin") `
    -Command "npm" `
    -Arguments @("run", "build")
} finally {
  if ($null -eq $PreviousOwnerApiUrl) {
    Remove-Item Env:\NEXT_PUBLIC_OWNER_API_URL -ErrorAction SilentlyContinue
  } else {
    $env:NEXT_PUBLIC_OWNER_API_URL = $PreviousOwnerApiUrl
  }
}

Invoke-ReadinessStep `
  -Name "Gateway durable capture" `
  -WorkingDirectory (Join-Path $RootDir "zroky-gateway") `
  -Command "go" `
  -Arguments @("test", "./...")

Invoke-ReadinessStep `
  -Name "Replay worker trust" `
  -WorkingDirectory (Join-Path $RootDir "zroky-replay-worker") `
  -Command "python" `
  -Arguments @("-m", "pytest")

Invoke-ReadinessStep `
  -Name "Python SDK capture" `
  -WorkingDirectory (Join-Path $RootDir "zroky-sdk") `
  -Command "python" `
  -Arguments @("-m", "pytest")

Invoke-ReadinessStep `
  -Name "JavaScript SDK capture" `
  -WorkingDirectory (Join-Path $RootDir "zroky-sdk-js") `
  -Command "npm" `
  -Arguments @("test")

Invoke-ReadinessStep `
  -Name "Regression CI action" `
  -WorkingDirectory (Join-Path $RootDir "zroky-regression-ci-action") `
  -Command "npm" `
  -Arguments @("test")

Invoke-ReadinessStep `
  -Name "Docs drift check" `
  -WorkingDirectory $RootDir `
  -Command "python" `
  -Arguments @("scripts/check_docs_drift.py")

$TrackedMarkdown = git -C $RootDir ls-files "*.md" | Where-Object {
  $_ -ne "README.md" -and (Test-Path -LiteralPath (Join-Path $RootDir $_))
}
if ($TrackedMarkdown) {
  Write-Host ""
  Write-Host "::error::Root README.md must be the only tracked product-planning Markdown file." -ForegroundColor Red
  $TrackedMarkdown | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
  exit 1
}

Write-Host ""
Write-Host "Paid launch readiness verification passed." -ForegroundColor Green
