"""Gemerkte Einstellungen in ``app/einstellungen.toml``.

- ``[claude]``: Projektordner, Rechte, Zeitlimit
- ``[reachy]``: Roboter-Adresse, Stimme, Sprecher, Bewegung an/aus

Was einmal per Parameter gesetzt wurde, gilt beim naechsten Start weiter. Die Datei darf
von Hand bearbeitet werden; unsichere oder fehlerhafte Werte fuehren zu einer klaren
Meldung statt zu einem Start.
"""

from __future__ import annotations

import re
import shutil
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .robot import DEFAULT_ROBOT
from .tts import DEFAULT_VOICE, VOICE_NAME_RE

SETTINGS_FILE = Path("einstellungen.toml")
APP_ROOT = Path(__file__).resolve().parents[3]  # Hauptordner reachy-claude (enthaelt app/)
# Erlaubte Programmnamen fuer Claude Code (kein beliebiges Programm aus einer veraenderten Datei)
CLAUDE_PROGRAM_NAMES = frozenset({"claude", "claude.exe", "claude.cmd"})
# Hostname oder IPv4/IPv6 – nichts, was in einer URL etwas anderes bedeuten koennte.
_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-:]{0,252}$")

# Reihenfolge und Kommentare beim Schreiben der Datei
_LAYOUT: dict[str, dict[str, str]] = {
    "claude": {
        "projektordner": "",
        "rechte": "read = nur lesen, edit = Dateien bearbeiten",
        "timeout_minuten": "",
        "claude_programm": "",
    },
    "reachy": {
        "roboter": "Name oder IP von Reachy",
        "stimme": "alle Stimmen: reachy-claude.ps1 voices",
        "sprecher": "nur bei Stimmen mit mehreren Sprechern",
        "bewegung": "true = Kopf und Antennen bewegen",
    },
}


class SettingsError(ValueError):
    """Einstellung fehlt oder ist ungueltig (Text ist fuer den Nutzer gedacht)."""


class MissingProjectError(SettingsError):
    """Es wurde noch kein Projektordner festgelegt."""


class Permission(StrEnum):
    """Was Claude per Sprachauftrag darf."""

    READ = "read"  # nur lesen und erklaeren
    EDIT = "edit"  # zusaetzlich Dateien im Projektordner bearbeiten (nie Shell, nie Internet)


@dataclass(frozen=True)
class ClaudeSettings:
    """Unveraenderliche Einstellungen fuer einen Lauf."""

    workdir: Path
    permission: Permission = Permission.EDIT
    claude_bin: str = "claude"
    timeout_s: float = 900.0
    max_turns: int = 30
    spoken_max_chars: int = 900


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_value(value: object) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        return _toml_string(value)
    return None  # Tabellen/Listen kommen in unserer Datei nicht vor


def _read_tolerant(path: Path) -> dict[str, dict[str, object]]:
    """Datei lesen; fehlt sie oder ist sie kaputt, wird neu angefangen (nur beim Speichern)."""
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _write(path: Path, data: dict[str, dict[str, object]]) -> None:
    lines = ["# Einstellungen fuer reachy-claude (von der App angelegt, darf bearbeitet werden)"]
    for section in [*_LAYOUT, *(name for name in data if name not in _LAYOUT)]:
        values = data.get(section) or {}
        if not values:
            continue
        lines += ["", f"[{section}]"]
        known = _LAYOUT.get(section, {})
        for key in [*(k for k in known if k in values), *(k for k in values if k not in known)]:
            rendered = _toml_value(values[key])
            if rendered is None:
                continue
            comment = known.get(key, "")
            lines.append(f"{key} = {rendered}" + (f"  # {comment}" if comment else ""))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_settings(path: Path, section: str, **values: object) -> None:
    """Werte in einem Abschnitt setzen (``None`` entfernt den Wert); alles andere bleibt erhalten."""
    data = _read_tolerant(path)
    table = dict(data.get(section, {}))
    for key, value in values.items():
        if value is None:
            table.pop(key, None)
        else:
            table[key] = value
    data[section] = table
    _write(path, data)


