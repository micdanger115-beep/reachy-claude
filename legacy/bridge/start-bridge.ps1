# Stufe 2: claude-bridge starten (Windows, PowerShell). Aufruf im Ordner bridge\:
#   powershell -ExecutionPolicy Bypass -File .\start-bridge.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
. (Join-Path $PSScriptRoot "python-env.ps1")

$python = Initialize-BridgeEnvironment
if (-not (Test-Path ".env")) {
    Write-Host "Keine .env gefunden. Kopiere .env.example nach .env und trage Token/Ordner ein." -ForegroundColor Red
    exit 1
}
& $python -m claude_bridge --env-file .env check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m claude_bridge --env-file .env serve
