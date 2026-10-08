import threading
import time

import numpy as np
import pytest
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


class FakeSpeaker:
    description = "Test"

    def synthesize(self, text: str) -> Audio:
        return np.full(SAMPLE_RATE // 2, 0.2, dtype=np.float32)


class RecordingMedia(ScriptedMedia):
    def __init__(self, audio: Audio) -> None:
        super().__init__(audio)
        self.pushed: list[Audio] = []

    def push_audio_sample(self, data: Audio) -> None:
        self.pushed.append(data)

    def start_playing(self) -> None:
        self.calls.append("start_playing")

    def stop_playing(self) -> None:
        self.calls.append("stop_playing")


def test_voice_says_text_on_robot(monkeypatch: pytest.MonkeyPatch) -> None:
    from reachy_claude.listener import Voice

    monkeypatch.setattr("reachy_claude.robot.time.sleep", lambda s: None)
    media = RecordingMedia(np.zeros(0, dtype=np.float32))
    lines: list[str] = []
    Voice(FakeSpeaker(), media, lines.append).say("Hallo\x1b[2J Welt")
    assert lines == ["Reachy: Hallo [2J Welt"]
    assert len(media.pushed) == 1 and media.pushed[0].size == SAMPLE_RATE // 2
    assert media.calls == ["start_playing", "stop_playing"]
    Voice(FakeSpeaker(), media, lines.append).say("   ")
    assert len(media.pushed) == 1  # leerer Text wird nicht gesprochen


class PhasedMedia(ScriptedMedia):
    """Liefert Audio in Phasen; die naechste Phase kommt erst nach ``release_next()`` – wie ein echtes Mikrofon."""

    def __init__(self, phases: list[Audio]) -> None:
        super().__init__(phases[0])
        self._phases = phases[1:]
        self.lock = threading.Lock()

    def get_audio_sample(self) -> Audio | None:
        with self.lock:
            return super().get_audio_sample()

    def release_next(self) -> None:
        audio = self._phases.pop(0)
        stereo = np.stack([audio, audio], axis=1)
        with self.lock:
            self._chunks.extend(stereo[i : i + 320] for i in range(0, len(stereo), 320))

    def drained(self) -> bool:
        with self.lock:
            return not self._chunks


def test_reachy_does_not_listen_to_itself() -> None:
    """Was das Mikrofon waehrend Reachys Antwort aufnimmt (Echo), wird verworfen."""
    media = PhasedMedia(
        [
            np.concatenate([noise(1.0), speech(1.0), noise(1.0)]),  # Auftrag
            np.concatenate([speech(1.0), noise(1.0)]),  # Echo, waehrend Reachy spricht
            np.concatenate([noise(0.5), speech(2.5), noise(1.2)]),  # spaeter: neuer, laengerer Auftrag
        ]
    )
    stop = threading.Event()

    class ByLength(ScriptedTranscriber):
        """Erster Satz = Auftrag; danach: lang = neuer Auftrag, kurz = Echo (darf nie ankommen)."""

        def transcribe(self, audio: Audio) -> str:
            self.durations.append(audio.size / SAMPLE_RATE)
            if len(self.durations) == 1:
                return "Claude, schreib einen Test"
            if audio.size / SAMPLE_RATE > 3.0:
                self.done.set()
                return "Claude, zweiter Auftrag"
            return "Claude, ECHO"

    transcriber = ByLength([], stop)
    commands: list[str] = []
    clock = Clock()

    def on_command(command: str) -> None:
        commands.append(command)
        if len(commands) > 1:
            return
        media.release_next()  # Reachy "spricht", das Mikrofon hoert das Echo
        while not media.drained():
            time.sleep(0.001)
        time.sleep(0.05)  # Echo liegt jetzt in der Warteschlange

        def later() -> None:
            time.sleep(0.2)
            clock.now += 10.0  # Taubheitsfenster ist vorbei
            media.release_next()

        threading.Thread(target=later, daemon=True).start()

    worker = threading.Thread(
        target=listen, args=(media, transcriber, lambda _: None, on_command, stop), kwargs={"clock": clock}
    )
    worker.start()
    worker.join(timeout=10)
    stop.set()
    worker.join(timeout=2)
    assert commands == ["schreib einen Test", "zweiter Auftrag"]
    assert len(transcriber.durations) == 2  # das Echo wurde nie erkannt


def test_events_for_speech_and_wake_word() -> None:
    audio = np.concatenate([noise(1.0), speech(1.0), noise(1.2)])
    stop = threading.Event()
    events: list[str] = []
    wakes: list[int] = []
    parser = CommandParser(lambda _: None, on_wake=lambda: wakes.append(1))
    transcriber = ScriptedTranscriber(["Claude, mach was"], stop)
    worker = threading.Thread(
        target=listen,
        args=(ScriptedMedia(audio), transcriber, lambda _: None, lambda _: None, stop),
        kwargs={"parser": parser, "on_event": events.append},
    )
    worker.start()
    worker.join(timeout=10)
    assert events[:2] == ["speech_start", "speech_end"]
    assert wakes == [1]


def test_on_wake_not_called_without_wake_word() -> None:
    wakes: list[int] = []
    parser = CommandParser(lambda _: None, on_wake=lambda: wakes.append(1))
    parser.handle("Wie spät ist es?")
    parser.handle("Hey Claude.")
    assert wakes == [1]
