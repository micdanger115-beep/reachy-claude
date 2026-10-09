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

import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Protocol, cast

from .audio import SAMPLE_RATE, Audio, to_mono
from .robot import RobotMedia, play
from .segmenter import SpeechSegmenter
from .stt import Transcriber
from .tts import Speaker
from .wakeword import Wake, clean_text, parse_wake

logger = logging.getLogger(__name__)

WAKE_FOLLOW_UP_S = 8.0  # nach "Claude." so lange auf den Auftrag warten
# Nachlauf: nach "Claude, ..." so lange auf weitere Saetze warten, die zum Auftrag gehoeren
# (lange Auftraege mit Denkpausen). Steuerwoerter ("stopp") gehen sofort raus.
FOLLOW_ON_S = 2.0
# Liefert das Mikrofon nichts (Netz stockt), geht der Auftrag spaetestens so viel spaeter (Uhrzeit) raus
FOLLOW_ON_EXTRA_S = 3.0


class MicrophoneError(RuntimeError):
    """Reachys Mikrofon liefert nicht mehr (Verbindung verloren)."""


_STOPPED = object()  # Marke in der Warteschlange: der Mikrofon-Thread ist beendet
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


Captured = tuple[Audio, bool]  # (Mono-Block, bei der Aufnahme weggehoert?)


