"""Claude Code CLI headless (``claude -p``) sicher aufrufen (uebernommen aus v1, legacy/bridge).

Sicherheitsprinzipien:
- Kein ``shell=True``; feste Argumentliste. Der (gesprochene, also nicht
  vertrauenswuerdige) Prompt geht ausschliesslich ueber stdin, nie ueber die
  Kommandozeile. Das schuetzt auch vor Argument-Injection, wenn ``claude`` unter
  Windows eine ``.cmd``-Datei ist ("BatBadBut").
- Rechte ueber ``--permission-mode dontAsk`` + ``--allowedTools``/``--disallowedTools``;
  Shell und Internet-Werkzeuge sind immer gesperrt, MCP-Server werden nicht geladen.
- Nur die eigenen Benutzer-Einstellungen gelten (``--setting-sources user``): Einstellungen
  und Hooks aus dem Projektordner (``.claude/settings.json``) koennten sonst an allen
  Werkzeug-Sperren vorbei Befehle ausfuehren (z. B. in einem fremden, manipulierten Repo).
- Steuer-Ordner (``.claude``, ``.git`` mit seinen Hooks, ``.vscode``) duerfen nie bearbeitet werden.
- Timeout und Abbruch ("Claude, stopp") beenden den ganzen Prozessbaum.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .settings import ClaudeSettings, Permission

logger = logging.getLogger(__name__)

# Darf keine fuer cmd.exe besonderen Zeichen (" % ^ & | < > !) enthalten, siehe Test.
SYSTEM_PROMPT = (
    "Du wirst per Sprache ueber den Roboter Reachy Mini bedient. Der Auftrag wurde per "
    "Spracherkennung transkribiert und kann Hoerfehler enthalten - interpretiere ihn sinnvoll, "
    "frage bei Unklarheit lieber nach, statt etwas Riskantes zu tun. Fuehre den Auftrag aus. "
    "Beende JEDE Antwort mit einer letzten Zeile, die mit SPRECHTEXT: beginnt. Danach folgen 1 bis 4 "
    "kurze, gut vorlesbare Saetze auf Deutsch, die erklaeren, was du getan oder herausgefunden hast - "
    "ohne Code, Dateipfade, URLs, Aufzaehlungszeichen oder Markdown."
)

ALWAYS_DISALLOWED: tuple[str, ...] = ("Bash", "WebFetch", "WebSearch", "NotebookEdit")
READ_TOOLS: tuple[str, ...] = ("Read", "Grep", "Glob", "LS", "TodoWrite")
EDIT_TOOLS: tuple[str, ...] = ("Edit", "MultiEdit", "Write")
# Gilt fuer alle Bearbeitungs-Werkzeuge und in jeder Ordnertiefe (gitignore-Muster).
PROTECTED_PATHS: tuple[str, ...] = ("Edit(.claude/**)", "Edit(.git/**)", "Edit(.vscode/**)")

_SESSION_ID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")


class ClaudeError(RuntimeError):
    """Claude konnte den Auftrag nicht ausfuehren (Text ist vorlesbar)."""


class ClaudeCancelled(ClaudeError):
    """Der Auftrag wurde auf Wunsch abgebrochen."""


CANCELLED_MESSAGE = "Abgebrochen. Claude hat eventuell schon einen Teil erledigt."


class ClaudeExitError(ClaudeError):
    """Die CLI ist ohne Ergebnis beendet worden (z. B. unbekannte Sitzung beim Fortsetzen)."""


ABORT_MESSAGES = {
    "error_max_turns": "Claude hat die maximale Anzahl an Arbeitsschritten erreicht, ohne fertig zu werden.",
    "error_during_execution": "Claude ist bei der Ausfuehrung auf einen Fehler gestossen.",
}


@dataclass(frozen=True)
class ClaudeResult:
    """Ergebnis eines Claude-Laufs."""

    text: str
    session_id: str | None
    is_error: bool
    duration_s: float
    cost_usd: float | None


class AskService(Protocol):
    """Schnittstelle zu Claude (im Test ersetzbar)."""

    def ask(self, prompt: str, new_conversation: bool = False) -> ClaudeResult: ...

    def cancel(self) -> bool:
        """Laufenden Auftrag abbrechen; ``True``, wenn einer lief."""
        ...


def build_argv(config: ClaudeSettings, session_id: str | None) -> list[str]:
    """Argumentliste fuer ``claude -p`` – enthaelt nie Nutzereingaben."""
    # "dontAsk": alles, was nicht ausdruecklich erlaubt ist, wird ohne Rueckfrage verweigert.
    if config.permission is Permission.EDIT:
        allowed = READ_TOOLS + EDIT_TOOLS
        disallowed = ALWAYS_DISALLOWED + PROTECTED_PATHS
    else:
        allowed = READ_TOOLS
        disallowed = ALWAYS_DISALLOWED + EDIT_TOOLS
    argv = [
        config.claude_bin,
        "-p",
        "--output-format",
        "json",
        "--max-turns",
        str(config.max_turns),
        "--permission-mode",
        "dontAsk",
        "--allowedTools",
        ",".join(allowed),
        "--disallowedTools",
        ",".join(disallowed),
        "--strict-mcp-config",
        "--setting-sources",
        "user",
        "--append-system-prompt",
        SYSTEM_PROMPT,
    ]
    if session_id is not None:
        if not _SESSION_ID_RE.fullmatch(session_id):
            raise ValueError("Ungueltige Session-ID")
        argv += ["--resume", session_id]
    return argv


def parse_cli_output(stdout: str) -> dict[str, Any]:
    """JSON-Ergebnis von ``claude -p --output-format json`` lesen."""
    text = stdout.strip()
    candidates = [text] + [line for line in reversed(text.splitlines()) if line.startswith("{")]
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        if "result" in parsed:
            return parsed
        if parsed.get("type") == "result":
            # Abbruch ohne Ergebnistext, z. B. subtype "error_max_turns".
            subtype = str(parsed.get("subtype", ""))
            message = ABORT_MESSAGES.get(subtype, "Claude hat den Auftrag abgebrochen.")
            return {**parsed, "result": message, "is_error": True}
    raise ClaudeError("Claude hat keine auswertbare Antwort geliefert.")


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        taskkill = ["taskkill", "/T", "/F", "/PID", str(proc.pid)]  # Windows-Systemprogramm
        subprocess.run(taskkill, capture_output=True, check=False)  # noqa: S607
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
    proc.kill()


class ClaudeRunner:
    """Fuehrt Auftraege nacheinander aus und haelt die laufende Claude-Sitzung."""

    def __init__(self, config: ClaudeSettings) -> None:
        self._config = config
        self._session_id: str | None = None
        self._lock = threading.Lock()  # ein Auftrag gleichzeitig
        self._proc_lock = threading.Lock()  # schuetzt _proc/_cancelled (auch waehrend ask laeuft)
        self._proc: subprocess.Popen[str] | None = None
        self._cancelled = False

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def reset(self) -> None:
        with self._lock:
            self._session_id = None

    def cancel(self) -> bool:
        """Laufenden Auftrag abbrechen (beendet den Prozessbaum); ``True``, wenn einer lief."""
        with self._proc_lock:
            proc = self._proc
            if proc is None or proc.poll() is not None:
                return False
            self._cancelled = True
        logger.info("Auftrag wird abgebrochen (PID %s).", proc.pid)
        _kill_tree(proc)
        return True

    def ask(self, prompt: str, new_conversation: bool = False) -> ClaudeResult:
        with self._lock:
            if new_conversation:
                self._session_id = None
            resume = self._session_id
            try:
                result = self._run(prompt, resume)
            except ClaudeExitError:
                if resume is None:
                    raise
                # Sitzung evtl. abgelaufen/geloescht: einmal mit frischer Sitzung probieren.
                logger.warning("Fortsetzen der Sitzung %s fehlgeschlagen, starte neu.", resume)
                result = self._run(prompt, None)
            if result.session_id:
                self._session_id = result.session_id
            return result

    def _run(self, prompt: str, session_id: str | None) -> ClaudeResult:
        argv = build_argv(self._config, session_id)
        popen_kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        started = time.monotonic()
        with self._proc_lock:
            self._cancelled = False
            proc = subprocess.Popen(
                argv,
                cwd=self._config.workdir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                **popen_kwargs,
            )
            self._proc = proc
        try:
            stdout, stderr = proc.communicate(prompt, timeout=self._config.timeout_s)
        except subprocess.TimeoutExpired as exc:
            _kill_tree(proc)
            proc.communicate()
            minutes = round(self._config.timeout_s / 60)
            raise ClaudeError(
                f"Claude hat nach {minutes} Minuten nicht geantwortet, ich habe abgebrochen."
            ) from exc
        except (BrokenPipeError, OSError):
            # Prozess wurde beendet, bevor der Auftrag ganz uebergeben war (Abbruch)
            stdout, stderr = "", ""
            proc.wait()
        finally:
            with self._proc_lock:
                self._proc = None
                cancelled = self._cancelled
        if cancelled:
            raise ClaudeCancelled(CANCELLED_MESSAGE)
        duration = time.monotonic() - started
        if proc.returncode != 0 and not stdout.strip():
            logger.error("claude beendet mit Code %s: %s", proc.returncode, stderr.strip()[-2000:])
            raise ClaudeExitError(
                "Claude Code ist mit einem Fehler beendet worden. Details stehen auf dem PC."
            )
        data = parse_cli_output(stdout)
        session = data.get("session_id")
        cost = data.get("total_cost_usd")
        return ClaudeResult(
            text=str(data.get("result") or ""),
            session_id=session if isinstance(session, str) else None,
            is_error=bool(data.get("is_error", False)),
            duration_s=duration,
            cost_usd=float(cost) if isinstance(cost, int | float) else None,
        )


def write_transcript(directory: Path, prompt: str, result: ClaudeResult) -> Path:
    """Vollstaendige Antwort lokal ablegen (nur auf dem PC, nie ins Netz)."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{time.strftime('%Y-%m-%d')}.md"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {time.strftime('%H:%M:%S')} – Session {result.session_id or '-'}\n\n")
        fh.write(f"**Auftrag:** {prompt}\n\n{result.text}\n")
    return path
