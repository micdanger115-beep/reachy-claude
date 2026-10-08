"""Zuhoeren: Mikrofon -> Saetze -> Text -> Aktivierungswort -> Auftrag.

Ein eigener Thread liest ununterbrochen Reachys Mikrofon (damit beim Erkennen nichts
verloren geht); der Hauptthread schneidet Saetze heraus, erkennt sie und entscheidet,
ob ein Auftrag fuer Claude dabei ist.

Waehrend Reachy selbst spricht und kurz danach wird alles verworfen, was das Mikrofon
aufnimmt – sonst hoert Reachy sich selbst zu ("Claude arbeitet noch." beginnt mit "Claude"!).
Das gilt fuer Ansagen im ``on_command``-Handler und – ueber ``SpeechGate`` – auch fuer
Ansagen aus dem Hintergrund, waehrend Claude arbeitet.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import Protocol

from .audio import SAMPLE_RATE, Audio, to_mono
from .robot import RobotMedia, play
from .segmenter import SpeechSegmenter
from .stt import Transcriber
from .tts import Speaker
from .wakeword import Wake, clean_text, parse_wake

WAKE_FOLLOW_UP_S = 8.0  # nach "Claude." so lange auf den Auftrag warten
# Nachlauf: nach "Claude, ..." so lange auf weitere Saetze warten, die zum Auftrag gehoeren
# (lange Auftraege mit Denkpausen). Steuerwoerter ("stopp") gehen sofort raus.
FOLLOW_ON_S = 2.0
DEAF_AFTER_RESPONSE_S = (
    1.5  # Reachy spielt verzoegert ab (Netz + Puffer) – Rest der eigenen Ansage ignorieren
)

Output = Callable[[str], None]
CommandHandler = Callable[[str], None]
EventHandler = Callable[[str], None]  # "speech_start", "speech_end", "wake"


class _Says(Protocol):
    def say(self, text: str) -> None: ...


class SpeechGate:
    """Sorgt dafuer, dass immer nur ein Satz gleichzeitig gesprochen wird, und meldet dem
    Zuhoeren, wann es weghoeren muss (waehrend Reachy spricht und kurz danach)."""

    def __init__(
        self,
        voice: _Says,
        *,
        clock: Callable[[], float] | None = None,
        after_s: float = DEAF_AFTER_RESPONSE_S,
    ) -> None:
        self._voice = voice
        self._clock = clock or time.monotonic
        self._after_s = after_s
        self._lock = threading.Lock()
        self._speaking = False
        self._quiet_until = 0.0

    def say(self, text: str) -> None:
        with self._lock:
            self._speaking = True
            try:
                self._voice.say(text)
            finally:
                self._quiet_until = self._clock() + self._after_s
                self._speaking = False

    def muted(self) -> bool:
        """Soll das Zuhoeren gerade weghoeren?"""
        return self._speaking or self._clock() < self._quiet_until


class Voice:
    """Laesst Reachy einen Text sprechen (Sprachausgabe + Lautsprecher)."""

    def __init__(self, speaker: Speaker, media: RobotMedia, output: Output) -> None:
        self._speaker = speaker
        self._media = media
        self._output = output

    def say(self, text: str) -> None:
        """Text anzeigen und auf Reachys Lautsprecher sprechen (blockiert bis zum Ende)."""
        text = clean_text(text)
        if not text:
            return
        self._output(f"Reachy: {text}")
        audio = self._speaker.synthesize(text)
        if audio.size:
            play(self._media, audio)


class CommandParser:
    """Entscheidet pro erkanntem Satz, ob (und welcher) Auftrag an Claude geht."""

    def __init__(
        self,
        output: Output,
        clock: Callable[[], float] | None = None,
        on_wake: Callable[[], None] | None = None,
    ) -> None:
        self._output = output
        self._clock = clock or time.monotonic
        self._on_wake = on_wake
        self._awaiting_until: float | None = None

    def handle(self, text: str) -> str | None:
        """Satz verarbeiten; gibt den Auftrag zurueck oder ``None``."""
        text = clean_text(text)
        if not text:
            return None
        self._output(f"Du:     {text}")
        result = parse_wake(text)
        now = self._clock()
        awaiting = self._awaiting_until is not None and now <= self._awaiting_until
        self._awaiting_until = None

        if result.kind is not Wake.NONE and self._on_wake is not None:
            self._on_wake()
        if result.kind is Wake.COMMAND:
            command = result.command
        elif result.kind is Wake.WAKE_ONLY:
            self._awaiting_until = now + WAKE_FOLLOW_UP_S
            self._output("        (Ja? Ich hoere – sag deinen Auftrag.)")
            return None
        elif awaiting:
            command = text
        else:
            self._output("        (ignoriert – beginnt nicht mit 'Claude')")
            return None
        self._output(f"  -> Auftrag fuer Claude: {command}")
        return command


def read_microphone(media: RobotMedia, chunks: queue.Queue[Audio], stop: threading.Event) -> None:
    """Thread: Mikrofon lesen und Mono-Bloecke in die Warteschlange legen."""
    media.start_recording()
    try:
        while not stop.is_set():
            sample = media.get_audio_sample()
            if sample is None:
                time.sleep(0.005)
                continue
            chunks.put(to_mono(sample))
    finally:
        media.stop_recording()


def listen(
    media: RobotMedia,
    transcriber: Transcriber,
    output: Output,
    on_command: CommandHandler,
    stop: threading.Event,
    *,
    segmenter: SpeechSegmenter | None = None,
    parser: CommandParser | None = None,
    clock: Callable[[], float] | None = None,
    on_event: EventHandler | None = None,
    muted: Callable[[], bool] | None = None,
    follow_on_s: float = FOLLOW_ON_S,
    immediate: Callable[[str], bool] | None = None,
) -> None:
    """Zuhoeren, bis ``stop`` gesetzt wird.

    ``on_event`` meldet Sprechbeginn/-ende (fuer Bewegungen); solange ``muted()`` wahr ist
    (Reachy spricht), wird nicht zugehoert. Ein Auftrag geht erst ``follow_on_s`` nach dem
    letzten Satz an ``on_command``; was du bis dahin weitersprichst, wird angehaengt.
    Auftraege, fuer die ``immediate(auftrag)`` wahr ist, gehen sofort raus.
    """
    clock = clock or time.monotonic
    segmenter = segmenter or SpeechSegmenter()
    parser = parser or CommandParser(output)
    emit = on_event or (lambda _event: None)
    deaf_until = 0.0
    was_speaking = False
    chunks: queue.Queue[Audio] = queue.Queue()
    reader = threading.Thread(
        target=read_microphone, args=(media, chunks, stop), name="mikrofon", daemon=True
    )
    reader.start()
    pending: str | None = None  # verstandener Auftrag, der noch auf Fortsetzung wartet
    quiet_s = 0.0  # Audio ohne neue Sprache seit dem letzten Satz des wartenden Auftrags (Audiozeit)

    def dispatch(command: str) -> None:
        nonlocal was_speaking, deaf_until
        on_command(command)  # darf Reachy sprechen lassen (blockiert)
        # Alles verwerfen, was Reachy waehrenddessen von sich selbst gehoert hat.
        _drain(chunks)
        segmenter.reset()
        was_speaking = False
        deaf_until = clock() + DEAF_AFTER_RESPONSE_S

    try:
        while not stop.is_set() or not chunks.empty():
            if pending is not None and quiet_s >= follow_on_s:
                ready, pending = pending, None
                dispatch(ready)
            try:
                chunk = chunks.get(timeout=0.1)
            except queue.Empty:
                continue
            if clock() < deaf_until or (muted is not None and muted()):
                segmenter.reset()  # angefangenen Satz und Vorlauf (Reachys eigene Stimme) verwerfen
                was_speaking = False
                continue
            utterances = list(segmenter.feed(chunk))
            if segmenter.in_speech and not was_speaking:
                emit("speech_start")
            if was_speaking and not segmenter.in_speech:
                emit("speech_end")
            was_speaking = segmenter.in_speech
            if pending is not None:
                quiet_s = 0.0 if segmenter.in_speech else quiet_s + chunk.size / SAMPLE_RATE
            for utterance in utterances:
                text = transcriber.transcribe(utterance)
                if pending is not None:
                    pending = _append(pending, text, output)
                    quiet_s = 0.0
                    continue
                command = parser.handle(text)
                if command is None:
                    continue
                if follow_on_s <= 0 or (immediate is not None and immediate(command)):
                    dispatch(command)
                    break
                pending, quiet_s = command, 0.0
                output("        (hoere weiter zu – sprich ruhig weiter, sonst geht es gleich los)")
        if pending is not None:  # beim regulaeren Ende nichts Verstandenes verlieren
            dispatch(pending)
    finally:
        stop.set()
        reader.join(timeout=2.0)


def _append(command: str, text: str, output: Output) -> str:
    """Fortsetzung an den wartenden Auftrag haengen (ein wiederholtes "Claude," wird entfernt)."""
    text = clean_text(text)
    if not text:
        return command
    result = parse_wake(text)
    if result.kind is Wake.COMMAND:
        text = result.command
    elif result.kind is Wake.WAKE_ONLY:
        return command
    output(f"Du:     {text}")
    combined = f"{command} {text}"
    output(f"  -> Auftrag (ergaenzt): {combined}")
    return combined


def _drain(chunks: queue.Queue[Audio]) -> None:
    while True:
        try:
            chunks.get_nowait()
        except queue.Empty:
            return
