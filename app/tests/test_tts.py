import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from reachy_claude import tts
from reachy_claude.audio import SAMPLE_RATE
from reachy_claude.tts import PiperSpeaker, TtsConfig, ensure_voice, normalize, resample, voice_repo_path


class Chunk:
    def __init__(self, audio: np.ndarray, rate: int) -> None:
        self.audio_float_array = audio
        self.sample_rate = rate


class FakeVoice:
    def __init__(self, rate: int = 22050) -> None:
        self.rate = rate
        self.texts: list[str] = []
        self.configs: list[Any] = []

    def synthesize(self, text: str, config: Any) -> list[Chunk]:
        self.texts.append(text)
        self.configs.append(config)
        half = np.full(self.rate // 2, 0.1, dtype=np.float32)
        return [Chunk(half, self.rate), Chunk(-half, self.rate)]


@pytest.fixture(autouse=True)
def fake_piper_module(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("piper")

    class SynthesisConfig:
        def __init__(self, length_scale: float) -> None:
            self.length_scale = length_scale

    module.SynthesisConfig = SynthesisConfig  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "piper", module)


def test_voice_repo_path() -> None:
    assert voice_repo_path("de_DE-thorsten-medium") == "de/de_DE/thorsten/medium"
    for bad in ("thorsten", "de-thorsten-medium", "a-b-c-d"):
        with pytest.raises(ValueError):
            voice_repo_path(bad)


def test_resample_keeps_duration_and_identity() -> None:
    one_second = np.linspace(-1, 1, 22050, dtype=np.float32)
    out = resample(one_second, 22050)
    assert out.size == SAMPLE_RATE and out.dtype == np.float32
    assert out[0] == pytest.approx(-1.0) and out[-1] == pytest.approx(1.0, abs=1e-3)
    same = np.ones(10, dtype=np.float32)
    assert resample(same, SAMPLE_RATE) is same


def test_normalize() -> None:
    assert np.max(np.abs(normalize(np.array([0.1, -0.2], dtype=np.float32)))) == pytest.approx(0.8)
    silent = np.zeros(5, dtype=np.float32)
    assert normalize(silent) is silent


def test_speaker_synthesizes_16k_normalized() -> None:
    voice = FakeVoice(rate=22050)
    speaker = PiperSpeaker(TtsConfig(length_scale=1.1), voice=voice)
    audio = speaker.synthesize("Hallo Welt")
    assert audio.dtype == np.float32
    assert audio.size == SAMPLE_RATE  # 2 x 0,5 s bei 22,05 kHz -> 1 s bei 16 kHz
    assert np.max(np.abs(audio)) == pytest.approx(0.8)
    assert voice.texts == ["Hallo Welt"] and voice.configs[0].length_scale == 1.1
    assert speaker.synthesize("   ").size == 0
    assert "thorsten" in speaker.description


def test_ensure_voice_uses_existing_files(tmp_path: Path) -> None:
    (tmp_path / "de_DE-thorsten-medium.onnx").write_bytes(b"x")
    (tmp_path / "de_DE-thorsten-medium.onnx.json").write_text("{}")
    assert ensure_voice(TtsConfig(voice_dir=tmp_path)) == tmp_path / "de_DE-thorsten-medium.onnx"


def test_ensure_voice_downloads_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_download(repo: str, filename: str, local_dir: Path) -> str:
        calls.append((repo, filename))
        target = Path(local_dir) / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("data")
        return str(target)

    hub = types.ModuleType("huggingface_hub")
    hub.hf_hub_download = fake_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)

    config = TtsConfig(voice_dir=tmp_path / "voices")
    model = ensure_voice(config)
    assert model.is_file() and model.with_suffix(".onnx.json").is_file()
    assert calls == [
        (tts.VOICES_REPO, "de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx"),
        (tts.VOICES_REPO, "de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json"),
    ]
    ensure_voice(config)
    assert len(calls) == 2  # zweiter Aufruf ohne Download


def test_pronunciations_replace_whole_words_case_insensitive() -> None:
    from reachy_claude.tts import DEFAULT_PRONUNCIATIONS, apply_pronunciations

    text = "Hallo, ich bin Reachy! REACHY und reachys Freund Claude; Reachymini bleibt."
    assert apply_pronunciations(text, DEFAULT_PRONUNCIATIONS) == (
        "Hallo, ich bin Rietschi! Rietschi und reachys Freund Klohd; Reachymini bleibt."
    )


def test_pronunciation_file_overrides_and_extends(tmp_path: Path) -> None:
    from reachy_claude.tts import load_pronunciations

    file = tmp_path / "aussprache.txt"
    file.write_text(
        "# Kommentar\nreachy = Riitschi\nmain.py = Mehn Punkt Pei\nkaputt\n = leer\n", encoding="utf-8"
    )
    table = load_pronunciations(file)
    assert table["reachy"] == "Riitschi" and "Reachy" not in table  # ueberschrieben
    assert table["main.py"] == "Mehn Punkt Pei"
    assert table["Claude"] == "Klohd"  # Standard bleibt
    assert load_pronunciations(tmp_path / "fehlt.txt") == {"Reachy": "Rietschi", "Claude": "Klohd"}


def test_speaker_uses_pronunciation_but_not_for_display(tmp_path: Path) -> None:
    voice = FakeVoice()
    speaker = PiperSpeaker(TtsConfig(pronunciation_file=tmp_path / "keine.txt"), voice=voice)
    speaker.synthesize("Ich bin Reachy.")
    assert voice.texts == ["Ich bin Rietschi."]
