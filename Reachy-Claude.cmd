@echo off
rem Reachy Claude starten: Doppelklick (startet "listen") oder z. B. "Reachy-Claude.cmd pruefen".
rem Alle Befehle und Parameter: siehe README.md
set "REACHY_START_DIR=%CD%"
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0reachy-claude.ps1" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo Reachy Claude wurde mit einem Fehler beendet ^(Code %RC%^). Hinweise stehen oben.
  echo Taste druecken zum Schliessen ...
  pause >nul
)
exit /b %RC%
