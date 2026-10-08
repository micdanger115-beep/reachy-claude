import threading

import numpy as np
from test_segmenter import noise, speech

from reachy_claude.audio import SAMPLE_RATE, Audio
from reachy_claude.listener import WAKE_FOLLOW_UP_S, CommandParser, listen


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_parser_command_ignore_and_two_step_wake() -> None:
    lines: list[str] = []
    clock = Clock()
    parser = CommandParser(lines.append, clock=clock)

    assert parser.handle("Claude, erklär mir main.py") == "erklär mir main.py"
    assert parser.handle("Wie spät ist es?") is None
    assert "ignoriert" in lines[-1]
    assert parser.handle("Claude.") is None
    assert "Ja?" in lines[-1]
    clock.now += 2
    assert parser.handle("Schreib einen Test") == "Schreib einen Test"
    assert parser.handle("Und noch etwas") is None  # Warten ist vorbei


def test_wake_only_expires() -> None:
    clock = Clock()
    parser = CommandParser(lambda _: None, clock=clock)
    parser.handle("Claude")
    clock.now += WAKE_FOLLOW_UP_S + 1
    assert parser.handle("Schreib einen Test") is None


def test_empty_text_is_silent() -> None:
    lines: list[str] = []
    assert CommandParser(lines.append).handle("  ") is None
    assert lines == []


class ScriptedMedia:
    """Spielt vorbereitetes Audio in 20-ms-Bloecken ab, danach kommt nichts mehr."""

    def __init__(self, audio: Audio) -> None:
        stereo = np.stack([audio, audio], axis=1)
        self._chunks = [stereo[i : i + 320] for i in range(0, len(stereo), 320)]
        self.calls: list[str] = []

    def start_recording(self) -> None:
        self.calls.append("start_recording")

    def stop_recording(self) -> None:
        self.calls.append("stop_recording")

    def get_audio_sample(self) -> Audio | None:
        return self._chunks.pop(0) if self._chunks else None

    def get_input_audio_samplerate(self) -> int:
        return SAMPLE_RATE

    def start_playing(self) -> None: ...
    def stop_playing(self) -> None: ...
    def push_audio_sample(self, data: Audio) -> None: ...
    def get_output_audio_samplerate(self) -> int:
        return SAMPLE_RATE


class ScriptedTranscriber:
    description = "Test"

    def __init__(self, texts: list[str], done: threading.Event) -> None:
        self.texts = texts
        self.durations: list[float] = []
        self.done = done

    def transcribe(self, audio: Audio) -> str:
        self.durations.append(audio.size / SAMPLE_RATE)
        text = self.texts.pop(0)
        if not self.texts:
            self.done.set()
        return text


def test_listen_end_to_end_with_fake_robot() -> None:
    audio = np.concatenate([noise(1.0), speech(1.2), noise(1.2), speech(1.0), noise(1.2)])
    media = ScriptedMedia(audio)
    stop = threading.Event()
    transcriber = ScriptedTranscriber(["Was läuft im Fernsehen?", "Claude, schreib einen Test"], stop)
    lines: list[str] = []
    commands: list[str] = []

    worker = threading.Thread(target=listen, args=(media, transcriber, lines.append, commands.append, stop))
    worker.start()
    worker.join(timeout=10)

    assert not worker.is_alive()
    assert commands == ["schreib einen Test"]
    assert lines[0] == "Du:     Was läuft im Fernsehen?"
    assert any("ignoriert" in line for line in lines)
    assert media.calls == ["start_recording", "stop_recording"]
    assert len(transcriber.durations) == 2
