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

function Invoke-BackendPytestStep {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string[]]$TestPaths
  )

  Invoke-ReadinessStep `
    -Name "Backend $Name" `
    -WorkingDirectory (Join-Path $RootDir "zroky-backend") `
    -Command "python" `
    -Arguments (@("-m", "pytest") + $TestPaths)
}

Invoke-BackendPytestStep -Name "tenant session selection" -TestPaths @("tests/test_tenant_session_project_selection.py")
Invoke-BackendPytestStep -Name "tenant path scoping" -TestPaths @("tests/test_tenant_project_route_scoping.py")
Invoke-BackendPytestStep -Name "durable ingest and trace graph" -TestPaths @("tests/test_ingest.py")
Invoke-BackendPytestStep -Name "capture health" -TestPaths @("tests/test_capture_health.py")
Invoke-BackendPytestStep -Name "failure intelligence" -TestPaths @("tests/test_failure_intelligence.py")
Invoke-BackendPytestStep -Name "replay run API contract" -TestPaths @("tests/test_replay_runs.py")
Invoke-BackendPytestStep -Name "replay executor trust" -TestPaths @("tests/test_replay_executor.py")
Invoke-BackendPytestStep -Name "replay worker claiming" -TestPaths @("tests/test_replay_worker_claiming.py")
Invoke-BackendPytestStep -Name "behavioral Goldens" -TestPaths @("tests/test_goldens.py")
Invoke-BackendPytestStep -Name "regression CI routes" -TestPaths @("tests/test_regression_ci_routes.py")
Invoke-BackendPytestStep -Name "regression CI orchestrator" -TestPaths @("tests/test_regression_ci_orchestrator.py")
Invoke-BackendPytestStep -Name "runtime policy gate" -TestPaths @("tests/test_runtime_policy_gate.py")
Invoke-BackendPytestStep -Name "billing and quota" -TestPaths @("tests/test_billing_v2.py")
Invoke-BackendPytestStep -Name "owner launch health" -TestPaths @("tests/test_owner_money_path_health.py")
Invoke-BackendPytestStep -Name "production config" -TestPaths @("tests/test_production_config.py")

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
