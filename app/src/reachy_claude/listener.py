"""Zuhoeren: Mikrofon -> Saetze -> Text -> Aktivierungswort -> Auftrag.

Ein eigener Thread liest ununterbrochen Reachys Mikrofon (damit beim Erkennen nichts
verloren geht); der Hauptthread schneidet Saetze heraus, erkennt sie und entscheidet,
ob ein Auftrag fuer Claude dabei ist.

Waehrend Reachy selbst spricht (im ``on_command``-Handler) und kurz danach wird alles
verworfen, was das Mikrofon aufnimmt – sonst hoert Reachy sich selbst zu.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable

from .audio import Audio, to_mono
from .robot import RobotMedia, play
from .segmenter import SpeechSegmenter
from .stt import Transcriber
from .tts import Speaker
from .wakeword import Wake, clean_text, parse_wake

WAKE_FOLLOW_UP_S = 8.0  # nach "Claude." so lange auf den Auftrag warten
DEAF_AFTER_RESPONSE_S = (
    1.5  # Reachy spielt verzoegert ab (Netz + Puffer) – Rest der eigenen Ansage ignorieren
)

Output = Callable[[str], None]
CommandHandler = Callable[[str], None]


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

    def __init__(self, output: Output, clock: Callable[[], float] | None = None) -> None:
        self._output = output
        self._clock = clock or time.monotonic
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
) -> None:
    """Zuhoeren, bis ``stop`` gesetzt wird."""
    clock = clock or time.monotonic
    segmenter = segmenter or SpeechSegmenter()
    parser = parser or CommandParser(output)
    deaf_until = 0.0
    chunks: queue.Queue[Audio] = queue.Queue()
    reader = threading.Thread(
        target=read_microphone, args=(media, chunks, stop), name="mikrofon", daemon=True
    )
    reader.start()
    try:
        while not stop.is_set() or not chunks.empty():
            try:
                chunk = chunks.get(timeout=0.1)
            except queue.Empty:
                continue
            if clock() < deaf_until:
                continue
            for utterance in segmenter.feed(chunk):
                command = parser.handle(transcriber.transcribe(utterance))
                if command is None:
                    continue
                on_command(command)  # darf Reachy sprechen lassen (blockiert)
                # Alles verwerfen, was Reachy waehrenddessen von sich selbst gehoert hat.
                _drain(chunks)
                segmenter.reset()
                deaf_until = clock() + DEAF_AFTER_RESPONSE_S
                break
    finally:
        stop.set()
        reader.join(timeout=2.0)


def _drain(chunks: queue.Queue[Audio]) -> None:
    while True:
        try:
            chunks.get_nowait()
        except queue.Empty:
            return
