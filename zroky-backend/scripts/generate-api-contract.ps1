# Generate OpenAPI contract from FastAPI app
# Run from zroky-backend/ directory with: .\scripts\generate-api-contract.ps1

$ErrorActionPreference = "Stop"

# Clear stale bytecode to prevent resurrecting deleted modules
Get-ChildItem -Path . -Recurse -Filter "*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Cleared stale bytecode caches" -ForegroundColor Green

# Run the export script
& .venv\Scripts\python.exe -B scripts\export_openapi.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "API contract generated successfully." -ForegroundColor Green
    Write-Host "Output: ..\api-contracts\zroky-api-v1.openapi.json"
} else {
    Write-Host "Failed to generate API contract. See errors above." -ForegroundColor Red
    exit 1
}
