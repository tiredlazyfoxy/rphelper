# RPHelper host-dev launcher. Run each half in its own terminal:
#   start.ps1 -app   (alias -api)  -> uvicorn on 127.0.0.1:8184 with reload
#   start.ps1 -ui    (alias -web)  -> Vite on 8193
# Ports are topology literals, not settings (docs/architecture/deployment.md).

param(
    [Alias("api")][switch]$app,
    [Alias("web")][switch]$ui
)

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"

if ($app -eq $ui) {
    Write-Host "Usage: start.ps1 -app|-api    run the backend (uvicorn, port 8184)"
    Write-Host "       start.ps1 -ui|-web     run the frontend (Vite, port 8193)"
    Write-Host "Pass exactly one switch; run each in its own terminal."
    exit 1
}

if ($app) {
    Set-Location $backendDir
    & ".venv/Scripts/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8184 --reload
    exit $LASTEXITCODE
}

if ($ui) {
    Set-Location $frontendDir
    & npx vite --port 8193
    exit $LASTEXITCODE
}
