import pytest

from reachy_claude.wakeword import Wake, clean_text, parse_wake


@pytest.mark.parametrize(
    ("text", "kind", "command"),
    [
        ("Claude, schreib einen Test für login.", Wake.COMMAND, "schreib einen Test für login."),
        ("claude erkläre mir die Datei main.py", Wake.COMMAND, "erkläre mir die Datei main.py"),
        ("Hey Claude, was macht calc.py?", Wake.COMMAND, "was macht calc.py?"),
        ("Okay Cloud: neues Thema", Wake.COMMAND, "neues Thema"),
        ("Klod, mach weiter", Wake.COMMAND, "mach weiter"),
        ("Claudé – Tests ausführen", Wake.COMMAND, "Tests ausführen"),
        ("Claude.", Wake.WAKE_ONLY, ""),
        ("Hallo Claude!", Wake.WAKE_ONLY, ""),
        ("Ich habe heute Claude getroffen.", Wake.NONE, ""),
        ("Wie wird das Wetter?", Wake.NONE, ""),
        ("Claudia, komm mal her", Wake.NONE, ""),
        ("", Wake.NONE, ""),
        ("Hey", Wake.NONE, ""),
    ],
)
def test_parse_wake(text: str, kind: Wake, command: str) -> None:
    result = parse_wake(text)
    assert result.kind is kind
    assert result.command == command


def test_control_characters_are_removed() -> None:
    assert clean_text("a\x1b[2Jb\n c") == "a [2Jb c"
    assert parse_wake("Claude, \x1b]0;x\x07 lies") == parse_wake("Claude, ]0;x lies")
