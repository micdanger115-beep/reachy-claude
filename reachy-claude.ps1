# reachy-claude starten (Windows, PowerShell). Am einfachsten: Doppelklick auf Reachy-Claude.cmd.
# Alles, was per Parameter gesetzt wird (Roboter, Projekt, Rechte, Stimme, Bewegung), wird gemerkt.
#   .\Reachy-Claude.cmd                                   zuhoeren (Standard)
#   .\Reachy-Claude.cmd pruefen                           Startpruefung: ist alles bereit?
#   .\Reachy-Claude.cmd verknuepfung                      Desktop-Verknuepfung anlegen
#   .\Reachy-Claude.cmd listen -Projekt "D:\code\x"       Projektordner wechseln
#   .\Reachy-Claude.cmd listen -Robot 192.168.1.30        andere Adresse von Reachy
#   .\Reachy-Claude.cmd listen -Stimme de_DE-kerstin-low  andere Stimme (siehe: voices)
#   .\Reachy-Claude.cmd listen -Bewegung aus              Reachy bewegt sich nicht
#   .\Reachy-Claude.cmd check-audio                       Mikrofon/Lautsprecher testen
#   .\Reachy-Claude.cmd say -Text "Hallo"                 Reachy etwas sagen lassen
# Ohne .cmd: powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 <Befehl> ...
# Beim ersten Start wird eine eigene Python-Umgebung in app\.venv eingerichtet.
param(
    [Parameter(Position = 0)]
    [ValidateSet("listen", "pruefen", "check-audio", "say", "voices", "verknuepfung")]
    [string]$Command = "listen",
    [string]$Robot = "",
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
    [ValidateSet("", "an", "aus")]
    [string]$Bewegung = "",
    [switch]$WachBleiben,
    [switch]$Silent,
    [switch]$Details
)
$ErrorActionPreference = "Stop"

if ($Command -eq "verknuepfung") {
    $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop, [Environment+SpecialFolderOption]::Create)
    $link = Join-Path $desktop "Reachy Claude.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($link)
    $shortcut.TargetPath = Join-Path $PSScriptRoot "Reachy-Claude.cmd"
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.Description = "Mit Reachy sprechen, Claude arbeitet"
    $shortcut.Save()
    Write-Host "Verknuepfung angelegt: $link"
    exit 0
}

# Relativer Projektpfad (z. B. -Projekt .) bezieht sich auf den Ordner, aus dem gestartet wurde
# (Reachy-Claude.cmd merkt ihn sich in REACHY_START_DIR, bevor es in den App-Ordner wechselt).
if ($Projekt) {
    $Projekt = $Projekt.Trim().TrimEnd('"')  # PS 5.1: "C:\Ordner" kommt sonst mit " am Ende an
    if (-not [System.IO.Path]::IsPathRooted($Projekt)) {
        $base = if ($env:REACHY_START_DIR) { $env:REACHY_START_DIR } else { (Get-Location).Path }
        $Projekt = [System.IO.Path]::GetFullPath((Join-Path $base $Projekt))
    }
}

$appDir = Join-Path $PSScriptRoot "app"
Set-Location -LiteralPath $appDir
. (Join-Path $appDir "python-env.ps1")

$python = Initialize-AppEnvironment
$cliArgs = @("-m", "reachy_claude")
if ($Robot) { $cliArgs += @("--robot", $Robot) }
if ($Details) { $cliArgs += "--debug" }
$cliArgs += $Command
if ($Command -eq "check-audio") { $cliArgs += @("--seconds", "$Seconds") }
if ($Command -eq "pruefen") { $cliArgs += @("--device", $Device) }
if ($Command -eq "say" -or $Command -eq "listen") {
    if ($Stimme) { $cliArgs += @("--voice", $Stimme) }
    if ($Sprecher) { $cliArgs += @("--speaker", $Sprecher) }
}
if ($Command -eq "say") { $cliArgs += @("--", $Text) }  # "--": Text darf mit "-" beginnen
if ($Command -eq "listen") {
    $cliArgs += @("--device", $Device)
    if ($Silent) { $cliArgs += "--silent" }
    if ($Projekt) { $cliArgs += @("--project", $Projekt) }
    if ($Rechte) { $cliArgs += @("--permission", $Rechte) }
    if ($OhneClaude) { $cliArgs += "--no-claude" }
    if ($Bewegung -eq "an") { $cliArgs += "--motion" }
    if ($Bewegung -eq "aus") { $cliArgs += "--no-motion" }
    if ($WachBleiben) { $cliArgs += "--stay-awake" }
}
& $python @cliArgs
exit $LASTEXITCODE
