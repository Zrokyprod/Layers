# Branch Protection Setup (Step 09)

This repository uses CI checks from:

- lint-type
- sqlite-fast
- postgres-security

Optional security scan lane (non-blocking):

- security-audit-optional

## Prerequisites

1. GitHub CLI installed (`gh`).
2. Repository admin permissions.
3. Authenticated session (`gh auth login`).

## Apply Protection

Run from repository root:

```powershell
cd zroky-backend
./scripts/configure-branch-protection.ps1 -Owner <github-owner> -Repo <github-repo> -Branch main
```

Dry-run preview:

```powershell
cd zroky-backend
./scripts/configure-branch-protection.ps1 -Owner <github-owner> -Repo <github-repo> -Branch main -DryRun
```

Verification (drift check):

```powershell
cd zroky-backend
./scripts/verify-branch-protection.ps1 -Owner <github-owner> -Repo <github-repo> -Branch main
```

Automated drift audit (GitHub Actions):

1. Configure repository secret `BRANCH_PROTECTION_AUDIT_TOKEN` (fine-grained PAT with repository administration read access).
2. Workflow: `.github/workflows/zroky-branch-protection-audit.yml`.
3. Runs daily on schedule and supports manual trigger (`workflow_dispatch`).

## What Gets Enforced

- Required status checks:
  - lint-type
  - sqlite-fast
  - postgres-security
- Require branches up-to-date before merge.
- Require at least 1 approving review.
- Dismiss stale approvals on new commits.
- Require conversation resolution before merge.
- Enforce settings for admins.
- Linear history required.
- Force-push and branch deletion blocked.

## Notes

- `security-audit-optional` is intentionally not required so PR flow remains unblocked while findings are triaged.
- If check names in workflow change, update the `-RequiredChecks` list in the script invocation.
- Branch protection can only be applied to an existing branch. If the repository is empty, create an initial commit (for example `README.md`) first.
