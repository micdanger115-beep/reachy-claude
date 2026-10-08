"""Schritt 6: Startpruefung – ist alles bereit? Jede Meldung sagt, wie man das Problem behebt.

Laeuft als eigener Befehl (``pruefen``, zeigt alles) und kurz vor jedem ``listen``
(zeigt nur Probleme; bei einem Fehler startet ``listen`` gar nicht erst).

Alle Pruefungen bleiben im Heimnetz bzw. auf dem PC: Reachy wird direkt gefragt
(``http://<reachy>:8000/api/daemon/status``), Claude ueber ``claude auth status``.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .robot import DAEMON_PORT, WEBRTC_SIGNALING_PORT, port_open
from .settings import MissingProjectError, SettingsError, load_settings

Output = Callable[[str], None]
Version = tuple[int, ...]


class Level(Enum):
    """Wie schlimm ist es?"""

    OK = "ok"
    INFO = "info"  # nur zur Kenntnis (wird bei listen nicht gezeigt)
    WARNUNG = "warnung"  # funktioniert, aber besser beheben
    FEHLER = "fehler"  # so geht es nicht


SYMBOL = {Level.OK: "[ OK ]", Level.INFO: "[INFO]", Level.WARNUNG: "[WARN]", Level.FEHLER: "[FEHL]"}


@dataclass(frozen=True)
class Check:
    """Ergebnis einer Pruefung."""

    name: str
    level: Level
    message: str
    fix: str = ""


@dataclass(frozen=True)
class RobotIssue:
    """Bekannte Sicherheitsluecke in Reachys eigener Software (SECURITY.md, S10)."""

    title: str
    fixed_in: Version | None  # None = noch kein Fix veroeffentlicht
    level: Level
    advice: str


# Stand 2026-10-08, Quelle: github.com/pollen-robotics/reachy_mini/security/advisories
ROBOT_ISSUES: tuple[RobotIssue, ...] = (
    RobotIssue(
        "Datei-Upload ohne Anmeldung (CVE-2026-55419)",
        (1, 8, 2),
        Level.WARNUNG,
        "Reachy ueber sein Dashboard (http://<reachy>:8000) aktualisieren.",
    ),
    RobotIssue(
        "Bluetooth-PIN-Umgehung (GHSA-993g-hgjh-whmf)",
        (1, 12, 0),
        Level.INFO,
        "Update, sobald 1.12 erscheint; bis dahin Bluetooth nur bei Bedarf koppeln.",
    ),
    RobotIssue(
        "Bluetooth-Pfad-Luecke (CVE-2026-62661)",
        None,
        Level.INFO,
        "Bluetooth nur bei Bedarf koppeln; fremde Geraete ins Gaeste-WLAN.",
    ),
)

REQUIRED_PACKAGES = {
    "reachy_mini": "Reachy-SDK",
    "faster_whisper": "Spracherkennung",
    "piper": "Sprachausgabe",
}
REINSTALL_FIX = r"Ordner app\.venv loeschen und das Startskript erneut starten (installiert alles neu)."


def parse_version(text: str) -> Version | None:
    """``"1.11.0"`` / ``"1.12.0rc1"`` -> ``(1, 11, 0)``; ``None`` wenn unlesbar."""
    match = re.match(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    return tuple(int(part) for part in match.groups(default="0"))


def _fmt(v: Version) -> str:
    return ".".join(str(part) for part in v)


# --- einzelne Pruefungen (Abhaengigkeiten als Parameter, damit sie testbar sind) ---


def check_packages(find_spec: Callable[[str], object | None] = importlib.util.find_spec) -> Check:
    missing = [label for module, label in REQUIRED_PACKAGES.items() if find_spec(module) is None]
    if missing:
        return Check("Python-Pakete", Level.FEHLER, "fehlt: " + ", ".join(missing), REINSTALL_FIX)
    return Check("Python-Pakete", Level.OK, "vollstaendig")


def _cuda_devices() -> int:
    import ctranslate2  # kommt mit faster-whisper

    return int(ctranslate2.get_cuda_device_count())


def check_gpu(device: str = "auto", cuda_devices: Callable[[], int] = _cuda_devices) -> Check:
    if device == "cpu":
        return Check("Grafikkarte", Level.OK, "Spracherkennung auf dem Prozessor (so gewaehlt)")
    try:
        count = cuda_devices()
    except Exception as exc:  # fehlende Treiber/Bibliotheken aeussern sich sehr unterschiedlich
        count = 0
        detail = f" ({type(exc).__name__})"
    else:
        detail = ""
    if count > 0:
        return Check("Grafikkarte", Level.OK, "NVIDIA-Grafikkarte wird fuer die Spracherkennung genutzt")
    return Check(
        "Grafikkarte",
        Level.FEHLER if device == "cuda" else Level.WARNUNG,
        f"keine nutzbare NVIDIA-Grafikkarte{detail} – Spracherkennung auf dem Prozessor (langsamer)",
        "NVIDIA-Treiber aktualisieren; danach " + REINSTALL_FIX,
    )


def check_voice(voice: str, voice_dir: Path = Path("voices")) -> Check:
    if (voice_dir / f"{voice}.onnx").is_file():
        return Check("Stimme", Level.OK, f"{voice} ist installiert")
    return Check(
        "Stimme",
        Level.INFO,
        f"{voice} wird beim ersten Start heruntergeladen (ca. 60 MB, einmalig Internet noetig)",
    )


def _claude_auth_status(claude_bin: str) -> str:
    done = subprocess.run(
        [claude_bin, "auth", "status", "--json"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    return done.stdout


def check_claude(
    claude_program: str = "claude",
    which: Callable[[str], str | None] = shutil.which,
    auth_status: Callable[[str], str] = _claude_auth_status,
) -> Check:
    path = which(claude_program)
    if path is None:
        return Check(
            "Claude Code",
            Level.FEHLER,
            "nicht installiert (oder nicht im PATH)",
            "Installieren: https://claude.com/claude-code – danach ein neues Fenster oeffnen.",
        )
    try:
        data = json.loads(auth_status(path))
        logged_in = bool(data.get("loggedIn"))
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError) as exc:
        return Check(
            "Claude Code",
            Level.WARNUNG,
            f"installiert, Anmeldung nicht pruefbar ({type(exc).__name__})",
            "Im Terminal 'claude' starten und pruefen, ob du angemeldet bist.",
        )
    if not logged_in:
        return Check(
            "Claude Code",
            Level.FEHLER,
            "installiert, aber nicht angemeldet",
            "Im Terminal einmal 'claude auth login' ausfuehren.",
        )
    return Check("Claude Code", Level.OK, "installiert und angemeldet")


def check_project(settings_file: Path) -> Check:
    try:
        settings = load_settings(settings_file)
    except MissingProjectError:
        return Check(
            "Projektordner",
            Level.WARNUNG,
            "noch keiner festgelegt (wird beim Start abgefragt)",
            'Oder einmalig: reachy-claude.ps1 listen -Projekt "D:\\pfad\\zum\\projekt"',
        )
    except SettingsError as exc:
        return Check("Projektordner", Level.FEHLER, str(exc), f"{settings_file} korrigieren.")
    rights = "lesen + bearbeiten" if settings.permission.value == "edit" else "nur lesen"
    return Check("Projektordner", Level.OK, f"{settings.workdir} ({rights})")


def check_robot(host: str, is_open: Callable[[str, int], bool] = port_open) -> list[Check]:
    """Erreichbarkeit: Steuerung (Daemon) und Ton/Video (WebRTC-Signalisierung)."""
    if not is_open(host, DAEMON_PORT):
        return [
            Check(
                "Reachy erreichbar",
                Level.FEHLER,
                f"{host} antwortet nicht (Port {DAEMON_PORT})",
                "Reachy eingeschaltet und im selben WLAN/LAN? Adresse richtig? Sonst mit "
                "-Robot <IP> starten (die IP steht im Router oder in der Reachy-App).",
            )
        ]
    checks = [Check("Reachy erreichbar", Level.OK, f"{host} (Steuerung)")]
    if is_open(host, WEBRTC_SIGNALING_PORT):
        checks.append(Check("Reachy Ton/Video", Level.OK, "bereit"))
    else:
        checks.append(
            Check(
                "Reachy Ton/Video",
                Level.FEHLER,
                f"nicht erreichbar (Port {WEBRTC_SIGNALING_PORT})",
                "Reachy neu starten; laeuft gerade eine andere App auf Reachy, diese beenden.",
            )
        )
    return checks


def _daemon_status(host: str) -> dict[str, object]:
    url = f"http://{host}:{DAEMON_PORT}/api/daemon/status"  # nur Heimnetz; host ist geprueft
    with urllib.request.urlopen(url, timeout=3) as response:  # noqa: S310 – feste http-URL
        data = json.loads(response.read(65536))
    return data if isinstance(data, dict) else {}


def _sdk_version() -> str | None:
    try:
        return version("reachy-mini")
    except PackageNotFoundError:
        return None


def check_robot_software(
    host: str,
    status: Callable[[str], dict[str, object]] = _daemon_status,
    sdk_version: Callable[[], str | None] = _sdk_version,
) -> list[Check]:
    """Reachys Software-Version: bekannte Sicherheitsluecken und Passung zur App."""
    try:
        raw = status(host)
    except Exception as exc:  # Netzwerk/JSON: nur ein Hinweis, die Verbindung prueft check_robot
        return [Check("Reachy-Version", Level.WARNUNG, f"nicht abrufbar ({type(exc).__name__})")]
    robot = parse_version(str(raw.get("version") or ""))
    if robot is None:
        return [Check("Reachy-Version", Level.WARNUNG, "unbekannt")]
    checks = [Check("Reachy-Version", Level.OK, _fmt(robot))]
    for issue in ROBOT_ISSUES:
        if issue.fixed_in is not None and robot >= issue.fixed_in:
            continue
        fixed = f"behoben ab {_fmt(issue.fixed_in)}" if issue.fixed_in else "noch kein Update"
        checks.append(Check("Reachy-Sicherheit", issue.level, f"{issue.title}; {fixed}", issue.advice))
    app = parse_version(sdk_version() or "")
    if app is not None and app[:2] != robot[:2]:
        checks.append(
            Check(
                "Reachy-Version",
                Level.WARNUNG,
                f"Reachy hat {_fmt(robot)}, die App nutzt das SDK {_fmt(app)}",
                "Bei Verbindungsproblemen die SDK-Version in app/pyproject.toml anpassen "
                "(reachy-mini~=<Reachy-Version>) und app\\.venv neu anlegen.",
            )
        )
    return checks


# --- Zusammenstellung ---


def run_checks(
    *,
    host: str,
    voice: str,
    settings_file: Path,
    device: str = "auto",
    with_claude: bool = True,
    with_project: bool = True,
    with_gpu: bool = True,
) -> list[Check]:
    """Alle Pruefungen (schnell, wenige Sekunden)."""
    checks = [check_packages()]
    if with_gpu:
        checks.append(check_gpu(device))
    checks.append(check_voice(voice))
    if with_claude:
        checks.append(check_claude())
        if with_project:
            checks.append(check_project(settings_file))
    robot = check_robot(host)
    checks += robot
    if robot[0].level is Level.OK:  # Steuerung erreichbar -> Version abfragen
        checks += check_robot_software(host)
    return checks


def has_errors(checks: Iterable[Check]) -> bool:
    return any(check.level is Level.FEHLER for check in checks)


def report(checks: Iterable[Check], output: Output, *, problems_only: bool = False) -> None:
    """Ergebnisse ausgeben; ``problems_only`` zeigt nur Warnungen und Fehler."""
    for check in checks:
        if problems_only and check.level in (Level.OK, Level.INFO):
            continue
        output(f"{SYMBOL[check.level]} {check.name}: {check.message}")
        if check.fix and check.level is not Level.OK:
            output(f"       -> {check.fix}")
