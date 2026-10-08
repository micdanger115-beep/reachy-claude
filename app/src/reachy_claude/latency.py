"""Verzoegerung Lautsprecher -> Mikrofon messen (Rundlauf PC -> Reachy -> PC).

Reachy spielt einen kurzen Piepton; gemessen wird, wann er im Mikrofon-Strom auftaucht.
Die Zahl bestimmt, wie lange die App nach eigenen Ansagen warten muss (Verbindung offen
halten, eigenes Echo ignorieren).
"""

from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np

from .audio import SAMPLE_RATE, Audio, level_dbfs, to_mono, tone
from .robot import RobotMedia

FRAME = SAMPLE_RATE // 100  # 10 ms
ONSET_MARGIN_DB = 15.0


def find_onset(samples: Audio, baseline_dbfs: float, margin_db: float = ONSET_MARGIN_DB) -> int | None:
    """Index des ersten 10-ms-Abschnitts, der deutlich lauter als die Ruhe ist."""
    threshold = baseline_dbfs + margin_db
    for start in range(0, samples.size - FRAME + 1, FRAME):
        if level_dbfs(samples[start : start + FRAME]) >= threshold:
            return start
    return None


def _drain(media: RobotMedia, max_chunks: int = 1000) -> None:
    """Wartende Mikrofon-Daten verwerfen (begrenzt, falls der Strom nie leer ist)."""
    for _ in range(max_chunks):
        if media.get_audio_sample() is None:
            return


def _collect(
    media: RobotMedia, seconds: float, clock: Callable[[], float], sleep: Callable[[float], None]
) -> Audio:
    chunks: list[Audio] = []
    deadline = clock() + seconds
    while clock() < deadline:
        sample = media.get_audio_sample()
        if sample is None:
            sleep(0.005)
            continue
        chunks.append(to_mono(sample))
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)


def measure_round_trip(
    media: RobotMedia,
    *,
    listen_s: float = 3.0,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> float | None:
    """Rundlauf-Verzoegerung in Sekunden, ``None`` wenn der Piepton nicht gehoert wurde."""
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    media.start_recording()
    baseline = level_dbfs(_collect(media, 0.5, clock, sleep))
    _drain(media)  # nur Mikrofon-Daten ab dem Abspielen zaehlen
    media.start_playing()
    media.push_audio_sample(tone(1000, 0.2, volume=0.5))
    heard = _collect(media, listen_s, clock, sleep)
    onset = find_onset(heard, baseline)
    return None if onset is None else onset / SAMPLE_RATE
