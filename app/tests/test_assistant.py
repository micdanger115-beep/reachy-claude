import threading
from pathlib import Path

import pytest

from reachy_claude.assistant import ClaudeAssistant, PrintOnly, show_answer
from reachy_claude.claude import ClaudeError, ClaudeResult


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

    def ask(self, prompt: str, new_conversation: bool = False) -> ClaudeResult:
        self.calls.append((prompt, new_conversation))
        if self.gate is not None:
            self.gate.wait(5)
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
