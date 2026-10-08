"""Einstellungen fuer Claude: Projektordner, Rechte, Zeitlimit (``app/einstellungen.toml``).

Die Datei wird beim ersten ``listen --project <Ordner>`` angelegt und danach wiederverwendet.
Unsichere oder fehlerhafte Werte fuehren zu einer klaren Meldung statt zu einem Start.
"""

from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

SETTINGS_FILE = Path("einstellungen.toml")


class SettingsError(ValueError):
    """Einstellung fehlt oder ist ungueltig (Text ist fuer den Nutzer gedacht)."""


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


def save_settings(path: Path, workdir: Path, permission: Permission) -> None:
    """Projektordner und Rechte speichern; uebrige (evtl. von Hand geaenderte) Werte bleiben erhalten."""
    existing: dict[str, object] = {}
    if path.is_file():
        try:
            existing = tomllib.loads(path.read_text(encoding="utf-8")).get("claude", {})
        except tomllib.TOMLDecodeError:
            existing = {}
    timeout = existing.get("timeout_minuten", 15)
    lines = [
        "# Einstellungen fuer reachy-claude (von der App angelegt, darf bearbeitet werden)",
        "[claude]",
        f"projektordner = {_toml_string(str(workdir))}",
        f"rechte = {_toml_string(permission.value)}  # read = nur lesen, edit = Dateien bearbeiten",
        f"timeout_minuten = {timeout if isinstance(timeout, int | float) else 15}",
    ]
    if isinstance(existing.get("claude_programm"), str):
        lines.append(f"claude_programm = {_toml_string(str(existing['claude_programm']))}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
        raise SettingsError(
            'Kein Projektordner fuer Claude festgelegt. Einmalig mit -Projekt "D:\\pfad\\zum\\projekt" starten.'
        )
    workdir = Path(str(raw_dir)).expanduser()
    if not workdir.is_dir():
        raise SettingsError(f"Projektordner existiert nicht: {workdir}")
    workdir = workdir.resolve()
    if workdir == Path(workdir.anchor):
        raise SettingsError(
            "Ein ganzes Laufwerk als Projektordner ist zu riskant. Bitte einen Unterordner waehlen."
        )

    try:
        permission = Permission(str(data.get("rechte", Permission.EDIT.value)).lower())
    except ValueError as exc:
        raise SettingsError("'rechte' muss read oder edit sein.") from exc

    timeout_min = data.get("timeout_minuten", 15)
    if not isinstance(timeout_min, int | float) or not 1 <= timeout_min <= 60:
        raise SettingsError("'timeout_minuten' muss zwischen 1 und 60 liegen.")

    claude_bin = shutil.which(str(data.get("claude_programm", "claude")))
    if claude_bin is None:
        raise SettingsError(
            "Claude Code wurde nicht gefunden. Installieren (https://claude.com/claude-code) und einmal "
            "'claude' im Terminal starten, um dich anzumelden."
        )
    return ClaudeSettings(
        workdir=workdir, permission=permission, claude_bin=claude_bin, timeout_s=float(timeout_min) * 60
    )
