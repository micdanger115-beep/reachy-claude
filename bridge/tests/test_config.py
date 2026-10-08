from pathlib import Path

import pytest
from conftest import FAKE_CLAUDE

from claude_bridge.config import ConfigError, PermissionLevel, load_config, load_environment, parse_env_file


def base_env(workdir: Path, **extra: str) -> dict[str, str]:
    env = {
        "CLAUDE_BRIDGE_TOKEN": "a" * 40,
        "CLAUDE_BRIDGE_HOST": "192.168.1.20",
        "CLAUDE_BRIDGE_ALLOWED_CLIENTS": "192.168.1.30",
        "CLAUDE_BRIDGE_WORKDIR": str(workdir),
        "CLAUDE_BRIDGE_CLAUDE_BIN": str(FAKE_CLAUDE),
    }
    env.update({f"CLAUDE_BRIDGE_{k}": v for k, v in extra.items()})
    return env


def test_valid_config_has_safe_defaults(tmp_path: Path) -> None:
    cfg = load_config(base_env(tmp_path))
    assert cfg.port == 8787
    assert cfg.permission_level is PermissionLevel.EDIT
    assert cfg.log_prompts is False
    assert cfg.client_allowed("192.168.1.30")
    assert cfg.client_allowed("::ffff:192.168.1.30")
    assert not cfg.client_allowed("192.168.1.31")
    assert not cfg.client_allowed("kein-ip")


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"TOKEN": "kurz"}, "zu kurz"),
        ({"HOST": "0.0.0.0"}, "allen Netzwerkkarten"),
        ({"ALLOWED_CLIENTS": " , "}, "leer"),
        ({"ALLOWED_CLIENTS": "0.0.0.0/0"}, "/0"),
        ({"ALLOWED_CLIENTS": "nope"}, "Ungueltige Adresse"),
        ({"PERMISSION_LEVEL": "root"}, "PERMISSION_LEVEL"),
        ({"PORT": "80"}, "PORT"),
        ({"TLS_CERT": "cert.pem"}, "gemeinsam"),
        ({"CLAUDE_BIN": "gibt-es-nicht-xyz"}, "nicht gefunden"),
        ({"LOG_PROMPTS": "vielleicht"}, "true oder false"),
    ],
)
def test_unsafe_or_invalid_settings_fail(tmp_path: Path, override: dict[str, str], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(base_env(tmp_path, **override))


def test_wildcard_host_needs_explicit_opt_in(tmp_path: Path) -> None:
    cfg = load_config(base_env(tmp_path, HOST="0.0.0.0", ALLOW_ALL_INTERFACES="true"))
    assert cfg.host == "0.0.0.0"


def test_missing_workdir_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="existiert nicht"):
        load_config(base_env(tmp_path / "fehlt"))


def test_env_file_inside_workdir_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Arbeitsordner"):
        load_config(base_env(tmp_path), env_file=tmp_path / "sub" / ".env")


def test_transcripts_can_be_disabled(tmp_path: Path) -> None:
    assert load_config(base_env(tmp_path, TRANSCRIPT_DIR="off")).transcript_dir is None


def test_parse_env_file_and_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        '# Kommentar\nCLAUDE_BRIDGE_PORT="9000"\nexport CLAUDE_BRIDGE_HOST=10.0.0.2\nkaputt\nCLAUDE_BRIDGE_X=a=b\n',
        encoding="utf-8",
    )
    assert parse_env_file(env_file) == {
        "CLAUDE_BRIDGE_PORT": "9000",
        "CLAUDE_BRIDGE_HOST": "10.0.0.2",
        "CLAUDE_BRIDGE_X": "a=b",
    }
    monkeypatch.setenv("CLAUDE_BRIDGE_PORT", "9100")
    merged = load_environment(env_file)
    assert merged["CLAUDE_BRIDGE_PORT"] == "9100"
    assert merged["CLAUDE_BRIDGE_HOST"] == "10.0.0.2"
