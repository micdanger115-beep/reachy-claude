from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClock, FakeMedia

import reachy_claude.__main__ as cli
from reachy_claude.robot import RobotConnectionError


def test_rejects_bad_duration(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["check-audio", "--seconds", "0"]) == 2
    assert "zwischen 1 und 60" in capsys.readouterr().out


def test_connection_error_is_explained(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    @contextmanager
    def failing_connect(host: str, debug: bool = False) -> Any:
        raise RobotConnectionError(f"Reachy unter '{host}' nicht erreichbar")
        yield

    monkeypatch.setattr(cli, "connect", failing_connect)
    assert cli.main(["--robot", "10.0.0.9", "check-audio"]) == 1
    assert "FEHLER: Reachy unter '10.0.0.9' nicht erreichbar" in capsys.readouterr().out


def test_check_audio_end_to_end_with_fake_robot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clock = FakeClock()

    class FakeMini:
        media = FakeMedia(clock)

    @contextmanager
    def fake_connect(host: str, debug: bool = False) -> Any:
        yield FakeMini()

    monkeypatch.setattr(cli, "connect", fake_connect)
    monkeypatch.setattr("reachy_claude.check_audio.time.sleep", clock.sleep)
    monkeypatch.setattr("reachy_claude.check_audio.time.monotonic", clock)
    assert cli.main(["check-audio", "--seconds", "1", "--save", str(tmp_path / "a.wav")]) == 0
    out = capsys.readouterr().out
    assert "Verbunden." in out and "Fertig." in out
    assert (tmp_path / "a.wav").exists()


def test_listen_needs_project_and_saves_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from conftest import FAKE_CLAUDE

    from reachy_claude.settings import load_settings

    monkeypatch.setattr("reachy_claude.doctor.run_checks", lambda **_kw: [])
    # Ohne Projektordner: klare Meldung, kein Modell-Download, kein Verbindungsaufbau.
    assert cli.main(["listen"]) == 1
    assert "-Projekt" in capsys.readouterr().out

    project = tmp_path / "projekt"
    project.mkdir()
    (tmp_path / "einstellungen.toml").write_text(
        f'[claude]\nclaude_programm = "{FAKE_CLAUDE.as_posix()}"\n', encoding="utf-8"
    )
    settings = cli.prepare_claude(cli.build_parser().parse_args(["listen", "--project", str(project)]))
    assert settings is not None and settings.workdir == project.resolve()
    assert load_settings(tmp_path / "einstellungen.toml").workdir == project.resolve()  # gespeichert

    settings = cli.prepare_claude(cli.build_parser().parse_args(["listen", "--permission", "read"]))
    assert settings is not None and settings.permission.value == "read"
    assert "nur lesen" in capsys.readouterr().out


def test_listen_stops_before_loading_anything_when_check_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from reachy_claude.doctor import Check, Level

    failing = [Check("Reachy erreichbar", Level.FEHLER, "antwortet nicht", "einschalten")]
    monkeypatch.setattr("reachy_claude.doctor.run_checks", lambda **_kw: failing)
    monkeypatch.setattr(cli, "prepare_claude", lambda *_a: pytest.fail("darf nicht weiterlaufen"))
    assert cli.main(["listen"]) == 1
    out = capsys.readouterr().out
    assert "[FEHL] Reachy erreichbar: antwortet nicht" in out and "-> einschalten" in out


def test_robot_voice_and_motion_are_remembered(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from reachy_claude.settings import load_reachy_settings

    seen: list[Any] = []
    monkeypatch.setattr(cli, "run_listen", lambda _args, reachy: seen.append(reachy) or 0)
    assert cli.main(["--robot", "192.168.1.30", "listen", "--voice", "de_DE-kerstin-low", "--no-motion"]) == 0
    assert cli.main(["listen"]) == 0  # zweiter Start ohne Parameter: alles wie gespeichert
    assert seen[1].robot == "192.168.1.30"
    assert seen[1].voice == "de_DE-kerstin-low" and seen[1].motion is False
    assert load_reachy_settings(tmp_path / "einstellungen.toml") == seen[1]
    assert cli.main(["listen", "--motion"]) == 0
    assert seen[2].motion is True


def test_say_tries_a_voice_without_saving_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from reachy_claude.settings import load_reachy_settings

    used: list[tuple[str, str | None]] = []

    def fake_load_speaker(voice: str, speaker: str | None = None) -> None:
        used.append((voice, speaker))  # None -> run_say bricht vor dem Verbinden ab

    monkeypatch.setattr(cli, "load_speaker", fake_load_speaker)
    assert cli.main(["say", "Hallo", "--voice", "de_DE-mls-medium", "--speaker", "3"]) == 1
    assert used == [("de_DE-mls-medium", "3")]
    assert load_reachy_settings(tmp_path / "einstellungen.toml").voice == "de_DE-thorsten-medium"


def test_bad_robot_address_is_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--robot", "http://x/../", "check-audio"]) == 2
    assert "keine gueltige Adresse" in capsys.readouterr().out


def test_missing_project_is_asked_for_and_saved(tmp_path: Path) -> None:
    from conftest import FAKE_CLAUDE

    from reachy_claude.settings import load_settings

    project = tmp_path / "projekt"
    project.mkdir()
    (tmp_path / "einstellungen.toml").write_text(
        f'[claude]\nclaude_programm = "{FAKE_CLAUDE.as_posix()}"\n', encoding="utf-8"
    )
    args = cli.build_parser().parse_args(["listen"])
    assert cli.prepare_claude(args, lambda: None) is None  # abgebrochen
    args = cli.build_parser().parse_args(["listen"])
    settings = cli.prepare_claude(args, lambda: project)
    assert settings is not None and settings.workdir == project.resolve()
    assert load_settings(tmp_path / "einstellungen.toml").workdir == project.resolve()


def test_ask_for_project_falls_back_to_typing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_folder_dialog", lambda: None)
    assert cli.ask_for_project(lambda _prompt: ' "D:\\code\\x" ') == Path("D:\\code\\x")
    assert cli.ask_for_project(lambda _prompt: "") is None
    monkeypatch.setattr(cli, "_folder_dialog", lambda: "")  # im Fenster abgebrochen: nicht nachfragen
    assert cli.ask_for_project(lambda _prompt: pytest.fail("nicht tippen lassen")) is None
    monkeypatch.setattr(cli, "_folder_dialog", lambda: "C:/code/y")
    assert cli.ask_for_project() == Path("C:/code/y")


def test_doctor_command_reports_and_fails_on_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from reachy_claude.doctor import Check, Level

    checks = [Check("A", Level.OK, "gut"), Check("B", Level.FEHLER, "kaputt", "reparieren")]
    monkeypatch.setattr("reachy_claude.doctor.run_checks", lambda **_kw: checks)
    assert cli.main(["pruefen"]) == 1
    out = capsys.readouterr().out
    assert "[ OK ] A: gut" in out and "[FEHL] B: kaputt" in out and "-> reparieren" in out
    monkeypatch.setattr("reachy_claude.doctor.run_checks", lambda **_kw: checks[:1])
    assert cli.main(["pruefen"]) == 0
    assert "Alles bereit" in capsys.readouterr().out


# --- Pruefrunde Paket D: Verdrahtung von run_listen (vorher blieben 5 eingebaute Fehler unbemerkt) ---


def test_listen_wiring(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """listen() bekommt: nicht blockierendes submit, Weghoeren beim Sprechen, sofortige Steuerwoerter,
    Verwerfen bei "stopp"; beim Beenden wird ein laufender Auftrag still abgebrochen."""
    import time

    from conftest import FAKE_CLAUDE

    from reachy_claude.assistant import ClaudeAssistant
    from reachy_claude.settings import ClaudeSettings

    clock = FakeClock()

    class FakeMini:
        media = FakeMedia(clock)

    @contextmanager
    def fake_connect(host: str, debug: bool = False) -> Any:
        yield FakeMini()

    class FakeTranscriber:
        description = "Test"

        def __init__(self, _config: object) -> None: ...

    settings = ClaudeSettings(workdir=tmp_path, claude_bin=str(FAKE_CLAUDE), timeout_s=30)
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "sleep")
    monkeypatch.setattr("reachy_claude.doctor.run_checks", lambda **_kw: [])
    monkeypatch.setattr(cli, "prepare_claude", lambda *_a: settings)
    monkeypatch.setattr("reachy_claude.stt.WhisperTranscriber", FakeTranscriber)
    monkeypatch.setattr(cli, "connect", fake_connect)
    monkeypatch.setattr(cli, "wait_for_audio", lambda _media: None)
    seen: dict[str, Any] = {}

    def fake_listen(
        media: Any, transcriber: Any, output: Any, *, on_command: Any, stop: Any, **kw: Any
    ) -> None:
        seen.update(kw, on_command=on_command)
        started = time.monotonic()
        on_command("lange Aufgabe")  # muss sofort zurueckkehren (Claude arbeitet im Hintergrund)
        seen["submit_s"] = time.monotonic() - started
        assistant = on_command.__self__
        seen["assistant"] = assistant
        deadline = time.monotonic() + 5
        while not assistant.busy and time.monotonic() < deadline:
            time.sleep(0.01)
        seen["busy"] = assistant.busy
        raise KeyboardInterrupt  # Strg+C waehrend Claude laeuft

    monkeypatch.setattr("reachy_claude.listener.listen", fake_listen)
    assert cli.main(["listen", "--silent", "--no-motion"]) == 0

    assert isinstance(seen["assistant"], ClaudeAssistant) and seen["on_command"].__name__ == "submit"
    assert seen["submit_s"] < 0.5 and seen["busy"]
    assert not seen["assistant"].busy  # Beenden hat den laufenden Auftrag abgebrochen
    # weghoeren ueber dieselbe Sprech-Sperre, ueber die auch der Assistent spricht
    gate = seen["muted"].__self__
    assert type(gate).__name__ == "SpeechGate" and seen["assistant"]._voice is gate
    assert seen["immediate"]("stopp") and seen["immediate"]("wiederhole") and not seen["immediate"]("baue x")
    assert seen["cancels"]("stopp") and not seen["cancels"]("wiederhole")
    assert callable(seen["on_discard"])
