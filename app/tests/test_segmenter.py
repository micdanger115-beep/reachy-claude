import numpy as np
import pytest

from reachy_claude.audio import SAMPLE_RATE, Audio
from reachy_claude.segmenter import SegmenterConfig, SpeechSegmenter

RNG = np.random.default_rng(42)


def noise(seconds: float, dbfs: float = -60.0) -> Audio:
    rms = 10 ** (dbfs / 20)
    return (RNG.standard_normal(int(seconds * SAMPLE_RATE)) * rms).astype(np.float32)


def speech(seconds: float, amplitude: float = 0.2) -> Audio:
    """Sprachaehnlich: Ton mit Silben-Huellkurve (4 Hz) ueber leisem Rauschen."""
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    envelope = 0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 2 * t))
    return (amplitude * envelope * np.sin(2 * np.pi * 220 * t)).astype(np.float32) + noise(seconds)


def run(segmenter: SpeechSegmenter, audio: Audio, chunk: int = 320) -> list[Audio]:
    found: list[Audio] = []
    for start in range(0, audio.size, chunk):
        found.extend(segmenter.feed(audio[start : start + chunk]))
    return found


def test_finds_two_sentences_and_ignores_click() -> None:
    audio = np.concatenate(
        [noise(1.0), speech(1.5), noise(1.2), speech(0.06), noise(1.2), speech(1.0), noise(1.2)]
    )
    found = run(SpeechSegmenter(), audio)
    assert len(found) == 2
    durations = [u.size / SAMPLE_RATE for u in found]
    assert durations[0] == pytest.approx(1.5 + 0.3 + 0.8, abs=0.15)  # Satz + Vorlauf + Pause
    assert durations[1] == pytest.approx(1.0 + 0.3 + 0.8, abs=0.15)


def test_pre_roll_keeps_first_syllable() -> None:
    audio = np.concatenate([noise(1.0), speech(0.6), noise(1.0)])
    (utterance,) = run(SpeechSegmenter(), audio)
    lead = utterance[: int(0.25 * SAMPLE_RATE)]
    assert np.max(np.abs(lead)) < 0.01  # Vorlauf ist Ruhe vor dem Satz


def test_long_speech_is_split_at_max_length() -> None:
    config = SegmenterConfig(max_speech_s=2.0)
    found = run(SpeechSegmenter(config), np.concatenate([noise(0.5), speech(5.0), noise(1.0)]))
    assert len(found) >= 2
    assert all(u.size / SAMPLE_RATE <= 2.0 + 0.4 for u in found)


def test_adapts_to_constant_background_noise() -> None:
    hum = noise(6.0, dbfs=-35.0)  # lauter Luefter, ab Start
    found = run(SpeechSegmenter(), hum)
    segmenter = SpeechSegmenter()
    run(segmenter, hum)
    assert segmenter.noise_dbfs == pytest.approx(-36.0, abs=3.0)
    # Danach wird Sprache ueber dem Luefter weiterhin erkannt.
    later = run(
        segmenter, np.concatenate([speech(1.0, amplitude=0.4) + noise(1.0, -35.0), noise(1.5, -35.0)])
    )
    assert len(later) == 1
    assert len(found) <= 1  # hoechstens der Einschwingvorgang am Anfang


def test_quiet_room_never_triggers() -> None:
    assert run(SpeechSegmenter(), noise(5.0, dbfs=-70.0)) == []


def test_muted_and_reset() -> None:
    segmenter = SpeechSegmenter()
    segmenter.muted = True
    assert run(segmenter, np.concatenate([noise(0.5), speech(1.0), noise(1.0)])) == []
    segmenter.muted = False
    run(segmenter, np.concatenate([noise(0.5), speech(0.5)]))
    assert segmenter.in_speech
    segmenter.reset()
    assert not segmenter.in_speech


def test_real_speech_regression_all_four_sentences_found() -> None:
    """Echte (synthetische) Sprache mit Raumrauschen; frueher wurden nur 2 von 4 Saetzen erkannt."""
    from pathlib import Path

    from reachy_claude.audio import load_wav

    audio, rate = load_wav(Path(__file__).parent / "data" / "vier_saetze_raumrauschen.wav")
    assert rate == SAMPLE_RATE
    found = run(SpeechSegmenter(), audio)
    assert len(found) == 4
    assert 0.9 <= found[2].size / SAMPLE_RATE <= 2.5  # das kurze "Claude."
