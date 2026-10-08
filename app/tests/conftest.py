from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from reachy_claude.settings import ClaudeSettings, Permission

_FAKE_CLAUDE_PY = Path(__file__).with_name("fake_claude.py")


def _fake_claude_executable() -> Path:
    """Unter Windows wie bei einer npm-Installation ueber eine .cmd-Datei starten."""
    if sys.platform != "win32":
        return _FAKE_CLAUDE_PY
    wrapper = Path(tempfile.mkdtemp()) / "claude.cmd"
    wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{_FAKE_CLAUDE_PY}" %*\r\n', encoding="utf-8")
    return wrapper


FAKE_CLAUDE = _fake_claude_executable()


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
