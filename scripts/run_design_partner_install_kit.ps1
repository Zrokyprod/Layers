$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$Python = Join-Path $RootDir ".venv\Scripts\python.exe"
$Kit = Join-Path $ScriptDir "run_design_partner_install_kit.py"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "Python virtualenv not found: $Python"
}

& $Python $Kit @args
exit $LASTEXITCODE
