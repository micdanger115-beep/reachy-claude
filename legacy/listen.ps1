# Bequemer Aufruf aus dem Hauptordner: leitet an bridge\listen.ps1 weiter.
#   powershell -ExecutionPolicy Bypass -File .\listen.ps1 [-Robot <Name/IP>] [-ShowTurns]
param(
    [string]$Robot = "reachy-mini.local",
    [switch]$ShowTurns
)
& (Join-Path (Join-Path $PSScriptRoot "bridge") "listen.ps1") -Robot $Robot -ShowTurns:$ShowTurns
