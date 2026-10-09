from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from reachy_claude.settings import ClaudeSettings, Permission

_FAKE_CLAUDE_PY = Path(__file__).with_name("fake_claude.py")


def _fake_claude_executable() -> Path:
    """Fake-CLI unter dem echten Namen (die App startet nur claude/claude.exe/claude.cmd).

    Unter Windows wie bei einer npm-Installation ueber eine .cmd-Datei.
    """
    folder = Path(tempfile.mkdtemp(prefix="fake-claude-"))
    if sys.platform == "win32":
        wrapper = folder / "claude.cmd"
        wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{_FAKE_CLAUDE_PY}" %*\r\n', encoding="utf-8")
    else:
        wrapper = folder / "claude"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{_FAKE_CLAUDE_PY}" "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
    return wrapper


FAKE_CLAUDE = _fake_claude_executable()


@pytest.fixture(autouse=True)
def _fake_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test-Ordner liegen unter Windows in AppData\Local\Temp – fuer die Projektordner-Pruefung
    # gilt deshalb ein eigener, leerer "Benutzerordner".
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setattr("reachy_claude.settings._home", lambda: home)


@pytest.fixture
def make_config(tmp_path: Path) -> Callable[..., ClaudeSettings]:
    def factory(**overrides: object) -> ClaudeSettings:
        values: dict[str, object] = {
            "workdir": tmp_path,
            "claude_bin": str(FAKE_CLAUDE),
            "permission": Permission.EDIT,
            "timeout_s": 10.0,
            "max_turns": 5,
        }
        values.update(overrides)
        return ClaudeSettings(**values)  # type: ignore[arg-type]

    return factory
