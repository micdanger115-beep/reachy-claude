from pathlib import Path

import pytest
from conftest import FAKE_CLAUDE

from reachy_claude.settings import (
    Permission,
    ReachySettings,
    SettingsError,
    load_reachy_settings,
    load_settings,
    remember_reachy,
    save_settings,
)


def write(path: Path, body: str) -> Path:
    path.write_text("[claude]\n" + body, encoding="utf-8")
    return path


def test_save_and_load_roundtrip_with_windows_path(tmp_path: Path) -> None:
    project = (
        tmp_path / "Mein Projekt (Kopie) – Übung"
    )  # Leerzeichen, Klammern, Umlaut: unter Windows erlaubt
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
        ('projektordner = "{tmp}"\nclaude_programm = "/gibt/es/nicht/claude"\n', "nicht gefunden"),
        ('projektordner = "{tmp}"\nclaude_programm = "C:/boese/start.cmd"\n', "nicht erlaubt"),
        ('projektordner = "{tmp}"\nclaude_programm = "python"\n', "nicht erlaubt"),
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


@pytest.mark.parametrize("value", ['C:\\Users\\a"b\\c', "D:\\code\\neu\\", 'Pfad mit "Anführung"'])
def test_toml_string_escaping_roundtrip(value: str) -> None:
    import tomllib

    from reachy_claude.settings import _toml_string

    assert tomllib.loads(f"x = {_toml_string(value)}")["x"] == value


def test_reachy_defaults_without_file(tmp_path: Path) -> None:
    assert load_reachy_settings(tmp_path / "fehlt.toml") == ReachySettings()


def test_remember_reachy_keeps_claude_section_and_vice_versa(tmp_path: Path) -> None:
    file = tmp_path / "e.toml"
    save_settings(file, tmp_path, Permission.READ)
    remember_reachy(file, robot="192.168.1.30", voice="de_DE-mls-medium", speaker="7", motion=False)
    save_settings(file, tmp_path, Permission.EDIT)  # darf [reachy] nicht verlieren
    text = file.read_text(encoding="utf-8")
    assert 'projektordner = "' in text and 'roboter = "192.168.1.30"' in text
    assert load_reachy_settings(file) == ReachySettings("192.168.1.30", "de_DE-mls-medium", "7", False)


def test_new_voice_drops_old_speaker(tmp_path: Path) -> None:
    file = tmp_path / "e.toml"
    remember_reachy(file, voice="de_DE-mls-medium", speaker="7")
    assert remember_reachy(file, voice="de_DE-kerstin-low").speaker is None
    assert remember_reachy(file, speaker="2").speaker == "2"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"robot": "http://evil/"}, "Adresse"),
        ({"robot": ""}, "Adresse"),
        ({"robot": "a b"}, "Adresse"),
        ({"voice": "../../etc/passwd"}, "Stimmenname"),
    ],
)
def test_invalid_reachy_values_are_rejected_and_file_unchanged(
    tmp_path: Path, kwargs: dict[str, str], message: str
) -> None:
    file = tmp_path / "e.toml"
    remember_reachy(file, robot="reachy.fritz.box")
    before = file.read_text(encoding="utf-8")
    with pytest.raises(SettingsError, match=message):
        remember_reachy(file, **kwargs)  # type: ignore[arg-type]
    assert file.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("host", ["reachy-mini.local", "192.168.1.30", "fe80::1", "REACHY"])
def test_valid_robot_addresses(tmp_path: Path, host: str) -> None:
    assert remember_reachy(tmp_path / "e.toml", robot=host).robot == host


def test_hand_edited_reachy_values_are_checked(tmp_path: Path) -> None:
    file = tmp_path / "e.toml"
    file.write_text('[reachy]\nbewegung = "ja"\n', encoding="utf-8")
    with pytest.raises(SettingsError, match="true oder false"):
        load_reachy_settings(file)
    file.write_text("[reachy]\nsprecher = 3\nbewegung = false\n", encoding="utf-8")
    assert load_reachy_settings(file).speaker == "3"


