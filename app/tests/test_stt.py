import sys
import types
from typing import Any

import pytest

from reachy_claude.stt import CPU_MODEL, GPU_MODEL, SttConfig, WhisperTranscriber


class FakeSegment:
    def __init__(self, text: str) -> None:
        self.text = text


def install_fake_whisper(monkeypatch: pytest.MonkeyPatch, failing_devices: set[str]) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []

    class FakeWhisperModel:
        def __init__(self, model: str, device: str, compute_type: str) -> None:
            created.append({"model": model, "device": device, "compute_type": compute_type})
            self.device = device

        def transcribe(self, audio: Any, **kwargs: Any) -> tuple[list[FakeSegment], None]:
            if self.device in failing_devices:
                raise RuntimeError("Library cublas64_12.dll is not found")
            assert kwargs["language"] == "de" and kwargs["vad_filter"] is True
            return [FakeSegment(" Claude, "), FakeSegment("schreib einen Test. ")], None

    module = types.ModuleType("faster_whisper")
    module.WhisperModel = FakeWhisperModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    return created


def test_uses_gpu_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    created = install_fake_whisper(monkeypatch, failing_devices=set())
    stt = WhisperTranscriber()
    assert created == [{"model": GPU_MODEL, "device": "cuda", "compute_type": "int8_float16"}]
    assert "Grafikkarte" in stt.description
    assert stt.transcribe(__import__("numpy").zeros(16000, dtype="float32")) == "Claude, schreib einen Test."


def test_falls_back_to_cpu_when_cuda_breaks(monkeypatch: pytest.MonkeyPatch) -> None:
    created = install_fake_whisper(monkeypatch, failing_devices={"cuda"})
    stt = WhisperTranscriber()
    assert [c["device"] for c in created] == ["cuda", "cpu"]
    assert created[1]["model"] == CPU_MODEL
    assert "Prozessor" in stt.description


def test_explicit_cpu_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    created = install_fake_whisper(monkeypatch, failing_devices=set())
    WhisperTranscriber(SttConfig(device="cpu", model="medium"))
    assert created == [{"model": "medium", "device": "cpu", "compute_type": "int8"}]


def test_reports_all_errors_when_nothing_works(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_whisper(monkeypatch, failing_devices={"cuda", "cpu"})
    with pytest.raises(RuntimeError, match="cuda: .*cublas.*cpu: "):
        WhisperTranscriber()
