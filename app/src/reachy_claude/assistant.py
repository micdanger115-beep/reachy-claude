"""Schritt 4: Auftrag -> Claude Code -> Antwort vorlesen.

Claude laeuft in einem eigenen Thread; Reachy meldet sich in der Zwischenzeit regelmaessig
("Claude arbeitet noch."). Die vollstaendige Antwort erscheint im Terminal und in der
lokalen Mitschrift, vorgelesen wird nur der kurze Sprechtext.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .claude import AskService, ClaudeError, ClaudeResult, write_transcript
from .spoken import make_spoken_text
from .wakeword import clean_text

logger = logging.getLogger(__name__)

PROGRESS_INTERVAL_S = 45.0
NEW_TOPIC_RE = re.compile(r"^\s*(?:neues thema|neue unterhaltung|von vorne)\b[\s,.:;!?-]*", re.IGNORECASE)
# Reine Hoeflichkeit ist kein Auftrag ("von vorne, bitte").
FILLER_WORDS = frozenset({"bitte", "danke", "ok", "okay", "jetzt", "mal"})

Output = Callable[[str], None]


class Speaks(Protocol):
    """Etwas, das Reachy sprechen laesst (``listener.Voice``)."""

    def say(self, text: str) -> None: ...


class PrintOnly:
    """Ersatz, wenn Reachy nicht sprechen soll: nur Textausgabe."""

    def __init__(self, output: Output) -> None:
        self._output = output

    def say(self, text: str) -> None:
        self._output(f"Reachy: {clean_text(text)}")


_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def show_answer(output: Output, text: str) -> None:
    """Vollstaendige Claude-Antwort zeilenweise anzeigen: Steuerzeichen raus, Einrueckung (Code) bleibt."""
    output("Claude:")
    for line in text.splitlines() or [""]:
        output(f"  {_CONTROL_RE.sub('', line.replace(chr(9), '    ')).rstrip()}")


class ClaudeAssistant:
    """Verarbeitet erkannte Auftraege nacheinander (einer gleichzeitig)."""

    def __init__(
        self,
        claude: AskService,
        voice: Speaks,
        output: Output,
        *,
        spoken_max_chars: int = 900,
        transcript_dir: Path | None = Path("mitschriften"),
        progress_interval_s: float = PROGRESS_INTERVAL_S,
    ) -> None:
        self._claude = claude
        self._voice = voice
        self._output = output
        self._spoken_max_chars = spoken_max_chars
        self._transcript_dir = transcript_dir
        self._progress_interval_s = progress_interval_s
        self._fresh_conversation = False

    def handle(self, command: str) -> None:
        """Einen Auftrag ausfuehren (blockiert, bis Claude fertig ist)."""
        prompt = command
        match = NEW_TOPIC_RE.match(command)
        if match:
            self._fresh_conversation = True
            prompt = command[match.end() :].strip()
            words = re.findall(r"\w+", prompt.lower())
            if all(word in FILLER_WORDS for word in words):
                self._voice.say("Okay, neues Thema. Was soll Claude tun?")
                return

        self._voice.say("Ich frage Claude.")
        result = self._ask_with_progress(prompt, new_conversation=self._fresh_conversation)
        if result is None:
            return
        self._fresh_conversation = False
        show_answer(self._output, result.text)
        if self._transcript_dir is not None:
            try:
                write_transcript(self._transcript_dir, prompt, result)
            except OSError as exc:
                logger.error("Mitschrift konnte nicht geschrieben werden: %s", exc)
        self._voice.say(make_spoken_text(result.text, self._spoken_max_chars))

    def _ask_with_progress(self, prompt: str, new_conversation: bool) -> ClaudeResult | None:
        box: dict[str, ClaudeResult | ClaudeError] = {}

        def work() -> None:
            try:
                box["result"] = self._claude.ask(prompt, new_conversation)
            except ClaudeError as exc:
                box["result"] = exc

        worker = threading.Thread(target=work, name="claude", daemon=True)
        worker.start()
        while True:
            worker.join(timeout=self._progress_interval_s)
            if not worker.is_alive():
                break
            self._voice.say("Claude arbeitet noch.")

        outcome = box.get("result")
        if isinstance(outcome, ClaudeError):
            self._voice.say(str(outcome))
            return None
        if outcome is None:  # unerwarteter Fehler im Thread (wurde bereits geloggt)
            self._voice.say("Bei der Anfrage an Claude ist ein unerwarteter Fehler passiert.")
            return None
        return outcome