def test_project_folder_must_not_expose_startup_or_the_app(tmp_path: Path) -> None:
    from reachy_claude.settings import check_workdir

    home = tmp_path / "Users" / "anna"
    (home / "AppData" / "Roaming").mkdir(parents=True)
    app = tmp_path / "tools" / "reachy-claude"
    (app / "app").mkdir(parents=True)
    project = home / "code" / "projekt"
    project.mkdir(parents=True)

    def check(path: Path) -> Path:
        return check_workdir(path, home=home, app_root=app)

    assert check(project) == project
    for bad, message in [
        (home, "Benutzerordner"),  # Autostart, PowerShell-Profil, .ssh ...
        (tmp_path / "Users", "Benutzerordner"),
        (home / "AppData" / "Roaming", "AppData"),
        (app, "dieser App"),  # Claude koennte die App/ihre Einstellungen umschreiben
        (app / "app", "dieser App"),
        (tmp_path / "tools", "dieser App"),
    ]:
        with pytest.raises(SettingsError, match=message):
            check(bad)


def test_claude_is_never_taken_from_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reachy_claude.settings import find_claude

    planted = tmp_path / "claude"
    planted.write_text("#!/bin/sh\n", encoding="utf-8")
    planted.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("shutil.which", lambda _p: str(planted))  # Windows sucht zuerst im aktuellen Ordner
    assert find_claude("claude") is None


def test_typo_in_voice_is_rejected_before_saving(tmp_path: Path) -> None:
    file = tmp_path / "e.toml"
    with pytest.raises(SettingsError, match="Unbekannte Stimme"):
        remember_reachy(file, voice="de_DE-kerstn-low")  # sonst scheiterte danach jeder Start
    assert not file.exists()


def test_windows_path_in_double_quotes_gets_a_helpful_message(tmp_path: Path) -> None:
    file = tmp_path / "einstellungen.toml"
    file.write_text('[claude]\nprojektordner = "D:\\code\\x"\n', encoding="utf-8")
    with pytest.raises(SettingsError, match="einfache"):
        load_settings(file)


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("1", True),
        ("60", True),
        ("0", False),
        ("0.5", False),
        ("61", False),
        ('"15"', False),
        ("true", False),
    ],
)
def test_timeout_limits(tmp_path: Path, value: str, ok: bool) -> None:
    file = write(
        tmp_path / "e.toml",
        f'projektordner = "{tmp_path.as_posix()}"\ntimeout_minuten = {value}\nclaude_programm = "{FAKE_CLAUDE.as_posix()}"\n',
    )
    if ok:
        assert load_settings(file).timeout_s == float(value) * 60
    else:
        with pytest.raises(SettingsError, match="timeout_minuten"):
            load_settings(file)


def test_default_permission_is_edit(tmp_path: Path) -> None:
    file = write(
        tmp_path / "e.toml",
        f'projektordner = "{tmp_path.as_posix()}"\nclaude_programm = "{FAKE_CLAUDE.as_posix()}"\n',
    )
    assert load_settings(file).permission is Permission.EDIT


def test_unchanged_reachy_settings_do_not_rewrite_the_file(tmp_path: Path) -> None:
    file = tmp_path / "e.toml"
    file.write_text('# meine Notiz\n[reachy]\nroboter = "reachy.fritz.box"\n', encoding="utf-8")
    remember_reachy(file, robot="reachy.fritz.box")  # nichts Neues
    assert "# meine Notiz" in file.read_text(encoding="utf-8")


@pytest.mark.parametrize("value", ["1.5", "[1, 2]", "true"])
def test_speaker_must_be_name_or_number(tmp_path: Path, value: str) -> None:
    file = tmp_path / "e.toml"
    file.write_text(f"[reachy]\nsprecher = {value}\n", encoding="utf-8")
    with pytest.raises(SettingsError, match="sprecher"):
        load_reachy_settings(file)


def test_broken_file_is_not_silently_overwritten(tmp_path: Path) -> None:
    # sonst gingen Projektordner und Rechte unbemerkt verloren; stattdessen klare Anleitung
    file = tmp_path / "e.toml"
    file.write_text("kaputt = = =\n", encoding="utf-8")
    with pytest.raises(SettingsError, match="loeschen"):
        remember_reachy(file, robot="10.1.2.3")
    assert file.read_text(encoding="utf-8") == "kaputt = = =\n"
