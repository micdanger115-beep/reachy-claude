import threading
from pathlib import Path

import pytest

from reachy_claude.assistant import (
    BUSY_MESSAGE,
    NOTHING_TO_CANCEL,
    NOTHING_TO_REPEAT,
    ClaudeAssistant,
    Control,
    PrintOnly,
    control_word,
    show_answer,
)
from reachy_claude.claude import CANCELLED_MESSAGE, ClaudeCancelled, ClaudeError, ClaudeResult


class FakeVoice:
    def __init__(self) -> None:
        self.said: list[str] = []

    def say(self, text: str) -> None:
        self.said.append(text)


class FakeClaude:
    def __init__(self, text: str = "Erledigt.\n```py\nx = 1\n```\nSPRECHTEXT: Ich habe x gesetzt.") -> None:
        self.text = text
        self.calls: list[tuple[str, bool]] = []
        self.error: str | None = None
        self.gate: threading.Event | None = None
        self.cancelled = False

    def cancel(self) -> bool:
        if self.gate is None or self.gate.is_set():
            return False
        self.cancelled = True
        self.gate.set()
        return True

    def ask(
        self, prompt: str, new_conversation: bool = False, cancel_event: threading.Event | None = None
    ) -> ClaudeResult:
        if cancel_event is not None and cancel_event.is_set():
            self.cancelled = True  # wie der echte Runner: gar nicht erst starten
            raise ClaudeCancelled(CANCELLED_MESSAGE)
        self.calls.append((prompt, new_conversation))
        if self.gate is not None:
            self.gate.wait(5)
        if self.cancelled:
            raise ClaudeCancelled(CANCELLED_MESSAGE)
        if self.error:
            raise ClaudeError(self.error)
        return ClaudeResult(self.text, "s1", False, 1.0, None)


def make(
    claude: FakeClaude, tmp_path: Path, **kwargs: object
) -> tuple[ClaudeAssistant, FakeVoice, list[str]]:
    voice, lines = FakeVoice(), []
    assistant = ClaudeAssistant(claude, voice, lines.append, transcript_dir=tmp_path / "m", **kwargs)  # type: ignore[arg-type]
    return assistant, voice, lines


def test_command_is_sent_answer_shown_and_spoken(tmp_path: Path) -> None:
    claude = FakeClaude()
    assistant, voice, lines = make(claude, tmp_path)
    assistant.handle("setz x auf eins")
    assert claude.calls == [("setz x auf eins", False)]
    assert voice.said == ["Ich frage Claude.", "Ich habe x gesetzt."]
    assert lines[0] == "Claude:" and "  x = 1" in lines  # vollstaendige Antwort im Terminal
    transcript = next((tmp_path / "m").glob("*.md")).read_text(encoding="utf-8")
    assert "setz x auf eins" in transcript and "x = 1" in transcript


def test_new_topic_resets_conversation(tmp_path: Path) -> None:
    claude = FakeClaude()
    assistant, voice, _ = make(claude, tmp_path)
    assistant.handle("Neues Thema: erklär mir main.py")
    assistant.handle("und jetzt die Tests")
    assert claude.calls == [("erklär mir main.py", True), ("und jetzt die Tests", False)]


def test_new_topic_alone_waits_for_next_command(tmp_path: Path) -> None:
    claude = FakeClaude()
    assistant, voice, _ = make(claude, tmp_path)
    assistant.handle("neues Thema.")
    assert claude.calls == [] and "neues Thema" in voice.said[0]
    assistant.handle("was macht calc.py")
    assert claude.calls == [("was macht calc.py", True)]


def test_claude_error_is_spoken(tmp_path: Path) -> None:
    claude = FakeClaude()
    claude.error = "Claude hat nach 15 Minuten nicht geantwortet, ich habe abgebrochen."
    assistant, voice, lines = make(claude, tmp_path)
    assistant.handle("x")
    assert voice.said == ["Ich frage Claude.", claude.error]
    assert lines == []


def test_progress_messages_while_claude_works(tmp_path: Path) -> None:
    claude = FakeClaude()
    claude.gate = threading.Event()
    assistant, voice, _ = make(claude, tmp_path, progress_interval_s=0.05)
    timer = threading.Timer(0.18, claude.gate.set)
    timer.start()
    assistant.handle("lange Aufgabe")
    timer.join()
    assert voice.said[0] == "Ich frage Claude."
    assert voice.said.count("Claude arbeitet noch.") >= 2
    assert voice.said[-1] == "Ich habe x gesetzt."


def test_failed_new_topic_is_kept_for_next_try(tmp_path: Path) -> None:
    claude = FakeClaude()
    claude.error = "Fehler"
    assistant, _, _ = make(claude, tmp_path)
    assistant.handle("neues Thema: a")
    claude.error = None
    assistant.handle("b")
    assert claude.calls[1] == ("b", True)


def test_show_answer_cleans_control_characters() -> None:
    lines: list[str] = []
    show_answer(lines.append, "Zeile\x1b[31m rot\ndef f():\n    return 1\n\tx = 2  ")
    assert lines == ["Claude:", "  Zeile[31m rot", "  def f():", "      return 1", "      x = 2"]
    out: list[str] = []
    PrintOnly(out.append).say("Hi\x07")
    assert out == ["Reachy: Hi"]


@pytest.mark.parametrize("text", ["neues Thema", "Neue Unterhaltung!", "von vorne, bitte"])
def test_new_topic_variants(tmp_path: Path, text: str) -> None:
    claude = FakeClaude()
    assistant, _, _ = make(claude, tmp_path)
    assistant.handle(text)
    assistant.handle("weiter")
    assert claude.calls[-1][1] is True


