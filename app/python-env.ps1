# Hilfsfunktionen fuer reachy-claude.ps1 (wird per ". .\python-env.ps1" geladen).
# Sucht ein passendes Python (3.11 bis 3.13), legt bei Bedarf .venv an und installiert die App.

$MinPython = [version]"3.11"
# Neuere Versionen: fuer Teile der Spracherkennung/des Reachy-SDK gibt es oft noch keine fertigen
# Pakete, pip wuerde dann versuchen, sie zu kompilieren (und scheitert). Getestet: 3.11 und 3.12.
$MaxPython = [version]"3.13"

function Find-Python {
    # Lokal "Continue": Unter Windows PowerShell 5.1 wuerde sonst jede stderr-Ausgabe
    # eines externen Programms das ganze Skript abbrechen.
    $ErrorActionPreference = "Continue"
    # Reihenfolge: bevorzugt 3.12 ueber den Python-Launcher "py", dann andere passende Versionen.
    # Der Windows-Store-Platzhalter "python" (oeffnet nur den Store) wird erkannt und uebersprungen.
    foreach ($candidate in @("py -3.12", "py -3.13", "py -3.11", "py -3", "python", "python3")) {
        $parts = $candidate.Split(" ")
        $exe = $parts[0]
        $extra = @($parts | Select-Object -Skip 1)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        try {
            $out = & $exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        } catch { continue }
        if ($LASTEXITCODE -ne 0 -or -not $out) { continue }
        $found = [version]("$out".Trim())
        if ($found -lt $MinPython) {
            Write-Host "Gefunden: Python $found ueber '$candidate' - zu alt (mindestens $MinPython noetig)."
            continue
        }
        if ($found -gt $MaxPython) {
            Write-Host "Gefunden: Python $found ueber '$candidate' - zu neu (hoechstens $MaxPython; empfohlen 3.12)."
            continue
        }
        return , (@($exe) + $extra)
    }
    return $null
}

function Get-VenvPython {
    foreach ($p in @(".venv\Scripts\python.exe", ".venv/bin/python")) {
        if (Test-Path -LiteralPath $p) { return (Resolve-Path -LiteralPath $p).Path }
    }
    return $null
}

function Show-InstallHelp {
    Write-Host ""
    Write-Host "So behebst du es:" -ForegroundColor Yellow
    Write-Host "  - Internetverbindung pruefen."
    Write-Host "  - Den Ordner app\.venv loeschen und Reachy-Claude.cmd erneut starten (installiert alles neu)."
    Write-Host "  - Details stehen in app\pip-log.txt."
}

function Initialize-AppEnvironment {
    $ErrorActionPreference = "Continue"
    $venvPython = Get-VenvPython
    if ($venvPython) {
        # Kaputte Umgebung (abgebrochener erster Start, Python deinstalliert/aktualisiert)? Neu anlegen.
        & $venvPython -c "pass" 2>$null | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Die Python-Umgebung (app\.venv) ist beschaedigt - lege sie neu an ..." -ForegroundColor Yellow
            Remove-Item -LiteralPath ".venv" -Recurse -Force -ErrorAction SilentlyContinue
            $venvPython = $null
        }
    }
    if (-not $venvPython) {
        $python = Find-Python
        if (-not $python) {
            Write-Host ""
            Write-Host "Kein passendes Python ($MinPython bis $MaxPython) gefunden." -ForegroundColor Red
            Write-Host "So installierst du es (einmalig):"
            Write-Host "  1. In PowerShell:  winget install -e --id Python.Python.3.12"
            Write-Host "     (oder 3.12 von https://www.python.org/downloads/ - beim Installieren"
            Write-Host "      'Add python.exe to PATH' anhaken)"
            Write-Host "  2. Dieses Fenster schliessen und Reachy-Claude.cmd erneut starten."
            exit 1
        }
        Write-Host "Erster Start: richte Python-Umgebung ein (mit $($python -join ' ')) ..."
        $pyExe = $python[0]
        $pyArgs = @($python | Select-Object -Skip 1)
        & $pyExe @pyArgs -m venv .venv | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Anlegen der Python-Umgebung (.venv) fehlgeschlagen." -ForegroundColor Red
            Remove-Item -LiteralPath ".venv" -Recurse -Force -ErrorAction SilentlyContinue
            exit 1
        }
        $venvPython = Get-VenvPython
    }
    # Auch nach einem abgebrochenen ersten Start oder einem Update: fehlende Pakete nachinstallieren.
    & $venvPython -c "import reachy_claude, reachy_mini, faster_whisper, piper" 2>$null | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installiere reachy-claude, Reachy-SDK, Spracherkennung und Sprachausgabe."
        Write-Host "Beim ersten Mal dauert das 5-20 Minuten (ca. 1 GB) - bitte das Fenster offen lassen ..."
        & $venvPython -m pip install --disable-pip-version-check --log pip-log.txt -e . | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Installation fehlgeschlagen." -ForegroundColor Red
            Show-InstallHelp
            exit 1
        }
    }
    # NVIDIA-Grafikkarte vorhanden? Dann CUDA-Bibliotheken fuer schnelle Spracherkennung (einmalig ~1-2 GB).
    # Ist das einmal gescheitert, nicht bei jedem Start erneut versuchen (Merker in .venv).
    $cudaSkipped = Join-Path ".venv" "cuda-uebersprungen.txt"
    if ((Get-Command nvidia-smi -ErrorAction SilentlyContinue) -and -not (Test-Path -LiteralPath $cudaSkipped)) {
        & $venvPython -c "import nvidia.cublas, nvidia.cudnn" 2>$null | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Host "NVIDIA-Grafikkarte gefunden: installiere CUDA-Bibliotheken fuer die Spracherkennung (einmalig, 1-2 GB) ..."
            & $venvPython -m pip install --disable-pip-version-check --log pip-log.txt -e ".[gpu]" | Out-Host
            if ($LASTEXITCODE -ne 0) {
                Write-Host "CUDA-Bibliotheken nicht installiert - Spracherkennung laeuft dann auf dem Prozessor." -ForegroundColor Yellow
                Write-Host "(Neuer Versuch: Datei app\.venv\cuda-uebersprungen.txt loeschen.)"
                Set-Content -LiteralPath $cudaSkipped -Value "CUDA-Installation fehlgeschlagen, siehe pip-log.txt"
            }
        }
    }
    return $venvPython
}
