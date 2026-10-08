import numpy as np
import pytest

from reachy_claude.audio import SAMPLE_RATE, Audio
from reachy_claude.segmenter import SegmenterConfig, SpeechSegmenter

RNG = np.random.default_rng(42)
PAUSE = SegmenterConfig().end_silence_s + 0.4  # sicher laenger als die Pause, die einen Satz beendet


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
        [noise(1.0), speech(1.5), noise(PAUSE), speech(0.06), noise(PAUSE), speech(1.0), noise(PAUSE)]
    )
    found = run(SpeechSegmenter(), audio)
    assert len(found) == 2
    durations = [u.size / SAMPLE_RATE for u in found]
    end = SegmenterConfig().end_silence_s
    assert durations[0] == pytest.approx(1.5 + 0.3 + end, abs=0.15)  # Satz + Vorlauf + Pause
    assert durations[1] == pytest.approx(1.0 + 0.3 + end, abs=0.15)


def test_pre_roll_keeps_first_syllable() -> None:
    audio = np.concatenate([noise(1.0), speech(0.6), noise(PAUSE)])
    (utterance,) = run(SpeechSegmenter(), audio)
    lead = utterance[: int(0.25 * SAMPLE_RATE)]
    assert np.max(np.abs(lead)) < 0.01  # Vorlauf ist Ruhe vor dem Satz


def test_long_speech_is_split_at_max_length() -> None:
    config = SegmenterConfig(max_speech_s=2.0)
    rng = np.random.default_rng(5)
    found = run(
        SpeechSegmenter(config), np.concatenate([noise(1.0, -45), words(5.0, rng), noise(PAUSE, -45)])
    )
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


# --- Lange Auftraege (Fehlerbild: lange Prompts wurden mittendrin abgeschnitten) ---


def words(seconds: float, rng: np.random.Generator, gap_s: tuple[float, float] = (0.02, 0.15)) -> Audio:
    """Fluessiges Sprechen: Woerter unterschiedlicher Lautstaerke mit kurzen Luecken."""
    parts: list[Audio] = []
    total = 0.0
    while total < seconds:
        word, gap = rng.uniform(0.2, 0.6), rng.uniform(*gap_s)
        parts += [speech(word, amplitude=rng.uniform(0.03, 0.25)), noise(gap, dbfs=-45.0)]
        total += word + gap
    return np.concatenate(parts)


def durations(audio: Audio) -> list[float]:
    return [round(u.size / SAMPLE_RATE, 1) for u in run(SpeechSegmenter(), audio)]


def test_long_dictation_is_not_cut_at_20_seconds() -> None:
    rng = np.random.default_rng(1)
    found = durations(np.concatenate([noise(1.0, -45), words(45.0, rng), noise(PAUSE, -45)]))
    assert len(found) == 1 and found[0] >= 45.0  # frueher: [20.0, ...]


@pytest.mark.parametrize("seed", range(6))
def test_fluent_speech_with_quiet_words_stays_one_sentence(seed: int) -> None:
    # frueher wanderte die Rauschschaetzung mit und schnitt z. B. nach 10,9 von 15 s
    rng = np.random.default_rng(seed)
    found = durations(np.concatenate([noise(1.0, -45), words(15.0, rng), noise(PAUSE, -45)]))
    assert len(found) == 1, found


def test_short_thinking_pause_keeps_the_sentence() -> None:
    rng = np.random.default_rng(7)
    audio = np.concatenate(
        [noise(1.0, -45), words(6.0, rng), noise(1.0, -45), words(4.0, rng), noise(PAUSE, -45)]
    )
    assert len(durations(audio)) == 1  # 1 s Denkpause trennt nicht mehr (frueher ab 0,8 s)


def test_fan_starting_mid_sentence_ends_it_and_adapts() -> None:
    # Hintergrund springt dauerhaft um 25 dB: kein endloser "Satz" bis zur Hoechstlaenge
    segmenter = SpeechSegmenter()
    rng = np.random.default_rng(3)
    run(segmenter, np.concatenate([noise(1.0, -60), words(1.0, rng)]))
    assert segmenter.in_speech
    fan = run(segmenter, noise(8.0, dbfs=-35.0))
    assert not segmenter.in_speech
    assert all(u.size / SAMPLE_RATE < 6.0 for u in fan)
    later = run(
        segmenter, np.concatenate([speech(1.0, amplitude=0.4) + noise(1.0, -35.0), noise(PAUSE, -35.0)])
    )
    assert len(later) == 1  # danach wird Sprache ueber dem Luefter wieder erkannt


def test_warmup_ignores_the_first_half_second() -> None:
    segmenter = SpeechSegmenter()
    run(segmenter, speech(0.4))
    assert not segmenter.in_speech


def test_quiet_words_after_long_loud_passage_keep_the_sentence() -> None:
    """Gezielt der Fehlerfall: nach langem, lautem, fluessigem Sprechen war die Schwelle so weit
    mitgewandert, dass die folgenden leisen Woerter als Stille galten -> Schnitt mittendrin."""
    rng = np.random.default_rng(0)

    def fluent(seconds: float, amplitude: float) -> Audio:
        # Silben mit voller Modulation wie bei echter Sprache (Pegel schwankt um >10 dB)
        parts: list[Audio] = []
        total = 0.0
        while total < seconds:
            word = rng.uniform(0.25, 0.5)
            t = np.arange(int(word * SAMPLE_RATE)) / SAMPLE_RATE
            syllables = 0.05 + 0.95 * np.abs(np.sin(2 * np.pi * rng.uniform(3.0, 5.0) * t))
            voiced = (amplitude * syllables * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
            parts += [voiced + noise(word, -45.0), noise(0.03, dbfs=-45.0)]
            total += word + 0.03
        return np.concatenate(parts)

    audio = np.concatenate(
        [noise(1.0, -45), fluent(6.0, 0.25), fluent(2.5, 0.02), fluent(2.0, 0.25), noise(PAUSE, -45)]
    )
    found = durations(audio)
    assert len(found) == 1 and found[0] >= 10.5, found  # alles drin: 6 + 2,5 + 2 s Sprache
