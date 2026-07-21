param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

$planPath = Join-Path $Root "ZROKY_FINAL_BUILD_PLAN.md"
$trackerPath = Join-Path $Root "ZROKY_BUILD_TRACKER.md"
$reportDir = Join-Path $Root "docs\build-reports"

$errors = New-Object System.Collections.Generic.List[string]

function Add-Error([string]$Message) {
    $errors.Add($Message) | Out-Null
}

function Require-File([string]$Path, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Add-Error "$Name missing: $Path"
    }
}

Require-File $planPath "Build plan"
Require-File $trackerPath "Build tracker"

if (-not (Test-Path -LiteralPath $reportDir -PathType Container)) {
    Add-Error "Build reports directory missing: $reportDir"
}

if ($errors.Count -eq 0) {
    $plan = Get-Content -LiteralPath $planPath
    $tracker = Get-Content -LiteralPath $trackerPath

    $requiredPlanSections = @(
        "## 1. Final Product Definition",
        "## 2. Non-Negotiable Product Boundary",
        "## 2.1 Dashboard Replacement Boundary",
        "## 2.2 GitHub And CI Boundary",
        "## 3. Product Invariants",
        "## 4. Core Flow",
        "## 7. Keep, Delete, Migrate",
        "## 11. Build Phases",
        "## 14. Live Readiness Gates",
        "## 15. Build-Time Anti-Hallucination Rules"
    )

    foreach ($section in $requiredPlanSections) {
        if (-not ($plan -contains $section)) {
            Add-Error "Build plan missing required section: $section"
        }
    }

    $validStatuses = @(
        "Pending",
        "In Progress",
        "Blocked",
        "Implemented",
        "Verified",
        "Deferred",
        "Deleted"
    )

    $requiredIds = @(
        "P0-001", "P0-002", "P0-003", "P0-004", "P0-005", "P0-006", "P0-007", "P0-008",
        "P0-009", "P0-010", "P0-011", "P0-012",
        "P1-001", "P2-001", "P3-001", "P4-001", "P5-001", "P6-001",
        "P6-004", "P6-005", "P7-001", "P8-001", "P9-001", "P10-001",
        "P10-005", "P10-006", "P11-001", "P11-002", "P11-003", "P11-004", "P11-005", "P11-006", "P11-007", "P11-008", "P11-009", "P11-010", "P11-011"
    )

    $seen = @{}
    $rows = @()

    foreach ($line in $tracker) {
        if ($line -notmatch '^\|\s*(P\d+-\d{3})\s*\|') {
            continue
        }

        $cells = $line.Trim("|").Split("|") | ForEach-Object { $_.Trim() }
        if ($cells.Count -lt 7) {
            Add-Error "Malformed tracker row: $line"
            continue
        }

        $id = $cells[0]
        $status = $cells[3]
        $evidence = $cells[4]
        $files = $cells[5]

        if ($seen.ContainsKey($id)) {
            Add-Error "Duplicate tracker ID: $id"
        } else {
            $seen[$id] = $true
        }

        if ($validStatuses -notcontains $status) {
            Add-Error "Invalid status for $id`: $status"
        }

        if (($status -eq "Verified") -and (($evidence -eq "-") -or [string]::IsNullOrWhiteSpace($evidence))) {
            Add-Error "$id is Verified without evidence"
        }

        if (($status -eq "Verified") -and (($files -eq "-") -or [string]::IsNullOrWhiteSpace($files))) {
            Add-Error "$id is Verified without file references"
        }

        $rows += [pscustomobject]@{
            ID = $id
            Phase = $cells[1]
            Task = $cells[2]
            Status = $status
            Evidence = $evidence
            Files = $files
        }
    }

    foreach ($id in $requiredIds) {
        if (-not $seen.ContainsKey($id)) {
            Add-Error "Required tracker ID missing: $id"
        }
    }

    $phase0Report = Join-Path $reportDir "phase-0-report.md"
    if (-not (Test-Path -LiteralPath $phase0Report -PathType Leaf)) {
        Add-Error "Phase 0 report missing: $phase0Report"
    }

    $unexpectedVerified = $rows | Where-Object {
        $_.Status -eq "Verified" -and $_.Evidence -notmatch "(?i)(pass|passed|deleted|verified|inventory|report|test|check)"
    }
    foreach ($row in $unexpectedVerified) {
        Add-Error "$($row.ID) evidence does not look like a verification result: $($row.Evidence)"
    }

    Write-Host "Zroky Build Plan Verification"
    Write-Host ""
    Write-Host "Tracker rows: $($rows.Count)"
    foreach ($status in $validStatuses) {
        $count = @($rows | Where-Object { $_.Status -eq $status }).Count
        Write-Host ("{0}: {1}" -f $status, $count)
    }
}

if ($errors.Count -gt 0) {
    Write-Host ""
    Write-Host "Result: FAIL"
    foreach ($err in $errors) {
        Write-Host "- $err"
    }
    exit 1
}

Write-Host ""
Write-Host "Result: PASS"
exit 0
