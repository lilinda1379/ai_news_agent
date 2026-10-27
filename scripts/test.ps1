$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
& ".\.venv\Scripts\python.exe" -m pytest -q
exit $LASTEXITCODE
