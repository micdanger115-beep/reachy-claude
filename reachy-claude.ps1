# reachy-claude starten (Windows, PowerShell). Im Hauptordner aufrufen:
#   powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 check-audio
#   powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 check-audio -Robot 192.168.1.30
#   powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 say -Text "Hallo, ich bin Reachy"
#   powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 listen -Projekt "D:\code\mein-projekt"   (einmalig)
#   powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 listen
#   powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 voices        (Stimmen anzeigen)
# Beim ersten Start wird eine eigene Python-Umgebung in app\.venv eingerichtet.
param(
    [Parameter(Position = 0)]
    [ValidateSet("check-audio", "say", "listen", "voices")]
    [string]$Command = "check-audio",
    [string]$Robot = "reachy-mini.local",
    [int]$Seconds = 5,
    [ValidateSet("auto", "cuda", "cpu")]
    [string]$Device = "auto",
    [string]$Text = "Hallo, ich bin Reachy. Ich kann jetzt sprechen.",
    [string]$Projekt = "",
    [ValidateSet("", "read", "edit")]
    [string]$Rechte = "",
    [switch]$OhneClaude,
    [string]$Stimme = "",
    [string]$Sprecher = "",
    [switch]$OhneBewegung,
    [switch]$WachBleiben,
    [switch]$Silent,
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
if ($Command -eq "say" -or $Command -eq "listen") {
    if ($Stimme) { $cliArgs += @("--voice", $Stimme) }
    if ($Sprecher) { $cliArgs += @("--speaker", $Sprecher) }
}
if ($Command -eq "say") { $cliArgs += $Text }
if ($Command -eq "listen") {
    $cliArgs += @("--device", $Device)
    if ($Silent) { $cliArgs += "--silent" }
    if ($Projekt) { $cliArgs += @("--project", $Projekt) }
    if ($Rechte) { $cliArgs += @("--permission", $Rechte) }
    if ($OhneClaude) { $cliArgs += "--no-claude" }
    if ($OhneBewegung) { $cliArgs += "--no-motion" }
    if ($WachBleiben) { $cliArgs += "--stay-awake" }
}
& $python @cliArgs
exit $LASTEXITCODE
