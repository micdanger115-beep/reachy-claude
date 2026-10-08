# Stufe 1: Gespraech mit Reachy live als Text anzeigen (Windows, PowerShell).
# Aufruf im Ordner bridge\:
#   powershell -ExecutionPolicy Bypass -File .\listen.ps1
#   powershell -ExecutionPolicy Bypass -File .\listen.ps1 -Robot 192.168.1.30
param(
    [string]$Robot = "reachy-mini.local",
    [switch]$ShowTurns
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Erster Start: richte Python-Umgebung ein ..."
    py -3 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -e .
}
$saveFile = "transcripts\gespraech-$(Get-Date -Format 'yyyy-MM-dd').md"
$listenArgs = @("-m", "claude_bridge", "listen", "--robot", $Robot, "--save", $saveFile)
if ($ShowTurns) { $listenArgs += "--show-turns" }
.\.venv\Scripts\python.exe @listenArgs
