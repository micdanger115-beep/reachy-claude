from pathlib import Path

import numpy as np
import pytest
from fakes import FakeClock, FakeMedia

from reachy_claude.audio import SAMPLE_RATE, load_wav
from reachy_claude.check_audio import peak_dbfs, run_audio_check


def run(media: FakeMedia, clock: FakeClock, tmp_path: Path, seconds: float = 2.0) -> tuple[list[str], object]:
    lines: list[str] = []
    result = run_audio_check(
        media, lines.append, seconds=seconds, save_to=tmp_path / "test.wav", sleep=clock.sleep, clock=clock
    )
    return lines, result


def test_full_check_records_saves_and_plays_back(tmp_path: Path) -> None:
    clock = FakeClock()
    media = FakeMedia(clock, amplitude=0.3)
    lines, result = run(media, clock, tmp_path)

    assert result.mic_ok  # type: ignore[attr-defined]
    assert result.seconds_recorded == pytest.approx(2.0, abs=0.05)  # type: ignore[attr-defined]
    assert any("Mikrofon [" in line for line in lines)  # Live-Pegel
    assert any(line.startswith("OK:") for line in lines)
    saved, rate = load_wav(tmp_path / "test.wav")
    assert rate == SAMPLE_RATE and saved.size == pytest.approx(2 * SAMPLE_RATE, abs=SAMPLE_RATE * 0.05)

    assert len(media.pushed) == 2  # 1) Toene + Aufnahme in einem Stueck, 2) Mess-Piepton
    played = media.pushed[0]
    assert played.dtype == np.float32 and played.ndim == 1
    assert played.size > saved.size  # Toene vor der Aufnahme
    assert media.pushed[1].size == SAMPLE_RATE // 5  # 0,2-s-Piepton
    assert media.calls[:4] == ["start_recording", "stop_recording", "start_playing", "stop_playing"]
    # Dauerton im Fake-Mikrofon -> kein Einsatz des Pieptons messbar, wird verstaendlich gemeldet
    assert result.round_trip_s is None  # type: ignore[attr-defined]
    assert any("nicht erkannt" in line for line in lines)


def test_quiet_microphone_is_reported(tmp_path: Path) -> None:
    clock = FakeClock()
    lines, result = run(FakeMedia(clock, amplitude=0.0001), clock, tmp_path)
    assert result.mic_ok  # type: ignore[attr-defined]
    assert any("sehr leise" in line for line in lines)


def test_silent_microphone_times_out_and_explains(tmp_path: Path) -> None:
    clock = FakeClock()
    media = FakeMedia(clock, silent_mic=True)
    lines, result = run(media, clock, tmp_path)
    assert not result.mic_ok  # type: ignore[attr-defined]
    assert any("Conversation-App" in line for line in lines)
    assert media.calls == ["start_recording", "stop_recording"]  # Mikrofon wieder freigegeben
    assert media.pushed == []
    assert not (tmp_path / "test.wav").exists()


def test_unexpected_samplerate_is_mentioned(tmp_path: Path) -> None:
    clock = FakeClock()
    lines, _ = run(FakeMedia(clock, rate=48_000), clock, tmp_path)
    assert "48000 Hz" in lines[0]


def test_peak_finds_loudest_part() -> None:
    quiet = np.zeros(SAMPLE_RATE, dtype=np.float32)
    quiet[1000:1100] = 0.5
    assert peak_dbfs(quiet) > -30
