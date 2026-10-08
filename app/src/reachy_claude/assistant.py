"""Schritt 4: Auftrag -> Claude Code -> Antwort vorlesen.

Claude laeuft im Hintergrund; Reachy hoert dabei weiter zu und meldet sich regelmaessig
("Claude arbeitet noch."). Die vollstaendige Antwort erscheint im Terminal und in der
lokalen Mitschrift, vorgelesen wird nur der kurze Sprechtext.

Steuerwoerter (Schritt 6), jeweils nach "Claude, ...":
- "stopp" / "abbrechen" / "hoer auf": laufenden Auftrag abbrechen
- "wiederhole" / "nochmal" / "wie bitte": letzte Antwort nochmal vorlesen
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Protocol

from .claude import AskService, ClaudeCancelled, ClaudeError, ClaudeResult, write_transcript
from .motion import Mood
from .spoken import make_spoken_text
from .wakeword import clean_text

logger = logging.getLogger(__name__)

PROGRESS_INTERVAL_S = 45.0
NEW_TOPIC_RE = re.compile(r"^\s*(?:neues thema|neue unterhaltung|von vorne)\b[\s,.:;!?-]*", re.IGNORECASE)
# Reine Hoeflichkeit ist kein Auftrag ("von vorne, bitte").
FILLER_WORDS = frozenset({"bitte", "danke", "ok", "okay", "jetzt", "mal"})

# Fuer Steuerwoerter zusaetzlich ignoriert ("stopp das jetzt bitte" = "stopp")
_CONTROL_FILLER = FILLER_WORDS | {"das", "es", "sofort", "doch", "einfach", "kurz"}
STOP_PHRASES = frozenset(
    {"stopp", "stop", "halt", "abbrechen", "abbruch", "brich ab", "hör auf", "hoer auf", "aufhören",
     "aufhoeren", "cancel"}
)  # fmt: skip
REPEAT_PHRASES = frozenset(
    {"wiederhole", "wiederhol", "wiederholen", "nochmal", "noch", "noch einmal", "sag nochmal",
     "sag noch einmal", "sag noch", "wie", "was hast du gesagt", "was hat claude gesagt"}
)  # fmt: skip

BUSY_MESSAGE = "Claude arbeitet noch am letzten Auftrag. Zum Abbrechen sag: Claude, stopp."
NOTHING_TO_CANCEL = "Es laeuft gerade kein Auftrag."
NOTHING_TO_REPEAT = "Ich habe noch keine Antwort von Claude vorgelesen."

Output = Callable[[str], None]


class Control(Enum):
    """Steuerwort statt Auftrag."""

    STOP = "stop"
    REPEAT = "repeat"


def control_word(command: str) -> Control | None:
    """Ist der ganze Auftrag nur ein Steuerwort? (Laengere Saetze gehen immer an Claude.)"""
    words = [w for w in re.findall(r"\w+", command.lower()) if w not in _CONTROL_FILLER]
    phrase = " ".join(words)
    if phrase in STOP_PHRASES:
        return Control.STOP
    if phrase in REPEAT_PHRASES:
        return Control.REPEAT
    return None


class MoodSink(Protocol):
    """Etwas, das Reachys Stimmung anzeigt (``motion.Animator``)."""

    def set_mood(self, mood: Mood) -> None: ...


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
        mood: MoodSink | None = None,
    ) -> None:
        self._claude = claude
        self._voice = voice
        self._output = output
        self._spoken_max_chars = spoken_max_chars
        self._transcript_dir = transcript_dir
        self._progress_interval_s = progress_interval_s
        self._fresh_conversation = False
        self._mood = mood
        self._last_spoken: str | None = None
        self._worker: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        """Laeuft gerade ein Auftrag?"""
        return self._worker is not None and self._worker.is_alive()

    def submit(self, command: str) -> None:
        """Auftrag aus dem Zuhoeren annehmen, ohne zu blockieren (Steuerwoerter sofort)."""
        control = control_word(command)
        if control is Control.STOP:
            self.cancel()
        elif control is Control.REPEAT:
            self.repeat()
        elif self.busy:
            self._voice.say(BUSY_MESSAGE)
        else:
            self._worker = threading.Thread(
                target=self._handle_safely, args=(command,), name="auftrag", daemon=True
            )
            self._worker.start()

    def cancel(self) -> None:
        """Laufenden Auftrag abbrechen (Reachy sagt "Abgebrochen", sobald Claude beendet ist)."""
        if not (self.busy and self._claude.cancel()):
            self._voice.say(NOTHING_TO_CANCEL)

    def repeat(self) -> None:
        """Letzte vorgelesene Antwort nochmal sprechen."""
        self._voice.say(self._last_spoken or NOTHING_TO_REPEAT)

    def shutdown(self, timeout_s: float = 5.0) -> None:
        """Beim Beenden: laufenden Auftrag still abbrechen und kurz auf den Thread warten."""
        worker = self._worker
        if worker is not None and worker.is_alive():
            self._claude.cancel()
            worker.join(timeout=timeout_s)

    def _handle_safely(self, command: str) -> None:
        try:
            self.handle(command)
        except Exception:  # der Hintergrund-Thread darf nie still sterben
            logger.exception("Auftrag fehlgeschlagen")
            self._voice.say("Bei dem Auftrag ist ein unerwarteter Fehler passiert.")

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
        self._last_spoken = make_spoken_text(result.text, self._spoken_max_chars)
        self._voice.say(self._last_spoken)

    def _ask_with_progress(self, prompt: str, new_conversation: bool) -> ClaudeResult | None:
        box: dict[str, ClaudeResult | ClaudeError] = {}

        def work() -> None:
            try:
                box["result"] = self._claude.ask(prompt, new_conversation)
            except ClaudeError as exc:
                box["result"] = exc

        worker = threading.Thread(target=work, name="claude", daemon=True)
        if self._mood is not None:
            self._mood.set_mood(Mood.THINKING)
        try:
            worker.start()
            while True:
                worker.join(timeout=self._progress_interval_s)
                if not worker.is_alive():
                    break
                self._voice.say("Claude arbeitet noch.")
        finally:
            if self._mood is not None:
                self._mood.set_mood(Mood.IDLE)

        outcome = box.get("result")
        if isinstance(outcome, ClaudeCancelled):
            self._output("        (Auftrag abgebrochen)")
            self._voice.say(str(outcome))
            return None
        if isinstance(outcome, ClaudeError):
            self._voice.say(str(outcome))
            return None
        if outcome is None:  # unerwarteter Fehler im Thread (wurde bereits geloggt)
            self._voice.say("Bei der Anfrage an Claude ist ein unerwarteter Fehler passiert.")
            return None
        return outcome
