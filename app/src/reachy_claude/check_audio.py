"""Schritt 1: Audio-Test PC <-> Reachy.

1. Mikrofon: einige Sekunden aufnehmen und dabei den Pegel live anzeigen.
2. Aufnahme als WAV auf dem PC speichern.
3. Lautsprecher: zwei Testtoene, danach die Aufnahme auf Reachy abspielen.

Eine Messung "Lautsprecher -> Mikrofon" ist nicht moeglich: Reachys Audiochip (XMOS) rechnet
den eigenen Lautsprecher per Echounterdrueckung aus dem Mikrofon heraus.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .audio import SAMPLE_RATE, Audio, level_bar, level_dbfs, save_wav, silence, to_mono, tone
from .robot import RobotMedia, play

MIC_READY_TIMEOUT_S = 5.0
LEVEL_INTERVAL_S = 0.25
QUIET_DBFS = -60.0  # leiser als das: Mikrofon vermutlich stumm


@dataclass(frozen=True)
class AudioCheckResult:
    """Ergebnis des Audio-Tests."""

    mic_ok: bool
    seconds_recorded: float
    peak_dbfs: float
    saved_to: Path | None


def record(
    media: RobotMedia,
    seconds: float,
    output: Callable[[str], None],
    *,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> Audio | None:
    """Vom Roboter-Mikrofon aufnehmen und den Pegel anzeigen. ``None``: Mikrofon antwortet nicht."""
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    media.start_recording()
    try:
        started = clock()
        first = media.get_audio_sample()
        while first is None:
            if clock() - started > MIC_READY_TIMEOUT_S:
                return None
            sleep(0.01)
            first = media.get_audio_sample()

        chunks = [to_mono(first)]
        window: list[Audio] = []
        started = last_report = clock()
        while clock() - started < seconds:
            sample = media.get_audio_sample()
            if sample is None:
                sleep(0.005)
                continue
            mono = to_mono(sample)
            chunks.append(mono)
            window.append(mono)
            if clock() - last_report >= LEVEL_INTERVAL_S:
                output(f"  Mikrofon {level_bar(level_dbfs(np.concatenate(window)))}")
                window.clear()
                last_report = clock()
        return np.concatenate(chunks)
    finally:
        media.stop_recording()


def peak_dbfs(samples: Audio, window: int = SAMPLE_RATE // 10) -> float:
    """Lautester 100-ms-Abschnitt in dBFS."""
    if samples.size == 0:
        return level_dbfs(samples)
    return max(level_dbfs(samples[i : i + window]) for i in range(0, samples.size, window))


def run_audio_check(
    media: RobotMedia,
    output: Callable[[str], None],
    *,
    seconds: float = 5.0,
    save_to: Path | None = None,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> AudioCheckResult:
    """Kompletter Audio-Test; gibt Klartext-Meldungen ueber ``output`` aus."""
    rate = media.get_input_audio_samplerate()
    if rate != SAMPLE_RATE:
        output(f"Hinweis: Reachy liefert {rate} Hz statt {SAMPLE_RATE} Hz.")

    output(f"1/3 Mikrofon: Sprich jetzt {seconds:.0f} Sekunden lang etwas (z. B. zaehle bis zehn) ...")
    recording = record(media, seconds, output, clock=clock, sleep=sleep)
    if recording is None:
        output(
            "FEHLER: Reachys Mikrofon liefert keine Daten. Laeuft auf Reachy noch eine andere App "
            "(z. B. die Conversation-App)? Bitte im Dashboard stoppen und erneut versuchen."
        )
        return AudioCheckResult(False, 0.0, level_dbfs(np.zeros(0, dtype=np.float32)), None)

    peak = peak_dbfs(recording)
    duration = recording.size / SAMPLE_RATE
    if peak < QUIET_DBFS:
        output(f"WARNUNG: Aufnahme sehr leise (lautester Moment {peak:.0f} dB). Ist Reachys Mikrofon stumm?")
    else:
        output(f"OK: {duration:.1f} s aufgenommen, lautester Moment {peak:.0f} dB.")

    saved = None
    if save_to is not None:
        save_wav(save_to, recording)
        saved = save_to
        output(f"2/3 Aufnahme gespeichert: {save_to}")

    output("3/3 Lautsprecher: Reachy spielt zwei Toene und danach deine Aufnahme ab ...")
    beeps = np.concatenate([tone(660, 0.25), silence(0.15), tone(880, 0.25), silence(0.5)])
    play(media, np.concatenate([beeps, recording]), sleep=sleep)
    (sleep or time.sleep)(2.0)  # Reachy spielt verzoegert ab – nicht vor dem Ende trennen
    output(
        "Fertig. Hast du die Toene und deine Stimme vollstaendig aus Reachy gehoert? Dann funktioniert Audio."
    )
    return AudioCheckResult(True, duration, peak, saved)
