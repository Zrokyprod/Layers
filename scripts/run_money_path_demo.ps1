$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$Python = Join-Path $RootDir ".venv\Scripts\python.exe"
$Demo = Join-Path $ScriptDir "run_money_path_demo.py"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "Python virtualenv not found: $Python"
}

& $Python $Demo
exit $LASTEXITCODE
