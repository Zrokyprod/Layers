param(
    [Parameter(Mandatory = $true)]
    [string]$Owner,

    [Parameter(Mandatory = $true)]
    [string]$Repo,

    [string]$Branch = "main",

    [string[]]$RequiredChecks = @("lint-type", "sqlite-fast", "postgres-security")
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required. Install from https://cli.github.com/ and run 'gh auth login'."
}

gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated. Run 'gh auth login' and retry."
}

$protectionJson = gh api "repos/$Owner/$Repo/branches/$Branch/protection" --header "Accept: application/vnd.github+json" --header "X-GitHub-Api-Version: 2022-11-28"
$protection = $protectionJson | ConvertFrom-Json

$expectedChecks = $RequiredChecks | Sort-Object
$actualChecks = @($protection.required_status_checks.contexts) | Sort-Object

$mismatches = @()

if ($null -eq $protection.required_status_checks -or -not $protection.required_status_checks.strict) {
    $mismatches += "required_status_checks.strict must be true"
}

if (-not ($expectedChecks -join "," -ceq $actualChecks -join ",")) {
    $mismatches += "required_status_checks.contexts mismatch. expected=[$($expectedChecks -join ', ')] actual=[$($actualChecks -join ', ')]"
}

if (-not $protection.enforce_admins.enabled) {
    $mismatches += "enforce_admins.enabled must be true"
}

if (-not $protection.required_linear_history.enabled) {
    $mismatches += "required_linear_history.enabled must be true"
}

if (-not $protection.required_conversation_resolution.enabled) {
    $mismatches += "required_conversation_resolution.enabled must be true"
}

if ($protection.required_pull_request_reviews.required_approving_review_count -lt 1) {
    $mismatches += "required_pull_request_reviews.required_approving_review_count must be >= 1"
}

if ($protection.allow_force_pushes.enabled) {
    $mismatches += "allow_force_pushes.enabled must be false"
}

if ($protection.allow_deletions.enabled) {
    $mismatches += "allow_deletions.enabled must be false"
}

if ($mismatches.Count -gt 0) {
    Write-Host "Branch protection verification failed for $Owner/$Repo branch '$Branch'."
    foreach ($m in $mismatches) {
        Write-Host "- $m"
    }
    exit 1
}

Write-Host "Branch protection verification passed for $Owner/$Repo branch '$Branch'."
Write-Host "Required checks: $($actualChecks -join ', ')"
