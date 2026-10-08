# Startet die claude-bridge unter Windows (PowerShell).
# Erster Start legt eine virtuelle Umgebung an. Aufruf im Ordner bridge\:
#   powershell -ExecutionPolicy Bypass -File .\start-bridge.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv")) {
    py -3 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -e .
}
if (-not (Test-Path ".env")) {
    Write-Error "Keine .env gefunden. Kopiere .env.example nach .env und trage Token/Ordner ein."
}
.\.venv\Scripts\python.exe -m claude_bridge --env-file .env check
.\.venv\Scripts\python.exe -m claude_bridge --env-file .env serve
