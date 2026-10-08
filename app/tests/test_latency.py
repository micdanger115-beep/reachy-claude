import numpy as np
import pytest
from fakes import FakeClock

from reachy_claude.audio import SAMPLE_RATE, Audio
from reachy_claude.latency import find_onset, measure_round_trip


class EchoMedia:
    """Mikrofon in Echtzeit (gemaess Uhr); Abgespieltes taucht nach ``delay_s`` im Mikrofon auf."""

    CHUNK = 320

    def __init__(self, clock: FakeClock, delay_s: float | None, noise_dbfs: float = -45.0) -> None:
        self.clock = clock
        self.delay = None if delay_s is None else int(delay_s * SAMPLE_RATE)
        self.rng = np.random.default_rng(3)
        self.noise_rms = 10 ** (noise_dbfs / 20)
        self.emitted = 0
        self.echo: list[tuple[int, Audio]] = []

    def start_recording(self) -> None: ...
    def stop_recording(self) -> None: ...
    def start_playing(self) -> None: ...
    def stop_playing(self) -> None: ...
    def get_input_audio_samplerate(self) -> int:
        return SAMPLE_RATE

    def get_output_audio_samplerate(self) -> int:
        return SAMPLE_RATE

    def get_audio_sample(self) -> Audio | None:
        if self.emitted + self.CHUNK > self.clock.now * SAMPLE_RATE:
            return None  # noch keine neuen Daten
        chunk = (self.rng.standard_normal(self.CHUNK) * self.noise_rms).astype(np.float32)
        for start, audio in self.echo:
            lo, hi = max(start, self.emitted), min(start + audio.size, self.emitted + self.CHUNK)
            if lo < hi:
                chunk[lo - self.emitted : hi - self.emitted] += audio[lo - start : hi - start] * 0.3
        self.emitted += self.CHUNK
        return np.stack([chunk, chunk], axis=1)

    def push_audio_sample(self, data: Audio) -> None:
        if self.delay is not None:
            self.echo.append((int(self.clock.now * SAMPLE_RATE) + self.delay, data))


@pytest.mark.parametrize("delay_s", [0.15, 0.8, 1.6])
def test_measures_round_trip(delay_s: float) -> None:
    clock = FakeClock()
    measured = measure_round_trip(EchoMedia(clock, delay_s), clock=clock, sleep=clock.sleep)
    assert measured == pytest.approx(delay_s, abs=0.05)


def test_unheard_beep_returns_none() -> None:
    clock = FakeClock()
    assert measure_round_trip(EchoMedia(clock, None), clock=clock, sleep=clock.sleep) is None


def test_find_onset() -> None:
    quiet = np.full(1600, 0.001, dtype=np.float32)
    loud = np.concatenate([quiet, np.full(800, 0.3, dtype=np.float32)])
    assert find_onset(loud, baseline_dbfs=-60) == 1600
    assert find_onset(quiet, baseline_dbfs=-60) is None
