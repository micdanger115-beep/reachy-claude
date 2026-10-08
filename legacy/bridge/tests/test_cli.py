from pathlib import Path

import pytest
from conftest import FAKE_CLAUDE

from claude_bridge.__main__ import main


def test_gen_token_is_long_and_random(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["gen-token"]) == 0
    first = capsys.readouterr().out.strip()
    main(["gen-token"])
    assert len(first) >= 48
    assert first != capsys.readouterr().out.strip()


def test_check_reports_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    workdir = tmp_path / "projekt"
    workdir.mkdir()
    env_file = tmp_path / "bridge" / ".env"
    env_file.parent.mkdir()
    env_file.write_text(
        "\n".join(
            [
                f"CLAUDE_BRIDGE_TOKEN={'z' * 40}",
                "CLAUDE_BRIDGE_HOST=127.0.0.1",
                "CLAUDE_BRIDGE_ALLOWED_CLIENTS=127.0.0.1",
                f"CLAUDE_BRIDGE_WORKDIR={workdir}",
                f"CLAUDE_BRIDGE_CLAUDE_BIN={FAKE_CLAUDE}",
            ]
        ),
        encoding="utf-8",
    )
    assert main(["--env-file", str(env_file), "check"]) == 0
    out = capsys.readouterr().out
    assert "Konfiguration OK" in out
    assert "z" * 40 not in out  # Token wird nie ausgegeben


def test_invalid_config_exits_with_code_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    for key in ("TOKEN", "HOST", "ALLOWED_CLIENTS", "WORKDIR"):
        monkeypatch.delenv(f"CLAUDE_BRIDGE_{key}", raising=False)
    assert main(["check"]) == 2
