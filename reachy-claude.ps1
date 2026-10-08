# reachy-claude starten (Windows, PowerShell). Im Hauptordner aufrufen:
#   powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 check-audio
#   powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 check-audio -Robot 192.168.1.30
#   powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 listen
# Beim ersten Start wird eine eigene Python-Umgebung in app\.venv eingerichtet.
param(
    [Parameter(Position = 0)]
    [ValidateSet("check-audio", "listen")]
    [string]$Command = "check-audio",
    [string]$Robot = "reachy-mini.local",
    [int]$Seconds = 5,
    [ValidateSet("auto", "cuda", "cpu")]
    [string]$Device = "auto",
    [switch]$Details
)
$ErrorActionPreference = "Stop"
$appDir = Join-Path $PSScriptRoot "app"
Set-Location -Path $appDir
. (Join-Path $appDir "python-env.ps1")

$python = Initialize-AppEnvironment
$cliArgs = @("-m", "reachy_claude", "--robot", $Robot)
if ($Details) { $cliArgs += "--debug" }
$cliArgs += $Command
if ($Command -eq "check-audio") { $cliArgs += @("--seconds", "$Seconds") }
if ($Command -eq "listen") { $cliArgs += @("--device", $Device) }
& $python @cliArgs
exit $LASTEXITCODE
