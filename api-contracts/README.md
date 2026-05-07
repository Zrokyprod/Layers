# ZROKY API Contracts

This directory contains the static, versioned OpenAPI contracts for the ZROKY backend API.

## Current Status

- `onboarding-trigger-test-failure.openapi.yaml` — Single endpoint contract for synthetic onboarding failures
- `zroky-api-v1.openapi.json` — **Generated from FastAPI** (regenerate after every schema change)

## Regenerating the Full Contract

From the `zroky-backend/` directory, with the virtual environment activated:

```powershell
# Windows
.venv\Scripts\python.exe -B scripts\export_openapi.py

# Or activate the venv first
.venv\Scripts\Activate.ps1
python -B scripts\export_openapi.py
```

```bash
# Linux/macOS
.venv/bin/python -B scripts/export_openapi.py
```

The script patches out heavy production dependencies (pgvector, redis, celery, etc.) so it can run in a minimal environment without a live database or Redis server.

## CI Enforcement

The `.github/workflows/api-contract-check.yml` workflow runs on every PR that touches the backend. It:

1. Installs dependencies in a clean Ubuntu runner
2. Generates the OpenAPI spec from the running FastAPI app
3. Fails the build if the committed spec has drifted from the generated one

To fix a drift failure locally:

```bash
cd zroky-backend
python -B scripts/export_openapi.py
git add ../api-contracts/zroky-api-v1.openapi.json
git commit -m "chore: regenerate API contract"
```

## Why Static Contracts Matter

- **SDK consumers** can generate typed clients from a committed source of truth
- **Frontend developers** can validate payloads before deployment
- **Versioning** is explicit — schema changes are reviewed as diff in PRs
- **Production safety** — FastAPI auto-docs are disabled in production (`docs_url=None`), so the static file is the only contract surface
