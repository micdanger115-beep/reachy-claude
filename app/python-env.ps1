# Hilfsfunktionen fuer reachy-claude.ps1 (wird per ". .\python-env.ps1" geladen).
# Sucht ein passendes Python (>= 3.11), legt bei Bedarf .venv an und installiert die Bridge.

$MinPython = [version]"3.11"

function Find-Python {
    # Lokal "Continue": Unter Windows PowerShell 5.1 wuerde sonst jede stderr-Ausgabe
    # eines externen Programms das ganze Skript abbrechen.
    $ErrorActionPreference = "Continue"
    # Reihenfolge: Python-Launcher "py", dann "python", dann "python3".
    # Der Windows-Store-Platzhalter "python" (oeffnet nur den Store) wird erkannt und uebersprungen.
    foreach ($candidate in @("py -3", "python", "python3")) {
        $parts = $candidate.Split(" ")
        $exe = $parts[0]
        $extra = @($parts | Select-Object -Skip 1)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        try {
            $out = & $exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        } catch { continue }
        if ($LASTEXITCODE -ne 0 -or -not $out) { continue }
        $found = [version]("$out".Trim())
        if ($found -ge $MinPython) {
            return , (@($exe) + $extra)
        }
        Write-Host "Gefunden: Python $found ueber '$candidate' - zu alt (mindestens $MinPython noetig)."
    }
    return $null
}

function Get-VenvPython {
    foreach ($p in @(".venv\Scripts\python.exe", ".venv/bin/python")) {
        if (Test-Path $p) { return (Resolve-Path $p).Path }
    }
    return $null
}

function Initialize-AppEnvironment {
    $ErrorActionPreference = "Continue"
    $venvPython = Get-VenvPython
    if (-not $venvPython) {
        $python = Find-Python
        if (-not $python) {
            Write-Host ""
            Write-Host "Python $MinPython oder neuer wurde nicht gefunden." -ForegroundColor Red
            Write-Host "So installierst du es (einmalig):"
            Write-Host "  1. In PowerShell:  winget install -e --id Python.Python.3.12"
            Write-Host "     (oder von https://www.python.org/downloads/ - beim Installieren"
            Write-Host "      'Add python.exe to PATH' anhaken)"
            Write-Host "  2. Dieses PowerShell-Fenster schliessen und ein NEUES oeffnen."
            Write-Host "  3. Pruefen mit:  py --version   (oder: python --version)"
            Write-Host "  4. Dieses Skript erneut starten."
            exit 1
        }
        Write-Host "Erster Start: richte Python-Umgebung ein (mit $($python -join ' ')) ..."
        $pyExe = $python[0]
        $pyArgs = @($python | Select-Object -Skip 1)
        & $pyExe @pyArgs -m venv .venv | Out-Host
        if ($LASTEXITCODE -ne 0) { Write-Host "Anlegen der Python-Umgebung (.venv) fehlgeschlagen." -ForegroundColor Red; exit 1 }
        $venvPython = Get-VenvPython
    }
    # Auch nach einem abgebrochenen ersten Start oder einem Update: fehlende Pakete nachinstallieren.
    & $venvPython -c "import reachy_claude, reachy_mini, faster_whisper, piper" 2>$null | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installiere reachy-claude, Reachy-SDK, Spracherkennung und Sprachausgabe (beim ersten Mal einige Minuten) ..."
        & $venvPython -m pip install --disable-pip-version-check -q -e . | Out-Host
        if ($LASTEXITCODE -ne 0) { Write-Host "Installation fehlgeschlagen (Internetverbindung?)." -ForegroundColor Red; exit 1 }
    }
    # NVIDIA-Grafikkarte vorhanden? Dann CUDA-Bibliotheken fuer schnelle Spracherkennung (einmalig ~1-2 GB).
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        & $venvPython -c "import nvidia.cublas, nvidia.cudnn" 2>$null | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Host "NVIDIA-Grafikkarte gefunden: installiere CUDA-Bibliotheken fuer die Spracherkennung (einmalig, gross) ..."
            & $venvPython -m pip install --disable-pip-version-check -q -e ".[gpu]" | Out-Host
            if ($LASTEXITCODE -ne 0) { Write-Host "CUDA-Bibliotheken nicht installiert - Spracherkennung laeuft dann auf dem Prozessor." -ForegroundColor Yellow }
        }
    }
    return $venvPython
}