def read_microphone(
    media: RobotMedia,
    chunks: queue.Queue[Captured | object],
    stop: threading.Event,
    muted: Callable[[], bool] | None = None,
) -> None:
    """Thread: Mikrofon lesen und Mono-Bloecke in die Warteschlange legen.

    Ob weggehoert werden muss (Reachy spricht), wird hier beim Aufnehmen festgehalten – nicht
    erst bei der Verarbeitung, die waehrend einer langen Spracherkennung hinterherhinkt.
    Faellt das Mikrofon aus, landet ein Fehler in der Warteschlange (sonst hoerte die App
    still nie wieder etwas).
    """
    try:
        media.start_recording()
        while not stop.is_set():
            sample = media.get_audio_sample()
            if sample is None:
                time.sleep(0.005)
                continue
            chunks.put((to_mono(sample), muted is not None and muted()))
    except Exception as exc:  # Verbindung weg o. ae.: an die Hauptschleife melden
        chunks.put(MicrophoneError(f"Reachys Mikrofon liefert nicht mehr ({type(exc).__name__}: {exc})"))
    finally:
        chunks.put(_STOPPED)
        try:
            media.stop_recording()
        except Exception as exc:  # beim Aufraeumen nach einem Ausfall egal
            logger.debug("stop_recording fehlgeschlagen: %s", exc)


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
    follow_on_max_s: float | None = None,
    immediate: Callable[[str], bool] | None = None,
    cancels: Callable[[str], bool] | None = None,
    on_discard: Callable[[], None] | None = None,
) -> None:
    """Zuhoeren, bis ``stop`` gesetzt wird.

    ``on_event`` meldet Sprechbeginn/-ende (fuer Bewegungen); solange ``muted()`` wahr ist
    (Reachy spricht), wird nicht zugehoert. Ein Auftrag geht erst ``follow_on_s`` nach dem
    letzten Satz an ``on_command``; was du bis dahin weitersprichst, wird angehaengt.
    Auftraege, fuer die ``immediate(auftrag)`` wahr ist, gehen sofort raus – auch waehrend des
    Nachlaufs; ist so ein Steuerwort ``cancels(auftrag)`` (z. B. "stopp"), wird der wartende
    Auftrag verworfen und ``on_discard()`` gerufen, statt das Steuerwort an den Auftrag zu haengen.
    Faellt das Mikrofon aus, endet ``listen`` mit ``MicrophoneError``.
    """
    clock = clock or time.monotonic
    segmenter = segmenter or SpeechSegmenter()
    parser = parser or CommandParser(output)
    emit = on_event or (lambda _event: None)
    deaf_until = 0.0
    was_speaking = False
    max_wait_s = follow_on_max_s if follow_on_max_s is not None else follow_on_s + FOLLOW_ON_EXTRA_S
    chunks: queue.Queue[Captured | object] = queue.Queue()
    reader = threading.Thread(
        target=read_microphone, args=(media, chunks, stop, muted), name="mikrofon", daemon=True
    )
    reader.start()
    pending: str | None = None  # verstandener Auftrag, der noch auf Fortsetzung wartet
    quiet_s = 0.0  # Audio ohne neue Sprache seit dem letzten Satz des wartenden Auftrags (Audiozeit)
    pending_since = 0.0  # Uhrzeit des letzten Satzes des wartenden Auftrags (Obergrenze, falls Audio stockt)

    def end_speech() -> None:
        nonlocal was_speaking
        if was_speaking:
            emit("speech_end")
        was_speaking = False

    def dispatch(command: str) -> None:
        nonlocal deaf_until
        end_speech()
        on_command(command)  # darf Reachy sprechen lassen (blockiert)
        # Alles verwerfen, was Reachy waehrenddessen von sich selbst gehoert hat.
        _drain(chunks)
        segmenter.reset()
        deaf_until = clock() + DEAF_AFTER_RESPONSE_S

    try:
        while not stop.is_set() or not chunks.empty():
            if pending is not None and (
                quiet_s >= follow_on_s or (not segmenter.in_speech and clock() - pending_since >= max_wait_s)
            ):
                ready, pending = pending, None
                dispatch(ready)
            try:
                item = chunks.get(timeout=0.1)
            except queue.Empty:
                continue
            if isinstance(item, MicrophoneError):
                raise item
            if item is _STOPPED:
                if stop.is_set():
                    continue
                raise MicrophoneError("Reachys Mikrofon hat aufgehoert zu liefern.")
            chunk, muted_at_capture = cast("Captured", item)
            if muted_at_capture or clock() < deaf_until:
                segmenter.reset()  # angefangenen Satz und Vorlauf (Reachys eigene Stimme) verwerfen
                end_speech()
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
                    control = _control_command(text, immediate)
                    if control is not None and cancels is not None and cancels(control):
                        output(f"Du:     {clean_text(text)}")
                        output("        (Auftrag verworfen – geht nicht an Claude)")
                        pending = None
                        if on_discard is not None:
                            on_discard()
                        continue
                    if control is not None:
                        output(f"Du:     {clean_text(text)}")
                        dispatch(control)  # z. B. "wiederhole"; der wartende Auftrag bleibt
                        pending_since = clock()
                        break
                    pending = _append(pending, text, output)
                    quiet_s, pending_since = 0.0, clock()
                    continue
                command = parser.handle(text)
                if command is None:
                    continue
                if follow_on_s <= 0 or (immediate is not None and immediate(command)):
                    dispatch(command)
                    break
                pending, quiet_s, pending_since = command, 0.0, clock()
                output("        (hoere weiter zu – sprich ruhig weiter, sonst geht es gleich los)")
        if pending is not None:  # beim regulaeren Ende nichts Verstandenes verlieren
            dispatch(pending)
    finally:
        stop.set()
        reader.join(timeout=2.0)


def _control_command(text: str, immediate: Callable[[str], bool] | None) -> str | None:
    """Ist ``text`` ein "Claude, <Steuerwort>"? Dann das Steuerwort, sonst ``None``."""
    if immediate is None:
        return None
    result = parse_wake(text)
    if result.kind is Wake.COMMAND and immediate(result.command):
        return result.command
    return None


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


def _drain(chunks: queue.Queue[Captured | object]) -> None:
    """Aufgenommenes Audio verwerfen – Meldungen des Mikrofon-Threads (Ende/Fehler) bleiben erhalten."""
    kept: list[object] = []
    while True:
        try:
            item = chunks.get_nowait()
        except queue.Empty:
            break
        if not isinstance(item, tuple):
            kept.append(item)
    for item in kept:
        chunks.put(item)
