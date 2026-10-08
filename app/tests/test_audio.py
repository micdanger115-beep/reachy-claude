from pathlib import Path

import numpy as np
import pytest

from reachy_claude.audio import (
    SAMPLE_RATE,
    SILENCE_DBFS,
    level_bar,
    level_dbfs,
    load_wav,
    save_wav,
    silence,
    to_mono,
    tone,
)


def test_to_mono_averages_stereo_and_keeps_mono() -> None:
    stereo = np.array([[1.0, 0.0], [0.5, 0.5]], dtype=np.float32)
    assert to_mono(stereo).tolist() == [0.5, 0.5]
    assert to_mono(np.array([0.1, 0.2])).dtype == np.float32


def test_level_dbfs() -> None:
    assert level_dbfs(np.zeros(100, dtype=np.float32)) == SILENCE_DBFS
    assert level_dbfs(np.zeros(0, dtype=np.float32)) == SILENCE_DBFS
    assert level_dbfs(np.ones(100, dtype=np.float32)) == pytest.approx(0.0)
    assert level_dbfs(np.full(100, 0.1, dtype=np.float32)) == pytest.approx(-20.0)


def test_level_bar_bounds() -> None:
    assert level_bar(-96, width=10).startswith("[----------]")
    assert level_bar(0, width=10).startswith("[##########]")
    assert level_bar(-30, width=10).startswith("[#####-----]")


def test_tone_has_fades_and_volume() -> None:
    signal = tone(440, 0.5, volume=0.3)
    assert signal.size == SAMPLE_RATE // 2
    assert abs(signal[0]) < 1e-6 and abs(signal[-1]) < 0.01
    assert np.max(np.abs(signal)) <= 0.3 + 1e-6
    assert silence(0.1).size == SAMPLE_RATE // 10


def test_wav_roundtrip_and_clipping(tmp_path: Path) -> None:
    data = np.array([0.0, 0.5, -0.5, 2.0], dtype=np.float32)
    path = tmp_path / "sub" / "x.wav"
    save_wav(path, data)
    loaded, rate = load_wav(path)
    assert rate == SAMPLE_RATE
    assert loaded == pytest.approx([0.0, 0.5, -0.5, 1.0], abs=1e-4)
