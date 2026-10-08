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
