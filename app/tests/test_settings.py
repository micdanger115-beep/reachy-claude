from pathlib import Path

import pytest
from conftest import FAKE_CLAUDE

from reachy_claude.settings import Permission, SettingsError, load_settings, save_settings


def write(path: Path, body: str) -> Path:
    path.write_text("[claude]\n" + body, encoding="utf-8")
    return path


def test_save_and_load_roundtrip_with_windows_path(tmp_path: Path) -> None:
    project = tmp_path / 'Projekt mit "Anfuehrung" und \\Backslash'
    project.mkdir()
    file = tmp_path / "einstellungen.toml"
    save_settings(file, project, Permission.READ)
    text = file.read_text(encoding="utf-8")
    text = text.replace(
        'rechte = "read"',
        'rechte = "read"\nclaude_programm = "' + str(FAKE_CLAUDE).replace("\\", "\\\\") + '"',
    )
    file.write_text(text, encoding="utf-8")
    settings = load_settings(file)
    assert settings.workdir == project.resolve()
    assert settings.permission is Permission.READ
    assert settings.timeout_s == 15 * 60


def test_override_wins(tmp_path: Path) -> None:
    other = tmp_path / "anders"
    other.mkdir()
    file = write(
        tmp_path / "e.toml",
        f'projektordner = "{tmp_path.as_posix()}"\nclaude_programm = "{FAKE_CLAUDE.as_posix()}"\n',
    )
    assert load_settings(file, workdir_override=other).workdir == other.resolve()


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("", "Kein Projektordner"),
        ('projektordner = "/gibt/es/nicht"\n', "existiert nicht"),
        ('projektordner = "/"\n', "Laufwerk"),
        ('projektordner = "{tmp}"\nrechte = "alles"\n', "read oder edit"),
        ('projektordner = "{tmp}"\ntimeout_minuten = 999\n', "zwischen 1 und 60"),
        ('projektordner = "{tmp}"\nclaude_programm = "gibt-es-nicht-xyz"\n', "nicht gefunden"),
        ("kaputt = = =\n", "fehlerhaft"),
    ],
)
def test_invalid_settings_are_explained(tmp_path: Path, body: str, message: str) -> None:
    file = write(tmp_path / "e.toml", body.replace("{tmp}", tmp_path.as_posix()))
    with pytest.raises(SettingsError, match=message):
        load_settings(file)


def test_missing_file_without_override_explains_how_to_start(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="-Projekt"):
        load_settings(tmp_path / "fehlt.toml")


def test_save_keeps_hand_edited_values(tmp_path: Path) -> None:
    file = write(
        tmp_path / "e.toml",
        f'projektordner = "{tmp_path.as_posix()}"\ntimeout_minuten = 30\nclaude_programm = "{FAKE_CLAUDE.as_posix()}"\n',
    )
    save_settings(file, tmp_path, Permission.READ)
    settings = load_settings(file)
    assert settings.timeout_s == 30 * 60
    assert settings.permission is Permission.READ
    assert settings.claude_bin.endswith(FAKE_CLAUDE.name)
