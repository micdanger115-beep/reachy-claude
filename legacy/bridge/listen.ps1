# Stufe 1: Gespraech mit Reachy live als Text anzeigen (Windows, PowerShell).
# Aufruf (im Ordner bridge\ oder im Hauptordner ueber ..\listen.ps1):
#   powershell -ExecutionPolicy Bypass -File .\listen.ps1
#   powershell -ExecutionPolicy Bypass -File .\listen.ps1 -Robot 192.168.1.30
param(
    [string]$Robot = "reachy-mini.local",
    [switch]$ShowTurns
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
. (Join-Path $PSScriptRoot "python-env.ps1")

$python = Initialize-BridgeEnvironment
$saveFile = Join-Path "transcripts" "gespraech-$(Get-Date -Format 'yyyy-MM-dd').md"
$listenArgs = @("-m", "claude_bridge", "listen", "--robot", $Robot, "--save", $saveFile)
if ($ShowTurns) { $listenArgs += "--show-turns" }
& $python @listenArgs
