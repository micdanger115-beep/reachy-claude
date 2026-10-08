from __future__ import annotations

import ipaddress
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from claude_bridge.config import BridgeConfig, PermissionLevel

_FAKE_CLAUDE_PY = Path(__file__).with_name("fake_claude.py")


def _fake_claude_executable() -> Path:
    """Unter Windows wie bei einer npm-Installation ueber eine .cmd-Datei starten."""
    if sys.platform != "win32":
        return _FAKE_CLAUDE_PY
    wrapper = Path(tempfile.mkdtemp()) / "claude.cmd"
    wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{_FAKE_CLAUDE_PY}" %*\r\n', encoding="utf-8")
    return wrapper


FAKE_CLAUDE = _fake_claude_executable()
TOKEN = "t" * 40


@pytest.fixture
def make_config(tmp_path: Path) -> Callable[..., BridgeConfig]:
    def factory(**overrides: object) -> BridgeConfig:
        values: dict[str, object] = {
            "token": TOKEN,
            "host": "127.0.0.1",
            "port": 0,
            "allowed_clients": (ipaddress.ip_network("127.0.0.1/32"),),
            "workdir": tmp_path,
            "claude_bin": str(FAKE_CLAUDE),
            "permission_level": PermissionLevel.EDIT,
            "timeout_s": 10.0,
            "max_turns": 5,
            "max_prompt_chars": 200,
            "spoken_max_chars": 300,
            "rate_limit_per_min": 50,
            "transcript_dir": None,
            "log_prompts": False,
            "tls_cert": None,
            "tls_key": None,
        }
        values.update(overrides)
        return BridgeConfig(**values)  # type: ignore[arg-type]

    return factory