def save_settings(path: Path, workdir: Path, permission: Permission) -> None:
    """Projektordner und Rechte speichern; uebrige (evtl. von Hand geaenderte) Werte bleiben erhalten."""
    timeout = _read_tolerant(path).get("claude", {}).get("timeout_minuten", 15)
    update_settings(
        path,
        "claude",
        projektordner=str(workdir),
        rechte=permission.value,
        timeout_minuten=timeout if isinstance(timeout, int | float) else 15,
    )


def _inside(path: Path, folder: Path) -> bool:
    return path == folder or folder in path.parents


def _home() -> Path:
    return Path.home()


def check_workdir(workdir: Path, home: Path | None = None, app_root: Path = APP_ROOT) -> Path:
    """Projektordner ablehnen, in dem Claude Dinge aendern koennte, die spaeter Code ausfuehren.

    Verboten: ganzes Laufwerk; dein Benutzerordner selbst oder ein Ordner darueber (enthielte
    Autostart, PowerShell-Profil, AppData); alles unter AppData; der Ordner dieser App
    (Claude koennte sonst die App oder ihre Einstellungen umschreiben).
    """
    home = (home or _home()).resolve()
    if workdir == Path(workdir.anchor):
        raise SettingsError(
            "Ein ganzes Laufwerk als Projektordner ist zu riskant. Bitte einen Unterordner waehlen."
        )
    if _inside(home, workdir):
        raise SettingsError(
            f"{workdir} enthaelt deinen ganzen Benutzerordner – zu riskant. Bitte einen Projektordner waehlen, "
            "z. B. D:\\code\\mein-projekt."
        )
    if _inside(workdir, home / "AppData"):
        raise SettingsError(
            "Ordner unter AppData sind als Projektordner nicht erlaubt (Programm- und Startdateien)."
        )
    if _inside(workdir, app_root) or _inside(app_root, workdir):
        raise SettingsError(
            "Der Ordner dieser App (reachy-claude) kann nicht Projektordner sein – Claude koennte sonst die "
            "App selbst oder ihre Einstellungen veraendern."
        )
    return workdir


def claude_program(path: Path) -> str:
    """Gespeicherter Programmname fuer Claude Code (Standard ``claude``), ohne strenge Pruefung."""
    if not path.is_file():
        return "claude"
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8")).get("claude", {}).get("claude_programm")
    except tomllib.TOMLDecodeError:
        return "claude"
    return value if isinstance(value, str) and value else "claude"


def find_claude(program: str) -> str | None:
    """Claude Code finden – nur unter einem der erlaubten Namen und nie aus dem aktuellen Ordner.

    (Windows sucht Programme sonst zuerst im aktuellen Ordner; eine dort eingeschleuste
    ``claude.cmd`` wuerde gestartet.)
    """
    if Path(program).name.lower() not in CLAUDE_PROGRAM_NAMES:
        raise SettingsError(
            f"'claude_programm' = {program!r} ist nicht erlaubt: nur claude, claude.exe oder claude.cmd "
            "(gern mit vollem Pfad)."
        )
    found = shutil.which(program)
    if found is None or Path(found).resolve().parent == Path.cwd().resolve():
        return None
    return found


