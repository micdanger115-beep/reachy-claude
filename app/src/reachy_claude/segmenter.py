"""Gesprochene Saetze aus dem Mikrofon-Strom herausschneiden (Sprachaktivitaet ueber den Pegel).

Ein Satz beginnt, wenn der Pegel deutlich ueber dem Grundrauschen liegt, und endet nach
einer kurzen Pause. Das Grundrauschen ist der leise Anteil (10 %-Quantil) der letzten
Sekunden – so passt es sich auch an Dauergeraeusche (Luefter) an, denn zwischen Woertern
gibt es immer kurze Pausen.

Waehrend eines Satzes gilt die Schwelle vom Satzbeginn (eingefroren, mit etwas
Hysterese): Sonst wuerde bei langem, fluessigem Sprechen die Schaetzung mitwandern, leise
Woerter galten als Stille und lange Auftraege wurden mittendrin abgeschnitten. Die
Schaetzung laeuft trotzdem weiter: Ist es ueber das ganze Fenster gleichmaessig laut
(Luefter springt an – Sprache schwankt dagegen stark), endet der "Satz", statt bis zur
Hoechstlaenge weiterzulaufen. Fehlerkennungen (Geraeusche) sind unkritisch: Die
Spracherkennung filtert Nicht-Sprache zusaetzlich mit Silero-VAD, und nur Saetze mit dem
Aktivierungswort gehen weiter.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from .audio import SAMPLE_RATE, Audio, level_dbfs

FRAME = SAMPLE_RATE * 30 // 1000  # 30 ms


@dataclass(frozen=True)
class SegmenterConfig:
    """Schwellwerte; Standardwerte passen zu Reachys Mikrofon im Wohnraum."""

    start_margin_db: float = (
        6.0  # so viel lauter als das Grundrauschen = Sprache (an echter Sprache abgestimmt)
    )
    continue_margin_db: float = 4.0  # im Satz genuegt weniger (Hysterese: leise Woerter halten ihn offen)
    steady_spread_db: float = (
        6.0  # schwankt der Pegel weniger (10 %..90 %), ist es Dauergeraeusch, keine Sprache
    )
    min_speech_dbfs: float = -50.0  # absolut leiser ist nie Sprache
    end_silence_s: float = 1.2  # so lange Pause beendet den Satz (Denkpausen beim Diktieren)
    min_speech_s: float = 0.3  # kuerzer = Klick/Klopfen, verwerfen
    max_speech_s: float = 120.0  # laenger = Satz zwangsweise beenden (lange Auftraege diktieren)
    pre_roll_s: float = 0.3  # Audio vor dem Start mitnehmen (erste Silbe)
    noise_window_s: float = 3.0  # Zeitraum fuer die Schaetzung des Grundrauschens
    warmup_s: float = 0.5  # so lange nach dem Start nur den Raum einmessen (keine Saetze)
    noise_quantile: float = 0.1


class SpeechSegmenter:
    """Nimmt beliebig grosse Mono-Bloecke an und liefert fertige Saetze."""

    def __init__(self, config: SegmenterConfig | None = None, initial_noise_dbfs: float = -60.0) -> None:
        self.config = config or SegmenterConfig()
        self._initial_noise = initial_noise_dbfs
        self._levels: deque[float] = deque(
            maxlen=max(1, int(self.config.noise_window_s * SAMPLE_RATE / FRAME))
        )
        self._warmup_frames = int(self.config.warmup_s * SAMPLE_RATE / FRAME)
        self._pending = np.zeros(0, dtype=np.float32)
        self._pre_roll: deque[Audio] = deque(maxlen=max(1, int(self.config.pre_roll_s * SAMPLE_RATE / FRAME)))
        self._speech: list[Audio] = []
        self._voiced_frames = 0
        self._silent_frames = 0
        self._speech_noise = initial_noise_dbfs  # Grundrauschen beim Satzbeginn (eingefroren)
        self.muted = False

    @property
    def noise_dbfs(self) -> float:
        """Aktuell geschaetztes Grundrauschen."""
        if not self._levels:
            return self._initial_noise
        return float(np.quantile(np.fromiter(self._levels, dtype=np.float64), self.config.noise_quantile))

    @property
    def in_speech(self) -> bool:
        """Laeuft gerade ein Satz?"""
        return bool(self._speech)

    def _steady_background(self) -> bool:
        """Ist das ganze Fenster gleichmaessig laut (Dauergeraeusch statt Sprache)?"""
        if len(self._levels) < (self._levels.maxlen or 0):
            return False
        cfg = self.config
        low, high = np.quantile(np.fromiter(self._levels, dtype=np.float64), [cfg.noise_quantile, 0.9])
        loud = (
            low >= self._speech_noise + cfg.continue_margin_db
        )  # selbst die leisen Anteile "klingen" wie Sprache
        return bool(loud and high - low < cfg.steady_spread_db)

    def reset(self) -> None:
        """Laufenden Satz verwerfen (z. B. wenn Reachy selbst spricht)."""
        self._speech.clear()
        self._pre_roll.clear()
        self._pending = np.zeros(0, dtype=np.float32)
        self._voiced_frames = self._silent_frames = 0

    def feed(self, samples: Audio) -> Iterator[Audio]:
        """Audio einspeisen; liefert jeden abgeschlossenen Satz."""
        if self.muted:
            return
        self._pending = np.concatenate([self._pending, samples.astype(np.float32, copy=False)])
        while self._pending.size >= FRAME:
            frame, self._pending = self._pending[:FRAME], self._pending[FRAME:]
            utterance = self._process(frame)
            if utterance is not None:
                yield utterance

    def _process(self, frame: Audio) -> Audio | None:
        cfg = self.config
        level = level_dbfs(frame)
        noise = self.noise_dbfs
        self._levels.append(level)  # Schaetzung laeuft immer weiter
        frame_s = FRAME / SAMPLE_RATE
        if self._warmup_frames > 0:  # Raum einmessen, bevor Saetze erkannt werden
            self._warmup_frames -= 1
            self._pre_roll.append(frame)
            return None

        if not self._speech:
            if level >= max(cfg.min_speech_dbfs, noise + cfg.start_margin_db):
                self._speech = [*self._pre_roll, frame]
                self._voiced_frames, self._silent_frames = 1, 0
                self._speech_noise = noise
                self._pre_roll.clear()
            else:
                self._pre_roll.append(frame)
            return None

        self._speech.append(frame)
        if level >= max(cfg.min_speech_dbfs, self._speech_noise + cfg.continue_margin_db):
            self._voiced_frames += 1
            self._silent_frames = 0
        else:
            self._silent_frames += 1

        too_long = len(self._speech) * frame_s >= cfg.max_speech_s
        background_changed = self._steady_background()
        if self._silent_frames * frame_s < cfg.end_silence_s and not too_long and not background_changed:
            return None

        utterance = np.concatenate(self._speech)
        long_enough = self._voiced_frames * frame_s >= cfg.min_speech_s
        self._speech = []
        self._voiced_frames = self._silent_frames = 0
        # Auch bei Dauergeraeusch weitergeben: die Spracherkennung filtert Nicht-Sprache selbst,
        # und falls es doch Sprache war, geht nichts verloren.
        return utterance if long_enough else None
