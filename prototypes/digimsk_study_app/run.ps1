# Local study UI only. Does not set DIGIMSK_PUBLIC_ACCESS / Cloud Run env.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python (Join-Path $Root "scripts\run_local.py") --kill-stale @args
exit $LASTEXITCODE