def load_settings(path: Path, workdir_override: Path | None = None) -> ClaudeSettings:
    """Einstellungen lesen und pruefen; ``workdir_override`` ersetzt den gespeicherten Ordner."""
    data: dict[str, object] = {}
    if path.is_file():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8")).get("claude", {})
        except tomllib.TOMLDecodeError as exc:
            raise SettingsError(f"{path} ist fehlerhaft: {exc}") from exc

    raw_dir = workdir_override or data.get("projektordner")
    if not raw_dir:
        raise MissingProjectError(
            'Kein Projektordner fuer Claude festgelegt. Einmalig mit -Projekt "D:\\pfad\\zum\\projekt" starten.'
        )
    workdir = Path(str(raw_dir)).expanduser()
    if not workdir.is_dir():
        raise SettingsError(f"Projektordner existiert nicht: {workdir}")
    workdir = check_workdir(workdir.resolve())

    try:
        permission = Permission(str(data.get("rechte", Permission.EDIT.value)).lower())
    except ValueError as exc:
        raise SettingsError("'rechte' muss read oder edit sein.") from exc

    timeout_min = data.get("timeout_minuten", 15)
    if not isinstance(timeout_min, int | float) or not 1 <= timeout_min <= 60:
        raise SettingsError("'timeout_minuten' muss zwischen 1 und 60 liegen.")

    claude_bin = find_claude(claude_program(path))
    if claude_bin is None:
        raise SettingsError(
            "Claude Code wurde nicht gefunden. Installieren (https://claude.com/claude-code) und einmal "
            "'claude' im Terminal starten, um dich anzumelden."
        )
    return ClaudeSettings(
        workdir=workdir, permission=permission, claude_bin=claude_bin, timeout_s=float(timeout_min) * 60
    )


@dataclass(frozen=True)
class ReachySettings:
    """Gemerkte Einstellungen fuer Reachy."""

    robot: str = DEFAULT_ROBOT
    voice: str = DEFAULT_VOICE
    speaker: str | None = None
    motion: bool = True


def load_reachy_settings(path: Path) -> ReachySettings:
    """Abschnitt ``[reachy]`` lesen und pruefen (fehlende Werte = Standard)."""
    data: dict[str, object] = {}
    if path.is_file():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8")).get("reachy", {})
        except tomllib.TOMLDecodeError as exc:
            raise SettingsError(f"{path} ist fehlerhaft: {exc}") from exc
    return _parse_reachy(data)


def _parse_reachy(data: dict[str, object]) -> ReachySettings:
    robot = data.get("roboter", DEFAULT_ROBOT)
    if not isinstance(robot, str) or not _HOST_RE.fullmatch(robot):
        raise SettingsError(f"'roboter' ist keine gueltige Adresse: {robot!r} (Beispiel: {DEFAULT_ROBOT})")
    voice = data.get("stimme", DEFAULT_VOICE)
    if not isinstance(voice, str) or not VOICE_NAME_RE.fullmatch(voice):
        raise SettingsError(f"'stimme' ist kein gueltiger Stimmenname: {voice!r} (Beispiel: {DEFAULT_VOICE})")
    speaker = data.get("sprecher")
    if speaker is not None and not isinstance(speaker, str | int):
        raise SettingsError("'sprecher' muss ein Name oder eine Nummer sein.")
    motion = data.get("bewegung", True)
    if not isinstance(motion, bool):
        raise SettingsError("'bewegung' muss true oder false sein.")
    return ReachySettings(
        robot=robot, voice=voice, speaker=None if speaker is None else str(speaker), motion=motion
    )


def remember_reachy(
    path: Path,
    *,
    robot: str | None = None,
    voice: str | None = None,
    speaker: str | None = None,
    motion: bool | None = None,
) -> ReachySettings:
    """Uebergebene Werte pruefen, speichern und die gesamten Reachy-Einstellungen zurueckgeben.

    Eine neue Stimme ohne Sprecher-Angabe loescht den alten Sprecher (er gehoert zur alten Stimme).
    """
    current = load_reachy_settings(path)
    changes: dict[str, object] = {}
    if robot is not None and robot != current.robot:
        changes["roboter"] = robot
    if voice is not None and voice != current.voice:
        changes["stimme"] = voice
        if speaker is None and current.speaker is not None:
            changes["sprecher"] = None
    if speaker is not None and speaker != current.speaker:
        changes["sprecher"] = speaker
    if motion is not None and motion != current.motion:
        changes["bewegung"] = motion
    if not changes:
        return current
    # erst pruefen, dann schreiben: ein Tippfehler darf die Datei nicht kaputt machen
    preview = dict(_read_tolerant(path).get("reachy", {}))
    for key, value in changes.items():
        if value is None:
            preview.pop(key, None)
        else:
            preview[key] = value
    _parse_reachy(preview)
    update_settings(path, "reachy", **changes)
    return load_reachy_settings(path)
