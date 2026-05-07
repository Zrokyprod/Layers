param(
    [Parameter(Mandatory = $true)]
    [string]$Owner,

    [Parameter(Mandatory = $true)]
    [string]$Repo,

    [string]$Branch = "main",

    [string[]]$RequiredChecks = @("lint-type", "sqlite-fast", "postgres-security"),

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required. Install from https://cli.github.com/ and run 'gh auth login'."
}

if (-not $DryRun) {
    gh auth status *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI is not authenticated. Run 'gh auth login' and retry."
    }
}

$payload = @{
    required_status_checks = @{
        strict = $true
        contexts = $RequiredChecks
    }
    enforce_admins = $true
    required_pull_request_reviews = @{
        dismiss_stale_reviews = $true
        require_code_owner_reviews = $false
        required_approving_review_count = 1
    }
    restrictions = $null
    required_linear_history = $true
    allow_force_pushes = $false
    allow_deletions = $false
    block_creations = $false
    required_conversation_resolution = $true
    lock_branch = $false
    allow_fork_syncing = $true
}

$jsonPayload = $payload | ConvertTo-Json -Depth 12
Write-Host "Applying branch protection for $Owner/$Repo branch '$Branch'"
Write-Host "Required checks: $($RequiredChecks -join ', ')"

if ($DryRun) {
    Write-Host "Dry run enabled. Payload preview:"
    Write-Output $jsonPayload
    exit 0
}

$tempFile = [System.IO.Path]::GetTempFileName()
try {
    # GitHub API rejects BOM-prefixed JSON in --input files on some PowerShell versions.
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($tempFile, $jsonPayload, $utf8NoBom)

    gh api --method PUT "repos/$Owner/$Repo/branches/$Branch/protection" --header "Accept: application/vnd.github+json" --header "X-GitHub-Api-Version: 2022-11-28" --input $tempFile | Out-Null

    Write-Host "Branch protection applied successfully."

    gh api "repos/$Owner/$Repo/branches/$Branch/protection" --header "Accept: application/vnd.github+json" --header "X-GitHub-Api-Version: 2022-11-28" --jq '.required_status_checks.contexts'
}
finally {
    if (Test-Path $tempFile) {
        Remove-Item $tempFile -Force
    }
}
