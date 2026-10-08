"""Nachgebauter Reachy (nur Audio) und simulierte Uhr fuer Tests."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from reachy_claude.audio import SAMPLE_RATE


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeMedia:
    """Liefert Stereo-Bloecke (20 ms) eines Sinus; jeder Block laesst die Uhr weiterlaufen."""

    CHUNK = SAMPLE_RATE // 50

    def __init__(
        self, clock: FakeClock, amplitude: float = 0.3, silent_mic: bool = False, rate: int = SAMPLE_RATE
    ):
        self.clock = clock
        self.amplitude = amplitude
        self.silent_mic = silent_mic
        self.rate = rate
        self.pushed: list[npt.NDArray[np.float32]] = []
        self.calls: list[str] = []
        self._phase = 0

    def start_recording(self) -> None:
        self.calls.append("start_recording")

    def stop_recording(self) -> None:
        self.calls.append("stop_recording")

    def get_audio_sample(self) -> npt.NDArray[np.float32] | None:
        if self.silent_mic:
            return None
        t = (np.arange(self.CHUNK) + self._phase) / SAMPLE_RATE
        self._phase += self.CHUNK
        mono = (self.amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        self.clock.now += self.CHUNK / SAMPLE_RATE
        return np.stack([mono, mono], axis=1)

    def get_input_audio_samplerate(self) -> int:
        return self.rate

    def start_playing(self) -> None:
        self.calls.append("start_playing")

    def stop_playing(self) -> None:
        self.calls.append("stop_playing")

    def push_audio_sample(self, data: npt.NDArray[np.float32]) -> None:
        self.pushed.append(data)

    def get_output_audio_samplerate(self) -> int:
        return self.rate