def test_thinking_mood_while_claude_works(tmp_path: Path) -> None:
    from reachy_claude.motion import Mood

    moods: list[Mood] = []

    class Sink:
        def set_mood(self, mood: Mood) -> None:
            moods.append(mood)

    claude = FakeClaude()
    voice = FakeVoice()
    ClaudeAssistant(claude, voice, lambda _: None, transcript_dir=None, mood=Sink()).handle("x")
    assert moods == [Mood.THINKING, Mood.IDLE]
    claude.error = "kaputt"
    ClaudeAssistant(claude, voice, lambda _: None, transcript_dir=None, mood=Sink()).handle("y")
    assert moods[-1] is Mood.IDLE  # auch nach Fehler wieder ruhig


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Stopp.", Control.STOP),
        ("stop!", Control.STOP),
        ("Abbrechen, bitte", Control.STOP),
        ("hör auf damit", None),  # "damit" ist kein Fuellwort -> geht an Claude
        ("Hör auf", Control.STOP),
        ("brich das sofort ab", Control.STOP),
        ("Wiederhole das bitte.", Control.REPEAT),
        ("noch mal", Control.REPEAT),
        ("Wie bitte?", Control.REPEAT),
        ("Was hast du gesagt?", Control.REPEAT),
        ("wiederhole den letzten Test", None),  # echter Auftrag
        ("stoppe den Server in main.py", None),
        ("", None),
    ],
)
def test_control_words(text: str, expected: Control | None) -> None:
    assert control_word(text) is expected


def wait_until(condition: object, timeout: float = 5.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while not condition():  # type: ignore[operator]
        assert time.monotonic() < deadline
        time.sleep(0.01)


def test_submit_runs_in_background_and_stop_cancels(tmp_path: Path) -> None:
    claude = FakeClaude()
    claude.gate = threading.Event()
    assistant, voice, lines = make(claude, tmp_path)
    assistant.submit("baue etwas Grosses")  # kehrt sofort zurueck
    wait_until(lambda: claude.calls)
    assert assistant.busy
    assistant.submit("noch ein Auftrag")
    assert voice.said[-1] == BUSY_MESSAGE and len(claude.calls) == 1
    assistant.submit("Stopp!")
    wait_until(lambda: not assistant.busy)
    assert voice.said[-1] == CANCELLED_MESSAGE
    assert "        (Auftrag abgebrochen)" in lines
    assert not any(line == "Claude:" for line in lines)  # keine Antwort angezeigt


def test_stop_without_running_job_says_so(tmp_path: Path) -> None:
    assistant, voice, _ = make(FakeClaude(), tmp_path)
    assistant.submit("stopp")
    assert voice.said == [NOTHING_TO_CANCEL]


def test_repeat_says_last_answer_again(tmp_path: Path) -> None:
    assistant, voice, _ = make(FakeClaude(), tmp_path)
    assistant.submit("wiederhole")
    assert voice.said == [NOTHING_TO_REPEAT]
    assistant.submit("setz x")
    wait_until(lambda: not assistant.busy and len(voice.said) == 3)
    assistant.submit("Nochmal, bitte.")
    assert voice.said[-1] == voice.said[-2] == "Ich habe x gesetzt."


def test_shutdown_cancels_running_job(tmp_path: Path) -> None:
    claude = FakeClaude()
    claude.gate = threading.Event()
    assistant, _, _ = make(claude, tmp_path)
    assistant.submit("lange Aufgabe")
    wait_until(lambda: claude.calls)
    assistant.shutdown()
    assert claude.cancelled and not assistant.busy


# --- Pruefrunde Paket B: Abbruch und Beenden ---


class SlowVoice(FakeVoice):
    """Sprechen dauert (wie echt) – in der Zeit kann "stopp" oder Strg+C kommen."""

    def __init__(self, seconds: float = 0.3) -> None:
        super().__init__()
        self.seconds = seconds

    def say(self, text: str) -> None:
        import time

        super().say(text)
        time.sleep(self.seconds)


def test_stop_while_announcing_never_starts_claude(tmp_path: Path) -> None:
    claude = FakeClaude()
    voice = SlowVoice()
    assistant = ClaudeAssistant(claude, voice, lambda _l: None, transcript_dir=None)
    assistant.submit("baue etwas")
    wait_until(lambda: voice.said == ["Ich frage Claude."])  # Claude ist noch nicht gestartet
    assistant.submit("stopp")
    wait_until(lambda: not assistant.busy)
    assert claude.calls == [] or claude.cancelled  # nie ohne Abbruch an Claude
    assert NOTHING_TO_CANCEL not in voice.said
    assert voice.said[-1] == CANCELLED_MESSAGE


def test_shutdown_is_quiet_and_stops_claude_even_before_it_started(tmp_path: Path) -> None:
    claude = FakeClaude()
    voice = SlowVoice()
    assistant = ClaudeAssistant(claude, voice, lambda _l: None, transcript_dir=None)
    assistant.submit("baue etwas")
    wait_until(lambda: voice.said == ["Ich frage Claude."])
    assistant.shutdown()
    assert not assistant.busy
    assert claude.calls == [] or claude.cancelled
    assert voice.said == ["Ich frage Claude."]  # keine Abbruch-Ansage beim Beenden


def test_stop_while_reading_the_answer_does_not_claim_nothing_runs(tmp_path: Path) -> None:
    claude = FakeClaude()
    voice = SlowVoice(0.3)
    assistant = ClaudeAssistant(claude, voice, lambda _l: None, transcript_dir=None)
    assistant.submit("setz x")
    wait_until(lambda: len(voice.said) == 2)  # liest gerade die Antwort vor
    assistant.submit("stopp")
    wait_until(lambda: not assistant.busy)
    assert NOTHING_TO_CANCEL not in voice.said
