"""Reine Audio-Hilfsfunktionen (ohne Roboter testbar).

Format im ganzen Programm: float32, Werte -1..1, 16 kHz (Reachys Mikrofon und Lautsprecher).
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np
import numpy.typing as npt

SAMPLE_RATE = 16_000
SILENCE_DBFS = -96.0

Audio = npt.NDArray[np.float32]


def to_mono(samples: npt.NDArray[np.floating]) -> Audio:
    """Stereo (n, 2) oder Mono (n,) zu Mono (n,) float32."""
    data = np.asarray(samples, dtype=np.float32)
    if data.ndim == 2:
        data = data.mean(axis=1, dtype=np.float32)
    return data.reshape(-1)


def level_dbfs(samples: Audio) -> float:
    """Lautstaerke (RMS) in dBFS; 0 = maximal, -96 = Stille."""
    if samples.size == 0:
        return SILENCE_DBFS
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    if rms <= 0.0:
        return SILENCE_DBFS
    return max(SILENCE_DBFS, 20.0 * math.log10(rms))


def level_bar(dbfs: float, width: int = 30) -> str:
    """Pegelanzeige als Text, z. B. ``[##########--------------------] -38 dB``."""
    filled = round(width * min(1.0, max(0.0, (dbfs + 60.0) / 60.0)))  # -60..0 dB
    return f"[{'#' * filled}{'-' * (width - filled)}] {dbfs:5.0f} dB"


def tone(freq_hz: float, seconds: float, volume: float = 0.3, sample_rate: int = SAMPLE_RATE) -> Audio:
    """Sinuston mit kurzem Ein-/Ausblenden (kein Knacken)."""
    n = int(seconds * sample_rate)
    t = np.arange(n, dtype=np.float32) / sample_rate
    signal = (volume * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float32)
    fade = min(n // 2, int(0.01 * sample_rate))
    if fade > 0:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        signal[:fade] *= ramp
        signal[-fade:] *= ramp[::-1]
    return signal


def silence(seconds: float, sample_rate: int = SAMPLE_RATE) -> Audio:
    """Stille der gegebenen Laenge."""
    return np.zeros(int(seconds * sample_rate), dtype=np.float32)


def save_wav(path: Path, samples: Audio, sample_rate: int = SAMPLE_RATE) -> None:
    """Mono-Audio als 16-Bit-WAV speichern."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def load_wav(path: Path) -> tuple[Audio, int]:
    """16-Bit-Mono-WAV laden (fuer Tests und Wiedergabe)."""
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2:
            raise ValueError("Nur 16-Bit-WAV wird unterstuetzt.")
        frames = wav.readframes(wav.getnframes())
        channels = wav.getnchannels()
        rate = wav.getframerate()
    data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32767.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1, dtype=np.float32)
    return data, rate
